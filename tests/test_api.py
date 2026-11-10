import collections.abc
import json
import pathlib
from typing import cast

import pytest
from pydantic import ValidationError

from siso_ref010 import EntityType, EntityTypePrefix, KindCode, SisoRef010API, SisoRef010ValueError
from siso_ref010.api import Collection, decode_key, encode_entity
from siso_ref010.catalog import ReferenceCatalog
from siso_ref010.cli import main
from siso_ref010.parsing.xml import EntityTypeXmlParser


@pytest.fixture(scope="module")
def api() -> SisoRef010API:
    # These API behavior assertions use the v37 golden source edition.
    return SisoRef010API.bundled(37)


def test_typed_describe(api: SisoRef010API, capsys: pytest.CaptureFixture[str]) -> None:
    item = api.describe("1.3.153.6.4.2.0")
    assert isinstance(item.entity, EntityType)
    assert item.description == "F803 Tromp"
    assert item.country_name == "Netherlands (NLD)"
    assert api.describe(item.entity) == item
    result = item.model_dump(mode="json", by_alias=True)
    assert result["entity"]["country"] == 153
    assert json.loads(json.dumps(result))["key"] == "72902676198982144"
    with pytest.raises(ValidationError):
        item.description = "mutated"
    assert capsys.readouterr() == ("", "")


def test_search_contract(api: SisoRef010API) -> None:
    results = api.search("F803")
    assert results.total == 1
    assert results.hits[0].entity == EntityType.from_string("1.3.153.6.4.2.0")
    assert not results.truncated
    assert api.search("", limit=0).hits == ()
    assert api.search("", limit=0).total == 27323
    assert api.search("", limit=1).truncated
    assert api.search("no-such-item-xyz").total == 0
    assert api.search("no-such-item-xyz").model_dump(mode="json", by_alias=True)["returned"] == 0
    default_page = api.search("")
    assert default_page.limit == 100
    assert len(default_page.hits) == 100
    assert default_page.truncated


def test_search_returns_all_descriptions_for_an_ambiguous_code() -> None:
    standard = EntityTypeXmlParser.from_string(
        '<ebv><enum uid="29" name="Country"><enumrow value="1" description="A"/></enum>'
        '<enum uid="30" name="Entity Kind"><enumrow value="1" description="Platform"/></enum>'
        '<cet><entity kind="1" domain="1" country="1">'
        '<category value="2" description="First source row"/>'
        '<category value="2" description="Second source row"/>'
        "</entity></cet></ebv>"
    )
    catalog = ReferenceCatalog(standard)
    api = SisoRef010API(catalog)

    results = api.search("Second source row")

    assert results.total == 1
    hit = results.hits[0]
    assert hit.entity == EntityType.from_string("1.1.1.2.0.0.0")
    assert hit.description is None
    assert hit.candidate_descriptions == ("First source row", "Second source row")
    assert hit.ambiguous
    serialized = results.model_dump(mode="json", by_alias=True)["hits"][0]
    assert serialized["description"] is None
    assert serialized["candidate_descriptions"] == ["First source row", "Second source row"]
    assert serialized["ambiguous"] is True
    with pytest.raises(SisoRef010ValueError) as error:
        catalog.search_description("Second source row")
    assert getattr(error.value, "code", None) == "ambiguous_entity_description"
    assert error.value.context["candidate_descriptions"] == (
        "First source row",
        "Second source row",
    )


@pytest.mark.parametrize("limit", [-1, True, 1.5, "1"])
def test_search_limit_validation(api: SisoRef010API, limit: object) -> None:
    with pytest.raises(ValueError):
        api.search("x", limit=cast(int, limit))


@pytest.mark.parametrize(
    "collection,parents,expected",
    [
        (Collection.COUNTRIES, (), 279),
        (Collection.KINDS, (), 11),
        (Collection.DOMAINS, (1,), 6),
        (Collection.CATEGORIES, (1, 4, 153), 2),
        (Collection.SUBCATEGORIES, (1, 4, 153, 5), 2),
        (Collection.SPECIFICS, (1, 2, 106, 20, 2), 3),
        (Collection.EXTRAS, (1, 2, 225, 7, 8, 7), 4),
    ],
)
def test_choices(
    api: SisoRef010API, collection: Collection | str, parents: tuple[int, ...], expected: int
) -> None:
    choices = api.choices(collection, EntityTypePrefix.from_values(parents))
    assert len(choices.items) == expected
    assert choices.parents == parents
    assert choices.collection is collection
    assert len(choices.model_dump(mode="json", by_alias=True)["choices"]) == expected


def test_choices_preserve_and_mark_duplicate_source_codes() -> None:
    standard = EntityTypeXmlParser.from_string(
        '<ebv><enum uid="29" name="Country"><enumrow value="1" description="A"/></enum>'
        '<enum uid="30" name="Entity Kind"><enumrow value="1" description="Platform"/></enum>'
        '<cet><entity kind="1" domain="1" country="1">'
        '<category value="2" description="First source row"/>'
        '<category value="2" description="Second source row"/>'
        "</entity></cet></ebv>"
    )
    catalog = ReferenceCatalog(standard)
    api = SisoRef010API(catalog)

    choices = api.choices("categories", EntityTypePrefix(kind=1, domain=1, country=1))

    assert [(choice.value, choice.description, choice.ambiguous) for choice in choices.items] == [
        (2, "First source row", True),
        (2, "Second source row", True),
    ]
    assert len(choices.model_dump(mode="json", by_alias=True)["choices"]) == 2


@pytest.mark.parametrize(
    "categories, expected",
    [
        (
            '<entity kind="1" domain="1" country="153">'
            '<category value="2" description="Specific earlier"/></entity>'
            '<entity kind="1" domain="1" country="0">'
            '<category value="2" description="Generic winner"/>'
            '<category value="2" description="Generic duplicate"/></entity>',
            {"Generic winner", "Generic duplicate"},
        ),
        (
            '<entity kind="1" domain="1" country="0">'
            '<category value="2" description="Generic earlier"/></entity>'
            '<entity kind="1" domain="1" country="153">'
            '<category value="2" description="Specific winner"/>'
            '<category value="2" description="Specific duplicate"/></entity>',
            {"Specific winner", "Specific duplicate"},
        ),
    ],
)
def test_country_overlay_keeps_duplicates_in_the_winning_scope(categories: str, expected: set[str]) -> None:
    standard = EntityTypeXmlParser.from_string(
        '<ebv><enum uid="29" name="Country"><enumrow value="1" description="A"/></enum>'
        '<enum uid="30" name="Entity Kind"><enumrow value="1" description="Platform"/></enum>'
        f"<cet>{categories}</cet></ebv>"
    )
    catalog = ReferenceCatalog(standard)
    api = SisoRef010API(catalog)

    choices = api.choices("categories", EntityTypePrefix(kind=1, domain=1, country=153))
    resolution = api.resolve_entity("1.1.153.2.0.0.0")

    assert {choice.description for choice in choices.items} == expected
    assert len(choices.items) == 2
    assert all(choice.ambiguous for choice in choices.items)
    assert resolution.status.value == "ambiguous"
    assert {row.description for row in resolution.ambiguous_candidates} == expected
    with pytest.raises(SisoRef010ValueError) as error:
        catalog.get_description_of(EntityType.from_string("1.1.153.2.0.0.0"))
    assert getattr(error.value, "code", None) == "ambiguous_entity_description"
    assert set(cast(tuple[str, ...], error.value.context["candidate_descriptions"])) == expected


def test_kind_and_domain_choices_preserve_duplicate_codes() -> None:
    standard = EntityTypeXmlParser.from_string(
        '<ebv><enum uid="29" name="Country"><enumrow value="1" description="A"/></enum>'
        '<enum uid="30" name="Entity Kind">'
        '<enumrow value="1" description="First kind"/>'
        '<enumrow value="1" description="Second kind"/></enum>'
        '<enum uid="31" name="Land Domain" applicability="1">'
        '<enumrow value="2" description="First domain"/>'
        '<enumrow value="2" description="Second domain"/></enum></ebv>'
    )
    catalog = ReferenceCatalog(standard)
    api = SisoRef010API(catalog)

    kinds = api.choices("kinds")
    domains = api.choices("domains", EntityTypePrefix(kind=1))

    assert [(item.value, item.description, item.ambiguous) for item in kinds.items] == [
        (1, "First kind", True),
        (1, "Second kind", True),
    ]
    assert [(item.value, item.description, item.ambiguous) for item in domains.items] == [
        (2, "First domain", True),
        (2, "Second domain", True),
    ]
    with pytest.raises(ValueError, match="multiple source descriptions"):
        catalog.get_all_kinds()
    with pytest.raises(ValueError, match="multiple source descriptions"):
        catalog.get_kind_name(KindCode(1))
    with pytest.raises(ValueError, match="multiple source descriptions"):
        catalog.get_all_domains_of(KindCode(1))
    with pytest.raises(ValueError, match="multiple source descriptions"):
        catalog.get_domain_name(EntityType(1, 2, 0, 0, 0, 0, 0))


@pytest.mark.parametrize(
    "collection,parents,error",
    [
        ("domains", (), ValueError),
        ("domains", (True,), ValueError),
        ("domains", (256,), ValueError),
        ("domains", (-1,), ValueError),
        ("categories", (1, 1, 65536), ValueError),
        ("unknown", (), ValueError),
    ],
)
def test_parent_validation(
    api: SisoRef010API, collection: str, parents: tuple[object, ...], error: type[Exception]
) -> None:
    with pytest.raises(error):
        api.choices(collection, EntityTypePrefix.from_values(cast(tuple[int, ...], parents)))


def test_encoding_contract() -> None:
    encoded = encode_entity("255.255.65535.255.255.255.255")
    assert encoded.key == -1
    assert encoded.unsigned_key == (1 << 64) - 1
    assert encoded.wire_bytes == b"\xff" * 8
    assert decode_key(encoded.key) == encoded
    assert decode_key("0xffffffffffffffff") == encoded
    assert decode_key("18446744073709551615") == encoded
    assert encoded.model_dump(mode="json", by_alias=True)["unsigned_key"] == "18446744073709551615"


def test_enumerations_resolve_by_exact_human_name(api: SisoRef010API) -> None:
    tables = api.find_enumeration_tables("  dis-pdu type ")
    assert [(table.uid, table.name) for table in tables] == [(4, "DIS-PDU Type")]
    result = api.resolve_enumeration("DIS-PDU Type", 1)
    assert result.status.value == "exact"
    assert result.match is not None
    assert result.match.description == "Entity State"
    assert "match" not in result.model_dump()
    assert api.resolve_enumeration_value(4, 1) == result.matches[0]
    unknown = api.resolve_enumeration("DIS-PDU Type", 1_000_000)
    assert unknown.status.value == "unknown"
    assert unknown.match is None

    ranged = api.resolve_enumeration("DIS-Protocol Version", 64)
    assert ranged.status.value == "range"
    assert ranged.match is not None
    assert ranged.match.value_min == 64
    assert api.resolve_enumeration_value(3, 64).status.value == "range"
    missing = api.resolve_enumeration("No Such Table", 1)
    assert missing.status.value == "table_not_found"
    assert missing.match is None
    ambiguous = api.resolve_enumeration("TCAS/ACAS Type", 0)
    assert ambiguous.status.value == "ambiguous_table"
    assert ambiguous.match is None

    with pytest.raises(TypeError):
        api.resolve_enumeration("DIS-PDU Type", True)
    with pytest.raises(ValueError):
        api.resolve_enumeration("DIS-PDU Type", -1)

    with pytest.raises(TypeError):
        api.find_enumeration_tables(cast(str, 7))
    with pytest.raises(ValueError):
        api.find_enumeration_tables("  ")


def test_bad_types(api: SisoRef010API) -> None:
    with pytest.raises(TypeError):
        encode_entity(cast(str, 123))
    with pytest.raises(TypeError):
        decode_key(cast(int, 1.5))
    with pytest.raises(TypeError):
        api.search(cast(str, 123))


def test_resolve_entity_and_entity_queries_reject_invalid_api_inputs(api: SisoRef010API) -> None:
    exact = EntityType.from_string("1.3.153.6.4.2.0")
    assert api.resolve_entity(exact).matched_depth >= 3
    with pytest.raises(TypeError, match="entity must be"):
        api.resolve_entity(cast(str, 123))

    with pytest.raises(ValueError, match="entity_kind must be"):
        api.query_entities(entity_kind=256)
    with pytest.raises(ValueError, match="country must be an integer"):
        api.query_entities(country=True)
    with pytest.raises(TypeError, match="text must be a string"):
        api.query_entities(text=cast(str, 1))
    with pytest.raises(ValueError, match="limit must be a nonnegative integer"):
        api.query_entities(limit=True)
    with pytest.raises(ValueError, match="offset must be a nonnegative integer"):
        api.query_entities(offset=False)

    empty = api.query_entities(entity_kind=255, limit=1)
    assert empty.total == 0
    assert empty.values == ()


def test_metadata_and_custom_xml(api: SisoRef010API, tmp_path: pathlib.Path) -> None:
    assert api.info().data_version == "SISO-REF-010-v37"
    assert api.info().counts.subcategories == 25473
    path = tmp_path / "custom.xml"
    path.write_text(
        '<ebv title="CUSTOM" date="2026-01-01"><enum uid="29" name="Country">'
        '<enumrow value="1" description="Afghanistan"/></enum></ebv>',
        encoding="utf-8",
    )
    custom_api = SisoRef010API.from_xml(path)
    assert custom_api.info().data_version == "CUSTOM"
    assert custom_api.info().data_date == "2026-01-01"
    assert custom_api.info().counts.countries == 1
    assert SisoRef010API(ReferenceCatalog()).info().data_version is None
    assert custom_api.describe("1.2.3.4.5.6.7").description == "-"


def test_bundled_version_discovery() -> None:
    available = SisoRef010API.bundled_versions()
    editions = SisoRef010API.bundled_editions()
    assert available.versions == tuple(edition.version for edition in editions)
    assert available.default_version == max(available.versions)
    default_edition = next(edition for edition in editions if edition.version == available.default_version)
    assert SisoRef010API().info().data_version == default_edition.title


@pytest.mark.parametrize(
    "args,method",
    [
        (
            ["describe", "1.3.153.6.4.2.0"],
            lambda api: api.describe("1.3.153.6.4.2.0").model_dump(mode="json", by_alias=True),
        ),
        (
            ["search", "F803"],
            lambda api: api.search("F803", limit=20).model_dump(mode="json", by_alias=True),
        ),
        (
            ["list", "categories", "1", "4", "153"],
            lambda api: api.choices("categories", EntityTypePrefix(kind=1, domain=4, country=153)).model_dump(
                mode="json", by_alias=True
            ),
        ),
        (
            ["key", "1.2.225.7.8.7.1"],
            lambda api: encode_entity("1.2.225.7.8.7.1").model_dump(mode="json", by_alias=True),
        ),
        (
            ["key", "--decode", "72621510476957441"],
            lambda api: decode_key("72621510476957441").model_dump(mode="json", by_alias=True),
        ),
        (["info"], lambda api: api.info().model_dump(mode="json", by_alias=True)),
    ],
)
def test_cli_api_json_parity(
    api: SisoRef010API,
    capsys: pytest.CaptureFixture[str],
    args: list[str],
    method: collections.abc.Callable[[SisoRef010API], object],
) -> None:
    for command in [["--json", *args], [*args, "--json"]]:
        assert main(["--standard-version", "37", *command]) == 0
        captured = capsys.readouterr()
        assert captured.err == ""
        output = json.loads(captured.out)
        assert output == {"schema_version": 1, "command": args[0], "result": method(api)}


def test_cli_resolves_enumeration_by_name(api: SisoRef010API, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["inspect", "resolve", "DIS-PDU Type", "1", "--json"]) == 0
    captured = capsys.readouterr()
    output = json.loads(captured.out)
    assert output["result"] == api.resolve_enumeration("DIS-PDU Type", 1).model_dump(
        mode="json", by_alias=True
    )
    assert captured.err == ""

    assert main(["inspect", "resolve", "DIS-PDU Type", "1"]) == 0
    captured = capsys.readouterr()
    assert "DIS-PDU Type, value 1: exact" in captured.out
    assert "Entity State" in captured.out
    assert captured.err == ""


@pytest.mark.parametrize(
    "args",
    [
        ["describe", "bad"],
        ["list", "domains"],
        ["list", "domains", "256"],
        ["list", "domains", "bad"],
        ["unknown"],
        ["search", "x", "--limit", "-1"],
    ],
)
def test_json_errors(capsys: pytest.CaptureFixture[str], args: list[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--json", *args])
    assert exc.value.code == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    error = json.loads(captured.err)
    assert error["schema_version"] == 1
    assert error["error"]["message"]


@pytest.mark.parametrize(
    "args,expected",
    [
        (["list", "domains", "1"], "1: Land"),
        (["search", "F803"], "1 of 1 matches"),
        (["key", "1.2.225.7.8.7.1"], "Wire bytes: 010200e107080701"),
        (["info"], "Data: bundled"),
    ],
)
def test_text_output(capsys: pytest.CaptureFixture[str], args: list[str], expected: str) -> None:
    assert main([*args, "--text"]) == 0
    assert expected in capsys.readouterr().out


def test_json_custom_xml_info(tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "input.xml"
    path.write_text(
        '<ebv title="CUSTOM"><enum uid="29" name="Country"><enumrow value="1" description="A"/></enum></ebv>',
        encoding="utf-8",
    )
    assert main(["--xml", str(path), "info", "--json"]) == 0
    info = json.loads(capsys.readouterr().out)["result"]
    assert info["data_version"] == "CUSTOM"
    assert info["counts"]["countries"] == 1


@pytest.mark.parametrize(
    "arguments",
    [
        ["--json", "search", "--text"],
        ["search", "--limit", "x", "--", "--json"],
    ],
)
def test_argument_error_output_override_and_terminator(
    arguments: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit):
        main(arguments)
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "error:" in captured.err
    assert '"schema_version"' not in captured.err


def test_unknown_leaf_and_country_fallbacks(api: SisoRef010API) -> None:
    assert api.describe("1.3.153.6.4.2.255").description == "F803 Tromp"
    prefix = EntityTypePrefix(kind=1, domain=4, country=65535)
    assert len(api.choices("categories", prefix).items) == 1

import json
from dataclasses import FrozenInstanceError

import pytest

from siso_entity_type import EntityTypeAPI, SisoEnum, SisoEnums
from siso_entity_type.api import Collection, decode_key, encode_entity
from siso_entity_type.cli import main


@pytest.fixture(scope="module")
def api():
    return EntityTypeAPI()


def test_typed_describe(api, capsys):
    item = api.describe("1.3.153.6.4.2.0")
    assert isinstance(item.entity, SisoEnum)
    assert item.description == "F803 Tromp"
    assert item.country_name == "Netherlands (NLD)"
    assert api.describe(item.entity) == item
    assert item.to_dict()["fields"]["country"] == 153
    assert json.loads(json.dumps(item.to_dict()))["key"] == "72902676198982144"
    with pytest.raises(FrozenInstanceError):
        item.description = "mutated"
    assert capsys.readouterr() == ("", "")


def test_search_contract(api):
    results = api.search("F803")
    assert results.total == 1
    assert results.hits[0].entity == SisoEnum.from_string("1.3.153.6.4.2.0")
    assert not results.truncated
    assert api.search("", limit=0).hits == ()
    assert api.search("", limit=0).total == 24637
    assert api.search("", limit=1).truncated
    assert api.search("no-such-item-xyz").total == 0
    assert api.search("no-such-item-xyz").to_dict()["returned"] == 0


@pytest.mark.parametrize("limit", [-1, True, 1.5, "1"])
def test_search_limit_validation(api, limit):
    with pytest.raises(ValueError):
        api.search("x", limit=limit)


@pytest.mark.parametrize(
    "collection,parents,expected",
    [
        (Collection.COUNTRIES, (), 279),
        (Collection.KINDS, (), 10),
        (Collection.DOMAINS, (1,), 6),
        (Collection.CATEGORIES, (1, 4, 153), 2),
        (Collection.SUBCATEGORIES, (1, 4, 153, 5), 2),
        (Collection.SPECIFICS, (1, 2, 106, 20, 2), 4),
        (Collection.EXTRAS, (1, 2, 225, 7, 8, 7), 5),
    ],
)
def test_choices(api, collection, parents, expected):
    choices = api.choices(collection, *parents)
    assert len(choices.items) == expected
    assert choices.parents == parents
    assert choices.collection is collection
    assert len(choices.to_dict()["choices"]) == expected


@pytest.mark.parametrize(
    "collection,parents,error",
    [
        ("domains", (), ValueError),
        ("domains", (True,), TypeError),
        ("domains", (256,), ValueError),
        ("domains", (-1,), ValueError),
        ("categories", (1, 1, 65536), ValueError),
        ("unknown", (), ValueError),
    ],
)
def test_parent_validation(api, collection, parents, error):
    with pytest.raises(error):
        api.choices(collection, *parents)


def test_encoding_contract():
    encoded = encode_entity("255.255.65535.255.255.255.255")
    assert encoded.key == -1
    assert encoded.unsigned_key == (1 << 64) - 1
    assert encoded.wire_bytes == b"\xff" * 8
    assert decode_key(encoded.key) == encoded
    assert decode_key("0xffffffffffffffff") == encoded
    assert decode_key("18446744073709551615") == encoded
    assert encoded.to_dict()["unsigned_key"] == "18446744073709551615"


def test_bad_types(api):
    with pytest.raises(TypeError):
        encode_entity(123)
    with pytest.raises(TypeError):
        decode_key(1.5)
    with pytest.raises(TypeError):
        api.search(123)


def test_metadata_and_custom_data(api, tmp_path):
    assert api.info()["data_version"] == "SISO-REF-010-v35"
    assert api.info()["counts"]["subcategories"] == 24637
    custom = {"countries": {}, "domains": {}, "categories": {}, "subcategories": {}}
    path = tmp_path / "bundled"
    path.write_text(json.dumps(custom))
    custom_api = EntityTypeAPI.from_json(path)
    assert custom_api.info()["data_version"] is None
    assert custom_api.info()["counts"]["countries"] == 0
    assert EntityTypeAPI(SisoEnums(custom)).info()["data_version"] is None
    assert custom_api.describe("1.2.3.4.5.6.7").description == "-"


@pytest.mark.parametrize(
    "args,method",
    [
        (["describe", "1.3.153.6.4.2.0"], lambda api: api.describe("1.3.153.6.4.2.0").to_dict()),
        (["search", "F803"], lambda api: api.search("F803", limit=20).to_dict()),
        (["list", "categories", "1", "4", "153"], lambda api: api.choices("categories", 1, 4, 153).to_dict()),
        (["key", "1.2.225.7.8.7.1"], lambda api: encode_entity("1.2.225.7.8.7.1").to_dict()),
        (["key", "--decode", "72621510476957441"], lambda api: decode_key("72621510476957441").to_dict()),
        (["info"], lambda api: api.info()),
    ],
)
def test_cli_api_json_parity(api, capsys, args, method):
    for command in [["--json", *args], [*args, "--json"]]:
        assert main(command) == 0
        captured = capsys.readouterr()
        assert captured.err == ""
        output = json.loads(captured.out)
        assert output == {"schema_version": 1, "command": args[0], "result": method(api)}


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
def test_json_errors(capsys, args):
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
def test_text_output(capsys, args, expected):
    assert main([*args, "--text"]) == 0
    assert expected in capsys.readouterr().out


def test_json_picker(monkeypatch, capsys):
    values = iter(["153", "1", "3", "6", "4", "2", "0"])
    monkeypatch.setattr("builtins.input", lambda _: next(values))
    assert main(["pick", "--json"]) == 0
    captured = capsys.readouterr()
    assert json.loads(captured.out)["result"]["entity"] == "1.3.153.6.4.2.0"
    assert "Country [0]:" in captured.err


def test_json_parse_and_custom_info(tmp_path, capsys):
    path = tmp_path / "input.xml"
    path.write_text('<ebv title="CUSTOM"><enum uid="29"><enumrow value="1" description="A"/></enum></ebv>')
    assert main(["parse", str(path), "--output", str(tmp_path), "--json"]) == 0
    parsed = json.loads(capsys.readouterr().out)["result"]
    assert parsed["title"] == "CUSTOM"
    assert parsed["counts"]["countries"] == 1
    assert main(["--data", parsed["output"], "info", "--json"]) == 0
    info = json.loads(capsys.readouterr().out)["result"]
    assert info["data_version"] is None
    assert info["counts"]["countries"] == 1


@pytest.mark.parametrize(
    "arguments",
    [
        ["--json", "search", "--text"],
        ["search", "--limit", "x", "--", "--json"],
    ],
)
def test_argument_error_output_override_and_terminator(arguments, capsys):
    with pytest.raises(SystemExit):
        main(arguments)
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "error:" in captured.err
    assert '"schema_version"' not in captured.err


def test_unknown_leaf_and_country_use_upstream_fallbacks(api):
    assert api.describe("1.3.153.6.4.2.255").description == "F803 Tromp"
    assert len(api.choices("categories", 1, 4, 65535).items) == 1


def test_json_cancel(monkeypatch, capsys):
    def cancel(_):
        raise KeyboardInterrupt

    monkeypatch.setattr("builtins.input", cancel)
    assert main(["pick", "--json"]) == 130
    captured = capsys.readouterr()
    assert captured.out == ""
    assert '"type": "Cancelled"' in captured.err


def test_text_parse(tmp_path, capsys):
    source = tmp_path / "source.xml"
    source.write_text("<ebv/>")
    assert main(["parse", str(source), "--output", str(tmp_path), "--text"]) == 0
    assert capsys.readouterr().out.startswith("Wrote ")

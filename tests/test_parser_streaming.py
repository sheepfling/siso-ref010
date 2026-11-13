"""Streaming must preserve the original source projection and error/selection contracts."""

import hashlib
import json
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from siso_ref010.parsing import EntityTypeXmlParser, ParseError
from siso_ref010.parsing.xml import _XmlTextStream
from siso_ref010.snapshots import available_snapshot_versions, read_snapshot_bytes
from tools.siso_ref010.benchmark_cold_start import measure_child

DIGESTS = Path(__file__).parent / "fixtures/standard-model-digests.json"


@pytest.mark.all_editions
@pytest.mark.parametrize("version", available_snapshot_versions())
def test_streamed_model_matches_original_tree_parser(version: int) -> None:
    # These are parsed-model output hashes, not the XML hashes in the source index.
    # Recorded before changing the parser, they include duplicate rows, annotations,
    # ranges, xrefs, and attribute ordering, not just lookup counts.
    registry = json.loads(DIGESTS.read_text())
    assert registry["schema_version"] == 2
    expected = registry["editions"][f"v{version}"]
    payload = read_snapshot_bytes(version)
    standard = EntityTypeXmlParser.from_bytes(payload)
    # read_snapshot_bytes already verifies the XML against the canonical source index.
    assert hashlib.sha256(payload).hexdigest() == standard.source_sha256
    assert hashlib.sha256(standard.model_dump_json().encode()).hexdigest() == expected
    assert standard.xml_parse_succeeded is True
    assert standard.date is not None


def _table(name: str, value: str = "1") -> str:
    return (
        f'<cet name="{name}"><entity kind="{value}" domain="1" country="0">'
        '<category value="2" description="A"><cr value="7"/></category>'
        '</entity><meta key="after" value="branch"/></cet>'
    )


@pytest.mark.parametrize(
    "tables, selected",
    [
        (_table("Other", "invalid") + _table("Comprehensive Entity Types"), "Comprehensive Entity Types"),
        (_table("Comprehensive Entity Types", "invalid") + _table("Entity Types"), "Entity Types"),
        (_table("First") + _table("Second", "invalid"), "First"),
        ('<cet name="Empty"/>' + _table("Other"), "Other"),
        ('<cet name="Entity Types"/>' + _table("Other", "invalid"), "Entity Types"),
        (_table("Entity Types") + _table("Entity Types", "invalid"), "Entity Types"),
    ],
)
def test_selection_ignores_invalid_unselected_branches(tables: str, selected: str) -> None:
    standard = EntityTypeXmlParser.from_string(f"<ebv>{tables}</ebv>")
    assert standard.entity_table is not None
    assert standard.entity_table.get("name") == selected
    if standard.entity_types:
        assert standard.entity_table.metadata == (("after", "branch"),)


@pytest.mark.parametrize(
    "xml, code",
    [
        ('<ebv><enum uid="bad"/><enum uid="also bad"/>', "malformed_xml"),
        ('<wrong><enum uid="bad"/></wrong>', "unexpected_xml_root"),
        ('<ebv><enum uid="bad"/><enum uid="also bad"/></ebv>', "invalid_siso_record"),
        (f"<ebv>{_table('Entity Types', 'bad')}</ebv>", "invalid_siso_record"),
    ],
)
def test_deferred_record_errors_preserve_xml_validation_priority(xml: str, code: str) -> None:
    with pytest.raises(ParseError) as error:
        EntityTypeXmlParser.from_string(xml)
    assert error.value.code == code


def test_projection_keeps_metadata_text_namespace_and_repeated_requests() -> None:
    xml = """<?xml version="1.0" encoding="ISO-8859-1"?>
<ebv xmlns="urn:test" title="Café">
<ignored><enum uid="bad"/><cet><entity kind="bad"/></cet></ignored>
<meta key="root" value="metadata"/><cr value="7"/><cr value="7"/>
<revisions><revision title="revision"><cr_range value_min="7" value_max="9"/></revision></revisions>
<copyright>Before <b>inside</b> after</copyright>
<enum uid="1" name="Test"><description>A <b>bold</b> description</description>
<enumrow value="1" description="Café"><cr value="7"/><cr value="7"/></enumrow></enum>
<cet name="Entity Types"><entity kind="1" domain="1" country="0"><cr value="7"/></entity></cet>
</ebv>"""
    standard = EntityTypeXmlParser.from_string(xml)
    assert standard.title == "Café"
    assert standard.namespace == "urn:test"
    assert standard.copyright_text == "Before inside after"
    assert standard.source.metadata == (("root", "metadata"),)
    assert standard.enumerations[0].annotations[0].text == "A bold description"
    request = standard.source.change_requests[0]
    assert standard.source.change_requests == (request, request)
    assert standard.enumerations[0].entries[0].source.change_requests == (request, request)
    assert standard.entity_types[0].source.change_requests[0] is not request
    assert standard.source.change_requests[1] is not request
    assert standard.revisions[0].change_requests[0].maximum == 9
    with pytest.raises(ValidationError):
        request.minimum = 1  # type: ignore[misc]
    another = EntityTypeXmlParser.from_string(xml)
    assert another == standard
    assert another.source.change_requests[0] is not request


@pytest.mark.parametrize("annotation", ['<cr value="7"/>', '<cr_range value_min="7" value_max="9"/>'])
def test_repeated_requests_keep_independent_public_field_tracking(annotation: str) -> None:
    standard = EntityTypeXmlParser.from_string(
        f'<ebv>{annotation}{annotation}<enum uid="1" name="Test">'
        f'<enumrow value="1">{annotation}</enumrow></enum></ebv>'
    )
    first, second = standard.source.change_requests
    nested = standard.enumerations[0].entries[0].source.change_requests[0]
    assert first == second == nested
    assert len({id(request) for request in (first, second, nested)}) == 3
    assert len({id(request.model_fields_set) for request in (first, second, nested)}) == 3
    expected = second.model_dump(exclude_unset=True)
    first.model_fields_set.remove("minimum")
    assert "minimum" not in first.model_dump(exclude_unset=True)
    assert second.model_dump(exclude_unset=True) == expected
    assert nested.model_dump(exclude_unset=True) == expected


def test_text_stream_read_boundaries() -> None:
    with _XmlTextStream("Aé文Z") as stream:
        assert stream.read(0) == ""
        assert stream.read(2) == "Aé"
        assert stream.read(99) == "文Z"
        assert stream.read() == ""
    with _XmlTextStream("text") as stream:
        assert stream.read(None) == "text"


def test_compact_models_keep_independent_field_tracking_and_shared_children() -> None:
    standard = EntityTypeXmlParser.from_string(
        '<ebv xmlns="urn:test"><enum uid="1" name="Test">'
        '<enumrow value="1" description="First"/>'
        '<enumrow value="2" description="Second"/></enum>'
        f"{_table('Entity Types')}</ebv>"
    )
    table = standard.enumerations[0]
    first, second = table.entries
    assert first.tag is second.tag
    assert (
        first.model_fields_set
        == second.model_fields_set
        == {"tag", "value", "value_min", "value_max", "description", "source", "children"}
    )
    assert first.model_fields_set is not second.model_fields_set
    updated = first.model_copy(update={"description": "Updated"})
    assert updated.source is first.source
    assert updated.children is first.children
    assert first.description == "First"
    assert updated.description == "Updated"
    assert updated.model_fields_set is not first.model_fields_set
    first.model_fields_set.remove("description")
    assert "description" not in first.model_dump(exclude_unset=True)
    assert second.model_dump(exclude_unset=True)["description"] == "Second"
    assert updated.model_dump(exclude_unset=True)["description"] == "Updated"
    assert table.model_fields_set == {
        "uid",
        "name",
        "applicability",
        "size",
        "source",
        "entries",
        "annotations",
    }
    assert standard.entity_types[0].model_fields_set == {"kind", "domain", "country", "source", "categories"}


def test_benchmark_alternatives_preserve_models(monkeypatch: pytest.MonkeyPatch) -> None:
    import siso_ref010.snapshots as snapshots

    xml = f'<ebv title="Test">{_table("Entity Types")}</ebv>'.encode()
    monkeypatch.setattr(snapshots, "read_snapshot_bytes", lambda _version: xml)
    results = [
        measure_child(1, strategy, strategy == "stream") for strategy in ("tree", "tree-cached", "stream")
    ]
    assert len({result["model_sha256"] for result in results}) == 1
    assert len({result["source_sha256"] for result in results}) == 1
    assert "retained_mib" in results[-1]["stages"]["xml_and_source_models"]
    assert "retained_mib" not in results[0]["stages"]["source_model_projection"]


@pytest.mark.parametrize("selection", ["ignored", "selected", "malformed", "wrong-root", "enum-malformed"])
def test_deep_projection_errors_are_deferred(selection: str) -> None:
    depth = sys.getrecursionlimit() + 10
    categories = '<category value="1">' * depth + "</category>" * depth
    other = f'<cet name="Other"><entity kind="1" domain="1" country="0">{categories}</entity></cet>'
    if selection == "enum-malformed":
        xml = f'<ebv><enum uid="1"><enumrow value="1">{categories}</enumrow></enum>'
    else:
        xml = f"<ebv>{other}"
        if selection != "selected":
            xml += '<cet name="Entity Types"/>'
        if selection != "malformed":
            xml += "</ebv>"
        if selection == "wrong-root":
            xml = xml.replace("ebv>", "wrong>")
    if selection == "ignored":
        assert EntityTypeXmlParser.from_string(xml).entity_types == ()
    elif selection == "selected":
        with pytest.raises(RecursionError):
            EntityTypeXmlParser.from_string(xml)
    else:
        with pytest.raises(ParseError) as error:
            EntityTypeXmlParser.from_string(xml)
        assert error.value.code == ("unexpected_xml_root" if selection == "wrong-root" else "malformed_xml")

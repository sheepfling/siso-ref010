import copy
import json

import pytest

from siso_entity_type.xml_types import Convert, Key, Status, Type, XMLShapeError


@pytest.fixture
def document():
    return {
        "?xml": {"__version": "1.0", "__encoding": "UTF-8"},
        "?xml-stylesheet": [],
        "ebv": {
            "copyright": "SISO notice",
            "revisions": {"__uid": "1", "__name": "Revisions"},
            "dict": {"cr": [], "dictrow": [], "__uid": "2", "__name": "Dictionary"},
            "enum": [],
            "cet": [],
            "bitfield": [],
            "record": [],
            "cot": [],
            "jammer_technique": {"__uid": "3", "__name": "Jammer"},
            "__xmlns": "urn:test",
            "__xmlns:xsi": "urn:xsi",
            "__xsi:schemaLocation": "test.xsd",
            "__title": "Test",
            "__release": "35",
            "__date": "2025-04-27",
            "__href": "",
            "__description": "Test document",
            "__organisation": "SISO",
        },
    }


def test_converter_aliases_and_roundtrip(document):
    text = Convert.sISOXMLTypesToJson(document)
    assert Convert.toSISOXMLTypes(text) == document
    assert Convert.to_siso_xml_types(Convert.siso_xml_types_to_json(document)) == document
    assert Convert.to_siso_xml_types(text)["ebv"]["__date"] == "2025-04-27"
    assert Status.New == "new"
    assert Key.Commid == "commid"
    assert Type.The16BitEnumeration == "16 bit enumeration"


@pytest.mark.parametrize("array", [True, False])
def test_nested_entity_shapes(document, array):
    def items(value):
        return [value] if array else value

    extra = {"__value": "1", "__description": "Extra", "__uid": "10"}
    specific = {"__value": "1", "__description": "Specific", "__uid": "9", "extra": items(extra)}
    sub = {"__value": "1", "__description": "Sub", "__uid": "8", "specific": items(specific)}
    category = {"__value": "1", "__description": "Cat", "__uid": "7", "subcategory": items(sub)}
    entity = {"__kind": "1", "__domain": "2", "__country": "225", "__uid": "6", "category": items(category)}
    document["ebv"]["cet"] = [{"__uid": "5", "__name": "Entities", "entity": items(entity)}]
    assert Convert.to_siso_xml_types(json.dumps(document)) == document
    extra["__value"] = 1
    with pytest.raises(XMLShapeError, match="__value"):
        Convert.to_siso_xml_types(json.dumps(document))


@pytest.mark.parametrize("change", ["missing", "unknown", "null", "date", "status", "array", "number"])
def test_invalid_document_shapes(document, change):
    original = copy.deepcopy(document)
    if change == "missing":
        del document["?xml"]
    elif change == "unknown":
        document["extra"] = "unexpected"
    elif change == "null":
        document["ebv"]["dict"] = None
    elif change == "date":
        document["ebv"]["__date"] = "2025-02-30"
    elif change == "status":
        document["ebv"]["enum"] = [{"__uid": "1", "__name": "x", "__size": "8", "__status": "old"}]
    elif change == "array":
        document["ebv"]["cet"] = {}
    elif change == "number":
        document["ebv"]["dict"]["__uid"] = 2
    with pytest.raises(XMLShapeError):
        Convert.to_siso_xml_types(json.dumps(document))
    with pytest.raises(XMLShapeError):
        Convert.siso_xml_types_to_json(document)
    assert Convert.to_siso_xml_types(json.dumps(original)) == original


@pytest.mark.parametrize("value", ["{", "null", "[]", "true", "NaN"])
def test_invalid_json_or_root(value):
    with pytest.raises(XMLShapeError):
        Convert.to_siso_xml_types(value)


def test_cycle_rejected(document):
    document["ebv"]["jammer_technique"]["jammer_kind"] = [{"__value": "1", "__description": "Cycle"}]
    item = document["ebv"]["jammer_technique"]["jammer_kind"][0]
    item["jammer_category"] = item
    with pytest.raises(XMLShapeError, match="cyclic"):
        Convert.siso_xml_types_to_json(document)

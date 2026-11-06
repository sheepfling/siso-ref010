# Modified work (2026): Python adaptation of TNO-MST/siso-entity-type.
# Original copyright 2025 TNO; Apache-2.0. See LICENSE and NOTICE.
"""Native records and validation for the public XML-as-JSON interchange API.

This is a structural interchange validator, not the SISO XML schema. Dates stay
ISO strings; no JavaScript runtime or generated code is used.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import TypeAlias, cast

JSONValue: TypeAlias = "str | int | float | bool | None | list[JSONValue] | dict[str, JSONValue]"
SISOXMLTypes: TypeAlias = dict[str, JSONValue]


class XMLShapeError(ValueError):
    """An XML-as-JSON document does not match the interchange shape."""


class Status(StrEnum):
    NEW = "new"
    New = NEW


class Type(StrEnum):
    The16BitEnumeration = "16 bit enumeration"
    The16BitUnsignedInteger = "16-bit unsigned integer"
    The32BitFloatingPoint = "32 bit floating point"
    The64BitFloatingPoint = "64 bit floating point"
    The8BitEnumeration = "8 bit enumeration"
    The8BitSignedInteger = "8-bit signed integer"


class Key(StrEnum):
    Commid = "commid"
    Email = "email"
    Natoid = "natoid"
    Org = "org"
    Poc = "poc"
    Type = "type"


@dataclass(frozen=True, slots=True)
class ExtraElement:
    """A leaf accepted by incremental parser methods (numeric DIS field value)."""

    value: int
    description: str


@dataclass(frozen=True, slots=True)
class SpecificElement:
    """A specific record and optional extra records for incremental insertion."""

    value: int
    description: str
    extra: ExtraElement | tuple[ExtraElement, ...] = ()


# A compact handwritten structural schema: suffix ? means optional; [] means
# an array; | means either shape. All objects reject unknown properties.
_SCHEMAS: dict[str, dict[str, str]] = {
    "SISOXMLTypes": {"?xml": "XML", "?xml-stylesheet": "XMLStylesheet[]", "ebv": "Ebv"},
    "XML": {"__version": "str", "__encoding": "str"},
    "XMLStylesheet": dict.fromkeys(("__type", "__href", "__title", "__alternate"), "str"),
    "Ebv": {
        "copyright": "str",
        "revisions": "JammerTechnique",
        "dict": "Dict",
        "enum": "Enum[]",
        "cet": "JammerTechnique[]",
        "bitfield": "Bitfield[]",
        "record": "JammerTechnique[]",
        "cot": "JammerTechnique[]",
        "jammer_technique": "JammerTechnique",
        **dict.fromkeys(
            (
                "__xmlns",
                "__xmlns:xsi",
                "__xsi:schemaLocation",
                "__title",
                "__release",
                "__href",
                "__description",
                "__organisation",
            ),
            "str",
        ),
        "__date": "date",
    },
    "CR": {"__value": "str"},
    "Bitfield": {
        "bitfieldrow?": "Bitfieldrow[]|Bitfieldrow",
        "__uid": "str",
        "__name": "str",
        "__size": "str",
        "cr?": "CR[]|CR",
    },
    "Bitfieldrow": {
        "cr": "CR[]|CR",
        "__name": "str",
        "__bit_position": "str",
        "__description": "str",
        "__xref?": "str",
        "__length?": "str",
        "__footnote?": "str",
    },
    "JammerTechnique": {
        "cr?": "CR",
        "entity?": "Entity[]|Entity",
        "__uid": "str",
        "__name": "str",
        "object?": "Object[]|Object",
        "jammer_kind?": "JammerKind[]",
        "field?": "Field[]|Field",
        "revision?": "Revision[]",
    },
    "Entity": {
        "cr?": "CR",
        "category": "Category[]|Category",
        "__kind": "str",
        "__domain": "str",
        "__country": "str",
        "__uid": "str",
        "__status?": "Status",
    },
    "Category": {
        "subcategory?": "Subcategory[]|Subcategory",
        "__value": "str",
        "__description": "str",
        "__uid": "str",
        "cr?": "CR[]|CR",
        "__status?": "Status",
        "__deprecated?": "str",
        "subcategory_xref?": "SubcategoryXref",
        "__variation?": "str",
        "specific?": "Specific[]|Specific",
    },
    "Subcategory": {
        "specific?": "Specific[]|Specific",
        "__value": "str",
        "__description": "str",
        "__uid": "str",
        "cr?": "CR[]|CR",
        "__variation?": "str",
        "__deprecated?": "str",
        "__status?": "Status",
    },
    "Specific": {
        "cr?": "CR[]|CR",
        "specific?": "Specific[]|Specific",
        "__value": "str",
        "__description": "str",
        "__uid": "str",
        "__variation?": "str",
        "__deprecated?": "str",
        "__status?": "Status",
        "__footnote?": "str",
        "__retired?": "str",
        "extra?": "Extra[]|Extra",
        "__transferred?": "str",
    },
    "Extra": {
        "cr?": "CR[]|CR",
        "__value": "str",
        "__description": "str",
        "__uid": "str",
        "__status?": "Status",
        "__deprecated?": "str",
        "__variation?": "str",
    },
    "JammerKind": {
        "cr?": "CR",
        "__value": "str",
        "__description": "str",
        "__uid?": "str",
        "__status?": "Status",
        "subcategory?": "Subcategory[]|Subcategory",
        "__deprecated?": "str",
        "jammer_category?": "JammerKind[]|JammerKind",
        "jammer_subcategory?": "JammerKind[]|JammerKind",
        "jammer_specific?": "JammerKind[]|JammerKind",
        "__footnote?": "str",
    },
    "SubcategoryXref": {
        "cr": "CR",
        "specific": "JammerKind",
        "__xref": "str",
        "__description": "str",
        "__uid": "str",
    },
    "Field": {"datatype": "Datatype[]|Datatype", "__name": "str", "cr?": "CR"},
    "Datatype": {"cr?": "CR", "__name": "str", "__type?": "Type"},
    "Object": {
        "cr": "CR",
        "category": "JammerKind[]|JammerKind",
        "__domain": "str",
        "__kind": "str",
        "__description": "str",
        "__uid": "str",
    },
    "Revision": {"cr?": "CR[]", "cr_range": "CRRange[]|CRRange", "__title": "str", "__date": "date"},
    "CRRange": {"__value_min": "str", "__value_max": "str"},
    "Dict": {"cr": "CR[]", "dictrow": "Dictrow[]", "__uid": "str", "__name": "str"},
    "Dictrow": {
        "__value": "str",
        "__description": "str",
        "cr?": "CR[]|CR",
        "__status?": "Status",
        "__footnote?": "str",
    },
    "Enum": {
        "cr?": "CR[]|CR",
        "enumrow?": "Enumrow[]|Enumrow",
        "__uid": "str",
        "__name": "str",
        "__size": "str",
        "__applicability?": "str",
        "__footnote?": "str",
        "description?": "Description[]",
        "enumrow_range?": "EnumrowRange[]|EnumrowRange",
        "__group?": "str",
        "header?": "Header",
        "__deprecated?": "str",
        "__status?": "Status",
    },
    "Description": {"cr": "CR", "#text": "str"},
    "Enumrow": {
        "__value": "str",
        "__description": "str",
        "cr?": "CR[]|CR",
        "__footnote?": "str",
        "__deprecated?": "str",
        "__status?": "Status",
        "__xref?": "str",
        "__group?": "str",
        "meta?": "Meta[]|Meta",
    },
    "Meta": {"__key": "Key", "__value": "str"},
    "EnumrowRange": {
        "__value_min": "str",
        "__value_max": "str",
        "__description": "str",
        "cr?": "CR",
        "__footnote?": "str",
    },
    "Header": {"col": "Col[]"},
    "Col": {"__key": "Key", "__name": "str"},
}
_ENUMS = {"Status": Status, "Type": Type, "Key": Key}


def _validate(value: object, shape: str, path: str) -> None:
    if "|" in shape:
        errors: list[str] = []
        for choice in shape.split("|"):
            try:
                _validate(value, choice, path)
                return
            except XMLShapeError as exc:
                errors.append(str(exc))
        raise XMLShapeError("; ".join(errors))
    if shape.endswith("[]"):
        if not isinstance(value, list):
            raise XMLShapeError(f"{path}: expected an array")
        for index, item in enumerate(cast(list[object], value)):
            _validate(item, shape[:-2], f"{path}[{index}]")
        return
    if shape in ("str", "date") or shape in _ENUMS:
        if not isinstance(value, str):
            raise XMLShapeError(f"{path}: expected a string")
        if shape == "date":
            try:
                datetime.fromisoformat(value)
            except ValueError as exc:
                raise XMLShapeError(f"{path}: expected an ISO 8601 date or datetime") from exc
        elif shape in _ENUMS and value not in {item.value for item in _ENUMS[shape]}:
            raise XMLShapeError(f"{path}: invalid {shape} value {value!r}")
        return
    if not isinstance(value, dict):
        raise XMLShapeError(f"{path}: expected an object")
    obj = cast(dict[object, object], value)
    fields = _SCHEMAS[shape]
    allowed = {key.removesuffix("?") for key in fields}
    for key in obj:
        if key not in allowed:
            raise XMLShapeError(f"{path}: unexpected property {key!r}")
    for field, field_shape in fields.items():
        key = field.removesuffix("?")
        if key not in obj:
            if field.endswith("?"):
                continue
            raise XMLShapeError(f"{path}.{key}: required property is missing")
        _validate(obj[key], field_shape, f"{path}.{key}")


class Convert:
    """Validate XML-as-JSON structures, with upstream-compatible method aliases."""

    @staticmethod
    def to_siso_xml_types(text: str) -> SISOXMLTypes:
        try:
            value: object = json.loads(text)
        except (ValueError, RecursionError) as exc:
            raise XMLShapeError(f"Invalid JSON: {exc}") from exc
        try:
            _validate(value, "SISOXMLTypes", "$")
        except RecursionError as exc:
            raise XMLShapeError("Document nesting is too deep") from exc
        return cast(SISOXMLTypes, value)

    @staticmethod
    def siso_xml_types_to_json(value: SISOXMLTypes) -> str:
        try:
            _validate(value, "SISOXMLTypes", "$")
            return json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)
        except RecursionError as exc:
            raise XMLShapeError("Document nesting is too deep or cyclic") from exc

    toSISOXMLTypes = to_siso_xml_types
    sISOXMLTypesToJson = siso_xml_types_to_json

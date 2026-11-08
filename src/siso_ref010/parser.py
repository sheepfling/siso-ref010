"""Read SISO-REF-010 XML into a structured standard model."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from hashlib import sha256

from pydantic import ValidationError

from .errors import EntityTypeValueError
from .paths import PathInput, normalize_path
from .reference import (
    ChangeRequest,
    EntityBranch,
    EntityTypeStandard,
    EnumerationTable,
    ReferenceEntry,
    SourceInfo,
    TableAnnotation,
)


class ParseError(EntityTypeValueError):
    """Malformed XML or a record that cannot be read from the standard."""


_ENTITY_ENTRY_TAGS = frozenset(
    {
        "category",
        "category_range",
        "subcategory",
        "subcategory_xref",
        "subcategory_range",
        "specific",
        "specific_range",
        "extra",
        "extra_range",
    }
)


def _tag(element: ET.Element) -> str:
    return element.tag.rsplit("}", 1)[-1]


def _children(element: ET.Element, tag: str) -> list[ET.Element]:
    return [child for child in element if _tag(child) == tag]


def _source_info(element: ET.Element) -> SourceInfo:
    requests: list[ChangeRequest] = []
    for child in element:
        tag = _tag(child)
        if tag == "cr":
            value = child.get("value")
            requests.append(ChangeRequest.model_validate({"minimum": value, "maximum": value}))
        elif tag == "cr_range":
            requests.append(
                ChangeRequest.model_validate(
                    {"minimum": child.get("value_min"), "maximum": child.get("value_max")}
                )
            )
    metadata: list[tuple[str, str]] = []
    for item in _children(element, "meta"):
        key = item.get("key")
        value = item.get("value")
        if key is not None and value is not None:
            metadata.append((key, value))
    return SourceInfo.model_validate(
        {
            "attributes": tuple(element.attrib.items()),
            "metadata": tuple(metadata),
            "change_requests": tuple(requests),
        }
    )


def _entry(element: ET.Element) -> ReferenceEntry:
    tag = _tag(element)
    children = tuple(_entry(child) for child in element if _tag(child) in _ENTITY_ENTRY_TAGS)
    return ReferenceEntry.model_validate(
        {
            "tag": tag,
            "value": element.get("value"),
            "value_min": element.get("value_min"),
            "value_max": element.get("value_max"),
            "description": element.get("description"),
            "source": _source_info(element),
            "children": children,
        }
    )


def _enumeration(element: ET.Element) -> EnumerationTable:
    return EnumerationTable.model_validate(
        {
            "uid": element.get("uid"),
            "name": element.get("name", ""),
            "applicability": element.get("applicability"),
            "size": element.get("size"),
            "source": _source_info(element),
            "entries": tuple(
                _entry(child) for child in element if _tag(child) in {"enumrow", "enumrow_range"}
            ),
            "annotations": tuple(
                TableAnnotation.model_validate(
                    {
                        "tag": _tag(child),
                        "text": "".join(child.itertext()).strip(),
                        "source": _source_info(child),
                    }
                )
                for child in element
                if _tag(child) in {"description", "header"}
            ),
        }
    )


def _entity_branch(element: ET.Element) -> EntityBranch:
    return EntityBranch.model_validate(
        {
            "kind": element.get("kind"),
            "domain": element.get("domain"),
            "country": element.get("country"),
            "source": _source_info(element),
            "categories": tuple(_entry(child) for child in element if _tag(child) in _ENTITY_ENTRY_TAGS),
        }
    )


class EntityTypeXmlParser:
    """Parse a standard file or string without flattening its source structure."""

    @classmethod
    def from_string(cls, xml_string: str) -> EntityTypeStandard:
        if re.search(r"<!\s*(?:DOCTYPE|ENTITY)\b", xml_string, re.IGNORECASE):
            raise ParseError(
                "DTD and entity declarations are not supported",
                code="unsupported_xml_declaration",
                context={"declaration": "DOCTYPE or ENTITY"},
            )
        try:
            root = ET.fromstring(xml_string)
        except ET.ParseError as exc:
            raise ParseError(
                f"Invalid SISO XML: {exc}",
                code="malformed_xml",
                context={"line": exc.position[0], "column": exc.position[1]},
            ) from exc
        if _tag(root) != "ebv":
            raise ParseError(
                "Expected an SISO-REF-010 <ebv> root element",
                code="unexpected_xml_root",
                context={"expected": "ebv", "actual": _tag(root)},
            )

        entity_tables = _children(root, "cet")
        entity_table = next(
            (table for table in entity_tables if table.get("name") == "Entity Types"),
            None,
        )
        if entity_table is None:
            entity_table = next(
                (table for table in entity_tables if table.get("name") == "Comprehensive Entity Types"),
                None,
            )
        if entity_table is None:
            entity_table = next((table for table in entity_tables if _children(table, "entity")), None)
        try:
            standard = EntityTypeStandard.model_validate(
                {
                    "source": _source_info(root),
                    "namespace": root.tag[1:].split("}", 1)[0] if root.tag.startswith("{") else None,
                    "revisions": tuple(
                        _source_info(row)
                        for group in _children(root, "revisions")
                        for row in _children(group, "revision")
                    ),
                    "copyright_text": "\n".join(
                        "".join(node.itertext()).strip() for node in _children(root, "copyright")
                    ),
                    "enumerations": tuple(_enumeration(table) for table in _children(root, "enum")),
                    "entity_table": _source_info(entity_table) if entity_table is not None else None,
                    "entity_types": (
                        tuple(_entity_branch(branch) for branch in _children(entity_table, "entity"))
                        if entity_table is not None
                        else ()
                    ),
                    "xml_parse_succeeded": True,
                }
            )
            return standard.model_copy(
                update={"source_sha256": sha256(xml_string.encode("utf-8")).hexdigest()}
            )
        except ValidationError as exc:
            details = tuple(
                {
                    "location": list(error["loc"]),
                    "code": error["type"],
                    "message": error["msg"],
                }
                for error in exc.errors()
            )
            raise ParseError(
                f"Invalid SISO record: {exc}",
                code="invalid_siso_record",
                context={"validation_errors": details},
            ) from exc

    @classmethod
    def from_file(cls, path: PathInput) -> EntityTypeStandard:
        source = normalize_path(path)
        return cls.from_bytes(source.read_bytes())

    @classmethod
    def from_bytes(cls, xml_bytes: bytes) -> EntityTypeStandard:
        """Parse XML bytes and retain their exact SHA-256 digest."""
        standard = cls.from_string(xml_bytes.decode("utf-8-sig"))
        return standard.model_copy(update={"source_sha256": sha256(xml_bytes).hexdigest()})

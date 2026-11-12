"""Read SISO-REF-010 XML into a structured standard model."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from hashlib import sha256
from io import TextIOBase

from pydantic import ValidationError

from .._paths import PathInput, normalize_path
from ..errors import SisoRef010ValueError
from ..models.standard import (
    ChangeRequest,
    EntityBranch,
    EntityTypeStandard,
    EnumerationTable,
    ReferenceEntry,
    SourceInfo,
    TableAnnotation,
)


class ParseError(SisoRef010ValueError):
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


class _ModelBuilder:
    """Reuse validated annotation values without sharing public model bookkeeping."""

    def __init__(self) -> None:
        self._requests: dict[tuple[str | None, str | None], ChangeRequest] = {}
        self._tags: dict[str, str] = {}

    def _change_request(self, minimum: str | None, maximum: str | None) -> ChangeRequest:
        key = (minimum, maximum)
        cached = self._requests.get(key)
        if cached is None:
            cached = ChangeRequest.model_validate({"minimum": minimum, "maximum": maximum})
            self._requests[key] = cached
        # Frozen models still expose mutable model_fields_set and __dict__.
        # Keep the cached template private and give each occurrence its own copy.
        return cached.model_copy()

    def source_info(self, element: ET.Element) -> SourceInfo:
        requests: list[ChangeRequest] = []
        for child in element:
            tag = _tag(child)
            if tag == "cr":
                value = child.get("value")
                requests.append(self._change_request(value, value))
            elif tag == "cr_range":
                requests.append(self._change_request(child.get("value_min"), child.get("value_max")))
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

    def entry(self, element: ET.Element) -> ReferenceEntry:
        tag = _tag(element)
        tag = self._tags.setdefault(tag, tag)
        children = tuple(self.entry(child) for child in element if _tag(child) in _ENTITY_ENTRY_TAGS)
        # A shallow public model copy compacts Pydantic's per-instance field-name
        # set on CPython. Validation still runs, and mutable sets are never shared.
        return ReferenceEntry.model_validate(
            {
                "tag": tag,
                "value": element.get("value"),
                "value_min": element.get("value_min"),
                "value_max": element.get("value_max"),
                "description": element.get("description"),
                "source": self.source_info(element),
                "children": children,
            }
        ).model_copy()

    def enumeration(self, element: ET.Element) -> EnumerationTable:
        return EnumerationTable.model_validate(
            {
                "uid": element.get("uid"),
                "name": element.get("name", ""),
                "applicability": element.get("applicability"),
                "size": element.get("size"),
                "source": self.source_info(element),
                "entries": tuple(
                    self.entry(child) for child in element if _tag(child) in {"enumrow", "enumrow_range"}
                ),
                "annotations": tuple(
                    TableAnnotation.model_validate(
                        {
                            "tag": _tag(child),
                            "text": "".join(child.itertext()).strip(),
                            "source": self.source_info(child),
                        }
                    )
                    for child in element
                    if _tag(child) in {"description", "header"}
                ),
            }
        ).model_copy()

    def entity_branch(self, element: ET.Element) -> EntityBranch:
        return EntityBranch.model_validate(
            {
                "kind": element.get("kind"),
                "domain": element.get("domain"),
                "country": element.get("country"),
                "source": self.source_info(element),
                "categories": tuple(
                    self.entry(child) for child in element if _tag(child) in _ENTITY_ENTRY_TAGS
                ),
            }
        ).model_copy()


@dataclass
class _EntityTable:
    element: ET.Element
    branches: list[EntityBranch] = field(default_factory=list[EntityBranch])
    error: ValidationError | RecursionError | None = None
    has_entities: bool = False

    def entity_types(self) -> tuple[EntityBranch, ...]:
        if self.error is not None:
            raise self.error
        return tuple(self.branches)


class _XmlTextStream(TextIOBase):
    """Feed Unicode directly without StringIO's full-size mutable buffer copy."""

    def __init__(self, text: str) -> None:
        self._text = text
        self._offset = 0

    def read(self, size: int | None = -1) -> str:
        end = len(self._text) if size is None or size < 0 else self._offset + size
        chunk = self._text[self._offset : end]
        self._offset += len(chunk)
        return chunk


class _StreamProjection:
    """Discard projected XML subtrees while retaining root metadata and source order."""

    def __init__(self, xml_string: str) -> None:
        self.builder = _ModelBuilder()
        self.enumerations: list[EnumerationTable] = []
        self.enumeration_error: ValidationError | RecursionError | None = None
        self.tables: list[_EntityTable] = []
        # Syntax/root errors take precedence; only the selected CET is validated.
        # Defer projection failures until those decisions are known.
        with _XmlTextStream(xml_string) as stream:
            events = ET.iterparse(stream, events=("start", "end"))
            self.root: ET.Element = next(events)[1]
            stack = [self.root]
            for event, element in events:
                if event == "start":
                    stack.append(element)
                    if len(stack) == 2 and _tag(element) == "cet":
                        self.tables.append(_EntityTable(element))
                    continue
                if len(stack) == 3 and _tag(stack[1]) == "cet" and _tag(element) == "entity":
                    table = self.tables[-1]
                    table.has_entities = True
                    if table.error is None:
                        try:
                            table.branches.append(self.builder.entity_branch(element))
                        except (ValidationError, RecursionError) as error:
                            table.error = error
                    stack[1].remove(element)
                    element.clear()
                elif len(stack) == 2 and _tag(element) == "enum":
                    if self.enumeration_error is None:
                        try:
                            self.enumerations.append(self.builder.enumeration(element))
                        except (ValidationError, RecursionError) as error:
                            self.enumeration_error = error
                    stack[0].remove(element)
                    element.clear()
                elif len(stack) == 2 and _tag(element) not in {
                    "cet",
                    "copyright",
                    "revisions",
                    "meta",
                    "cr",
                    "cr_range",
                }:
                    stack[0].remove(element)
                    element.clear()
                stack.pop()

    def enumeration_tables(self) -> tuple[EnumerationTable, ...]:
        if self.enumeration_error is not None:
            raise self.enumeration_error
        return tuple(self.enumerations)

    def entity_table(self) -> _EntityTable | None:
        for name in ("Entity Types", "Comprehensive Entity Types"):
            match = next((table for table in self.tables if table.element.get("name") == name), None)
            if match is not None:
                return match
        return next((table for table in self.tables if table.has_entities), None)


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
            projection = _StreamProjection(xml_string)
            root = projection.root
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

        entity_table = projection.entity_table()
        builder = projection.builder
        try:
            standard = EntityTypeStandard.model_validate(
                {
                    "source": builder.source_info(root),
                    "date": root.get("date") or None,
                    "namespace": root.tag[1:].split("}", 1)[0] if root.tag.startswith("{") else None,
                    "revisions": tuple(
                        builder.source_info(row)
                        for group in _children(root, "revisions")
                        for row in _children(group, "revision")
                    ),
                    "copyright_text": "\n".join(
                        "".join(node.itertext()).strip() for node in _children(root, "copyright")
                    ),
                    "enumerations": projection.enumeration_tables(),
                    "entity_table": builder.source_info(entity_table.element)
                    if entity_table is not None
                    else None,
                    "entity_types": (entity_table.entity_types() if entity_table is not None else ()),
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

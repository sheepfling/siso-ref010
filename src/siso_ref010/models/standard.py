"""Validated Pydantic models for the structured SISO-REF-010 source."""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import date as Date
from types import MappingProxyType
from typing import Annotated, Any, Self, TypeAlias

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, model_validator


def _unsigned_integer(value: Any) -> int:
    if isinstance(value, bool):
        raise ValueError("boolean is not an unsigned decimal value")
    if isinstance(value, int):
        return value
    if isinstance(value, str) and re.fullmatch(r"[0-9]+", value.strip()):
        return int(value.strip())
    raise ValueError(f"expected an unsigned decimal integer, got {value!r}")


UnsignedInteger = Annotated[int, BeforeValidator(_unsigned_integer), Field(ge=0)]
UnsignedByte = Annotated[UnsignedInteger, Field(le=255)]
UnsignedCountry = Annotated[UnsignedInteger, Field(le=65535)]

Attributes = tuple[tuple[str, str], ...]
Metadata = tuple[tuple[str, str], ...]


class ReferenceModel(BaseModel):
    """Common immutable configuration for source and API result models."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class ChangeRequest(ReferenceModel):
    minimum: UnsignedInteger
    maximum: UnsignedInteger

    @model_validator(mode="after")
    def validate_range(self) -> Self:
        if self.minimum > self.maximum:
            raise ValueError("change-request range minimum exceeds maximum")
        return self


class SourceInfo(ReferenceModel):
    """Attributes and annotations retained from one source XML element."""

    attributes: Attributes
    metadata: Metadata = ()
    change_requests: tuple[ChangeRequest, ...] = ()

    def get(self, name: str) -> str | None:
        return next((value for key, value in self.attributes if key == name), None)


class ReferenceEntry(ReferenceModel):
    """An enum row, range, or hierarchical entity entry as written in the XML."""

    tag: str
    value: UnsignedInteger | None
    value_min: UnsignedInteger | None
    value_max: UnsignedInteger | None
    description: str | None
    source: SourceInfo
    children: tuple[ReferenceEntry, ...] = ()

    @model_validator(mode="after")
    def validate_value_shape(self) -> Self:
        has_minimum = self.value_min is not None
        has_maximum = self.value_max is not None
        if has_minimum != has_maximum:
            raise ValueError("value range must supply both endpoints")
        if self.value is not None and has_minimum:
            raise ValueError("entry cannot have both a scalar value and a range")
        if self.value_min is not None and self.value_max is not None:
            if self.value_min > self.value_max:
                raise ValueError("value range minimum exceeds maximum")
        if self.tag in {"enumrow", "enumrow_range"} and self.value is None and not has_minimum:
            raise ValueError(f"<{self.tag}> requires a value or value range")
        return self


class TableAnnotation(ReferenceModel):
    """Textual description or header attached to an enumeration table."""

    tag: str
    text: str
    source: SourceInfo


class EnumerationTable(ReferenceModel):
    uid: UnsignedInteger
    name: str
    applicability: str | None
    size: UnsignedInteger | None
    source: SourceInfo
    entries: tuple[ReferenceEntry, ...]
    annotations: tuple[TableAnnotation, ...] = ()


EnumerationTableIndex: TypeAlias = Mapping[int, tuple[EnumerationTable, ...]]


class EntityBranch(ReferenceModel):
    kind: UnsignedByte
    domain: UnsignedByte
    country: UnsignedCountry
    source: SourceInfo
    categories: tuple[ReferenceEntry, ...]


class EntityTypeStandard(ReferenceModel):
    """Parsed SISO data, retaining source attributes and a typed edition date."""

    source: SourceInfo
    namespace: str | None
    revisions: tuple[SourceInfo, ...]
    copyright_text: str
    enumerations: tuple[EnumerationTable, ...]
    entity_table: SourceInfo | None
    entity_types: tuple[EntityBranch, ...]
    date: Date | None = Field(
        default=None,
        exclude=True,
        description="Source-declared calendar date, parsed by Pydantic from the XML date attribute.",
    )
    source_sha256: str | None = None
    xml_parse_succeeded: bool | None = Field(default=None, exclude=True)

    @property
    def title(self) -> str:
        return self.source.get("title") or ""

    def enumeration(self, name: str) -> EnumerationTable | None:
        """Return a table only when its name uniquely identifies one definition."""
        matches = self.enumerations_named(name)
        return matches[0] if len(matches) == 1 else None

    def enumerations_named(self, name: str) -> list[EnumerationTable]:
        return [table for table in self.enumerations if table.name == name]

    @property
    def enumeration_uid_index(self) -> EnumerationTableIndex:
        tables_by_uid: dict[int, list[EnumerationTable]] = {}
        for table in self.enumerations:
            tables_by_uid.setdefault(table.uid, []).append(table)
        return MappingProxyType({uid: tuple(tables) for uid, tables in tables_by_uid.items()})

    def enumeration_tables_by_uid(self, uid: int) -> tuple[EnumerationTable, ...]:
        """Return every table definition carrying a UID, in source order."""
        return self.enumeration_uid_index.get(uid, ())

    def enumeration_by_uid(self, uid: int) -> EnumerationTable | None:
        """Return a table only when its UID uniquely identifies one definition."""
        matches = self.enumeration_tables_by_uid(uid)
        return matches[0] if len(matches) == 1 else None

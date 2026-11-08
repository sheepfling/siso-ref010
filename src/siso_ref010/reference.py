"""Validated Pydantic models for the structured SISO-REF-010 source."""

from __future__ import annotations

import re
from datetime import date as Date
from typing import Annotated, Any, Self

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


class EntityBranch(ReferenceModel):
    kind: UnsignedByte
    domain: UnsignedByte
    country: UnsignedCountry
    source: SourceInfo
    categories: tuple[ReferenceEntry, ...]


class EntityTypeStandard(ReferenceModel):
    """Parsed SISO standard data, retaining its hierarchy and source metadata."""

    source: SourceInfo
    namespace: str | None
    revisions: tuple[SourceInfo, ...]
    copyright_text: str
    enumerations: tuple[EnumerationTable, ...]
    entity_table: SourceInfo | None
    entity_types: tuple[EntityBranch, ...]
    date: Date | None = Field(default=None, exclude=True)
    source_sha256: str | None = None
    xml_parse_succeeded: bool | None = Field(default=None, exclude=True)

    @property
    def title(self) -> str:
        return self.source.get("title") or ""

    def enumeration(self, name: str) -> EnumerationTable | None:
        return next((table for table in self.enumerations if table.name == name), None)

    def enumerations_named(self, name: str) -> list[EnumerationTable]:
        return [table for table in self.enumerations if table.name == name]

    def enumeration_by_uid(self, uid: int) -> EnumerationTable | None:
        return next((table for table in self.enumerations if table.uid == uid), None)

"""Metadata-aware inspection of values in one parsed SISO-REF-010 edition."""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Callable, Iterable, Iterator, Mapping
from dataclasses import dataclass
from enum import StrEnum
from functools import cached_property
from typing import Literal, TypeAlias, cast

from pydantic import BaseModel, ConfigDict, computed_field

from ._version import __version__
from .errors import SisoRef010ValueError
from .models.standard import (
    EntityTypeStandard,
    EnumerationTable,
    ReferenceEntry,
    SourceInfo,
    TableAnnotation,
)

SourceOccurrence: TypeAlias = tuple[str, int | None, str | None]


class EditionValueKind(StrEnum):
    ENUMERATION = "enumeration"
    ENTITY_TYPE = "entity_type"


class ResolutionStatus(StrEnum):
    EXACT = "exact"
    UNSPECIFIED = "unspecified"
    PARTIAL = "partial"
    UNKNOWN = "unknown"
    AMBIGUOUS = "ambiguous"


class ResolutionMatchMode(StrEnum):
    DIRECT = "direct"
    GENERIC_COUNTRY = "generic_country"
    RANGE = "range"
    XREF = "xref"


class EnumerationValueStatus(StrEnum):
    EXACT = "exact"
    RANGE = "range"
    AMBIGUOUS = "ambiguous"
    UNKNOWN = "unknown"


class DiagnosticSeverity(StrEnum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class ProvenanceStatus(StrEnum):
    BUNDLED_CHECKSUM_VERIFIED = "bundled_checksum_verified"
    UNVERIFIED = "unverified"


class ValidationStatus(StrEnum):
    PASSED = "passed"
    NOT_RUN = "not_run"
    UNVERIFIED = "unverified"


class SemanticCheckStatus(StrEnum):
    CHECKED = "checked"
    NOT_RUN = "not_run"


class IdentityClassification(StrEnum):
    SOURCE_RECORD_REUSE = "source_record_reuse"
    DUPLICATE_SOURCE_IDENTIFIER = "duplicate_source_identifier"
    CONFLICTING_SOURCE_RECORDS = "conflicting_source_records"
    LIBRARY_IDENTITY_COLLISION = "library_identity_collision"


class EditionIdentityGroup(BaseModel):
    """Repeated value identity with source-row and hierarchy-context evidence."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    key: str
    uuid: str | None
    identity_keys: tuple[str, ...]
    classification: IdentityClassification
    occurrences: int
    repeated_uuid_occurrences: int
    repeated_identity_key_occurrences: int
    source_record_count: int
    reference_context_occurrences: int
    conflict_fields: tuple[str, ...]
    sample_contexts: tuple[str, ...]
    message: str


class EditionIdentityDiagnostics(BaseModel):
    """Counts and grouped evidence for repeated UUID and library identities."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    checked: bool
    error: str | None
    inspected_records: int | None
    records_with_uuid: int | None
    distinct_uuid_values: int | None
    repeated_uuid_occurrences: int | None
    repeated_uuid_groups: int | None
    distinct_value_identity_keys: int | None
    repeated_identity_key_occurrences: int | None
    source_record_reuse_groups: int | None
    duplicate_source_identifier_groups: int | None
    conflicting_source_record_groups: int | None
    groups: tuple[EditionIdentityGroup, ...]


class EditionSemanticCheck(BaseModel):
    """Whether a named semantic integrity check ran and how many findings it had."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    code: str
    status: SemanticCheckStatus
    finding_count: int | None
    description: str


class EnumerationTableInfo(BaseModel):
    """Summary for one source enumeration table."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    uid: int
    name: str
    applicability: str | None
    declared_size_bits: int | None
    entry_count: int
    range_count: int
    source: SourceInfo
    annotations: tuple[TableAnnotation, ...]

    @property
    def declared_size(self) -> int | None:
        """Deprecated alias for the source-declared width in bits."""
        return self.declared_size_bits


class EditionValue(BaseModel):
    """One source value with its edition, table, hierarchy, and XML metadata."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: EditionValueKind
    tag: str
    value: int | None
    value_min: int | None
    value_max: int | None
    description: str | None
    table_uid: int | None
    table_name: str | None
    applicability: str | None
    hierarchy_codes: tuple[int, ...]
    path: tuple[str, ...]
    uuid: str | None
    status: str | None
    deprecated: bool
    footnote: str | None
    source: SourceInfo
    table_source: SourceInfo | None = None
    table_annotations: tuple[TableAnnotation, ...] = ()
    reference_source: SourceInfo | None = None

    @property
    def identity(self) -> str:
        """Return a stable best-effort key for comparing values across editions."""
        if self.uuid:
            return f"{self.kind.value}:uuid:{self.uuid.casefold()}"
        if self.hierarchy_codes:
            codes = ".".join(str(code) for code in self.hierarchy_codes)
            value = _value_key(self.value, self.value_min, self.value_max)
            return f"{self.kind.value}:path:{codes}:{value}"
        value = _value_key(self.value, self.value_min, self.value_max)
        return f"{self.kind.value}:table:{self.table_uid}:{value}"


class EditionSearchHit(EditionValue):
    """A matched value with the fields that caused it to match."""

    matched_fields: tuple[str, ...]


class EntityResolution(BaseModel):
    """Resolution outcome for a full entity code or contiguous field prefix."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    code: str
    status: ResolutionStatus
    requested_depth: int
    matched_depth: int
    is_prefix: bool
    resolution_description: str
    matched_path: tuple[EditionValue, ...]
    match_modes: tuple[ResolutionMatchMode, ...]
    unspecified_components: tuple[str, ...]
    unresolved_components: tuple[str, ...]
    ambiguous_candidates: tuple[EditionValue, ...] = ()

    @computed_field
    @property
    def human_outcome(self) -> str:
        """Human-facing result label while preserving the stable status enum."""
        if self.is_prefix:
            return "Resolved prefix"
        return {
            ResolutionStatus.EXACT: "Exact match",
            ResolutionStatus.UNSPECIFIED: "Explicitly unspecified component",
            ResolutionStatus.UNKNOWN: "Unknown supplied component",
            ResolutionStatus.AMBIGUOUS: "Ambiguous match",
            ResolutionStatus.PARTIAL: "Partial resolution",
        }[self.status]

    @computed_field
    @property
    def not_supplied_components(self) -> tuple[str, ...]:
        """Trailing DIS fields omitted by the caller, regardless of match outcome."""
        names = ("kind", "domain", "country", "category", "subcategory", "specific", "extra")
        return names[self.requested_depth :]


class EnumerationValueResolution(BaseModel):
    """Exact, ranged, ambiguous, or missing result for one table code."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    table_uid: int
    value: int
    status: EnumerationValueStatus
    table: EnumerationTableInfo | None
    tables: tuple[EnumerationTableInfo, ...]
    matches: tuple[EditionValue, ...]


class EditionExampleKind(StrEnum):
    ENUMERATION_TABLE = "enumeration_table"
    ENUMERATION_VALUE = "enumeration_value"
    ENTITY_RESOLUTION = "entity_resolution"


class EditionInspectionExample(BaseModel):
    """A reproducible query and its typed result for one edition report."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: EditionExampleKind
    query: str
    label: str
    status: str | None
    result: EnumerationTableInfo | EnumerationValueResolution | EntityResolution


class EditionSummary(BaseModel):
    """Counts and identity for the parsed standard and its inspectable values."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    title: str
    date: str
    namespace: str | None
    enumeration_tables: int
    enumeration_values: int
    enumeration_ranges: int
    entity_values: int
    entity_levels: dict[str, int]
    unclassified_entity_rows: int
    deprecated_values: int
    records_with_uuid: int
    distinct_uuid_values: int
    distinct_value_identities: int
    attached_reference_records: int
    change_request_entries: int

    @computed_field
    @property
    def value_path_records(self) -> int:
        """Enumeration and entity inspection records, including expanded paths."""
        return self.enumeration_values + self.entity_values

    @computed_field
    @property
    def repeated_uuid_occurrences(self) -> int:
        """Excess UUID-bearing value/path occurrences beyond distinct UUIDs."""
        return max(self.records_with_uuid - self.distinct_uuid_values, 0)

    @computed_field
    @property
    def repeated_identity_key_occurrences(self) -> int:
        """Excess inspected records beyond distinct library identity keys."""
        return max(self.value_path_records - self.distinct_value_identities, 0)

    @property
    def values_with_uuid(self) -> int:
        """Deprecated alias for records_with_uuid."""
        return self.records_with_uuid

    @property
    def change_request_ranges(self) -> int:
        """Deprecated alias; counts source change-request entries, not only ranges."""
        return self.change_request_entries

    @property
    def unresolved_entity_values(self) -> int:
        """Deprecated alias; this is a source-row count, not lookup failures."""
        return self.unclassified_entity_rows


class EditionSearchResults(BaseModel):
    """Edition-scoped value search with total and bounded hits."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    title: str
    date: str
    query: str
    total: int
    hits: tuple[EditionSearchHit, ...]
    limit: int | None
    offset: int

    @computed_field
    @property
    def returned(self) -> int:
        return len(self.hits)

    @computed_field
    @property
    def truncated(self) -> bool:
        return self.offset + len(self.hits) < self.total


class EditionTableResults(BaseModel):
    """Edition-scoped enumeration table listing."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    title: str
    date: str
    query: str | None
    total: int
    tables: tuple[EnumerationTableInfo, ...]
    limit: int | None

    @computed_field
    @property
    def returned(self) -> int:
        return len(self.tables)

    @computed_field
    @property
    def truncated(self) -> bool:
        return self.returned < self.total


class EditionValueResults(BaseModel):
    """Edition-scoped value listing with explicit filters and limit."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    title: str
    date: str
    kind: EditionValueKind | None
    table_uid: int | None
    status: str | None
    deprecated: bool | None
    total: int
    values: tuple[EditionValue, ...]
    limit: int | None

    @computed_field
    @property
    def returned(self) -> int:
        return len(self.values)

    @computed_field
    @property
    def truncated(self) -> bool:
        return len(self.values) < self.total


class EditionUUIDResults(BaseModel):
    """Edition-scoped matches for one source UUID."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    title: str
    date: str
    uuid: str
    total: int
    values: tuple[EditionValue, ...]
    limit: int | None

    @computed_field
    @property
    def returned(self) -> int:
        return len(self.values)

    @computed_field
    @property
    def truncated(self) -> bool:
        return self.returned < self.total


class EntityExplanation(BaseModel):
    """Source rows that define the hierarchy path for one entity code."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    entity: str
    description: str
    qualified_description: str
    path: tuple[EditionValue, ...]
    resolution: EntityResolution


class EditionDiagnostic(BaseModel):
    """One source-integrity or metadata observation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    code: str
    severity: DiagnosticSeverity
    message: str
    location: str
    table_uid: int | None = None
    table_name: str | None = None


class EditionDiagnosticGroup(BaseModel):
    """Compact aggregate for one severity, diagnostic code, and source table."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    code: str
    severity: DiagnosticSeverity
    table_uid: int | None
    table_name: str | None
    count: int
    message: str
    sample_locations: tuple[str, ...]


class EditionDiagnostics(BaseModel):
    """Edition diagnostics with aggregate counts and a bounded finding page."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    title: str
    date: str
    total: int
    counts: dict[str, int]
    severity_counts: dict[str, int]
    groups: tuple[EditionDiagnosticGroup, ...]
    findings: tuple[EditionDiagnostic, ...]
    limit: int | None
    offset: int

    @computed_field
    @property
    def returned(self) -> int:
        return len(self.findings)

    @computed_field
    @property
    def truncated(self) -> bool:
        return self.offset + self.returned < self.total


class EditionIdentity(BaseModel):
    """Source identity and integrity metadata for one parsed edition."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    title: str
    date: str
    namespace: str | None
    source_sha256: str | None
    source_evidence_registry: str | None = None
    provenance_status: ProvenanceStatus
    edition_number: int | None = None
    package_version: str


class EditionValidation(BaseModel):
    """Scope-labeled validation and provenance results for one parsed source."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    xml_well_formedness: ValidationStatus
    typed_model_validation: ValidationStatus
    xsd_validation: ValidationStatus
    bundled_integrity: ProvenanceStatus
    publisher_provenance: ValidationStatus
    typed_model_scope: str
    semantic_checks: tuple[EditionSemanticCheck, ...]


class EditionAudit(BaseModel):
    """Optional full table inventory and individual diagnostic findings."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    enumeration_tables: tuple[EnumerationTableInfo, ...]
    diagnostics: EditionDiagnostics


class EditionReport(BaseModel):
    """Concise, typed overview of one edition and its diagnostics."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    identity: EditionIdentity
    validation: EditionValidation
    summary: EditionSummary | None
    summary_error: str | None
    diagnostics: EditionDiagnostics
    identity_diagnostics: EditionIdentityDiagnostics
    examples: tuple[EditionInspectionExample, ...]
    audit: EditionAudit | None = None
    report_schema_version: Literal[1]


def _value_key(value: int | None, minimum: int | None, maximum: int | None) -> str:
    if value is not None:
        return str(value)
    if minimum is not None and maximum is not None:
        return f"{minimum}-{maximum}"
    return "none"


def _is_deprecated(source: SourceInfo) -> bool:
    return (source.get("deprecated") or "").casefold() in {"true", "1", "yes"}


def _edition_value(
    *,
    kind: EditionValueKind,
    entry: ReferenceEntry,
    path: tuple[str, ...],
    hierarchy_codes: tuple[int, ...] = (),
    table: EnumerationTable | None = None,
    applicability: str | None = None,
    reference_source: SourceInfo | None = None,
) -> EditionValue:
    source = entry.source
    return EditionValue(
        kind=kind,
        tag=entry.tag,
        value=entry.value,
        value_min=entry.value_min,
        value_max=entry.value_max,
        description=entry.description,
        table_uid=table.uid if table is not None else None,
        table_name=table.name if table is not None else None,
        applicability=applicability if applicability is not None else table.applicability if table else None,
        hierarchy_codes=hierarchy_codes,
        path=path,
        uuid=source.get("uuid"),
        status=source.get("status"),
        deprecated=_is_deprecated(source),
        footnote=source.get("footnote"),
        source=source,
        table_source=table.source if table is not None else None,
        table_annotations=table.annotations if table is not None else (),
        reference_source=reference_source,
    )


def _entry_has_value(entry: ReferenceEntry) -> bool:
    return entry.value is not None or (entry.value_min is not None and entry.value_max is not None)


def _walk_reference_entries(entries: tuple[ReferenceEntry, ...]) -> Iterator[ReferenceEntry]:
    for entry in entries:
        yield entry
        yield from _walk_reference_entries(entry.children)


def _walk_entries_with_location(
    entries: tuple[ReferenceEntry, ...], parent: str
) -> Iterator[tuple[ReferenceEntry, str]]:
    for index, entry in enumerate(entries):
        identity = (
            f"{entry.tag}[value={entry.value}]"
            if entry.value is not None
            else f"{entry.tag}[range={entry.value_min}..{entry.value_max}]"
            if entry.value_min is not None
            else f"{entry.tag}[index={index}]"
        )
        location = f"{parent}/{identity}"
        yield entry, location
        yield from _walk_entries_with_location(entry.children, location)


def _entry_numeric_values(entry: ReferenceEntry) -> Iterable[int]:
    if entry.value is not None:
        return (entry.value,)
    if entry.value_min is not None and entry.value_max is not None:
        return range(entry.value_min, entry.value_max + 1)
    return ()


def _walk_table_entries(
    table: EnumerationTable,
    entry: ReferenceEntry,
    parents: tuple[str, ...] = (),
) -> Iterator[EditionValue]:
    label = entry.description or f"<{entry.tag}>"
    path = (*parents, label)
    if _entry_has_value(entry):
        yield _edition_value(
            kind=EditionValueKind.ENUMERATION,
            entry=entry,
            path=(table.name, *path),
            table=table,
        )
    for child in entry.children:
        yield from _walk_table_entries(table, child, path)


def _walk_entity_records(
    enumerations_by_uid: Mapping[int, EnumerationTable],
    entry: ReferenceEntry,
    parents: tuple[int, ...],
    parent_path: tuple[str, ...],
) -> Iterator[
    tuple[ReferenceEntry, tuple[int, ...], tuple[str, ...], EnumerationTable | None, SourceInfo | None]
]:
    """Traverse source rows without constructing result models."""
    if entry.tag == "subcategory_xref":
        raw_uid = entry.source.get("xref")
        try:
            table = enumerations_by_uid.get(int(raw_uid)) if raw_uid is not None else None
        except ValueError:
            table = None
        if table is None:
            raise SisoRef010ValueError(
                f"Unresolved SISO enumeration cross-reference: {raw_uid!r}",
                code="unresolved_enumeration_reference",
                context={"xref": raw_uid},
            )
        for row in table.entries:
            label = row.description or f"<{row.tag}>"
            if _entry_has_value(row):
                codes = (*parents, row.value) if row.value is not None else parents
                yield row, codes, (*parent_path, label), table, entry.source
            for value in _entry_numeric_values(row):
                for child in entry.children:
                    yield from _walk_entity_records(
                        enumerations_by_uid, child, (*parents, value), (*parent_path, label)
                    )
        return
    label = entry.description or f"<{entry.tag}>"
    path = (*parent_path, label)
    if _entry_has_value(entry):
        codes = (*parents, entry.value) if entry.value is not None else parents
        yield entry, codes, path, None, None
    for value in _entry_numeric_values(entry):
        for child in entry.children:
            yield from _walk_entity_records(enumerations_by_uid, child, (*parents, value), path)


def _walk_entity_entries(
    enumerations_by_uid: Mapping[int, EnumerationTable],
    entry: ReferenceEntry,
    parents: tuple[int, ...],
    parent_path: tuple[str, ...],
) -> Iterator[EditionValue]:
    for row, codes, path, table, reference_source in _walk_entity_records(
        enumerations_by_uid, entry, parents, parent_path
    ):
        yield _edition_value(
            kind=EditionValueKind.ENTITY_TYPE,
            entry=row,
            path=path,
            hierarchy_codes=codes,
            table=table,
            applicability=table.applicability if table is not None else None,
            reference_source=reference_source,
        )


class EditionInspector:
    """Read-only queries over all enumeration and entity values in one edition."""

    def __init__(
        self,
        standard: EntityTypeStandard,
        *,
        provenance_status: ProvenanceStatus | str = ProvenanceStatus.UNVERIFIED,
        edition_number: int | None = None,
    ) -> None:
        self.standard = standard
        self.provenance_status = ProvenanceStatus(provenance_status)
        self.edition_number = edition_number

    @property
    def title(self) -> str:
        return self.standard.title

    @property
    def date(self) -> str:
        return self.standard.date.isoformat() if self.standard.date is not None else ""

    def enumeration_tables(self, query: str | None = None) -> tuple[EnumerationTableInfo, ...]:
        """List tables, optionally matching their names or applicability text."""
        if query is not None and not isinstance(cast(object, query), str):
            raise TypeError("query must be a string or None")
        normalized = query.casefold() if query is not None else None
        tables: list[EnumerationTableInfo] = []
        for table in self.standard.enumerations:
            if (
                normalized is not None
                and normalized not in " ".join((table.name, table.applicability or "")).casefold()
            ):
                continue
            tables.append(self._table_info(table))
        return tuple(tables)

    def enumeration_table_results(
        self, query: str | None = None, *, limit: int | None = None
    ) -> EditionTableResults:
        """List enumeration tables with total and bounded-result metadata."""
        _validate_limit(limit)
        tables = self.enumeration_tables(query)
        selected = tables if limit is None else tables[:limit]
        return EditionTableResults(
            title=self.title,
            date=self.date,
            query=query,
            total=len(tables),
            tables=selected,
            limit=limit,
        )

    def enumeration_table(self, uid: int) -> EnumerationTableInfo | None:
        """Return a table only when its UID uniquely identifies one source table."""
        _validate_nonnegative_integer(uid, "table UID")
        tables = self.enumeration_tables_by_uid(uid)
        return tables[0] if len(tables) == 1 else None

    def enumeration_tables_by_uid(self, uid: int) -> tuple[EnumerationTableInfo, ...]:
        """Return all definitions for a UID so duplicate identities stay visible."""
        _validate_nonnegative_integer(uid, "table UID")
        return tuple(self._table_info(row) for row in self.standard.enumerations if row.uid == uid)

    def _table_info(self, table: EnumerationTable) -> EnumerationTableInfo:
        rows = tuple(_walk_reference_entries(table.entries))
        return EnumerationTableInfo(
            uid=table.uid,
            name=table.name,
            applicability=table.applicability,
            declared_size_bits=table.size,
            entry_count=sum(_entry_has_value(entry) for entry in rows),
            range_count=sum(entry.value_min is not None for entry in rows),
            source=table.source,
            annotations=table.annotations,
        )

    @cached_property
    def _enumeration_values(self) -> tuple[EditionValue, ...]:
        values: list[EditionValue] = []
        for table in self.standard.enumerations:
            for entry in table.entries:
                values.extend(_walk_table_entries(table, entry))
        return tuple(values)

    @cached_property
    def _entity_values(self) -> tuple[EditionValue, ...]:
        values: list[EditionValue] = []
        enumerations_by_uid = {table.uid: table for table in self.standard.enumerations}
        for branch in self.standard.entity_types:
            prefix = (branch.kind, branch.domain, branch.country)
            path = (f"kind {branch.kind}", f"domain {branch.domain}", f"country {branch.country}")
            for entry in branch.categories:
                values.extend(_walk_entity_entries(enumerations_by_uid, entry, prefix, path))
        return tuple(values)

    @cached_property
    def _values(self) -> tuple[EditionValue, ...]:
        return (*self._enumeration_values, *self._entity_values)

    def entity_values(self) -> tuple[EditionValue, ...]:
        """Return source entity hierarchy rows without materializing enumeration rows."""
        return self._entity_values

    def values(
        self,
        *,
        kind: EditionValueKind | str | None = None,
        table_uid: int | None = None,
        status: str | None = None,
        deprecated: bool | None = None,
    ) -> tuple[EditionValue, ...]:
        """Return inspectable values, optionally filtered by kind and row metadata."""
        if table_uid is not None:
            _validate_nonnegative_integer(table_uid, "table UID")
        if status is not None and not isinstance(cast(object, status), str):
            raise TypeError("status must be a string or None")
        if deprecated is not None and not isinstance(cast(object, deprecated), bool):
            raise TypeError("deprecated must be a boolean or None")
        selected_kind = EditionValueKind(kind) if kind is not None else None
        source_values = (
            self._entity_values
            if selected_kind is EditionValueKind.ENTITY_TYPE
            else self._enumeration_values
            if selected_kind is EditionValueKind.ENUMERATION
            else self._values
        )
        return tuple(
            value
            for value in source_values
            if (selected_kind is None or value.kind is selected_kind)
            and (table_uid is None or value.table_uid == table_uid)
            and (status is None or value.status == status)
            and (deprecated is None or value.deprecated is deprecated)
        )

    def value_results(
        self,
        *,
        kind: EditionValueKind | str | None = None,
        table_uid: int | None = None,
        status: str | None = None,
        deprecated: bool | None = None,
        limit: int | None = 100,
    ) -> EditionValueResults:
        """Return filtered values with total, limit, and truncation information."""
        _validate_limit(limit)
        selected_kind = EditionValueKind(kind) if kind is not None else None
        values = self.values(
            kind=selected_kind,
            table_uid=table_uid,
            status=status,
            deprecated=deprecated,
        )
        selected = values if limit is None else values[:limit]
        return EditionValueResults(
            title=self.title,
            date=self.date,
            kind=selected_kind,
            table_uid=table_uid,
            status=status,
            deprecated=deprecated,
            total=len(values),
            values=selected,
            limit=limit,
        )

    def enumeration_rows(self, table_uid: int, *, value: int | None = None) -> tuple[EditionValue, ...]:
        """Return rows from one table, optionally matching a scalar or range value."""
        _validate_nonnegative_integer(table_uid, "table UID")
        if value is not None:
            _validate_nonnegative_integer(value, "enumeration value")
        rows = tuple(
            row
            for table in self.standard.enumerations
            if table.uid == table_uid
            for entry in table.entries
            for row in _walk_table_entries(table, entry)
        )
        if value is None:
            return rows
        return tuple(row for row in rows if _contains(row, value))

    def resolve_enumeration_value(self, table_uid: int, value: int) -> EnumerationValueResolution:
        """Resolve a value to its exact row or covering range in one table."""
        _validate_nonnegative_integer(table_uid, "table UID")
        _validate_nonnegative_integer(value, "enumeration value")
        tables = tuple(table for table in self.standard.enumerations if table.uid == table_uid)
        table_infos = tuple(self._table_info(table) for table in tables)
        matches = self.enumeration_rows(table_uid, value=value) if tables else ()
        if len(tables) > 1 or len(matches) > 1:
            status = EnumerationValueStatus.AMBIGUOUS
        elif not matches:
            status = EnumerationValueStatus.UNKNOWN
        elif matches[0].value is not None:
            status = EnumerationValueStatus.EXACT
        else:
            status = EnumerationValueStatus.RANGE
        return EnumerationValueResolution(
            table_uid=table_uid,
            value=value,
            status=status,
            table=table_infos[0] if table_infos else None,
            tables=table_infos,
            matches=matches,
        )

    def lookup_uuid(self, uuid: str) -> tuple[EditionValue, ...]:
        """Find every source value carrying a UUID, case-insensitively."""
        if not isinstance(cast(object, uuid), str):
            raise TypeError("uuid must be a string")
        normalized = uuid.casefold()
        return tuple(
            sorted(
                (value for value in self._values if value.uuid and value.uuid.casefold() == normalized),
                key=_stable_value_key,
            )
        )

    def uuid_results(self, uuid: str, *, limit: int | None = None) -> EditionUUIDResults:
        """Find UUID matches with an explicit result count and optional limit."""
        _validate_limit(limit)
        values = self.lookup_uuid(uuid)
        selected = values if limit is None else values[:limit]
        return EditionUUIDResults(
            title=self.title,
            date=self.date,
            uuid=uuid,
            total=len(values),
            values=selected,
            limit=limit,
        )

    def entity_path(self, entity_fields: tuple[int, ...]) -> tuple[EditionValue, ...]:
        """Return entity hierarchy records that contribute to a seven-field code."""
        if not 4 <= len(entity_fields) <= 7:
            raise ValueError("entity_fields must contain four through seven hierarchy values")
        if any(
            isinstance(value, bool) or not isinstance(cast(object, value), int) for value in entity_fields
        ):
            raise TypeError("entity_fields must contain integers, not booleans")
        if any(value < 0 for value in entity_fields):
            raise ValueError("entity_fields must contain nonnegative values")
        matches: list[EditionValue] = []
        for value in self.values(kind=EditionValueKind.ENTITY_TYPE):
            codes = value.hierarchy_codes
            if not codes or len(codes) > len(entity_fields):
                continue
            if not _codes_match(codes, entity_fields):
                continue
            is_range = value.value is None and value.value_min is not None and value.value_max is not None
            if is_range:
                if len(entity_fields) <= len(codes) or not _contains(value, entity_fields[len(codes)]):
                    continue
            if value.value is not None and value.hierarchy_codes[-1] != value.value:
                continue
            if value.value is None and not is_range:
                continue
            if value.value is not None or is_range:
                matches.append(value)
        return tuple(sorted(matches, key=_entity_depth))

    def resolve_entity(self, entity_fields: tuple[int, ...]) -> EntityResolution:
        """Resolve a full entity code or prefix without hiding unknown components."""
        if not 1 <= len(entity_fields) <= 7:
            raise ValueError("entity_fields must contain one through seven fields")
        if any(
            isinstance(value, bool) or not isinstance(cast(object, value), int) for value in entity_fields
        ):
            raise TypeError("entity_fields must contain integers, not booleans")
        if any(value < 0 for value in entity_fields):
            raise ValueError("entity_fields must contain nonnegative values")

        field_names = ("kind", "domain", "country", "category", "subcategory", "specific", "extra")
        requested_code = ".".join(map(str, entity_fields))
        matched_path: list[EditionValue] = []
        ambiguous_candidates: tuple[EditionValue, ...] = ()
        unspecified_components: list[str] = []
        unresolved_components: list[str] = []
        match_modes: list[ResolutionMatchMode] = []
        matched_depth = 0
        stop_resolution = False

        for field_index in range(min(len(entity_fields), 3)):
            selected_value = entity_fields[field_index]
            component = field_names[field_index]
            if field_index == 0:
                known = self._has_enumeration_value("Entity Kind", selected_value) or any(
                    branch.kind == selected_value for branch in self.standard.entity_types
                )
            elif field_index == 1:
                known = any(
                    branch.kind == entity_fields[0] and branch.domain == selected_value
                    for branch in self.standard.entity_types
                )
            else:
                known = self._has_enumeration_value("Country", selected_value) or any(
                    branch.kind == entity_fields[0]
                    and branch.domain == entity_fields[1]
                    and branch.country == selected_value
                    for branch in self.standard.entity_types
                )
            if selected_value == 0 and not known:
                unspecified_components.extend(
                    field_names[index]
                    for index in range(field_index, len(entity_fields))
                    if entity_fields[index] == 0
                )
                unresolved_components.extend(
                    field_names[index]
                    for index in range(field_index + 1, len(entity_fields))
                    if entity_fields[index] != 0
                )
                stop_resolution = True
                break
            if not known:
                unresolved_components.append(component)
                unresolved_components.extend(
                    field_names[index]
                    for index in range(field_index + 1, len(entity_fields))
                    if entity_fields[index] != 0
                )
                break
            matched_depth = field_index + 1

        records: tuple[EditionValue, ...] = (
            self.entity_path(entity_fields)
            if len(entity_fields) >= 4 and not unresolved_components and not stop_resolution
            else ()
        )
        country_value = entity_fields[2] if len(entity_fields) > 2 else None

        for depth in range(4, len(entity_fields) + 1) if not stop_resolution else ():
            if unresolved_components:
                break
            field_index = depth - 1
            selected_value = entity_fields[field_index]
            candidates: tuple[EditionValue, ...] = tuple(
                row for row in records if _entity_depth(row) == depth
            )
            if not candidates:
                if selected_value == 0:
                    unspecified_components.extend(
                        field_names[index]
                        for index in range(field_index, len(entity_fields))
                        if entity_fields[index] == 0
                    )
                    unresolved_components.extend(
                        field_names[index]
                        for index in range(field_index + 1, len(entity_fields))
                        if entity_fields[index] != 0
                    )
                    break
                unresolved_components.extend(
                    field_names[index]
                    for index in range(field_index, len(entity_fields))
                    if entity_fields[index] != 0
                )
                break

            exact_country: tuple[EditionValue, ...] = tuple(
                row
                for row in candidates
                if country_value is not None
                and len(row.hierarchy_codes) > 2
                and row.hierarchy_codes[2] == country_value
            )
            generic_country: tuple[EditionValue, ...] = tuple(
                row for row in candidates if len(row.hierarchy_codes) > 2 and row.hierarchy_codes[2] == 0
            )
            preferred: tuple[EditionValue, ...] = exact_country or generic_country or candidates
            if not preferred:
                break
            if len(preferred) > 1:
                ambiguous_candidates = preferred
                unresolved_components.extend(
                    field_names[index]
                    for index in range(field_index, len(entity_fields))
                    if entity_fields[index] != 0
                )
                break

            matched = next(iter(preferred), None)
            if matched is None:
                break
            matched_path.append(matched)
            matched_depth = depth
            special_mode = False
            if (
                len(matched.hierarchy_codes) > 2
                and matched.hierarchy_codes[2] == 0
                and country_value is not None
                and country_value != 0
            ):
                match_modes.append(ResolutionMatchMode.GENERIC_COUNTRY)
                special_mode = True
            if matched.value_min is not None:
                match_modes.append(ResolutionMatchMode.RANGE)
                special_mode = True
            if matched.reference_source is not None:
                match_modes.append(ResolutionMatchMode.XREF)
                special_mode = True
            if not special_mode:
                match_modes.append(ResolutionMatchMode.DIRECT)

        if ambiguous_candidates:
            status = ResolutionStatus.AMBIGUOUS
        elif unresolved_components:
            status = ResolutionStatus.UNKNOWN
        elif unspecified_components:
            status = ResolutionStatus.UNSPECIFIED
        elif len(entity_fields) < 7:
            status = ResolutionStatus.PARTIAL
        else:
            status = ResolutionStatus.EXACT if len(entity_fields) == 7 else ResolutionStatus.PARTIAL

        return EntityResolution(
            code=requested_code,
            status=status,
            requested_depth=len(entity_fields),
            matched_depth=matched_depth,
            is_prefix=(
                len(entity_fields) < 7
                and status is ResolutionStatus.PARTIAL
                and matched_depth == len(entity_fields)
            ),
            resolution_description=_resolution_description(
                status,
                requested_depth=len(entity_fields),
                matched_depth=matched_depth,
                unspecified=tuple(dict.fromkeys(unspecified_components)),
                unresolved=tuple(dict.fromkeys(unresolved_components)),
                ambiguous_count=len(ambiguous_candidates),
            ),
            matched_path=tuple(matched_path),
            match_modes=tuple(dict.fromkeys(match_modes)),
            unspecified_components=tuple(unspecified_components),
            unresolved_components=tuple(unresolved_components),
            ambiguous_candidates=ambiguous_candidates,
        )

    def _has_enumeration_value(self, name: str, value: int) -> bool:
        return any(
            entry.value == value
            or (
                entry.value_min is not None
                and entry.value_max is not None
                and entry.value_min <= value <= entry.value_max
            )
            for table in self.standard.enumerations
            if table.name == name
            for entry in _walk_reference_entries(table.entries)
        )

    def search(self, query: str, *, limit: int | None = 100, offset: int = 0) -> EditionSearchResults:
        """Search in stable order; see ``matched_fields`` on each result."""
        return self.search_page(query, limit=limit, offset=offset)

    def search_page(self, query: str, *, limit: int | None = 100, offset: int = 0) -> EditionSearchResults:
        """Search descriptions, identifiers, and metadata with pagination."""
        if not isinstance(cast(object, query), str):
            raise TypeError("query must be a string")
        _validate_limit(limit)
        _validate_nonnegative_integer(offset, "offset")
        normalized = query.casefold()
        matching_rows: list[tuple[EditionValue, tuple[str, ...]]] = []
        for value in self._values:
            fields = _search_fields(value, normalized)
            if fields:
                matching_rows.append((value, fields))
        matches = tuple(
            sorted(
                matching_rows,
                key=lambda item: _stable_value_key(item[0]),
            )
        )
        selected = matches[offset:] if limit is None else matches[offset : offset + limit]
        return EditionSearchResults(
            title=self.title,
            date=self.date,
            query=query,
            total=len(matches),
            hits=tuple(
                EditionSearchHit(**value.model_dump(), matched_fields=fields) for value, fields in selected
            ),
            limit=limit,
            offset=offset,
        )

    def diagnostics(
        self,
        *,
        limit: int | None = 100,
        offset: int = 0,
        code: str | None = None,
        table_uid: int | None = None,
        severity: DiagnosticSeverity | str | None = None,
    ) -> EditionDiagnostics:
        """Report and group source observations, with optional individual findings."""
        _validate_limit(limit)
        _validate_nonnegative_integer(offset, "offset")
        if code is not None and not isinstance(cast(object, code), str):
            raise TypeError("code must be a string or None")
        if table_uid is not None:
            _validate_nonnegative_integer(table_uid, "table UID")
        selected_severity = DiagnosticSeverity(severity) if severity is not None else None
        findings: list[EditionDiagnostic] = []

        def add(
            code_value: str,
            severity_value: DiagnosticSeverity,
            message: str,
            location: str,
            *,
            source_table_uid: int | None = None,
            source_table_name: str | None = None,
        ) -> None:
            findings.append(
                EditionDiagnostic(
                    code=code_value,
                    severity=severity_value,
                    message=message,
                    location=location,
                    table_uid=source_table_uid,
                    table_name=source_table_name,
                )
            )

        tables_by_uid: dict[int, list[EnumerationTable]] = {}
        for table in self.standard.enumerations:
            tables_by_uid.setdefault(table.uid, []).append(table)
        for uid, tables in sorted(tables_by_uid.items()):
            if len(tables) > 1:
                names = tuple(dict.fromkeys(table.name for table in tables))
                add(
                    "duplicate_table_uid",
                    DiagnosticSeverity.ERROR,
                    f"Enumeration UID {uid} is defined {len(tables)} times.",
                    f"enumeration[uid={uid}]",
                    source_table_uid=uid,
                    source_table_name=" / ".join(names),
                )

        source_locations: dict[str, list[SourceOccurrence]] = {}
        source_uid_locations: dict[str, list[SourceOccurrence]] = {}
        row_records: list[tuple[ReferenceEntry, str, int | None, str | None]] = []
        enum_uids = set(tables_by_uid)
        for table in self.standard.enumerations:
            table_location = f"enumeration[uid={table.uid}] {table.name!r}"
            context = (table.uid, table.name)
            _collect_source_uuid(source_locations, table.source, table_location, *context)
            _collect_source_uid(source_uid_locations, table.source, table_location, *context)
            for index, annotation in enumerate(table.annotations):
                annotation_location = f"{table_location}/annotation[{index}]"
                _collect_source_uuid(source_locations, annotation.source, annotation_location, *context)
                _collect_source_uid(source_uid_locations, annotation.source, annotation_location, *context)
            for entry, location in _walk_entries_with_location(table.entries, table_location):
                row_records.append((entry, location, *context))
                _collect_source_uuid(source_locations, entry.source, location, *context)
                _collect_source_uid(source_uid_locations, entry.source, location, *context)
                if entry.tag == "subcategory_xref":
                    raw_uid = entry.source.get("xref")
                    try:
                        resolved_uid = int(raw_uid) if raw_uid is not None else None
                    except ValueError:
                        resolved_uid = None
                    if resolved_uid not in enum_uids:
                        add(
                            "unresolved_enumeration_reference",
                            DiagnosticSeverity.ERROR,
                            f"Entity subcategory references missing enumeration UID {raw_uid!r}.",
                            location,
                            source_table_uid=table.uid,
                            source_table_name=table.name,
                        )
            _check_overlaps(table.entries, table_location, add, table_uid=table.uid, table_name=table.name)

        if self.standard.entity_table is not None:
            _collect_source_uuid(source_locations, self.standard.entity_table, "entity_table")
            _collect_source_uid(source_uid_locations, self.standard.entity_table, "entity_table")
        for branch in self.standard.entity_types:
            branch_location = f"entity[kind={branch.kind},domain={branch.domain},country={branch.country}]"
            _collect_source_uuid(source_locations, branch.source, branch_location)
            _collect_source_uid(source_uid_locations, branch.source, branch_location)
            for entry, location in _walk_entries_with_location(branch.categories, branch_location):
                row_records.append((entry, location, None, None))
                _collect_source_uuid(source_locations, entry.source, location)
                _collect_source_uid(source_uid_locations, entry.source, location)
                if entry.tag == "subcategory_xref":
                    raw_uid = entry.source.get("xref")
                    try:
                        resolved_uid = int(raw_uid) if raw_uid is not None else None
                    except ValueError:
                        resolved_uid = None
                    if resolved_uid not in enum_uids:
                        add(
                            "unresolved_enumeration_reference",
                            DiagnosticSeverity.ERROR,
                            f"Entity subcategory references missing enumeration UID {raw_uid!r}.",
                            location,
                        )
            _check_overlaps(branch.categories, branch_location, add)

        def common_table_context(
            occurrences: list[SourceOccurrence],
        ) -> tuple[int | None, str | None]:
            contexts = {(uid, name) for _, uid, name in occurrences}
            table_uids = {uid for uid, _ in contexts}
            if len(table_uids) == 1 and None not in table_uids:
                uid = next(iter(table_uids))
                names = sorted({name for _, name in contexts if name is not None})
                return uid, " / ".join(names) if names else None
            return next(iter(contexts)) if len(contexts) == 1 else (None, None)

        for uuid, occurrences in sorted(source_locations.items()):
            if len(occurrences) > 1:
                table_context = common_table_context(occurrences)
                add(
                    "duplicate_uuid",
                    DiagnosticSeverity.WARNING,
                    f"UUID {uuid!r} appears on {len(occurrences)} source records.",
                    "; ".join(location for location, _, _ in occurrences),
                    source_table_uid=table_context[0],
                    source_table_name=table_context[1],
                )
        for uid, occurrences in sorted(source_uid_locations.items()):
            if len(occurrences) > 1:
                table_context = common_table_context(occurrences)
                add(
                    "duplicate_source_uid",
                    DiagnosticSeverity.WARNING,
                    f"Source UID {uid!r} appears on {len(occurrences)} records.",
                    "; ".join(location for location, _, _ in occurrences),
                    source_table_uid=table_context[0],
                    source_table_name=table_context[1],
                )

        for entry, location, source_table_uid, source_table_name in row_records:
            if not _entry_has_value(entry):
                continue
            if not entry.description:
                add(
                    "missing_description",
                    DiagnosticSeverity.INFO,
                    "Value row has no description attribute; this may be intentionally unspecified.",
                    location,
                    source_table_uid=source_table_uid,
                    source_table_name=source_table_name,
                )
            if not entry.source.get("uuid"):
                add(
                    "missing_uuid",
                    DiagnosticSeverity.INFO,
                    "Value row has no UUID attribute.",
                    location,
                    source_table_uid=source_table_uid,
                    source_table_name=source_table_name,
                )

        if code is not None:
            findings = [finding for finding in findings if finding.code == code]
        if table_uid is not None:
            findings = [finding for finding in findings if finding.table_uid == table_uid]
        if selected_severity is not None:
            findings = [finding for finding in findings if finding.severity is selected_severity]

        severity_order = {
            DiagnosticSeverity.ERROR: 0,
            DiagnosticSeverity.WARNING: 1,
            DiagnosticSeverity.INFO: 2,
        }
        findings.sort(
            key=lambda item: (
                severity_order[item.severity],
                item.code,
                item.table_uid if item.table_uid is not None else -1,
                item.table_name or "",
                item.location,
                item.message,
            )
        )
        counts = dict(sorted(Counter(finding.code for finding in findings).items()))
        severity_counts = dict(sorted(Counter(finding.severity.value for finding in findings).items()))
        grouped: dict[tuple[DiagnosticSeverity, str, int | None, str | None], list[EditionDiagnostic]] = {}
        for finding in findings:
            key = (finding.severity, finding.code, finding.table_uid, finding.table_name)
            grouped.setdefault(key, []).append(finding)
        groups = tuple(
            EditionDiagnosticGroup(
                code=group_code,
                severity=group_severity,
                table_uid=group_table_uid,
                table_name=group_table_name,
                count=len(group_findings),
                message=group_findings[0].message,
                sample_locations=tuple(finding.location for finding in group_findings[:3]),
            )
            for (group_severity, group_code, group_table_uid, group_table_name), group_findings in sorted(
                grouped.items(),
                key=lambda item: (
                    severity_order[item[0][0]],
                    item[0][1],
                    item[0][2] if item[0][2] is not None else -1,
                    item[0][3] or "",
                ),
            )
        )
        page = findings[offset:] if limit is None else findings[offset : offset + limit]
        return EditionDiagnostics(
            title=self.title,
            date=self.date,
            total=len(findings),
            counts=counts,
            severity_counts=severity_counts,
            groups=groups,
            findings=tuple(page),
            limit=limit,
            offset=offset,
        )

    def identity_diagnostics(self) -> EditionIdentityDiagnostics:
        """Classify repeated UUIDs and value identities by their source evidence."""
        try:
            values = self._values
        except SisoRef010ValueError as error:
            return EditionIdentityDiagnostics(
                checked=False,
                error=str(error),
                inspected_records=None,
                records_with_uuid=None,
                distinct_uuid_values=None,
                repeated_uuid_occurrences=None,
                repeated_uuid_groups=None,
                distinct_value_identity_keys=None,
                repeated_identity_key_occurrences=None,
                source_record_reuse_groups=None,
                duplicate_source_identifier_groups=None,
                conflicting_source_record_groups=None,
                groups=(),
            )

        uuid_groups: dict[str, list[EditionValue]] = {}
        identity_groups: dict[str, list[EditionValue]] = {}
        for value in values:
            identity_groups.setdefault(value.identity, []).append(value)
            if value.uuid:
                uuid_groups.setdefault(value.uuid.casefold(), []).append(value)

        groups: list[EditionIdentityGroup] = []
        for uuid, rows in sorted(uuid_groups.items()):
            if len(rows) < 2:
                continue
            groups.append(_identity_group(f"uuid:{uuid}", rows, uuid=uuid))

        # UUID identities are already covered above. This second pass catches
        # collisions in the library's path/value fallback key for UUID-less rows.
        for identity, rows in sorted(identity_groups.items()):
            if len(rows) < 2 or any(row.uuid for row in rows):
                continue
            groups.append(_identity_group(f"identity:{identity}", rows, uuid=None))

        groups.sort(key=lambda group: group.key)
        records_with_uuid = sum(bool(value.uuid) for value in values)
        distinct_uuids = len(uuid_groups)
        repeated_uuid_occurrences = max(records_with_uuid - distinct_uuids, 0)
        repeated_identity_occurrences = sum(max(len(rows) - 1, 0) for rows in identity_groups.values())
        return EditionIdentityDiagnostics(
            checked=True,
            error=None,
            inspected_records=len(values),
            records_with_uuid=records_with_uuid,
            distinct_uuid_values=distinct_uuids,
            repeated_uuid_occurrences=repeated_uuid_occurrences,
            repeated_uuid_groups=sum(len(rows) > 1 for rows in uuid_groups.values()),
            distinct_value_identity_keys=len(identity_groups),
            repeated_identity_key_occurrences=repeated_identity_occurrences,
            source_record_reuse_groups=sum(
                group.classification is IdentityClassification.SOURCE_RECORD_REUSE for group in groups
            ),
            duplicate_source_identifier_groups=sum(
                group.uuid is not None
                and group.classification
                in {
                    IdentityClassification.DUPLICATE_SOURCE_IDENTIFIER,
                    IdentityClassification.CONFLICTING_SOURCE_RECORDS,
                }
                for group in groups
            ),
            conflicting_source_record_groups=sum(
                group.classification is IdentityClassification.CONFLICTING_SOURCE_RECORDS for group in groups
            ),
            groups=tuple(groups),
        )

    def report(self, *, audit: bool = False) -> EditionReport:
        """Build a presentation-independent report, optionally including full audit rows."""
        try:
            summary = self.summary()
            summary_error = None
        except SisoRef010ValueError as error:
            summary = None
            summary_error = str(error)
        diagnostics = self.diagnostics(limit=0)
        identity_diagnostics = self.identity_diagnostics()
        semantic_checks = _semantic_checks(diagnostics, identity_diagnostics)
        audit_data = (
            EditionAudit(
                enumeration_tables=self.enumeration_tables(),
                diagnostics=self.diagnostics(limit=None),
            )
            if audit
            else None
        )
        return EditionReport(
            identity=EditionIdentity(
                title=self.title,
                date=self.date,
                namespace=self.standard.namespace,
                source_sha256=self.standard.source_sha256,
                source_evidence_registry=(
                    "data/standards/PROVENANCE.json"
                    if self.provenance_status is ProvenanceStatus.BUNDLED_CHECKSUM_VERIFIED
                    else None
                ),
                provenance_status=self.provenance_status,
                edition_number=self.edition_number,
                package_version=__version__,
            ),
            validation=EditionValidation(
                xml_well_formedness=(
                    ValidationStatus.PASSED
                    if self.standard.xml_parse_succeeded is True
                    else ValidationStatus.NOT_RUN
                ),
                typed_model_validation=ValidationStatus.PASSED,
                xsd_validation=ValidationStatus.NOT_RUN,
                bundled_integrity=ProvenanceStatus(self.provenance_status),
                publisher_provenance=ValidationStatus.UNVERIFIED,
                typed_model_scope=(
                    "Pydantic field parsing and declared bounds; valid scalar/range shape; "
                    "ordered change-request ranges. Source-reference, identifier, and overlap "
                    "checks are reported separately as semantic checks."
                ),
                semantic_checks=semantic_checks,
            ),
            summary=summary,
            summary_error=summary_error,
            diagnostics=diagnostics,
            identity_diagnostics=identity_diagnostics,
            examples=self.inspection_examples(),
            audit=audit_data,
            report_schema_version=1,
        )

    def inspection_examples(self) -> tuple[EditionInspectionExample, ...]:
        """Select deterministic, edition-backed inspection examples."""
        examples: list[EditionInspectionExample] = []
        tables = self.enumeration_tables()
        unique_tables = tuple(
            table for table in tables if len(self.enumeration_tables_by_uid(table.uid)) == 1
        )
        annotated = next((table for table in unique_tables if table.annotations), None)
        selected_table = annotated or (unique_tables[0] if unique_tables else None)
        if selected_table is not None:
            examples.append(
                EditionInspectionExample(
                    kind=EditionExampleKind.ENUMERATION_TABLE,
                    query=str(selected_table.uid),
                    label=selected_table.name,
                    status=None,
                    result=selected_table,
                )
            )

        range_example: tuple[int, int] | None = None
        for candidate_table in sorted(self.standard.enumerations, key=lambda item: (item.uid, item.name)):
            if len(self.enumeration_tables_by_uid(candidate_table.uid)) != 1:
                continue
            candidate_rows = sorted(
                (
                    row
                    for entry in candidate_table.entries
                    for row in _walk_table_entries(candidate_table, entry)
                    if row.value_min is not None and row.value_max is not None
                ),
                key=_stable_value_key,
            )
            if candidate_rows:
                row = candidate_rows[0]
                if row.value_min is not None and row.value_max is not None:
                    range_example = (
                        candidate_table.uid,
                        row.value_min + (row.value_max - row.value_min) // 2,
                    )
                    break
        if range_example is not None:
            range_resolution = self.resolve_enumeration_value(*range_example)
        else:
            range_resolution = None
        if range_resolution is not None and range_resolution.matches:
            value_row = range_resolution.matches[0]
            examples.append(
                EditionInspectionExample(
                    kind=EditionExampleKind.ENUMERATION_VALUE,
                    query=f"{range_resolution.table_uid}, {range_resolution.value}",
                    label=value_row.description or "<no description>",
                    status=range_resolution.status.value,
                    result=range_resolution,
                )
            )

        try:
            entity_values = self.values(kind=EditionValueKind.ENTITY_TYPE)
        except SisoRef010ValueError:
            entity_values = ()
        entity_hit = next(
            (
                value
                for value in sorted(entity_values, key=_stable_value_key)
                if value.tag == "category" and len(value.hierarchy_codes) == 4 and value.value is not None
            ),
            None,
        )
        if entity_hit is None:
            entity_hit = next(
                (
                    value
                    for value in sorted(entity_values, key=_stable_value_key)
                    if len(value.hierarchy_codes) in {4, 5, 6} and value.value is not None
                ),
                None,
            )
        if entity_hit is not None:
            entity_fields = entity_hit.hierarchy_codes[:7]
            resolution = self.resolve_entity(entity_fields)
            label = (
                " / ".join(row.description for row in resolution.matched_path if row.description)
                or "<no matching source description>"
            )
            examples.append(
                EditionInspectionExample(
                    kind=EditionExampleKind.ENTITY_RESOLUTION,
                    query=resolution.code,
                    label=label,
                    status=resolution.status.value,
                    result=resolution,
                )
            )
        return tuple(examples)

    def summary(self) -> EditionSummary:
        """Return counts for the edition's tables and inspectable values."""
        values = self._values
        enumeration_values = tuple(value for value in values if value.kind is EditionValueKind.ENUMERATION)
        entity_values = tuple(value for value in values if value.kind is EditionValueKind.ENTITY_TYPE)
        level_names = {4: "categories", 5: "subcategories", 6: "specifics", 7: "extras"}
        tag_names = {
            "category": "categories",
            "category_range": "categories",
            "subcategory": "subcategories",
            "subcategory_range": "subcategories",
            "specific": "specifics",
            "specific_range": "specifics",
            "extra": "extras",
            "extra_range": "extras",
        }
        entity_level = tuple(
            tag_names.get(value.tag, level_names.get(_entity_depth(value), "unresolved"))
            for value in entity_values
        )
        level_counts = Counter(entity_level)
        sources_with_change_requests = {
            id(value.source): value.source for value in values if value.source.change_requests
        }
        return EditionSummary(
            title=self.title,
            date=self.date,
            namespace=self.standard.namespace,
            enumeration_tables=len(self.standard.enumerations),
            enumeration_values=len(enumeration_values),
            enumeration_ranges=sum(value.value_min is not None for value in enumeration_values),
            entity_values=len(entity_values),
            entity_levels={
                name: level_counts.get(name, 0)
                for name in ("categories", "subcategories", "specifics", "extras")
            },
            unclassified_entity_rows=level_counts.get("unresolved", 0),
            deprecated_values=sum(value.deprecated for value in values),
            records_with_uuid=sum(bool(value.uuid) for value in values),
            distinct_uuid_values=len({value.uuid.casefold() for value in values if value.uuid}),
            distinct_value_identities=len({value.identity for value in values}),
            attached_reference_records=sum(value.reference_source is not None for value in values),
            change_request_entries=sum(
                len(source.change_requests) for source in sources_with_change_requests.values()
            ),
        )


@dataclass(frozen=True, slots=True)
class _SourceRecordSignature:
    """Comparable, context-free fields from one parsed source row."""

    tag: str
    value: int | None
    value_min: int | None
    value_max: int | None
    description: str | None
    table_uid: int | None
    applicability: str | None
    status: str | None
    deprecated: bool
    footnote: str | None
    attributes: tuple[tuple[str, str], ...]
    metadata: tuple[tuple[str, str], ...]
    change_requests: tuple[tuple[int, int], ...]

    def differing_fields(self, other: _SourceRecordSignature) -> tuple[str, ...]:
        """Return the semantic field names whose values differ."""
        fields: list[str] = []
        if self.tag != other.tag:
            fields.append("tag")
        if self.value != other.value:
            fields.append("value")
        if self.value_min != other.value_min:
            fields.append("value_min")
        if self.value_max != other.value_max:
            fields.append("value_max")
        if self.description != other.description:
            fields.append("description")
        if self.table_uid != other.table_uid:
            fields.append("table_uid")
        if self.applicability != other.applicability:
            fields.append("applicability")
        if self.status != other.status:
            fields.append("status")
        if self.deprecated != other.deprecated:
            fields.append("deprecated")
        if self.footnote != other.footnote:
            fields.append("footnote")
        if self.attributes != other.attributes:
            fields.append("attributes")
        if self.metadata != other.metadata:
            fields.append("metadata")
        if self.change_requests != other.change_requests:
            fields.append("change_requests")
        return tuple(fields)


def _source_record_signature(value: EditionValue) -> _SourceRecordSignature:
    """Fields that describe a source row, excluding its expanded hierarchy context."""
    return _SourceRecordSignature(
        tag=value.tag,
        value=value.value,
        value_min=value.value_min,
        value_max=value.value_max,
        description=value.description,
        table_uid=value.table_uid,
        applicability=value.applicability,
        status=value.status,
        deprecated=value.deprecated,
        footnote=value.footnote,
        attributes=tuple(sorted((key, item) for key, item in value.source.attributes if key != "uuid")),
        metadata=value.source.metadata,
        change_requests=tuple((request.minimum, request.maximum) for request in value.source.change_requests),
    )


def _identity_group(
    key: str,
    rows: list[EditionValue],
    *,
    uuid: str | None,
) -> EditionIdentityGroup:
    by_source: dict[int, list[EditionValue]] = {}
    for row in rows:
        by_source.setdefault(id(row.source), []).append(row)
    signatures: dict[int, _SourceRecordSignature] = {
        source_id: _source_record_signature(source_rows[0]) for source_id, source_rows in by_source.items()
    }
    first_signature = next(iter(signatures.values()))
    conflict_fields = tuple(
        sorted(
            {
                field
                for signature in signatures.values()
                for field in first_signature.differing_fields(signature)
            }
        )
    )
    if len(by_source) == 1:
        classification = IdentityClassification.SOURCE_RECORD_REUSE
        message = "One XML source row is represented by multiple inspection records or hierarchy contexts."
    elif conflict_fields:
        classification = IdentityClassification.CONFLICTING_SOURCE_RECORDS
        message = (
            "Distinct source rows sharing this identifier have differing semantic fields."
            if uuid is not None
            else "Distinct source rows sharing this library key have differing semantic fields."
        )
    elif uuid is None:
        classification = IdentityClassification.LIBRARY_IDENTITY_COLLISION
        message = "Multiple XML source rows share one UUID-less library identity key."
    else:
        classification = IdentityClassification.DUPLICATE_SOURCE_IDENTIFIER
        message = "The same UUID is assigned to multiple distinct source rows with equivalent fields."

    identity_counts = Counter(row.identity for row in rows)
    contexts = tuple(sorted({_identity_context(row) for row in rows}))[:3]
    return EditionIdentityGroup(
        key=key,
        uuid=uuid,
        identity_keys=tuple(sorted(identity_counts)),
        classification=classification,
        occurrences=len(rows),
        repeated_uuid_occurrences=max(len(rows) - 1, 0) if uuid is not None else 0,
        repeated_identity_key_occurrences=sum(max(count - 1, 0) for count in identity_counts.values()),
        source_record_count=len(by_source),
        reference_context_occurrences=sum(row.reference_source is not None for row in rows),
        conflict_fields=conflict_fields,
        sample_contexts=contexts,
        message=message,
    )


def _identity_context(value: EditionValue) -> str:
    label = value.description or f"<{value.tag}>"
    if value.kind is EditionValueKind.ENUMERATION:
        return f"enumeration UID {value.table_uid} {value.table_name}: {label}"
    code = ".".join(map(str, value.hierarchy_codes))
    return f"entity {code}: {label}"


def _semantic_checks(
    diagnostics: EditionDiagnostics,
    identity: EditionIdentityDiagnostics,
) -> tuple[EditionSemanticCheck, ...]:
    descriptions = {
        "duplicate_table_uid": "Enumeration table UIDs were checked for duplicate definitions.",
        "unresolved_enumeration_reference": (
            "Entity subcategory cross-references were checked against table UIDs."
        ),
        "duplicate_uuid": "Source XML records were checked for repeated UUID attributes.",
        "duplicate_source_uid": "Source XML records were checked for repeated UID attributes.",
        "overlapping_values": "Scalar and ranged values were checked for overlaps within their source scope.",
        "possible_value_alias": (
            "Repeated scalar values were checked for reciprocal alias labels; candidates remain ambiguous."
        ),
        "missing_description": "Value rows were checked for absent descriptions; absence may be intentional.",
        "missing_uuid": "Value rows were checked for absent UUID attributes.",
    }
    checks = [
        EditionSemanticCheck(
            code=code,
            status=SemanticCheckStatus.CHECKED,
            finding_count=diagnostics.counts.get(code, 0),
            description=description,
        )
        for code, description in descriptions.items()
    ]
    identity_checks = (
        (
            "source_record_reuse",
            "Repeated inspection identities were checked for reuse of one parsed XML source row.",
            identity.source_record_reuse_groups,
        ),
        (
            "duplicate_source_identifier",
            "Repeated UUIDs were checked for assignment to multiple distinct XML source rows.",
            identity.duplicate_source_identifier_groups,
        ),
        (
            "conflicting_source_records",
            "Repeated identifiers were checked for differences in semantic source-row fields.",
            identity.conflicting_source_record_groups,
        ),
    )
    checks.extend(
        EditionSemanticCheck(
            code=code,
            status=SemanticCheckStatus.CHECKED if identity.checked else SemanticCheckStatus.NOT_RUN,
            finding_count=count if identity.checked else None,
            description=description,
        )
        for code, description, count in identity_checks
    )
    return tuple(checks)


def _contains(value: EditionValue, candidate: int) -> bool:
    if value.value is not None:
        return value.value == candidate
    return (
        value.value_min is not None
        and value.value_max is not None
        and value.value_min <= candidate <= value.value_max
    )


def _resolution_description(
    status: ResolutionStatus,
    *,
    requested_depth: int,
    matched_depth: int,
    unspecified: tuple[str, ...],
    unresolved: tuple[str, ...],
    ambiguous_count: int,
) -> str:
    if status is ResolutionStatus.EXACT:
        return "All seven requested components matched source records."
    if status is ResolutionStatus.PARTIAL:
        return (
            f"The supplied {requested_depth}-component prefix matched a known entity path; "
            "the caller did not request the remaining components."
        )
    if status is ResolutionStatus.UNSPECIFIED:
        return (
            f"Matched {matched_depth} source components; zero-filled components "
            f"({', '.join(unspecified)}) are unspecified in this edition."
        )
    if status is ResolutionStatus.AMBIGUOUS:
        return (
            f"Found {ambiguous_count} source candidates at matched depth {matched_depth}; "
            "no single interpretation was selected."
        )
    unresolved_text = ", ".join(unresolved) or "an unknown component"
    return (
        f"Matched {matched_depth} of {requested_depth} requested components; "
        f"unresolved component(s) {unresolved_text} have no source match in this edition."
    )


def _validate_limit(limit: int | None) -> None:
    if isinstance(limit, bool) or (
        limit is not None and (not isinstance(cast(object, limit), int) or limit < 0)
    ):
        raise ValueError("limit must be a nonnegative integer or None")


def _validate_nonnegative_integer(value: int, label: str) -> None:
    if isinstance(value, bool) or not isinstance(cast(object, value), int):
        raise TypeError(f"{label} must be an integer")
    if value < 0:
        raise ValueError(f"{label} must be nonnegative")


def _collect_source_uuid(
    locations: dict[str, list[tuple[str, int | None, str | None]]],
    source: SourceInfo,
    location: str,
    table_uid: int | None = None,
    table_name: str | None = None,
) -> None:
    uuid = source.get("uuid")
    if uuid:
        locations.setdefault(uuid.casefold(), []).append((location, table_uid, table_name))


def _collect_source_uid(
    locations: dict[str, list[tuple[str, int | None, str | None]]],
    source: SourceInfo,
    location: str,
    table_uid: int | None = None,
    table_name: str | None = None,
) -> None:
    uid = source.get("uid")
    if uid:
        locations.setdefault(uid.casefold(), []).append((location, table_uid, table_name))


def _check_overlaps(
    entries: tuple[ReferenceEntry, ...],
    parent: str,
    add: Callable[..., None],
    *,
    table_uid: int | None = None,
    table_name: str | None = None,
) -> None:
    intervals: list[tuple[int, int, str, str, str | None, bool]] = []
    for index, entry in enumerate(entries):
        identity = (
            f"{entry.tag}[value={entry.value}]"
            if entry.value is not None
            else f"{entry.tag}[range={entry.value_min}..{entry.value_max}]"
            if entry.value_min is not None
            else f"{entry.tag}[index={index}]"
        )
        location = f"{parent}/{identity}"
        if entry.value is not None:
            intervals.append(
                (
                    entry.value,
                    entry.value,
                    location,
                    entry.description or entry.tag,
                    entry.source.get("uuid"),
                    True,
                )
            )
        elif entry.value_min is not None and entry.value_max is not None:
            intervals.append(
                (
                    entry.value_min,
                    entry.value_max,
                    location,
                    entry.description or entry.tag,
                    entry.source.get("uuid"),
                    False,
                )
            )
        _check_overlaps(
            entry.children,
            location,
            add,
            table_uid=table_uid,
            table_name=table_name,
        )
    intervals.sort()
    for index, left in enumerate(intervals):
        for right in intervals[index + 1 :]:
            if right[0] > left[1]:
                break
            if right[0] <= left[1]:
                add(
                    "overlapping_values",
                    DiagnosticSeverity.WARNING,
                    f"{left[3]!r} ({left[0]}..{left[1]}) overlaps {right[3]!r} ({right[0]}..{right[1]}).",
                    f"{left[2]} <> {right[2]}",
                    source_table_uid=table_uid,
                    source_table_name=table_name,
                )
                if (
                    left[5]
                    and right[5]
                    and left[0] == left[1] == right[0] == right[1]
                    and left[4] is not None
                    and right[4] is not None
                    and left[4].casefold() != right[4].casefold()
                    and _has_reciprocal_alias_labels(left[3], right[3])
                ):
                    add(
                        "possible_value_alias",
                        DiagnosticSeverity.INFO,
                        f"Scalar code {left[0]} has reciprocal alias descriptions across distinct UUIDs "
                        f"{left[4]!r} and {right[4]!r}: {left[3]!r} / {right[3]!r}. This is a review hint; "
                        "the lookup remains ambiguous.",
                        f"{left[2]} <> {right[2]}",
                        source_table_uid=table_uid,
                        source_table_name=table_name,
                    )


def _alias_description(description: str) -> tuple[str, str] | None:
    match = re.fullmatch(r"\s*(.*?)\s*\(\s*aka\s+([^()]*)\)\s*", description, flags=re.IGNORECASE)
    if match is None:
        return None
    primary = " ".join(re.findall(r"[a-z0-9]+", match.group(1).casefold()))
    alias = " ".join(re.findall(r"[a-z0-9]+", match.group(2).casefold()))
    return (primary, alias) if primary and alias and primary != alias else None


def _has_reciprocal_alias_labels(first: str, second: str) -> bool:
    first_alias = _alias_description(first)
    second_alias = _alias_description(second)
    return (
        first_alias is not None
        and second_alias is not None
        and first_alias[0] == second_alias[1]
        and first_alias[1] == second_alias[0]
    )


def _search_fields(value: EditionValue, normalized: str) -> tuple[str, ...]:
    source_attributes = " ".join(item for pair in value.source.attributes for item in pair)
    source_metadata = " ".join(item for pair in value.source.metadata for item in pair)
    reference_attributes = (
        " ".join(item for pair in value.reference_source.attributes for item in pair)
        if value.reference_source is not None
        else ""
    )
    reference_metadata = (
        " ".join(item for pair in value.reference_source.metadata for item in pair)
        if value.reference_source is not None
        else ""
    )
    table_attributes = (
        " ".join(item for pair in value.table_source.attributes for item in pair)
        if value.table_source is not None
        else ""
    )
    table_metadata = (
        " ".join(item for pair in value.table_source.metadata for item in pair)
        if value.table_source is not None
        else ""
    )
    fields = (
        ("description", value.description or ""),
        ("table_name", value.table_name or ""),
        ("applicability", value.applicability or ""),
        ("uuid", value.uuid or ""),
        ("status", value.status or ""),
        ("footnote", value.footnote or ""),
        ("annotation", " ".join(annotation.text for annotation in value.table_annotations)),
        ("source_attribute", source_attributes),
        ("source_metadata", source_metadata),
        ("reference_attribute", reference_attributes),
        ("reference_metadata", reference_metadata),
        ("table_attribute", table_attributes),
        ("table_metadata", table_metadata),
        ("path", " ".join(value.path)),
        ("hierarchy_code", " ".join(str(code) for code in value.hierarchy_codes)),
        ("value", _value_key(value.value, value.value_min, value.value_max)),
    )
    return tuple(name for name, text in fields if text and (not normalized or normalized in text.casefold()))


def _stable_value_key(value: EditionValue) -> tuple[object, ...]:
    return (
        value.kind.value,
        value.table_uid if value.table_uid is not None else -1,
        value.hierarchy_codes,
        value.value if value.value is not None else value.value_min if value.value_min is not None else -1,
        value.value_max if value.value_max is not None else -1,
        value.tag,
        value.description or "",
        value.uuid or "",
        value.path,
    )


def _codes_match(codes: tuple[int, ...], entity_fields: tuple[int, ...]) -> bool:
    return all(
        code == entity_fields[index] or (index == 2 and code == 0 and entity_fields[index] != 0)
        for index, code in enumerate(codes)
    )


def _entity_depth(value: EditionValue) -> int:
    """Return the hierarchy depth including a range's represented field."""
    if value.kind is not EditionValueKind.ENTITY_TYPE:
        return len(value.hierarchy_codes)
    if value.value is None and value.value_min is not None:
        return len(value.hierarchy_codes) + 1
    return len(value.hierarchy_codes)

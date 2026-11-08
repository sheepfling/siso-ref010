"""Version histories and semantic comparisons for parsed SISO-REF-010 editions."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Iterator, Sequence
from hashlib import sha256
from typing import Literal

from pydantic import BaseModel, ConfigDict

from ._version import __version__
from .catalog import EntityTypeCatalog
from .inspection import EditionInspector, EditionValue, EditionValueKind
from .model import EntityType
from .parser import EntityTypeXmlParser
from .reference import EntityTypeStandard, TableAnnotation
from .sources import BUNDLED_STANDARD_SOURCE, StandardSource

ComparisonScope = Literal["all", "entities", "enumerations"]
ChangeAction = Literal["added", "removed", "modified", "moved", "recoded"]
RecordScope = Literal["entity", "enumeration_table", "enumeration_value"]
IdentityMatch = Literal["uuid", "code", "unmatched", "ambiguous_uuid", "ambiguous_code"]
ChangeCategory = Literal[
    "semantic", "relationship", "lifecycle", "documentation", "provenance", "raw_metadata"
]
Compatibility = Literal[
    "unchanged", "additive", "potentially_breaking", "breaking", "not_applicable", "not_assessed"
]
SemanticMeaning = Literal["unchanged", "changed", "not_applicable", "not_assessed"]
ApplicationMigration = Literal["none", "recommended", "required", "not_applicable", "not_assessed"]
ReviewPriority = Literal["none", "low", "medium", "high"]
ChangeOrigin = Literal["direct", "derived", "mixed"]
DefaultQueueDisposition = Literal["included", "excluded_low_priority", "excluded_no_priority"]
ChangeReasonCode = Literal[
    "record_added",
    "record_removed",
    "entity_identifier_changed",
    "enumeration_value_changed",
    "enumeration_table_uid_changed",
    "enumeration_declared_width_changed",
    "relationship_changed",
    "deprecation_introduced",
    "retirement_introduced",
    "documentation_changed",
    "source_uuid_changed",
    "release_status_cleared",
    "source_metadata_changed",
    "inherited_path_label_changed",
    "identity_ambiguous",
    "same_code_different_uuid",
    "possible_code_reuse",
    "other_field_changed",
]
RecommendationCode = Literal[
    "review_new_value_if_consumed",
    "check_removed_value_references",
    "validate_enum_width_against_wire_field",
    "review_entity_identifier_dependents",
    "update_enum_value_mappings",
    "review_base_relationship_dependents",
    "review_deprecated_references",
    "review_retired_references",
    "verify_source_meaning",
    "resolve_identity_manually",
    "inspect_ancestor_change",
]
IdentityDiagnosticCode = Literal[
    "duplicate_uuid",
    "duplicate_code",
    "uuid_changed_at_stable_code",
    "possible_code_reuse",
]


class ComparisonModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ValueRecord(ComparisonModel):
    """One value as exposed by an edition, with its source identity and metadata."""

    scope: RecordScope
    identifier: str
    stable_id: str | None = None
    path: tuple[int, ...] = ()
    path_labels: tuple[str, ...] = ()
    table_uid: int | None = None
    reference_uid: int | None = None
    value: int | None = None
    value_min: int | None = None
    value_max: int | None = None
    name: str | None = None
    applicability: str | None = None
    size: int | None = None
    description: str | None = None
    tag: str | None = None
    status: str | None = None
    deprecated: bool = False
    base_uuid: str | None = None
    retired: bool | None = None
    footnote: str | None = None
    attributes: tuple[tuple[str, str], ...] = ()
    metadata: tuple[tuple[str, str], ...] = ()
    change_requests: tuple[tuple[int, int], ...] = ()
    annotations: tuple[TableAnnotation, ...] = ()


class ChangeAssessment(ComparisonModel):
    """Separate encoding, lookup, semantic, and application-level assessments."""

    wire_encoding: Compatibility = "not_assessed"
    identifier_resolution: Compatibility = "not_assessed"
    semantic_meaning: SemanticMeaning = "not_assessed"
    application_migration: ApplicationMigration = "not_assessed"

    @property
    def is_material(self) -> bool:
        return (
            self.wire_encoding not in {"unchanged", "not_applicable"}
            or self.identifier_resolution not in {"unchanged", "not_applicable"}
            or self.semantic_meaning not in {"unchanged", "not_applicable"}
            or self.application_migration not in {"none", "not_applicable"}
        )


class ChangeReference(ComparisonModel):
    """Stable identity for a change that caused an inherited result."""

    scope: RecordScope
    identifier: str
    stable_id: str | None = None


class EditionChange(ComparisonModel):
    """A changed value or source record between two editions."""

    action: ChangeAction
    scope: RecordScope
    identifier: str
    stable_id: str | None = None
    identity_match: IdentityMatch = "unmatched"
    identity_diagnostics: tuple[IdentityDiagnosticCode, ...] = ()
    changed_fields: tuple[str, ...] = ()
    categories: tuple[ChangeCategory, ...] = ()
    assessment: ChangeAssessment = ChangeAssessment()
    review_priority: ReviewPriority = "none"
    review_disposition: DefaultQueueDisposition = "excluded_no_priority"
    reason_codes: tuple[ChangeReasonCode, ...] = ()
    recommendation_codes: tuple[RecommendationCode, ...] = ()
    origin: ChangeOrigin = "direct"
    caused_by: tuple[ChangeReference, ...] = ()
    before: ValueRecord | None = None
    after: ValueRecord | None = None

    @property
    def compatibility(self) -> Compatibility:
        """Compatibility alias for the wire-encoding assessment."""
        return self.assessment.wire_encoding


class ChangeCounts(ComparisonModel):
    added: int = 0
    removed: int = 0
    modified: int = 0
    moved: int = 0
    recoded: int = 0


class SourceHashes(ComparisonModel):
    from_sha256: str = ""
    to_sha256: str = ""


class AddedByScope(ComparisonModel):
    entity_types: int = 0
    enumeration_values: int = 0
    enumeration_tables: int = 0


class UnassessedMeaningCounts(ComparisonModel):
    new_catalog_records: int = 0
    changed_base_uuid_relationships: int = 0
    other: int = 0


class UnassessedAssessmentCounts(ComparisonModel):
    wire_encoding: int = 0
    identifier_resolution: int = 0
    semantic_meaning: int = 0
    application_migration: int = 0


class EditionDiff(ComparisonModel):
    report_type: Literal["audit"] = "audit"
    schema_version: int = 5
    generator_version: str = __version__
    from_version: int
    to_version: int
    source_sha256: SourceHashes = SourceHashes()
    scope: ComparisonScope
    changes: tuple[EditionChange, ...]
    total: int
    truncated: bool
    counts: ChangeCounts

    def summary(self) -> EditionDiffSummary:
        if self.truncated:
            raise ValueError("A complete edition summary requires an untruncated diff; use limit=None")
        added = [change for change in self.changes if change.action == "added"]
        reviewable = _rank_review_changes(self.changes)
        meaning_unassessed = [
            change for change in self.changes if change.assessment.semantic_meaning == "not_assessed"
        ]
        unassessed_additions = sum(change.action == "added" for change in meaning_unassessed)
        unassessed_relationships = sum("base_uuid" in change.changed_fields for change in meaning_unassessed)
        return EditionDiffSummary(
            report_type="summary",
            schema_version=5,
            generator_version=self.generator_version,
            from_version=self.from_version,
            to_version=self.to_version,
            scope=self.scope,
            source_sha256=self.source_sha256,
            total=self.total,
            counts=self.counts,
            new_deprecations=sum(
                change.before is not None
                and change.after is not None
                and not change.before.deprecated
                and change.after.deprecated
                for change in self.changes
            ),
            newly_retired=sum(
                change.before is not None
                and change.after is not None
                and change.before.retired is not True
                and change.after.retired is True
                for change in self.changes
            ),
            relationship_changes=sum("base_uuid" in change.changed_fields for change in self.changes),
            added_by_scope=AddedByScope(
                entity_types=sum(change.scope == "entity" for change in added),
                enumeration_values=sum(change.scope == "enumeration_value" for change in added),
                enumeration_tables=sum(change.scope == "enumeration_table" for change in added),
            ),
            table_size_changes=sum(
                change.scope == "enumeration_table" and "size" in change.changed_fields
                for change in self.changes
            ),
            derived_changes=sum(change.origin == "derived" for change in self.changes),
            status_cleanups=sum(
                change.action == "modified"
                and change.scope != "enumeration_table"
                and change.before is not None
                and change.after is not None
                and change.before.status == "new"
                and change.after.status is None
                and set(change.changed_fields) <= {"status", "attributes"}
                for change in self.changes
            ),
            table_status_cleanups=sum(
                change.action == "modified"
                and change.scope == "enumeration_table"
                and change.before is not None
                and change.after is not None
                and change.before.status == "new"
                and change.after.status is None
                and set(change.changed_fields) <= {"status", "attributes"}
                for change in self.changes
            ),
            review_queue_count=len(reviewable),
            high_priority_count=sum(item.review_priority == "high" for item in reviewable),
            medium_priority_count=sum(item.review_priority == "medium" for item in reviewable),
            other_priority_count=sum(item.review_priority not in {"high", "medium"} for item in reviewable),
            low_priority_omitted_count=_omitted_low_priority_count(self.changes),
            explicit_filter_only_count=sum(
                change.review_disposition == "excluded_no_priority" for change in self.changes
            ),
            unassessed_assessment_counts=UnassessedAssessmentCounts(
                wire_encoding=sum(
                    change.assessment.wire_encoding == "not_assessed" for change in self.changes
                ),
                identifier_resolution=sum(
                    change.assessment.identifier_resolution == "not_assessed" for change in self.changes
                ),
                semantic_meaning=sum(
                    change.assessment.semantic_meaning == "not_assessed" for change in self.changes
                ),
                application_migration=sum(
                    change.assessment.application_migration == "not_assessed" for change in self.changes
                ),
            ),
            unassessed_semantic_meaning_by_change=UnassessedMeaningCounts(
                new_catalog_records=unassessed_additions,
                changed_base_uuid_relationships=unassessed_relationships,
                other=len(meaning_unassessed) - unassessed_additions - unassessed_relationships,
            ),
            review_preview=tuple(
                _concise_change(change).model_copy(update={"record_before": None, "record_after": None})
                for change in reviewable[:10]
            ),
        )

    def review_queue(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
        priority: ReviewPriority | None = None,
        compatibility: Compatibility | None = None,
        scope: RecordScope | None = None,
        action: ChangeAction | None = None,
        category: ChangeCategory | None = None,
        identifier_resolution: Compatibility | None = None,
        semantic_meaning: SemanticMeaning | None = None,
        application_migration: ApplicationMigration | None = None,
    ) -> ReviewQueuePage:
        """Return risk-ranked review items or explicitly selected lower-priority items."""
        if self.truncated:
            raise ValueError("A complete review queue requires an untruncated diff; use limit=None")
        if type(limit) is not int or limit < 1:
            raise ValueError("limit must be a positive integer")
        if type(offset) is not int or offset < 0:
            raise ValueError("offset must be a nonnegative integer")
        rows = _rank_review_changes(
            self.changes,
            include_low_priority=priority == "low" or category is not None,
            include_no_priority=priority == "none",
        )
        selected = tuple(
            change
            for change in rows
            if (priority is None or change.review_priority == priority)
            and (compatibility is None or change.compatibility == compatibility)
            and (
                identifier_resolution is None
                or change.assessment.identifier_resolution == identifier_resolution
            )
            and (semantic_meaning is None or change.assessment.semantic_meaning == semantic_meaning)
            and (
                application_migration is None
                or change.assessment.application_migration == application_migration
            )
            and (scope is None or change.scope == scope)
            and (action is None or change.action == action)
            and (category is None or category in change.categories)
        )
        page = selected[offset : offset + limit]
        return ReviewQueuePage(
            report_type="review_queue",
            schema_version=5,
            generator_version=self.generator_version,
            from_version=self.from_version,
            to_version=self.to_version,
            scope=self.scope,
            source_sha256=self.source_sha256,
            total=len(selected),
            offset=offset,
            limit=limit,
            returned=len(page),
            has_more=offset + len(page) < len(selected),
            low_priority_omitted_count=_omitted_low_priority_count(self.changes),
            explicit_filter_only_count=sum(
                change.review_disposition == "excluded_no_priority" for change in self.changes
            ),
            changes=tuple(_concise_change(change) for change in page),
        )

    def concise(self) -> ConciseEditionDiff:
        """Return a consumer-facing projection without full before/after snapshots."""
        changes_list: list[ConciseChange] = []
        for change in self.changes:
            changes_list.append(_concise_change(change))
        changes = tuple(changes_list)
        return ConciseEditionDiff(
            report_type="concise",
            from_version=self.from_version,
            to_version=self.to_version,
            schema_version=self.schema_version,
            generator_version=self.generator_version,
            source_sha256=self.source_sha256,
            scope=self.scope,
            changes=changes,
            total=self.total,
            truncated=self.truncated,
            counts=self.counts,
        )


class FieldDelta(ComparisonModel):
    name: str
    before: object | None
    after: object | None


class ConciseRecord(ComparisonModel):
    scope: RecordScope
    stable_id: str | None = None
    label: str | None = None
    path: tuple[int, ...] = ()
    table_uid: int | None = None
    value: int | None = None
    value_min: int | None = None
    value_max: int | None = None
    name: str | None = None
    size: int | None = None
    applicability: str | None = None
    status: str | None = None
    deprecated: bool = False
    base_uuid: str | None = None
    retired: bool | None = None


class ConciseChange(ComparisonModel):
    scope: RecordScope
    identifier: str
    stable_id: str | None = None
    identity_match: IdentityMatch = "unmatched"
    action: ChangeAction
    categories: tuple[ChangeCategory, ...]
    identity_diagnostics: tuple[IdentityDiagnosticCode, ...]
    assessment: ChangeAssessment
    review_priority: ReviewPriority
    review_disposition: DefaultQueueDisposition
    reason_codes: tuple[ChangeReasonCode, ...]
    recommendation_codes: tuple[RecommendationCode, ...]
    origin: ChangeOrigin
    caused_by: tuple[ChangeReference, ...] = ()
    label: str | None = None
    path: tuple[int, ...] = ()
    table_uid: int | None = None
    value: int | None = None
    record_before: ConciseRecord | None = None
    record_after: ConciseRecord | None = None
    fields: tuple[FieldDelta, ...]

    @property
    def compatibility(self) -> Compatibility:
        """Compatibility alias for the wire-encoding assessment."""
        return self.assessment.wire_encoding


class ConciseEditionDiff(ComparisonModel):
    report_type: Literal["concise"] = "concise"
    schema_version: int
    generator_version: str
    from_version: int
    to_version: int
    source_sha256: SourceHashes
    scope: ComparisonScope
    changes: tuple[ConciseChange, ...]
    total: int
    truncated: bool
    counts: ChangeCounts


class EditionDiffSummary(ComparisonModel):
    report_type: Literal["summary"] = "summary"
    schema_version: int
    generator_version: str
    from_version: int
    to_version: int
    scope: ComparisonScope
    source_sha256: SourceHashes
    total: int
    counts: ChangeCounts
    added_by_scope: AddedByScope
    new_deprecations: int
    newly_retired: int
    relationship_changes: int
    table_size_changes: int
    status_cleanups: int
    table_status_cleanups: int
    derived_changes: int
    review_queue_count: int
    high_priority_count: int
    medium_priority_count: int
    other_priority_count: int
    low_priority_omitted_count: int
    explicit_filter_only_count: int
    unassessed_assessment_counts: UnassessedAssessmentCounts
    unassessed_semantic_meaning_by_change: UnassessedMeaningCounts
    review_preview: tuple[ConciseChange, ...]


class ReviewQueuePage(ComparisonModel):
    report_type: Literal["review_queue"] = "review_queue"
    schema_version: int
    generator_version: str
    from_version: int
    to_version: int
    scope: ComparisonScope
    source_sha256: SourceHashes
    total: int
    offset: int
    limit: int
    returned: int
    has_more: bool
    low_priority_omitted_count: int
    explicit_filter_only_count: int
    changes: tuple[ConciseChange, ...]


def _display_label(record: ValueRecord | None) -> str | None:
    if record is None:
        return None
    if record.scope == "enumeration_table":
        return record.name or f"Enumeration UID {record.table_uid}"
    if record.description:
        return record.description
    if record.scope == "enumeration_value":
        value = (
            str(record.value)
            if record.value is not None
            else f"{record.value_min}–{record.value_max}"
            if record.value_min is not None and record.value_max is not None
            else "unspecified value"
        )
        return f"{record.name or 'Enumeration'} · UID {record.table_uid} · Value {value}"
    path = ".".join(map(str, record.path))
    return f"Entity type {path}" if path else "Entity type"


def _rank_review_changes(
    changes: Sequence[EditionChange],
    *,
    include_low_priority: bool = False,
    include_no_priority: bool = False,
) -> list[EditionChange]:
    rows = [
        change
        for change in changes
        if change.review_priority in {"high", "medium"}
        or _has_encoding_or_identifier_risk(change)
        or (include_low_priority and change.review_priority == "low")
        or (include_no_priority and change.review_priority == "none")
    ]
    scope_rank: dict[RecordScope, int] = {"entity": 0, "enumeration_table": 1, "enumeration_value": 2}
    priority_rank: dict[ReviewPriority, int] = {"high": 0, "medium": 1, "low": 2, "none": 3}

    def rank_group(change: EditionChange) -> int:
        if _has_wire_encoding_risk(change):
            return 0
        if change.review_priority == "high":
            return 1
        if _has_identifier_resolution_risk(change):
            return 2
        if (
            change.assessment.semantic_meaning == "not_assessed"
            or change.assessment.application_migration == "not_assessed"
        ):
            return 3
        if change.review_priority == "medium":
            return 4
        return 5

    def numeric_identity(change: EditionChange) -> tuple[int, ...]:
        record = change.after or change.before
        if record is None:
            return ()
        if change.scope == "entity":
            return record.path
        if change.scope == "enumeration_table":
            return (record.table_uid,) if record.table_uid is not None else ()
        value = record.value if record.value is not None else record.value_min
        return tuple(number for number in (record.table_uid, value, record.value_max) if number is not None)

    return sorted(
        rows,
        key=lambda change: (
            rank_group(change),
            priority_rank[change.review_priority],
            change.origin == "derived",
            scope_rank[change.scope],
            numeric_identity(change),
            change.stable_id or "",
            change.identifier,
        ),
    )


def _omitted_low_priority_count(changes: Sequence[EditionChange]) -> int:
    return sum(change.review_disposition == "excluded_low_priority" for change in changes)


def _has_encoding_or_identifier_risk(change: EditionChange) -> bool:
    return _has_wire_encoding_risk(change) or _has_identifier_resolution_risk(change)


def _has_wire_encoding_risk(change: EditionChange) -> bool:
    return change.assessment.wire_encoding in {"breaking", "potentially_breaking"}


def _has_identifier_resolution_risk(change: EditionChange) -> bool:
    return change.assessment.identifier_resolution in {"breaking", "potentially_breaking"}


def _concise_change(change: EditionChange) -> ConciseChange:
    record = change.after or change.before
    if change.action in {"added", "removed"}:
        return ConciseChange(
            scope=change.scope,
            identifier=change.identifier,
            stable_id=change.stable_id,
            identity_match=change.identity_match,
            identity_diagnostics=change.identity_diagnostics,
            action=change.action,
            categories=change.categories,
            assessment=change.assessment,
            review_priority=change.review_priority,
            review_disposition=change.review_disposition,
            reason_codes=change.reason_codes,
            recommendation_codes=change.recommendation_codes,
            origin=change.origin,
            caused_by=change.caused_by,
            label=_display_label(record),
            path=record.path if record is not None else (),
            table_uid=record.table_uid if record is not None else None,
            value=record.value if record is not None else None,
            record_before=_concise_record(change.before),
            record_after=_concise_record(change.after),
            fields=(),
        )
    fields = list(change.changed_fields)
    fields = [name for name in fields if name != "attributes"]
    if not change.changed_fields and record is not None:
        fields.extend(
            name
            for name in (
                "value",
                "value_min",
                "value_max",
                "description",
                "size",
                "name",
                "status",
                "deprecated",
                "base_uuid",
                "retired",
                "path",
                "applicability",
            )
            if getattr(record, name) is not None
        )

    before_attributes = dict(change.before.attributes) if change.before is not None else {}
    after_attributes = dict(change.after.attributes) if change.after is not None else {}
    attribute_to_field = {
        "status": "status",
        "deprecated": "deprecated",
        "baseuuid": "base_uuid",
        "retired": "retired",
        "uuid": "stable_id",
        "description": "description",
        "footnote": "footnote",
        "uid": "table_uid",
        "value": "value",
        "value_min": "value_min",
        "value_max": "value_max",
        "size": "size",
        "name": "name",
        "applicability": "applicability",
    }
    attribute_deltas = [
        key
        for key in sorted(before_attributes.keys() | after_attributes.keys())
        if before_attributes.get(key) != after_attributes.get(key)
        and attribute_to_field.get(key) not in fields
    ]
    deltas = [
        FieldDelta(
            name=name,
            before=getattr(change.before, name) if change.before is not None else None,
            after=getattr(change.after, name) if change.after is not None else None,
        )
        for name in fields
    ]
    deltas.extend(
        FieldDelta(
            name=f"attribute:{key}",
            before=before_attributes.get(key),
            after=after_attributes.get(key),
        )
        for key in attribute_deltas
    )
    return ConciseChange(
        scope=change.scope,
        identifier=change.identifier,
        stable_id=change.stable_id,
        identity_match=change.identity_match,
        identity_diagnostics=change.identity_diagnostics,
        action=change.action,
        categories=change.categories,
        assessment=change.assessment,
        review_priority=change.review_priority,
        review_disposition=change.review_disposition,
        reason_codes=change.reason_codes,
        recommendation_codes=change.recommendation_codes,
        origin=change.origin,
        caused_by=change.caused_by,
        label=_display_label(record),
        path=record.path if record is not None else (),
        table_uid=record.table_uid if record is not None else None,
        value=record.value if record is not None else None,
        fields=tuple(deltas),
    )


def _concise_record(record: ValueRecord | None) -> ConciseRecord | None:
    if record is None:
        return None
    return ConciseRecord(
        scope=record.scope,
        stable_id=record.stable_id,
        label=_display_label(record),
        path=record.path,
        table_uid=record.table_uid,
        value=record.value,
        value_min=record.value_min,
        value_max=record.value_max,
        name=record.name,
        size=record.size,
        applicability=record.applicability,
        status=record.status,
        deprecated=record.deprecated,
        base_uuid=record.base_uuid,
        retired=record.retired,
    )


class HistoryPoint(ComparisonModel):
    version: int
    present: bool
    description: str | None = None
    qualified_description: str | None = None
    matched_path: tuple[int, ...] = ()
    stable_id: str | None = None
    name: str | None = None
    applicability: str | None = None
    size: int | None = None
    attributes: tuple[tuple[str, str], ...] = ()


class ValueHistory(ComparisonModel):
    kind: Literal["entity", "enumeration"]
    target: str
    points: tuple[HistoryPoint, ...]


def _as_value_record(value: EditionValue) -> ValueRecord:
    is_entity = value.kind is EditionValueKind.ENTITY_TYPE
    reference_uid: int | None = None
    if value.reference_source is not None:
        raw_uid = value.reference_source.get("xref")
        try:
            reference_uid = int(raw_uid) if raw_uid is not None else None
        except ValueError:
            reference_uid = None
    return ValueRecord(
        scope="entity" if is_entity else "enumeration_value",
        identifier=value.identity,
        stable_id=value.uuid,
        path=value.hierarchy_codes,
        path_labels=value.path,
        table_uid=value.table_uid,
        reference_uid=reference_uid,
        value=value.value,
        value_min=value.value_min,
        value_max=value.value_max,
        name=value.table_name,
        applicability=value.applicability,
        description=value.description,
        tag=value.tag,
        status=value.status,
        deprecated=value.deprecated,
        base_uuid=value.source.get("baseuuid"),
        retired=_optional_source_bool(value.source.get("retired")),
        footnote=value.footnote,
        attributes=tuple(sorted(value.source.attributes)),
        metadata=tuple(sorted(value.source.metadata)),
        change_requests=tuple((row.minimum, row.maximum) for row in value.source.change_requests),
    )


def _inspection_records(standard: EntityTypeStandard) -> Iterator[ValueRecord]:
    inspector = EditionInspector(standard)
    for table in inspector.enumeration_tables():
        yield ValueRecord(
            scope="enumeration_table",
            identifier=f"enumeration:{table.uid}",
            stable_id=table.source.get("uuid"),
            table_uid=table.uid,
            name=table.name,
            applicability=table.applicability,
            size=table.declared_size,
            status=table.source.get("status"),
            deprecated=(table.source.get("deprecated") or "").casefold() in {"true", "1", "yes"},
            base_uuid=table.source.get("baseuuid"),
            retired=_optional_source_bool(table.source.get("retired")),
            tag="enum",
            attributes=tuple(sorted(table.source.attributes)),
            metadata=tuple(sorted(table.source.metadata)),
            change_requests=tuple((row.minimum, row.maximum) for row in table.source.change_requests),
            annotations=table.annotations,
        )
    yield from (_as_value_record(value) for value in inspector.values())


def _fallback_identity(record: ValueRecord) -> str:
    """Build a code identity independent of UUIDs and mutable descriptions."""
    if record.scope == "enumeration_table":
        return f"enumeration:{record.table_uid}"
    value_key = (
        str(record.value)
        if record.value is not None
        else f"{record.value_min}-{record.value_max}"
        if record.value_min is not None and record.value_max is not None
        else "none"
    )
    if record.scope == "entity":
        path = ".".join(map(str, record.path))
        return f"entity:{path}:{record.tag}:{value_key}"
    return f"enumeration-value:{record.table_uid}:{record.tag}:{value_key}"


def _optional_source_bool(value: str | None) -> bool | None:
    if value is None:
        return None
    normalized = value.strip().casefold()
    if normalized in {"true", "1", "yes"}:
        return True
    if normalized in {"false", "0", "no"}:
        return False
    return None


def _uuid_counts(records: Sequence[ValueRecord]) -> Counter[tuple[RecordScope, str]]:
    counts: Counter[tuple[RecordScope, str]] = Counter()
    for record in records:
        if record.stable_id is not None:
            counts[(record.scope, record.stable_id.casefold())] += 1
    return counts


def _changed_fields(before: ValueRecord, after: ValueRecord) -> tuple[str, ...]:
    fields = (
        "path",
        "path_labels",
        "table_uid",
        "reference_uid",
        "stable_id",
        "value",
        "value_min",
        "value_max",
        "name",
        "applicability",
        "size",
        "description",
        "tag",
        "status",
        "deprecated",
        "base_uuid",
        "retired",
        "footnote",
        "attributes",
        "metadata",
        "change_requests",
        "annotations",
    )
    return tuple(name for name in fields if getattr(before, name) != getattr(after, name))


def _match_records(
    before: Sequence[ValueRecord], after: Sequence[ValueRecord]
) -> tuple[list[tuple[ValueRecord, ValueRecord, IdentityMatch]], list[ValueRecord], list[ValueRecord]]:
    """Match unique UUIDs first, then stable code paths for remaining records."""
    before_ids = _uuid_counts(before)
    after_ids = _uuid_counts(after)
    before_codes = Counter(_fallback_identity(record) for record in before)
    after_codes = Counter(_fallback_identity(record) for record in after)
    after_by_uuid = {
        (record.scope, record.stable_id.casefold()): index
        for index, record in enumerate(after)
        if record.stable_id is not None
        and after_ids[(record.scope, record.stable_id.casefold())] == 1
        and before_ids[(record.scope, record.stable_id.casefold())] == 1
    }
    used_before: set[int] = set()
    used_after: set[int] = set()
    pairs: list[tuple[ValueRecord, ValueRecord, IdentityMatch]] = []
    for old_index, old in enumerate(before):
        stable_id = old.stable_id
        if stable_id is None:
            continue
        stable_key = (old.scope, stable_id.casefold())
        if before_ids[stable_key] == 1 and stable_key in after_by_uuid:
            new_index = after_by_uuid[stable_key]
            pairs.append((old, after[new_index], "uuid"))
            used_before.add(old_index)
            used_after.add(new_index)

    after_by_fallback: dict[str, list[int]] = {}
    for index, record in enumerate(after):
        if index not in used_after:
            after_by_fallback.setdefault(_fallback_identity(record), []).append(index)
    for old_index, old in enumerate(before):
        if old_index in used_before:
            continue
        fallback = _fallback_identity(old)
        candidates = after_by_fallback.get(fallback, [])
        if before_codes[fallback] == 1 and after_codes[fallback] == 1 and len(candidates) == 1:
            new_index = candidates[0]
            pairs.append((old, after[new_index], "code"))
            used_before.add(old_index)
            used_after.add(new_index)

    removed = [record for index, record in enumerate(before) if index not in used_before]
    added = [record for index, record in enumerate(after) if index not in used_after]
    return pairs, removed, added


def _record_changes(before: Sequence[ValueRecord], after: Sequence[ValueRecord]) -> list[EditionChange]:
    pairs, removed, added = _match_records(before, after)
    changes: list[EditionChange] = []
    before_uuid_counts = _uuid_counts(before)
    after_uuid_counts = _uuid_counts(after)
    before_code_counts = Counter(_fallback_identity(record) for record in before)
    after_code_counts = Counter(_fallback_identity(record) for record in after)

    def unmatched_identity(row: ValueRecord) -> IdentityMatch:
        stable_id = row.stable_id
        if stable_id is not None and (
            before_uuid_counts[(row.scope, stable_id.casefold())] > 1
            or after_uuid_counts[(row.scope, stable_id.casefold())] > 1
        ):
            return "ambiguous_uuid"
        fallback = _fallback_identity(row)
        if before_code_counts[fallback] > 1 or after_code_counts[fallback] > 1:
            return "ambiguous_code"
        return "unmatched"

    def unmatched_diagnostics(row: ValueRecord) -> tuple[IdentityDiagnosticCode, ...]:
        diagnostics: set[IdentityDiagnosticCode] = set()
        stable_id = row.stable_id
        if stable_id is not None and (
            before_uuid_counts[(row.scope, stable_id.casefold())] > 1
            or after_uuid_counts[(row.scope, stable_id.casefold())] > 1
        ):
            diagnostics.add("duplicate_uuid")
        fallback = _fallback_identity(row)
        if before_code_counts[fallback] > 1 or after_code_counts[fallback] > 1:
            diagnostics.add("duplicate_code")
        return tuple(sorted(diagnostics))

    for old in removed:
        changes.append(
            EditionChange(
                action="removed",
                scope=old.scope,
                identifier=old.identifier,
                stable_id=old.stable_id,
                identity_match=unmatched_identity(old),
                identity_diagnostics=unmatched_diagnostics(old),
                before=old,
            )
        )
    for new in added:
        changes.append(
            EditionChange(
                action="added",
                scope=new.scope,
                identifier=new.identifier,
                stable_id=new.stable_id,
                identity_match=unmatched_identity(new),
                identity_diagnostics=unmatched_diagnostics(new),
                after=new,
            )
        )
    for old, new, match_basis in pairs:
        fields = _changed_fields(old, new)
        if not fields:
            continue
        entity_value_changed = (
            old.value != new.value or old.value_min != new.value_min or old.value_max != new.value_max
        )
        old_parent_path = old.path[:-1] if old.value is not None else old.path
        new_parent_path = new.path[:-1] if new.value is not None else new.path
        moved = old_parent_path != new_parent_path and old.scope == "entity"
        recoded = (
            old.table_uid != new.table_uid or entity_value_changed
        ) and old.scope == "enumeration_value"
        recoded_table = old.scope == "enumeration_table" and old.table_uid != new.table_uid
        recoded_entity = old.scope == "entity" and entity_value_changed
        action: ChangeAction = (
            "recoded" if recoded or recoded_table or recoded_entity else "moved" if moved else "modified"
        )
        identity_diagnostics: set[IdentityDiagnosticCode] = set()
        if (
            match_basis == "code"
            and old.stable_id is not None
            and new.stable_id is not None
            and old.stable_id.casefold() != new.stable_id.casefold()
        ):
            identity_diagnostics.add("uuid_changed_at_stable_code")
            if old.description != new.description or old.name != new.name:
                identity_diagnostics.add("possible_code_reuse")
        changes.append(
            EditionChange(
                action=action,
                scope=old.scope,
                identifier=new.identifier,
                stable_id=new.stable_id or old.stable_id,
                identity_match=match_basis,
                identity_diagnostics=tuple(sorted(identity_diagnostics)),
                changed_fields=fields,
                before=old,
                after=new,
            )
        )
    classified = [_classify_change(change) for change in changes]
    classified = _attach_derived_causes(classified)
    return sorted(
        classified,
        key=lambda row: (row.scope, row.identifier, row.action),
    )


def _attach_derived_causes(changes: Sequence[EditionChange]) -> list[EditionChange]:
    """Link inherited entity-label updates to the direct ancestor description change."""
    parent_changes = [
        change
        for change in changes
        if change.scope == "entity"
        and change.before is not None
        and change.after is not None
        and change.before.path == change.after.path
        and "description" in change.changed_fields
    ]
    result: list[EditionChange] = []
    for change in changes:
        if change.origin != "derived" or change.before is None or change.after is None:
            result.append(change)
            continue
        changed_indexes = [
            index
            for index, (old, new) in enumerate(
                zip(change.before.path_labels, change.after.path_labels, strict=False)
            )
            if old != new
        ]
        causes = {
            (parent.scope, parent.identifier, parent.stable_id): ChangeReference(
                scope=parent.scope, identifier=parent.identifier, stable_id=parent.stable_id
            )
            for parent in parent_changes
            if parent.before is not None
            and any(
                len(parent.before.path) == index + 1 and parent.before.path == change.before.path[: index + 1]
                for index in changed_indexes
            )
        }
        ordered_causes = tuple(causes[key] for key in sorted(causes))
        recommendations = set(change.recommendation_codes)
        if ordered_causes:
            recommendations.add("inspect_ancestor_change")
        result.append(
            change.model_copy(
                update={
                    "caused_by": ordered_causes,
                    "recommendation_codes": tuple(sorted(recommendations)),
                }
            )
        )
    return result


def _classify_change(change: EditionChange) -> EditionChange:
    """Assess wire, lookup, meaning, and application effects independently."""
    fields = set(change.changed_fields)
    semantic = {
        "path",
        "table_uid",
        "reference_uid",
        "value",
        "value_min",
        "value_max",
        "size",
        "applicability",
        "tag",
    }
    lifecycle = {"status", "deprecated", "retired"}
    documentation = {"description", "footnote", "annotations", "path_labels"}
    provenance = {"stable_id", "change_requests"}
    categories: set[ChangeCategory] = set()
    if change.action in {"added", "removed"}:
        categories.add("semantic")
    if fields & semantic:
        categories.add("semantic")
    if fields & lifecycle:
        categories.add("lifecycle")
    if fields & documentation:
        categories.add("documentation")
    if fields & provenance:
        categories.add("provenance")
    if "base_uuid" in fields:
        categories.add("relationship")
    raw_attributes = _unclassified_attribute_changes(change)
    if fields & {"metadata"} or raw_attributes:
        categories.add("raw_metadata")
    if not categories:
        categories.add("raw_metadata")
    origin: ChangeOrigin = "derived" if fields == {"path_labels"} else "direct"
    wire_encoding: Compatibility = "unchanged"
    identifier_resolution: Compatibility = "unchanged"
    semantic_meaning: SemanticMeaning = "unchanged"
    application_migration: ApplicationMigration = "none"
    reasons: set[ChangeReasonCode] = set()
    recommendations: set[RecommendationCode] = set()

    if change.action == "added":
        identifier_resolution = "additive"
        semantic_meaning = "not_assessed"
        application_migration = "not_assessed"
        reasons.add("record_added")
        recommendations.add("review_new_value_if_consumed")
    elif change.action == "removed":
        identifier_resolution = "potentially_breaking"
        semantic_meaning = "not_assessed"
        application_migration = "recommended"
        reasons.add("record_removed")
        recommendations.add("check_removed_value_references")

    entity_code_changed = change.scope == "entity" and bool(fields & {"path", "value"})
    enum_value_changed = change.scope == "enumeration_value" and bool(
        fields & {"value", "value_min", "value_max", "table_uid"}
    )
    if entity_code_changed:
        wire_encoding = "potentially_breaking"
        identifier_resolution = "breaking"
        semantic_meaning = "not_assessed"
        application_migration = "recommended"
        reasons.add("entity_identifier_changed")
        recommendations.add("review_entity_identifier_dependents")
    if enum_value_changed:
        wire_encoding = "potentially_breaking"
        identifier_resolution = "breaking"
        semantic_meaning = "changed"
        application_migration = "recommended"
        reasons.add("enumeration_value_changed")
        recommendations.add("update_enum_value_mappings")
    if change.scope == "enumeration_table" and "size" in fields:
        # The bundled XSD defines enum/@size as "Enumeration size (bits)".
        # The table alone does not identify every PDU field that consumes it.
        wire_encoding = "potentially_breaking"
        semantic_meaning = "not_assessed"
        application_migration = "recommended"
        reasons.add("enumeration_declared_width_changed")
        recommendations.add("validate_enum_width_against_wire_field")
    if change.scope == "enumeration_table" and "table_uid" in fields:
        identifier_resolution = "breaking"
        semantic_meaning = "not_assessed"
        application_migration = "recommended"
        reasons.add("enumeration_table_uid_changed")
        recommendations.add("update_enum_value_mappings")
    if "base_uuid" in fields:
        identifier_resolution = "potentially_breaking"
        semantic_meaning = "not_assessed"
        application_migration = "recommended"
        reasons.add("relationship_changed")
        recommendations.add("review_base_relationship_dependents")
    if "stable_id" in fields:
        identifier_resolution = "potentially_breaking"
        semantic_meaning = "not_assessed"
        application_migration = "recommended"
        reasons.add("source_uuid_changed")
        recommendations.add("resolve_identity_manually")
    if fields & {"description", "footnote", "annotations", "name", "path_labels"}:
        semantic_meaning = "not_assessed"
        application_migration = "not_assessed"
        if fields == {"path_labels"}:
            reasons.add("inherited_path_label_changed")
            recommendations.add("inspect_ancestor_change")
        else:
            reasons.add("documentation_changed")
            recommendations.add("verify_source_meaning")
    if "deprecated" in fields and change.before is not None and change.after is not None:
        if not change.before.deprecated and change.after.deprecated:
            reasons.add("deprecation_introduced")
            application_migration = "recommended"
            recommendations.add("review_deprecated_references")
    if "retired" in fields and change.before is not None and change.after is not None:
        if change.before.retired is not True and change.after.retired is True:
            reasons.add("retirement_introduced")
            application_migration = "recommended"
            recommendations.add("review_retired_references")
    if "status" in fields and change.before is not None and change.after is not None:
        if change.before.status == "new" and change.after.status is None:
            reasons.add("release_status_cleared")
        else:
            semantic_meaning = "not_assessed"
            application_migration = "not_assessed"
            reasons.add("source_metadata_changed")
    if "metadata" in fields or raw_attributes:
        semantic_meaning = "not_assessed"
        application_migration = "not_assessed"
        reasons.add("source_metadata_changed")
        recommendations.add("verify_source_meaning")
    if change.identity_match in {"ambiguous_uuid", "ambiguous_code"}:
        reasons.add("identity_ambiguous")
        recommendations.add("resolve_identity_manually")
    if "uuid_changed_at_stable_code" in change.identity_diagnostics:
        reasons.add("same_code_different_uuid")
        recommendations.add("resolve_identity_manually")
    if "possible_code_reuse" in change.identity_diagnostics:
        reasons.add("possible_code_reuse")
        semantic_meaning = "not_assessed"
        application_migration = "recommended"
        recommendations.add("resolve_identity_manually")
    if "change_requests" in fields or (fields and fields <= {"metadata", "change_requests"}):
        if not reasons:
            reasons.add("source_metadata_changed")
    if not reasons:
        reasons.add("other_field_changed")

    assessment = ChangeAssessment(
        wire_encoding=wire_encoding,
        identifier_resolution=identifier_resolution,
        semantic_meaning=semantic_meaning,
        application_migration=application_migration,
    )
    if "size" in fields or (
        fields & {"deprecated", "retired"}
        and change.before is not None
        and change.after is not None
        and (
            ("deprecated" in fields and not change.before.deprecated and change.after.deprecated)
            or ("retired" in fields and change.before.retired is not True and change.after.retired is True)
        )
    ):
        priority: ReviewPriority = "high"
    elif "lifecycle" in categories and categories <= {"lifecycle", "raw_metadata"}:
        priority = "none"
    elif (
        change.identity_match in {"ambiguous_uuid", "ambiguous_code"}
        or "possible_code_reuse" in change.identity_diagnostics
    ):
        priority = "high"
    elif fields:
        priority = (
            "medium" if categories & {"semantic", "relationship", "documentation", "lifecycle"} else "low"
        )
    else:
        priority = "none"
    has_default_review = priority in {"high", "medium"} or (
        wire_encoding in {"breaking", "potentially_breaking"}
        or identifier_resolution in {"breaking", "potentially_breaking"}
    )
    disposition: DefaultQueueDisposition = (
        "included"
        if has_default_review
        else "excluded_low_priority"
        if priority == "low"
        else "excluded_no_priority"
    )
    return change.model_copy(
        update={
            "categories": tuple(sorted(categories)),
            "assessment": assessment,
            "review_priority": priority,
            "review_disposition": disposition,
            "reason_codes": tuple(sorted(reasons)),
            "recommendation_codes": tuple(sorted(recommendations)),
            "origin": origin,
        }
    )


def _unclassified_attribute_changes(change: EditionChange) -> set[str]:
    before = dict(change.before.attributes) if change.before is not None else {}
    after = dict(change.after.attributes) if change.after is not None else {}
    normalized = {
        "status",
        "deprecated",
        "baseuuid",
        "retired",
        "description",
        "footnote",
        "uuid",
        "uid",
        "value",
        "value_min",
        "value_max",
        "size",
        "name",
        "applicability",
        "xref",
        "title",
        "date",
        "release",
        "href",
    }
    return {
        key
        for key in before.keys() | after.keys()
        if before.get(key) != after.get(key) and key not in normalized
    }


def _load_standard(source: StandardSource, version: int) -> EntityTypeStandard:
    if type(version) is not int or version not in source.versions:
        raise ValueError(f"Version {version!r} is unavailable; available versions: {source.versions}")
    return EntityTypeXmlParser.from_bytes(source.read_xml(version))


def _select_versions(source: StandardSource, versions: Iterable[int] | None) -> tuple[int, ...]:
    selected = source.versions if versions is None else tuple(versions)
    if not selected:
        raise ValueError("At least one version is required")
    if any(type(version) is not int for version in selected):
        raise ValueError("Versions must be integers")
    if len(set(selected)) != len(selected):
        raise ValueError("Versions must not contain duplicates")
    unavailable = tuple(
        version for version in selected if type(version) is not int or version not in source.versions
    )
    if unavailable:
        raise ValueError(f"Unavailable versions {unavailable}; available versions: {source.versions}")
    return tuple(selected)


def compare_editions(
    from_version: int,
    to_version: int,
    *,
    source: StandardSource = BUNDLED_STANDARD_SOURCE,
    scope: ComparisonScope = "all",
    entity_prefix: tuple[int, ...] | None = None,
    enumeration_uid: int | None = None,
    limit: int | None = 500,
) -> EditionDiff:
    """Compare effective entity values and enumeration values between two editions."""
    if scope not in {"all", "entities", "enumerations"}:
        raise ValueError(f"Unsupported comparison scope: {scope!r}")
    if entity_prefix is not None and (
        not 3 <= len(entity_prefix) <= 7
        or any(type(value) is not int or value < 0 for value in entity_prefix)
    ):
        raise ValueError("entity_prefix must contain 3 through 7 nonnegative entity fields")
    if enumeration_uid is not None and (type(enumeration_uid) is not int or enumeration_uid < 0):
        raise ValueError("enumeration_uid must be a nonnegative integer")
    if entity_prefix is not None and enumeration_uid is not None:
        raise ValueError("entity_prefix and enumeration_uid filters cannot be combined")
    if entity_prefix is not None and scope == "enumerations":
        raise ValueError("entity_prefix cannot be used with enumeration-only scope")
    if enumeration_uid is not None and scope == "entities":
        raise ValueError("enumeration_uid cannot be used with entity-only scope")
    if limit is not None and (type(limit) is not int or limit < 0):
        raise ValueError("limit must be a nonnegative integer or None")
    old_standard = _load_standard(source, from_version)
    new_standard = _load_standard(source, to_version)
    all_before = tuple(_inspection_records(old_standard))
    all_after = tuple(_inspection_records(new_standard))
    before = [
        row
        for row in all_before
        if (scope in {"all", "entities"} and row.scope == "entity")
        or (scope in {"all", "enumerations"} and row.scope.startswith("enumeration"))
    ]
    after = [
        row
        for row in all_after
        if (scope in {"all", "entities"} and row.scope == "entity")
        or (scope in {"all", "enumerations"} and row.scope.startswith("enumeration"))
    ]
    changes = _record_changes(before, after)
    if entity_prefix is not None:
        changes = [
            change
            for change in changes
            if any(
                record is not None and _entity_prefix_matches(record, entity_prefix)
                for record in (change.before, change.after)
            )
        ]
    if enumeration_uid is not None:
        changes = [
            change
            for change in changes
            if any(
                record is not None and record.table_uid == enumeration_uid
                for record in (change.before, change.after)
            )
        ]
    total = len(changes)
    selected = changes if limit is None else changes[:limit]
    result_scope: ComparisonScope = (
        "entities" if entity_prefix is not None else "enumerations" if enumeration_uid is not None else scope
    )
    return EditionDiff(
        schema_version=5,
        from_version=from_version,
        to_version=to_version,
        source_sha256=SourceHashes(
            from_sha256=sha256(source.read_xml(from_version)).hexdigest(),
            to_sha256=sha256(source.read_xml(to_version)).hexdigest(),
        ),
        scope=result_scope,
        changes=tuple(selected),
        total=total,
        truncated=total > len(selected),
        counts=ChangeCounts(**dict(Counter(change.action for change in changes))),
    )


def entity_history(
    entity: EntityType | str,
    *,
    source: StandardSource = BUNDLED_STANDARD_SOURCE,
    versions: Iterable[int] | None = None,
) -> ValueHistory:
    """Return the effective lookup result for one entity code in each selected edition."""
    selected = _select_versions(source, versions)
    parsed = entity if isinstance(entity, EntityType) else EntityType.from_string(entity)
    values = parsed.as_tuple()
    points: list[HistoryPoint] = []
    for version in selected:
        standard = _load_standard(source, version)
        catalog = EntityTypeCatalog(standard)
        description = catalog.get_description_of(parsed)
        qualified = catalog.get_description_of(parsed, fully_qualified=True)
        matching = EditionInspector(standard).entity_path(values)
        match = max(matching, key=lambda row: len(row.path), default=None)
        points.append(
            HistoryPoint(
                version=version,
                present=match is not None,
                description=description if match is not None else None,
                qualified_description=qualified if match is not None else None,
                matched_path=match.hierarchy_codes if match is not None else (),
                stable_id=match.uuid if match is not None else None,
                attributes=match.source.attributes if match is not None else (),
            )
        )
    return ValueHistory(kind="entity", target="entity:" + ".".join(map(str, values)), points=tuple(points))


def enumeration_history(
    uid: int,
    value: int | None = None,
    *,
    source: StandardSource = BUNDLED_STANDARD_SOURCE,
    versions: Iterable[int] | None = None,
) -> ValueHistory:
    """Return the table or one enumerated value by UID across selected editions."""
    if type(uid) is not int or uid < 0:
        raise ValueError("enumeration UID must be a nonnegative integer")
    if value is not None and (type(value) is not int or value < 0):
        raise ValueError("enumeration value must be a nonnegative integer")
    selected = _select_versions(source, versions)
    points: list[HistoryPoint] = []
    for version in selected:
        standard = _load_standard(source, version)
        inspector = EditionInspector(standard)
        table = inspector.enumeration_table(uid)
        matching = inspector.enumeration_rows(uid, value=value) if value is not None and table else ()
        entry = matching[0] if matching else None
        points.append(
            HistoryPoint(
                version=version,
                present=table is not None if value is None else entry is not None,
                description=entry.description if entry is not None else None,
                stable_id=entry.uuid if entry is not None else (table.source.get("uuid") if table else None),
                name=table.name if table is not None else None,
                applicability=table.applicability if table is not None else None,
                size=table.declared_size if table is not None else None,
                attributes=entry.source.attributes
                if entry is not None
                else (table.source.attributes if table else ()),
            )
        )
    target = f"enumeration:{uid}" if value is None else f"enumeration:{uid}/value:{value}"
    return ValueHistory(kind="enumeration", target=target, points=tuple(points))


def _entity_prefix_matches(record: ValueRecord, prefix: tuple[int, ...]) -> bool:
    path = record.path
    common = min(len(path), len(prefix))
    if not all(
        left == right or (index == 2 and left == 0 and right != 0)
        for index, (left, right) in enumerate(zip(path[:common], prefix[:common], strict=False))
    ):
        return False
    if len(path) >= len(prefix):
        return True
    # A source range represents the next entity field and should remain visible
    # when a filter selects a code inside that range, including a deeper prefix.
    return (
        record.value_min is not None
        and record.value_max is not None
        and record.value_min <= prefix[len(path)] <= record.value_max
    )

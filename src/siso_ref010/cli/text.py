"""Plain-text presentation for command results."""

from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO

from pydantic import BaseModel

from ..api import EntityQueryResults, EnumerationNameResolution
from ..comparison import ConciseChange, EditionDiff, ReviewQueuePage, ValueHistory, ValueRecord
from ..inspection import (
    EditionDiagnostics,
    EditionSearchHit,
    EditionSearchResults,
    EditionSummary,
    EditionTableResults,
    EditionUUIDResults,
    EditionValue,
    EditionValueKind,
    EditionValueResults,
    EntityExplanation,
    EnumerationValueResolution,
    EnumerationValueStatus,
    ResolutionStatus,
)


def print_history_text(history: ValueHistory) -> None:
    print(f"{history.kind} history: {history.target}")
    for point in history.points:
        if (
            point.match_status
            in {
                ResolutionStatus.AMBIGUOUS,
                EnumerationValueStatus.AMBIGUOUS_TABLE,
                EnumerationValueStatus.AMBIGUOUS_VALUE,
            }
            or len(point.table_candidates) > 1
        ):
            details: list[str] = []
            if point.candidates:
                details.append(f"{len(point.candidates)} matching source rows")
            if len(point.table_candidates) > 1:
                details.append(f"{len(point.table_candidates)} tables share the UID")
            suffix = f" ({'; '.join(details)})" if details else ""
            print(f"v{point.version}: ambiguous{suffix}")
            continue
        if not point.present:
            print(f"v{point.version}: absent")
            continue
        description = point.description if point.description is not None else point.name or "present"
        suffix = f" ({point.qualified_description})" if point.qualified_description else ""
        print(f"v{point.version}: {description}{suffix}")


def print_diff_text(diff: EditionDiff) -> None:
    summary = diff.summary()
    print("SISO-REF-010 · Edition comparison")
    print(
        f"\nv{diff.from_version} -> v{diff.to_version}: {diff.total:,} total changes"
        f" · {diff.counts.added:,} added · {diff.counts.modified:,} modified"
    )
    if diff.counts.removed or diff.counts.moved or diff.counts.recoded:
        print(
            f"Removed: {diff.counts.removed:,} · moved: {diff.counts.moved:,}"
            f" · recoded: {diff.counts.recoded:,}"
        )
    print(
        f"Added by scope: {summary.added_by_scope.entity_types:,} entity types · "
        f"{summary.added_by_scope.enumeration_values:,} enumeration values · "
        f"{summary.added_by_scope.enumeration_tables:,} enumeration tables"
    )
    unassessed_meaning = summary.unassessed_semantic_meaning_by_change
    reasons = [
        f"{unassessed_meaning.new_catalog_records:,} new catalog records",
        f"{unassessed_meaning.changed_base_uuid_relationships:,} changed base-UUID relationships",
    ]
    if unassessed_meaning.other:
        reasons.append(f"{unassessed_meaning.other:,} other")
    print(
        f"Semantic meaning not assessed: {summary.unassessed_assessment_counts.semantic_meaning:,} changes "
        f"({'; '.join(reasons)})"
    )
    assessment_counts = summary.unassessed_assessment_counts
    print(
        "Assessments not assessed: "
        f"wire {assessment_counts.wire_encoding:,} · "
        f"identifier resolution {assessment_counts.identifier_resolution:,} · "
        f"meaning {assessment_counts.semantic_meaning:,} · "
        f"application migration {assessment_counts.application_migration:,}"
    )
    if summary.relationship_changes:
        print(
            f"Catalog relationships changed: {summary.relationship_changes:,} base-UUID links"
            " (review dependent identifier resolution and application effects)"
        )
    print(
        f"\nReview queue: {summary.review_queue_count:,} records "
        f"({summary.high_priority_count:,} high · {summary.medium_priority_count:,} medium)"
    )
    if summary.low_priority_omitted_count:
        print(
            f"{summary.low_priority_omitted_count:,} low-priority changes are below the default review "
            "threshold; inspect with --detail review-queue --priority low --category raw_metadata."
        )
    if summary.other_priority_count:
        print(f"Other review priorities: {summary.other_priority_count:,}")
    if summary.high_priority_count:
        print("High priority")
    if summary.table_size_changes:
        print(f"  Enumeration-table size changes: {summary.table_size_changes}")
        size_changes = diff.review_queue(
            limit=10, compatibility="potentially_breaking", scope="enumeration_table"
        ).changes
        for change in (row for row in size_changes if row.scope == "enumeration_table"):
            delta = next((field for field in change.fields if field.name == "size"), None)
            print(
                f"  {change.label} — UID {change.table_uid}: "
                f"declared width {delta.before if delta else '?'} → {delta.after if delta else '?'} bits"
                " · Potentially breaking"
            )
    if summary.new_deprecations:
        print(f"  {summary.new_deprecations:,} newly deprecated records — inspect migration impact")
    if summary.newly_retired:
        print(f"  {summary.newly_retired:,} newly retired records — inspect lifecycle impact")
    other_high = (
        summary.high_priority_count
        - summary.table_size_changes
        - summary.new_deprecations
        - summary.newly_retired
    )
    if other_high > 0:
        excluded = {"size", "deprecated", "retired"}
        examples = [
            item
            for item in diff.review_queue(limit=20, priority="high").changes
            if item.review_priority == "high" and not {field.name for field in item.fields} & excluded
        ][:3]
        for item in examples:
            print(f"  {item.label}: {', '.join(field.name for field in item.fields)}")
    if summary.medium_priority_count:
        print(f"Medium priority: {summary.medium_priority_count:,} records")
        examples = diff.review_queue(limit=3, priority="medium").changes
        for item in examples:
            changes = _summary_delta_text(item)
            print(f"  {item.label}: {changes}")
    print(
        f"\nOther changes: {summary.status_cleanups:,} record-status cleanups · "
        f"{summary.table_status_cleanups:,} table-status cleanups · "
        f"{summary.derived_changes:,} inherited path-label changes"
    )
    print("Routine groups are summarized; every change remains available in concise and audit output.")


def render_diff_summary(diff: EditionDiff) -> str:
    """Render the human-readable overview used by the CLI and report tools."""
    output = StringIO()
    with redirect_stdout(output):
        print_diff_text(diff)
    return output.getvalue()


def _summary_delta_text(change: ConciseChange) -> str:
    labels = {
        "path_labels": "inherited path labels updated",
        "change_requests": "change-request references updated",
    }
    return ", ".join(
        labels.get(field.name, f"{field.name}: {field.before!r} → {field.after!r}") for field in change.fields
    )


def print_review_queue_text(page: ReviewQueuePage) -> None:
    print(
        f"Review queue v{page.from_version} -> v{page.to_version}: "
        f"{len(page.changes)} of {page.total} records from offset {page.offset}"
    )
    if page.low_priority_omitted_count:
        print(
            f"{page.low_priority_omitted_count:,} low-priority changes are below the default review "
            "threshold; use --priority low --category raw_metadata to include metadata changes."
        )
    for change in page.changes:
        details = _summary_delta_text(change)
        print(
            f"{change.review_priority} · wire {change.assessment.wire_encoding} · "
            f"lookup {change.assessment.identifier_resolution} · {change.action} · "
            f"{change.label or change.identifier}"
            + (f" — {details}" if details else "")
            + (f" · reasons: {', '.join(change.reason_codes)}" if change.reason_codes else "")
            + (f" · next: {', '.join(change.recommendation_codes)}" if change.recommendation_codes else "")
        )


def print_diff_detail_text(diff: EditionDiff, *, concise: bool) -> None:
    print(f"v{diff.from_version} -> v{diff.to_version}: {diff.total:,} changes ({diff.scope})")
    concise_changes = diff.concise().changes if concise else ()
    rows = (
        zip(diff.changes, concise_changes, strict=True)
        if concise
        else ((change, None) for change in diff.changes)
    )
    for change, concise_change in rows:
        if concise:
            assert concise_change is not None
            label = concise_change.label or concise_change.identifier
            if concise_change.action == "added" and concise_change.record_after is not None:
                record = concise_change.record_after
                print(
                    f"added: {concise_change.scope}: {record.label} "
                    f"[{record.stable_id or concise_change.identifier}]"
                )
                continue
            if concise_change.action == "removed" and concise_change.record_before is not None:
                record = concise_change.record_before
                print(
                    f"removed: {concise_change.scope}: {record.label} "
                    f"[{record.stable_id or concise_change.identifier}]"
                )
                continue
            deltas = ", ".join(
                f"{item.name}: {item.before!r} -> {item.after!r}" for item in concise_change.fields
            )
            print(f"{change.review_priority}: {change.scope}: {label} [{deltas}]")
        else:
            before = _record_summary(change.before) if change.before else "∅"
            after = _record_summary(change.after) if change.after else "∅"
            print(
                f"{change.action}: {change.scope}: {before} -> {after} [{', '.join(change.changed_fields)}]"
            )


def _record_summary(record: ValueRecord) -> str:
    if record.scope == "enumeration_table":
        location = f"table {record.table_uid}"
        label = record.name or ""
    else:
        value = (
            str(record.value)
            if record.value is not None
            else f"{record.value_min}..{record.value_max}"
            if record.value_min is not None and record.value_max is not None
            else ""
        )
        if record.scope == "entity":
            path = ".".join(map(str, record.path))
            location = path if record.value is not None else ".".join(part for part in (path, value) if part)
        else:
            location = f"table {record.table_uid}:{value}"
        label = record.description or ""
    return f"{location} {label}".strip()


def _inspection_value_text(value: EditionValue) -> str:
    item = (
        str(value.value)
        if value.value is not None
        else f"{value.value_min}..{value.value_max}"
        if value.value_min is not None and value.value_max is not None
        else "?"
    )
    if value.kind is EditionValueKind.ENTITY_TYPE:
        path = tuple(map(str, value.hierarchy_codes))
        location = ".".join(path if value.value is not None else (*path, item))
    else:
        location = f"table {value.table_uid}:{item}"
    text = f"{location}: {value.description or '<no description>'}"
    metadata: list[str] = []
    if value.uuid:
        metadata.append(f"uuid={value.uuid}")
    if value.status:
        metadata.append(f"status={value.status}")
    if value.deprecated:
        metadata.append("deprecated")
    return f"{text} ({', '.join(metadata)})" if metadata else text


def print_entity_query_text(result: EntityQueryResults) -> None:
    print(f"{result.title} ({result.date}) · {result.total:,} matching entity records")
    for value in result.values:
        print(_inspection_value_text(value))
    print(f"Showing {result.returned:,} records from offset {result.offset:,}")


def print_inspect_text(action: str, result: BaseModel) -> None:
    if isinstance(result, EditionSummary):
        print(f"{result.title} ({result.date})")
        print(
            f"tables={result.enumeration_tables:,}, value/path records={result.value_path_records:,} "
            f"(enumeration={result.enumeration_values:,}, entity={result.entity_values:,})"
        )
        print(f"entity levels: {result.entity_levels}; unclassified rows={result.unclassified_entity_rows}")
        print(
            f"deprecated records={result.deprecated_values:,}, "
            f"records with UUID={result.records_with_uuid:,}, "
            f"distinct UUIDs={result.distinct_uuid_values:,}, distinct value identities="
            f"{result.distinct_value_identities:,}, attached reference records="
            f"{result.attached_reference_records:,}, change-request entries={result.change_request_entries:,}"
        )
        return
    if isinstance(result, EditionDiagnostics):
        print(f"{result.title} ({result.date}): {result.total} diagnostic findings")
        print(f"severity counts: {result.severity_counts}; code counts: {result.counts}")
        for group in result.groups:
            table = f" · UID {group.table_uid} {group.table_name}" if group.table_uid is not None else ""
            print(f"{group.severity.value} {group.code}: {group.count:,}{table}")
        for finding in result.findings:
            print(f"{finding.severity.value} {finding.code}: {finding.message} [{finding.location}]")
        if result.truncated and result.limit != 0:
            print(f"Showing {result.returned} from offset {result.offset}; use --limit 0 for all.")
        return
    if isinstance(result, EnumerationValueResolution):
        print(f"table {result.table_uid}, value {result.value}: {result.status.value}")
        if result.status is EnumerationValueStatus.TABLE_NOT_FOUND:
            print("Enumeration table not found.")
        elif result.status is EnumerationValueStatus.AMBIGUOUS_TABLE:
            for table in result.tables:
                print(f"  candidate table: {table.name} (UID {table.uid})")
        for value in result.matches:
            print(_inspection_value_text(value))
        return
    if isinstance(result, EnumerationNameResolution):
        print(f"{result.name}, value {result.value}: {result.status.value}")
        if result.status.value == "table_not_found":
            print("No enumeration table has that exact name.")
        for resolved in result.matches:
            if resolved.status is EnumerationValueStatus.AMBIGUOUS_TABLE:
                for table in resolved.tables:
                    print(f"  candidate table: {table.name} (UID {table.uid})")
            table_name = resolved.table.name if resolved.table is not None else "<ambiguous table UID>"
            print(f"  {table_name} (UID {resolved.table_uid}): {resolved.status.value}")
            for value in resolved.matches:
                print(f"    {_inspection_value_text(value)}")
        return
    if isinstance(result, EditionTableResults):
        print(f"{result.title} ({result.date}): {result.total} enumeration tables")
        for table in result.tables:
            details = [f"uid={table.uid}", f"{table.entry_count} values"]
            if table.range_count:
                details.append(f"{table.range_count} ranges")
            if table.declared_size is not None:
                unit = "bit" if table.declared_size == 1 else "bits"
                details.append(f"declared width={table.declared_size} {unit}")
            if table.applicability:
                details.append(f"applies={table.applicability}")
            print(f"{table.name} ({'; '.join(details)})")
            for annotation in table.annotations:
                print(f"  {annotation.tag}: {annotation.text}")
        return
    if isinstance(result, EditionValueResults):
        values = result.values
        print(f"{result.title} ({result.date}): {result.total} values")
    elif isinstance(result, EditionSearchResults):
        values = result.hits
        print(f"{result.title} ({result.date}): {result.total} matches for {result.query!r}")
    elif isinstance(result, EditionUUIDResults):
        values = result.values
        print(f"{result.title} ({result.date}): {result.total} matches for UUID {result.uuid}")
    elif isinstance(result, EntityExplanation):
        resolution = result.resolution
        print("ENTITY INSPECTION")
        print(f"### {result.description}")
        print(f"Requested code: `{result.entity}`")
        if resolution.is_prefix:
            print(f"{resolution.human_outcome} — {resolution.matched_depth} of 7 components")
        else:
            print(
                f"{resolution.human_outcome} — {resolution.matched_depth} of "
                f"{resolution.requested_depth} supplied components matched"
            )
        if resolution.matched_path:
            labels = [value.description for value in resolution.matched_path if value.description]
            print(f"Matched hierarchy: {' / '.join(labels) if labels else '<source labels unavailable>'}")
        for component in resolution.not_supplied_components:
            print(f"Trailing {component.title()} component: Not supplied")
        if result.resolution.unspecified_components:
            print(f"Explicitly unspecified components: {', '.join(result.resolution.unspecified_components)}")
        if result.resolution.unresolved_components:
            print(f"Unknown supplied components: {', '.join(result.resolution.unresolved_components)}")
        else:
            print("Unknown supplied components: None")
        if resolution.ambiguous_candidates:
            print(f"Ambiguous source candidates: {len(resolution.ambiguous_candidates)}")
        for value in result.path:
            print(f"  {_inspection_value_text(value)}")
        return
    else:
        raise TypeError(f"Unsupported inspect result for {action}: {type(result).__name__}")
    for value in values:
        match_detail = (
            f" [matched via {', '.join(value.matched_fields)}]" if isinstance(value, EditionSearchHit) else ""
        )
        print(f"{_inspection_value_text(value)}{match_detail}")
    if getattr(result, "truncated", False):
        print(f"Showing {len(values)} of {result.total}; use --limit 0 for all.")

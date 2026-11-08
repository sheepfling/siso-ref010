"""CLI adapter for the public Python API. Use --text for people or --json for scripts."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from collections.abc import Mapping
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from typing import BinaryIO, NoReturn, NotRequired, TypedDict, cast

from pydantic import BaseModel

from ._version import __version__
from .api import Collection, EntityQueryResults, EntityTypeAPI, decode_key, encode_entity
from .comparison import (
    ApplicationMigration,
    ChangeAction,
    ChangeCategory,
    ChangeCounts,
    Compatibility,
    ConciseChange,
    EditionDiff,
    ReviewPriority,
    ReviewQueuePage,
    SemanticMeaning,
    ValueHistory,
    ValueRecord,
)
from .errors import EntityTypeError
from .inspection import (
    EditionDiagnostics,
    EditionReport,
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
)
from .model import EntityTypePrefix
from .reporting import render_json_envelope, render_markdown, render_terminal
from .sources import BUNDLED_STANDARD_SOURCE

JSON_SCHEMA_VERSION = 1


class _CliErrorPayload(TypedDict):
    type: str
    message: str
    code: NotRequired[str]
    context: NotRequired[Mapping[str, object]]


def _json_result(command: str, result: BaseModel) -> None:
    if isinstance(result, EditionReport):
        print(
            render_json_envelope(
                result,
                command=command,
                schema_version=JSON_SCHEMA_VERSION,
            )
        )
        return
    print(
        json.dumps(
            {
                "schema_version": JSON_SCHEMA_VERSION,
                "command": command,
                "result": result.model_dump(mode="json", by_alias=True),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def _error(
    message: str,
    error_type: str,
    command: str | None,
    package_error: EntityTypeError | None = None,
) -> None:
    error: _CliErrorPayload = {"type": error_type, "message": message}
    if package_error is not None:
        error["code"] = package_error.code
        error["context"] = package_error.context
    # Keep diagnostics on stderr so successful JSON output on stdout stays parseable.
    print(
        json.dumps(
            {
                "schema_version": JSON_SCHEMA_VERSION,
                "command": command,
                "error": error,
            },
            ensure_ascii=False,
        ),
        file=sys.stderr,
    )


def _error_type(error: Exception) -> str:
    if isinstance(error, TypeError):
        return "TypeError"
    if isinstance(error, ValueError):
        return "ValueError"
    if isinstance(error, IndexError):
        return "IndexError"
    return type(error).__name__


class _ArgumentParser(argparse.ArgumentParser):
    json_errors = False

    def error(self, message: str) -> NoReturn:
        if self.json_errors:
            _error(message, "ArgumentError", None)
            self.exit(2)
        super().error(message)


def _output_options(
    parser: argparse.ArgumentParser,
    *,
    root: bool = False,
    include_text: bool = True,
) -> None:
    group = parser.add_mutually_exclusive_group()
    default = "text" if root else argparse.SUPPRESS
    group.add_argument(
        "--json",
        dest="output_format",
        action="store_const",
        const="json",
        default=default,
        help="Versioned JSON result on stdout; structured errors on stderr",
    )
    if include_text:
        group.add_argument(
            "--text",
            dest="output_format",
            action="store_const",
            const="text",
            default=default,
            help="Human-readable text output",
        )


def _parser(*, json_errors: bool = False) -> _ArgumentParser:
    parser = _ArgumentParser(
        description=__doc__, epilog="Python API: from dis_entity_types.api import EntityTypeAPI"
    )
    parser.json_errors = json_errors
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    standard_source = parser.add_mutually_exclusive_group()
    standard_source.add_argument("--xml", type=Path, help="Use a different SISO-REF-010 XML source")
    standard_source.add_argument(
        "--standard-version", type=int, help="Use a bundled SISO-REF-010 edition, such as 35"
    )
    parser.add_argument(
        "--warmup",
        action="store_true",
        help="Build the selected edition's entity-query indexes before running the command",
    )
    _output_options(parser, root=True)
    commands = parser.add_subparsers(dest="command", required=True)
    describe = commands.add_parser("describe", help="Describe a seven-field entity type")
    describe.add_argument("entity")
    describe.add_argument(
        "--qualified", action="store_true", help="Use full description in text/default output"
    )
    search = commands.add_parser("search", help="Search descriptions (case-insensitive substring)")
    search.add_argument("query")
    search.add_argument("--limit", type=int, default=20, help="Maximum results, 0 means all (default: 20)")
    query = commands.add_parser("query", help="Filter entity records by code fields and description text")
    query.add_argument("--entity-kind", type=int, help="DIS entity kind code")
    query.add_argument("--domain", type=int, help="DIS domain code")
    query.add_argument("--country", type=int, help="DIS country code")
    query.add_argument("--category", type=int, help="DIS category code")
    query.add_argument("--subcategory", type=int, help="DIS subcategory code")
    query.add_argument("--specific", type=int, help="DIS specific code")
    query.add_argument("--extra", type=int, help="DIS extra code")
    query.add_argument("--text", help="Case-insensitive text in source descriptions or hierarchy paths")
    query.add_argument("--limit", type=int, default=100, help="Maximum results, 0 means all")
    query.add_argument("--offset", type=int, default=0, help="Skip this many matching records")
    listing = commands.add_parser("list", help="List choices beneath a parent prefix")
    listing.add_argument("collection", choices=tuple(Collection))
    listing.add_argument(
        "parents",
        nargs="*",
        type=int,
        help="Required parents: kind domain country category subcategory specific",
    )
    key = commands.add_parser("key", help="Encode an entity or decode a decimal/0x 64-bit key")
    key.add_argument("value")
    key.add_argument("--decode", action="store_true")
    info = commands.add_parser("info", help="Source, version and actual catalog counts")
    versions = commands.add_parser("versions", help="List bundled SISO-REF-010 editions")
    history = commands.add_parser("history", help="Inspect one entity or enumeration value across editions")
    history_target = history.add_mutually_exclusive_group(required=True)
    history_target.add_argument("--entity", help="Seven-field entity code, for example 1.3.153.6.4.2.0")
    history_target.add_argument("--enum-uid", type=int, help="Enumeration table UID")
    history.add_argument("--value", type=int, help="Enumeration value (requires --enum-uid)")
    history.add_argument("--versions", nargs="+", type=int, help="Editions to inspect; defaults to all")
    compare = commands.add_parser("compare", help="Compare values between two SISO-REF-010 editions")
    compare.add_argument("from_version", type=int)
    compare.add_argument("to_version", type=int)
    compare.add_argument("--scope", choices=("all", "entities", "enumerations"), default="all")
    comparison_filter = compare.add_mutually_exclusive_group()
    comparison_filter.add_argument("--entity-prefix", help="Filter entities by dotted code prefix")
    comparison_filter.add_argument("--enum-uid", type=int, help="Filter to one enumeration table UID")
    compare.add_argument("--limit", type=int, default=100, help="Maximum detail records; 0 means all")
    compare.add_argument(
        "--detail",
        choices=("summary", "concise", "audit", "review-queue"),
        help="Select summary, concise, audit, or paged review-queue output",
    )
    compare.add_argument("--offset", type=int, default=0, help="Review-queue page offset")
    compare.add_argument(
        "--priority", choices=("high", "medium", "low", "none"), help="Filter review-queue priority"
    )
    compare.add_argument(
        "--wire-encoding",
        "--compatibility",
        dest="wire_encoding",
        choices=(
            "unchanged",
            "additive",
            "potentially_breaking",
            "breaking",
            "not_applicable",
            "not_assessed",
        ),
        help="Filter review-queue wire-encoding assessment (--compatibility is an alias)",
    )
    compare.add_argument(
        "--identifier-resolution",
        choices=(
            "unchanged",
            "additive",
            "potentially_breaking",
            "breaking",
            "not_applicable",
            "not_assessed",
        ),
        help="Filter review-queue identifier-resolution assessment",
    )
    compare.add_argument(
        "--semantic-meaning",
        choices=("unchanged", "changed", "not_applicable", "not_assessed"),
        help="Filter review-queue semantic-meaning assessment",
    )
    compare.add_argument(
        "--application-migration",
        choices=("none", "recommended", "required", "not_applicable", "not_assessed"),
        help="Filter review-queue application-migration assessment",
    )
    compare.add_argument(
        "--action",
        choices=("added", "removed", "modified", "moved", "recoded"),
        help="Filter review-queue action",
    )
    compare.add_argument(
        "--category",
        choices=("semantic", "relationship", "lifecycle", "documentation", "provenance", "raw_metadata"),
        help="Filter by change category; includes matching low-priority records",
    )
    compare.add_argument(
        "--material-only", action="store_true", help="Hide changes assessed as non-material in all dimensions"
    )
    inspect = commands.add_parser("inspect", help="Inspect one edition's tables, values, and metadata")
    inspection = inspect.add_subparsers(dest="inspect_action", required=True)
    summary = inspection.add_parser("summary", help="Count values and metadata in the selected edition")
    report = inspection.add_parser("report", help="Build an edition overview with identity and diagnostics")
    report.add_argument("--audit", action="store_true", help="Include complete table and diagnostic rows")
    report.add_argument(
        "--format",
        choices=("text", "markdown", "json"),
        dest="report_format",
        help="Select the report renderer",
    )
    diagnostics = inspection.add_parser(
        "diagnostics", help="Group source findings; add --details to list individual findings"
    )
    diagnostics.add_argument("--details", action="store_true", help="List individual findings")
    diagnostics.add_argument("--limit", type=int, default=100, help="Maximum detailed findings, 0 means all")
    diagnostics.add_argument(
        "--offset", type=int, default=0, help="Skip detailed findings (requires --details)"
    )
    diagnostics.add_argument("--code", help="Filter by diagnostic code")
    diagnostics.add_argument("--table-uid", type=int, help="Filter findings attached to one source table")
    diagnostics.add_argument("--severity", choices=("error", "warning", "info"))
    tables = inspection.add_parser("tables", help="List enumeration tables and their annotations")
    tables.add_argument("--query", help="Filter table name or applicability")
    values = inspection.add_parser("values", help="List source values with optional metadata filters")
    values.add_argument("--kind", choices=tuple(kind.value for kind in EditionValueKind))
    values.add_argument("--table-uid", type=int, help="Limit to one enumeration table")
    values.add_argument("--status", help="Match an exact source status attribute")
    deprecated = values.add_mutually_exclusive_group()
    deprecated.add_argument("--deprecated", dest="deprecated", action="store_true")
    deprecated.add_argument("--not-deprecated", dest="deprecated", action="store_false")
    values.set_defaults(deprecated=None)
    values.add_argument("--limit", type=int, default=100, help="Maximum results, 0 means all")
    value_search = inspection.add_parser("search", help="Search source values and metadata")
    value_search.add_argument("query")
    value_search.add_argument("--limit", type=int, default=100, help="Maximum results, 0 means all")
    value_search.add_argument("--offset", type=int, default=0, help="Skip this many results")
    enum_value = inspection.add_parser("value", help="Resolve a value in one enumeration table")
    enum_value.add_argument("table_uid", type=int)
    enum_value.add_argument("value", type=int)
    uuid_lookup = inspection.add_parser("uuid", help="Find source values by UUID")
    uuid_lookup.add_argument("uuid")
    entity = inspection.add_parser("entity", help="Explain the hierarchy path for one entity code")
    entity.add_argument("entity")
    dump = commands.add_parser("dump", help="Write original XML bytes from bundled editions")
    dump.add_argument("version", nargs="?", type=int, help="Edition number to write to stdout or --output")
    dump.add_argument("--all", action="store_true", help="Write every bundled edition")
    dump.add_argument("--output", type=Path, help="File path for one edition; refuses to overwrite")
    dump.add_argument("--output-dir", type=Path, help="Directory for --all; refuses to overwrite files")
    inspect_commands = (
        summary,
        report,
        diagnostics,
        tables,
        values,
        value_search,
        enum_value,
        uuid_lookup,
        entity,
    )
    for child in (
        describe,
        search,
        query,
        listing,
        key,
        info,
        versions,
        history,
        compare,
        inspect,
        *inspect_commands,
        dump,
    ):
        child.json_errors = json_errors
    for child in (describe, search, query, listing, key, info, versions, history, compare, *inspect_commands):
        # ``query --text`` is a search filter; that spelling takes precedence
        # over the optional output-format override on this one subcommand.
        _output_options(child, include_text=child is not query)
    return parser


def _write_new_file(path: Path, data: bytes) -> None:
    """Write an export without replacing a file that is already present."""
    with path.open("xb") as stream:
        stream.write(data)


def _dump_bundled(args: argparse.Namespace, *, machine: bool) -> None:
    if machine:
        raise ValueError("dump writes raw XML bytes and cannot use --json")
    version = cast(int | None, args.version)
    output = cast(Path | None, args.output)
    output_dir = cast(Path | None, args.output_dir)
    all_versions = cast(bool, args.all)

    if all_versions:
        if version is not None or output is not None or output_dir is None:
            raise ValueError("dump --all requires --output-dir and cannot use a version or --output")
        output_dir.mkdir(parents=True, exist_ok=True)
        targets = tuple((item, output_dir / f"v{item}.xml") for item in BUNDLED_STANDARD_SOURCE.versions)
        existing = tuple(path for _, path in targets if path.exists())
        if existing:
            raise FileExistsError(f"Refusing to overwrite {existing[0]}")
        for item, path in targets:
            _write_new_file(path, BUNDLED_STANDARD_SOURCE.read_xml(item))
        print(f"Wrote {len(targets)} editions to {output_dir}")
        return

    if version is None:
        raise ValueError("dump requires an edition number or --all")
    if output_dir is not None:
        raise ValueError("--output-dir can only be used with dump --all")
    data = BUNDLED_STANDARD_SOURCE.read_xml(version)
    if output is None:
        raw_stream = getattr(sys.stdout, "buffer", None)
        if raw_stream is None:
            raise OSError("stdout does not support binary output; use --output")
        stream = cast(BinaryIO, raw_stream)
        stream.write(data)
        stream.flush()
    else:
        _write_new_file(output, data)
        print(f"Wrote v{version} to {output}")


def _history_text(history: ValueHistory) -> None:
    print(f"{history.kind} history: {history.target}")
    for point in history.points:
        if not point.present:
            print(f"v{point.version}: absent")
            continue
        description = point.description if point.description is not None else point.name or "present"
        suffix = f" ({point.qualified_description})" if point.qualified_description else ""
        print(f"v{point.version}: {description}{suffix}")


def _diff_text(diff: EditionDiff) -> None:
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
    if diff.truncated:
        print(f"Showing {len(diff.changes)} of {diff.total}; increase --limit or use --limit 0.")


def render_diff_summary(diff: EditionDiff) -> str:
    """Render the human-readable overview used by the CLI and report tools."""
    output = StringIO()
    with redirect_stdout(output):
        _diff_text(diff)
    return output.getvalue()


def _summary_delta_text(change: ConciseChange) -> str:
    labels = {
        "path_labels": "inherited path labels updated",
        "change_requests": "change-request references updated",
    }
    return ", ".join(
        labels.get(field.name, f"{field.name}: {field.before!r} → {field.after!r}") for field in change.fields
    )


def _review_queue_text(page: ReviewQueuePage) -> None:
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


def _diff_detail_text(diff: EditionDiff, *, concise: bool) -> None:
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


def _entity_query_text(result: EntityQueryResults) -> None:
    print(f"{result.title} ({result.date}) · {result.total:,} matching entity records")
    for value in result.values:
        print(_inspection_value_text(value))
    print(f"Showing {result.returned:,} records from offset {result.offset:,}")


def _inspect_text(action: str, result: BaseModel) -> None:
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
        if result.table is None:
            print("Enumeration table not found.")
        for value in result.matches:
            print(_inspection_value_text(value))
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


def _parse_entity_prefix(value: str) -> tuple[int, ...]:
    try:
        fields = tuple(int(part) for part in value.split("."))
    except ValueError as error:
        raise ValueError("--entity-prefix must be dotted decimal fields, such as 1.3.153") from error
    if not 3 <= len(fields) <= 7 or any(field < 0 for field in fields):
        raise ValueError("--entity-prefix must contain 3 through 7 nonnegative dotted fields")
    return fields


def _compare_result(args: argparse.Namespace) -> EditionDiff:
    entity_prefix = _parse_entity_prefix(args.entity_prefix) if args.entity_prefix is not None else None
    return EntityTypeAPI.compare_editions(
        args.from_version,
        args.to_version,
        scope=args.scope,
        entity_prefix=entity_prefix,
        enumeration_uid=args.enum_uid,
        limit=None
        if args.detail in (None, "summary", "review-queue") or args.limit == 0 or args.material_only
        else args.limit,
    )


def _filtered_diff(result: EditionDiff, args: argparse.Namespace) -> EditionDiff:
    if not args.material_only:
        return result
    material = tuple(change for change in result.changes if change.assessment.is_material)
    return result.model_copy(
        update={
            "changes": material,
            "total": len(material),
            "truncated": False,
            "counts": ChangeCounts(**dict(Counter(change.action for change in material))),
        }
    )


def _review_queue_page(result: EditionDiff, args: argparse.Namespace) -> ReviewQueuePage:
    priority = cast(ReviewPriority | None, args.priority)
    compatibility = cast(Compatibility | None, args.wire_encoding)
    action = cast(ChangeAction | None, args.action)
    category = cast(ChangeCategory | None, args.category)
    identifier_resolution = cast(Compatibility | None, args.identifier_resolution)
    semantic_meaning = cast(SemanticMeaning | None, args.semantic_meaning)
    application_migration = cast(ApplicationMigration | None, args.application_migration)
    offset = cast(int, args.offset)

    def page(limit: int) -> ReviewQueuePage:
        return result.review_queue(
            limit=limit,
            offset=offset,
            priority=priority,
            compatibility=compatibility,
            action=action,
            category=category,
            identifier_resolution=identifier_resolution,
            semantic_meaning=semantic_meaning,
            application_migration=application_migration,
        )

    if args.limit == 0:
        probe = page(1)
        limit = max(probe.total - offset, 1)
    else:
        limit = cast(int, args.limit)
    return page(limit)


def _handle_compare(args: argparse.Namespace, command: str, machine: bool) -> None:
    if args.xml is not None or args.standard_version is not None:
        raise ValueError(f"{command} uses the bundled version source; remove --xml/--standard-version")
    result = _filtered_diff(_compare_result(args), args)
    detail = args.detail or ("audit" if machine else "summary")
    if detail == "review-queue":
        queue = _review_queue_page(result, args)
        if machine:
            _json_result(command, queue)
        else:
            _review_queue_text(queue)
        return
    if args.material_only and detail != "summary" and args.limit > 0:
        selected = result.changes[: args.limit]
        result = result.model_copy(update={"changes": selected, "truncated": len(selected) < result.total})
    if detail == "summary":
        output_result = result.summary()
    elif detail == "concise":
        output_result = result.concise()
    else:
        output_result = result
    if machine:
        _json_result(command, output_result)
    elif detail == "summary":
        _diff_text(result)
    else:
        _diff_detail_text(result, concise=detail == "concise")


def _inspect_result(action: str, args: argparse.Namespace, api: EntityTypeAPI) -> BaseModel:
    inspector = api.inspector
    if action == "summary":
        return inspector.summary()
    if action == "report":
        return inspector.report(audit=cast(bool, args.audit))
    if action == "diagnostics":
        limit = cast(int, args.limit)
        offset = cast(int, args.offset)
        if limit < 0 or offset < 0:
            raise ValueError("--limit and --offset must be nonnegative")
        details = cast(bool, args.details)
        if offset and not details:
            raise ValueError("--offset requires --details")
        return inspector.diagnostics(
            limit=(None if limit == 0 else limit) if details else 0,
            offset=offset,
            code=cast(str | None, args.code),
            table_uid=cast(int | None, args.table_uid),
            severity=cast(str | None, args.severity),
        )
    if action == "tables":
        return inspector.enumeration_table_results(cast(str | None, args.query))
    if action == "values":
        kind_text = cast(str | None, args.kind)
        table_uid = cast(int | None, args.table_uid)
        limit = cast(int, args.limit)
        if table_uid is not None and table_uid < 0:
            raise ValueError("--table-uid must be nonnegative")
        if limit < 0:
            raise ValueError("--limit must be nonnegative")
        return inspector.value_results(
            kind=EditionValueKind(kind_text) if kind_text is not None else None,
            table_uid=table_uid,
            status=cast(str | None, args.status),
            deprecated=cast(bool | None, args.deprecated),
            limit=None if limit == 0 else limit,
        )
    if action == "search":
        limit = cast(int, args.limit)
        offset = cast(int, args.offset)
        if limit < 0 or offset < 0:
            raise ValueError("--limit and --offset must be nonnegative")
        return inspector.search_page(
            cast(str, args.query), limit=None if limit == 0 else limit, offset=offset
        )
    if action == "value":
        table_uid = cast(int, args.table_uid)
        value = cast(int, args.value)
        if table_uid < 0 or value < 0:
            raise ValueError("table UID and value must be nonnegative")
        return inspector.resolve_enumeration_value(table_uid, value)
    if action == "uuid":
        return inspector.uuid_results(cast(str, args.uuid))
    if action == "entity":
        return api.explain_entity(cast(str, args.entity))
    raise ValueError(f"Unknown inspect action: {action}")


def _handle_api_command(command: str, args: argparse.Namespace, machine: bool, api: EntityTypeAPI) -> None:
    if command == "inspect":
        action = cast(str, args.inspect_action)
        result = _inspect_result(action, args, api)
        if action == "report":
            report = cast(EditionReport, result)
            report_format = cast(str | None, args.report_format)
            selected_format = report_format or ("json" if machine else "text")
            if selected_format == "markdown":
                print(render_markdown(report), end="")
            elif selected_format == "json":
                _json_result(f"inspect.{action}", report)
            else:
                print(render_terminal(report), end="")
            return
        if machine:
            _json_result(f"inspect.{action}", result)
        else:
            _inspect_text(action, result)
    elif command == "info":
        info = api.info()
        if machine:
            _json_result(command, info)
            return
        print(
            f"dis-entity-types {info.version}\nData: {info.data_source}\n"
            f"Data version: {info.data_version or 'unspecified'}"
        )
        for label, count in (
            ("countries", info.counts.countries),
            ("kinds", info.counts.kinds),
            ("domains", info.counts.domains),
            ("categories", info.counts.categories),
            ("subcategories", info.counts.subcategories),
        ):
            print(f"{label}: {count}")
    elif command == "describe":
        description = api.describe(cast(str, args.entity))
        if machine:
            _json_result(command, description)
        else:
            print(description.qualified_description if args.qualified else description.description)
    elif command == "search":
        limit = cast(int, args.limit)
        results = api.search(cast(str, args.query), limit=None if limit == 0 else limit)
        if machine:
            _json_result(command, results)
        else:
            for hit in results.hits:
                print(f"{hit.entity}: {hit.description}")
            print(f"{len(results.hits)} of {results.total} matches")
        if results.truncated and not machine:
            print(
                f"Showing {len(results.hits)} of {results.total} results; use --limit 0 for all.",
                file=sys.stderr,
            )
    elif command == "query":
        result = api.query_entities(
            entity_kind=cast(int | None, args.entity_kind),
            domain=cast(int | None, args.domain),
            country=cast(int | None, args.country),
            category=cast(int | None, args.category),
            subcategory=cast(int | None, args.subcategory),
            specific=cast(int | None, args.specific),
            extra=cast(int | None, args.extra),
            text=cast(str | None, args.text),
            limit=None if args.limit == 0 else cast(int, args.limit),
            offset=cast(int, args.offset),
        )
        if machine:
            _json_result(command, result)
        else:
            _entity_query_text(result)
    elif command == "list":
        prefix = EntityTypePrefix.from_values(tuple(cast(list[int], args.parents)))
        choices = api.choices(cast(str, args.collection), prefix)
        if machine:
            _json_result(command, choices)
        else:
            for choice in choices.items:
                print(f"{choice.value}: {choice.description}")


def _handle_command(command: str, args: argparse.Namespace, machine: bool) -> None:
    if args.warmup and command in {"versions", "dump", "history", "compare", "key"}:
        raise ValueError("--warmup applies only to commands that load an edition API")
    if command == "versions":
        bundled = EntityTypeAPI.bundled_versions()
        if machine:
            _json_result(command, bundled)
        else:
            print(f"Bundled SISO-REF-010 versions (default: {bundled.default_version}):")
            for version in bundled.versions:
                suffix = " (default)" if version == bundled.default_version else ""
                print(f"{version}{suffix}")
    elif command == "dump":
        if args.xml is not None or args.standard_version is not None:
            raise ValueError("dump reads bundled editions; select its version after the dump command")
        _dump_bundled(args, machine=machine)
    elif command == "history":
        if args.xml is not None or args.standard_version is not None:
            raise ValueError("history uses the bundled version source; remove --xml/--standard-version")
        if args.value is not None and args.enum_uid is None:
            raise ValueError("history --value requires --enum-uid")
        if args.entity is not None:
            result = EntityTypeAPI.entity_history(args.entity, versions=args.versions)
        else:
            result = EntityTypeAPI.enumeration_history(
                cast(int, args.enum_uid), args.value, versions=args.versions
            )
        if machine:
            _json_result(command, result)
        else:
            _history_text(result)
    elif command == "compare":
        _handle_compare(args, command, machine)
    elif command == "key":
        encoding = decode_key(cast(str, args.value)) if args.decode else encode_entity(cast(str, args.value))
        if machine:
            _json_result(command, encoding)
        else:
            print(
                f"Entity: {encoding.entity}\nKey: {encoding.key}\nUnsigned key: {encoding.unsigned_key}"
                f"\nWire bytes: {encoding.wire_bytes.hex()}"
            )
    else:
        if args.xml is not None:
            api = EntityTypeAPI.from_xml(cast(Path, args.xml))
        elif args.standard_version is not None:
            api = EntityTypeAPI.bundled(cast(int, args.standard_version))
        else:
            api = EntityTypeAPI()
        if args.warmup:
            result = api.warmup()
            if not machine:
                count = (
                    f"{result.indexed_records:,} source rows"
                    if result.indexed_records is not None
                    else "query indexes"
                )
                print(
                    f"Warmed {result.backend} for {result.title} ({result.date}): {count}",
                    file=sys.stderr,
                )
        _handle_api_command(command, args, machine, api)


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:]) if argv is None else argv
    # Resolve presentation before argparse can fail. Respect subcommand overrides
    # and stop at '--', after which these spellings are positional data.
    requested_format = "text"
    for argument in arguments:
        if argument == "--":
            break
        if argument in ("--json", "--text"):
            requested_format = argument[2:]
    parser = _parser(json_errors=requested_format == "json")
    args = parser.parse_args(arguments)
    command = cast(str, args.command)
    machine = cast(str, args.output_format) == "json"
    try:
        _handle_command(command, args, machine)
    except EntityTypeError as exc:
        if machine:
            _error(str(exc), _error_type(exc), command, exc)
            parser.exit(2)
        parser.exit(2, f"{parser.prog}: error: {exc}\n")
    except (ValueError, TypeError, OSError) as exc:
        if machine:
            _error(str(exc), type(exc).__name__, command)
            parser.exit(2)
        parser.exit(2, f"{parser.prog}: error: {exc}\n")
    except KeyboardInterrupt:
        if machine:
            _error("Interrupted.", "Interrupted", command)
        else:
            print("\nInterrupted.", file=sys.stderr)
        return 130
    return 0

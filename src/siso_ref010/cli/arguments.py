"""Build the supported command-line argument tree."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import NoReturn

from .._version import __version__
from ..api import Collection
from ..inspection import EditionValueKind
from .output import write_json_error


class _ArgumentParser(argparse.ArgumentParser):
    json_errors = False

    def error(self, message: str) -> NoReturn:
        if self.json_errors:
            write_json_error(message, "ArgumentError", None)
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


def build_parser(*, json_errors: bool = False) -> _ArgumentParser:
    parser = _ArgumentParser(description=__doc__, epilog="Python API: from siso_ref010 import SisoRef010API")
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
        help="Select output detail (defaults to summary for text and JSON)",
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
    enum_resolve = inspection.add_parser("resolve", help="Resolve a value by exact enumeration table name")
    enum_resolve.add_argument("name", help="Exact table name; matching ignores case and outer whitespace")
    enum_resolve.add_argument("value", type=int)
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
        enum_resolve,
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

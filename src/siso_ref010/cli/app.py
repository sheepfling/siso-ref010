"""CLI adapter for the public Python API. Use --text for people or --json for scripts."""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import BinaryIO, cast

from pydantic import BaseModel

from ..api import (
    SisoRef010API,
    decode_key,
    encode_entity,
)
from ..comparison import (
    ApplicationMigration,
    ChangeAction,
    ChangeCategory,
    ChangeCounts,
    Compatibility,
    EditionDiff,
    ReviewPriority,
    ReviewQueuePage,
    SemanticMeaning,
)
from ..errors import SisoRef010Error
from ..inspection import (
    EditionReport,
    EditionValueKind,
)
from ..models.entity import EntityTypePrefix
from ..reporting import render_markdown, render_terminal
from ..sources import BUNDLED_STANDARD_SOURCE
from .arguments import build_parser
from .output import error_type, write_json_error, write_json_result
from .text import (
    print_diff_detail_text,
    print_diff_text,
    print_entity_query_text,
    print_history_text,
    print_inspect_text,
    print_review_queue_text,
)


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
    available_versions = BUNDLED_STANDARD_SOURCE.versions
    if type(version) is not int or version not in available_versions:
        raise ValueError(
            f"SISO-REF-010 version {version!r} is unavailable; available versions: {available_versions}"
        )
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
    return SisoRef010API.compare_editions(
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
            write_json_result(command, queue)
        else:
            print_review_queue_text(queue)
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
        write_json_result(command, output_result)
    elif detail == "summary":
        print_diff_text(result)
    else:
        print_diff_detail_text(result, concise=detail == "concise")


def _inspect_result(action: str, args: argparse.Namespace, api: SisoRef010API) -> BaseModel:
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
    if action == "resolve":
        return api.resolve_enumeration(cast(str, args.name), cast(int, args.value))
    if action == "uuid":
        return inspector.uuid_results(cast(str, args.uuid))
    if action == "entity":
        return api.explain_entity(cast(str, args.entity))
    raise ValueError(f"Unknown inspect action: {action}")


def _handle_api_command(command: str, args: argparse.Namespace, machine: bool, api: SisoRef010API) -> None:
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
                write_json_result(f"inspect.{action}", report)
            else:
                print(render_terminal(report), end="")
            return
        if machine:
            write_json_result(f"inspect.{action}", result)
        else:
            print_inspect_text(action, result)
    elif command == "info":
        info = api.info()
        if machine:
            write_json_result(command, info)
            return
        print(
            f"siso-ref010 {info.version}\nData: {info.data_source}\n"
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
            write_json_result(command, description)
        else:
            print(description.qualified_description if args.qualified else description.description)
    elif command == "search":
        limit = cast(int, args.limit)
        results = api.search(cast(str, args.query), limit=None if limit == 0 else limit)
        if machine:
            write_json_result(command, results)
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
            write_json_result(command, result)
        else:
            print_entity_query_text(result)
    elif command == "list":
        prefix = EntityTypePrefix.from_values(tuple(cast(list[int], args.parents)))
        choices = api.choices(cast(str, args.collection), prefix)
        if machine:
            write_json_result(command, choices)
        else:
            for choice in choices.items:
                suffix = " (ambiguous source code)" if choice.ambiguous else ""
                print(f"{choice.value}: {choice.description}{suffix}")


def _handle_command(command: str, args: argparse.Namespace, machine: bool) -> None:
    if args.warmup and command in {"versions", "dump", "history", "compare", "key"}:
        raise ValueError("--warmup applies only to commands that load an edition API")
    if command == "versions":
        bundled = SisoRef010API.bundled_versions()
        if machine:
            write_json_result(command, bundled)
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
            result = SisoRef010API.entity_history(args.entity, versions=args.versions)
        else:
            result = SisoRef010API.enumeration_history(
                cast(int, args.enum_uid), args.value, versions=args.versions
            )
        if machine:
            write_json_result(command, result)
        else:
            print_history_text(result)
    elif command == "compare":
        _handle_compare(args, command, machine)
    elif command == "key":
        encoding = decode_key(cast(str, args.value)) if args.decode else encode_entity(cast(str, args.value))
        if machine:
            write_json_result(command, encoding)
        else:
            print(
                f"Entity: {encoding.entity}\nKey: {encoding.key}\nUnsigned key: {encoding.unsigned_key}"
                f"\nWire bytes: {encoding.wire_bytes.hex()}"
            )
    else:
        if args.xml is not None:
            api = SisoRef010API.from_xml(cast(Path, args.xml))
        elif args.standard_version is not None:
            api = SisoRef010API.bundled(cast(int, args.standard_version))
        else:
            api = SisoRef010API()
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


def _configure_cli_output_encoding() -> None:
    """Use UTF-8 for executable CLI output on every supported Python version."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    if argv is None:
        _configure_cli_output_encoding()
    arguments = list(sys.argv[1:] if argv is None else argv)
    # Resolve presentation before argparse can fail. Respect subcommand overrides
    # and stop at '--', after which these spellings are positional data.
    requested_format = "text"
    for argument in arguments:
        if argument == "--":
            break
        if argument in ("--json", "--text"):
            requested_format = argument[2:]
    parser = build_parser(json_errors=requested_format == "json")
    args = parser.parse_args(arguments)
    command = cast(str, args.command)
    machine = cast(str, args.output_format) == "json"
    try:
        _handle_command(command, args, machine)
    except SisoRef010Error as exc:
        if machine:
            write_json_error(str(exc), error_type(exc), command, exc)
            parser.exit(2)
        parser.exit(2, f"{parser.prog}: error: {exc}\n")
    except (ValueError, TypeError, OSError) as exc:
        if machine:
            write_json_error(str(exc), type(exc).__name__, command)
            parser.exit(2)
        parser.exit(2, f"{parser.prog}: error: {exc}\n")
    except KeyboardInterrupt:
        if machine:
            write_json_error("Interrupted.", "Interrupted", command)
        else:
            print("\nInterrupted.", file=sys.stderr)
        return 130
    return 0

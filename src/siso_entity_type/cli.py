"""CLI adapter for the public Python API. Use --text for people or --json for scripts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import NoReturn, cast

from ._version import __version__
from .api import Collection, EntityTypeAPI, decode_key, encode_entity
from .catalog import SisoEnums
from .model import SisoEnum
from .parser import SisoEnumsParser

JSON_SCHEMA_VERSION = 1


def _json_result(command: str, result: object) -> None:
    print(
        json.dumps(
            {"schema_version": JSON_SCHEMA_VERSION, "command": command, "result": result},
            ensure_ascii=False,
            indent=2,
        )
    )


def _error(message: str, error_type: str, command: str | None) -> None:
    print(
        json.dumps(
            {
                "schema_version": JSON_SCHEMA_VERSION,
                "command": command,
                "error": {"type": error_type, "message": message},
            },
            ensure_ascii=False,
        ),
        file=sys.stderr,
    )


class _ArgumentParser(argparse.ArgumentParser):
    json_errors = False

    def error(self, message: str) -> NoReturn:
        if self.json_errors:
            _error(message, "ArgumentError", None)
            self.exit(2)
        super().error(message)


def _choose(label: str, options: dict[int, str], *, machine: bool = False) -> int:
    stream = sys.stderr if machine else sys.stdout
    for value, description in options.items():
        print(f"{value}: {description}", file=stream)
    while True:
        if machine:
            print(f"{label} [0]: ", end="", file=stream, flush=True)
            text = input("").strip()
        else:
            text = input(f"{label} [0]: ").strip()
        try:
            value = int(text) if text else 0
        except ValueError:
            print("Enter a listed number, or 0 for unspecified.", file=stream)
            continue
        if value == 0 or value in options:
            return value
        print("Enter a listed number, or 0 for unspecified.", file=stream)


def _pick(api: EntityTypeAPI, *, machine: bool = False) -> SisoEnum:
    def choose(label: str, collection: Collection, *parents: int) -> int:
        choices = api.choices(collection, *parents)
        return _choose(label, {choice.value: choice.description for choice in choices.items}, machine=machine)

    country = choose("Country", Collection.COUNTRIES)
    kind = choose("Kind", Collection.KINDS)
    domain = choose("Domain", Collection.DOMAINS, kind)
    category = choose("Category", Collection.CATEGORIES, kind, domain, country)
    subcategory = choose("Subcategory", Collection.SUBCATEGORIES, kind, domain, country, category)
    specific = choose("Specific", Collection.SPECIFICS, kind, domain, country, category, subcategory)
    extra = choose("Extra", Collection.EXTRAS, kind, domain, country, category, subcategory, specific)
    return SisoEnum(kind, domain, country, category, subcategory, specific, extra)


def pick(catalog: SisoEnums) -> SisoEnum:
    """Compatibility entry point for the interactive terminal picker."""
    return _pick(EntityTypeAPI(catalog))


def _output_options(parser: argparse.ArgumentParser, *, root: bool = False) -> None:
    group = parser.add_mutually_exclusive_group()
    default = "legacy" if root else argparse.SUPPRESS
    group.add_argument(
        "--json",
        dest="output_format",
        action="store_const",
        const="json",
        default=default,
        help="Versioned JSON result on stdout; structured errors on stderr",
    )
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
        description=__doc__, epilog="Python API: from siso_entity_type.api import EntityTypeAPI"
    )
    parser.json_errors = json_errors
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--data", type=Path, help="Custom JSON for describe/search/list/pick/info")
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
    parse = commands.add_parser("parse", help="Parse SISO XML into upstream-format JSON")
    parse.add_argument("input", type=Path)
    parse.add_argument("--output", type=Path, required=True, help="Output directory")
    parse.add_argument(
        "--qualified", action="store_true", help="Store joined descriptions (nondefault extension)"
    )
    picker = commands.add_parser("pick", help="Interactive terminal entity picker")
    info = commands.add_parser("info", help="Source, version and actual catalog counts")
    for child in (describe, search, listing, key, parse, picker, info):
        child.json_errors = json_errors
        _output_options(child)
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:]) if argv is None else argv
    # Resolve presentation before argparse can fail. Respect subcommand overrides
    # and stop at '--', after which these spellings are positional data.
    requested_format = "legacy"
    for argument in arguments:
        if argument == "--":
            break
        if argument in ("--json", "--text"):
            requested_format = argument[2:]
    parser = _parser(json_errors=requested_format == "json")
    args = parser.parse_args(arguments)
    command = cast(str, args.command)
    output_format = cast(str, args.output_format)
    machine = output_format == "json"
    human = output_format == "text"
    try:
        if command == "parse":
            parsed = SisoEnumsParser.from_file(cast(Path, args.input), qualified=bool(args.qualified))
            destination = parsed.write_output_files(cast(Path, args.output))
            if machine:
                _json_result(
                    command,
                    {
                        "output": str(destination),
                        "title": parsed.title,
                        "date": parsed.date,
                        "counts": {
                            "countries": parsed.country_count,
                            "kinds": parsed.kind_count,
                            "domains": parsed.domain_count,
                            "categories": parsed.category_count,
                            "subcategories": parsed.subcategory_count,
                        },
                    },
                )
            elif human:
                print(f"Wrote {destination}")
            else:
                print(destination)
            return 0
        if command == "key":
            encoding = (
                decode_key(cast(str, args.value)) if args.decode else encode_entity(cast(str, args.value))
            )
            if machine:
                _json_result(command, encoding.to_dict())
            elif human:
                print(
                    f"Entity: {encoding.entity}\nKey: {encoding.key}\nUnsigned key: {encoding.unsigned_key}"
                    f"\nWire bytes: {encoding.wire_bytes.hex()}"
                )
            elif args.decode:
                print(encoding.entity)
            else:
                result = encoding.to_dict()
                print(
                    json.dumps(
                        {
                            "key": result["key"],
                            "unsigned_key": result["unsigned_key"],
                            "wire_hex": result["wire_hex"],
                        }
                    )
                )
            return 0
        api = EntityTypeAPI.from_json(cast(Path, args.data)) if args.data is not None else EntityTypeAPI()
        if command == "info":
            info = api.info()
            if machine:
                _json_result(command, info)
            elif human:
                print(
                    f"siso-entity-type {info['version']}\nData: {info['data_source']}\n"
                    f"Data version: {info['data_version'] or 'unspecified'}\n"
                    f"Upstream: {info['upstream_commit']}"
                )
                for label, count in info["counts"].items():
                    print(f"{label}: {count}")
            else:
                print(json.dumps(info, indent=2))
        elif command == "describe":
            description = api.describe(cast(str, args.entity))
            if machine:
                _json_result(command, description.to_dict())
            else:
                print(description.qualified_description if args.qualified else description.description)
        elif command == "search":
            limit = cast(int, args.limit)
            results = api.search(cast(str, args.query), limit=None if limit == 0 else limit)
            if machine:
                _json_result(command, results.to_dict())
            elif human:
                for hit in results.hits:
                    print(f"{hit.entity}: {hit.description}")
                print(f"{len(results.hits)} of {results.total} matches")
            else:
                print(
                    json.dumps(
                        {str(hit.entity): hit.description for hit in results.hits},
                        ensure_ascii=False,
                        indent=2,
                    )
                )
            if results.truncated and not machine:
                print(
                    f"Showing {len(results.hits)} of {results.total} results; use --limit 0 for all.",
                    file=sys.stderr,
                )
        elif command == "list":
            choices = api.choices(cast(str, args.collection), *cast(list[int], args.parents))
            if machine:
                _json_result(command, choices.to_dict())
            elif human:
                for choice in choices.items:
                    print(f"{choice.value}: {choice.description}")
            else:
                print(
                    json.dumps(
                        {choice.value: choice.description for choice in choices.items},
                        ensure_ascii=False,
                        indent=2,
                    )
                )
        elif command == "pick":
            description = api.describe(_pick(api, machine=machine))
            if machine:
                _json_result(command, description.to_dict())
            else:
                print(f"\n{description.entity}\n{description.qualified_description}")
    except (ValueError, TypeError, OSError) as exc:
        if machine:
            _error(str(exc), type(exc).__name__, command)
            parser.exit(2)
        parser.exit(2, f"{parser.prog}: error: {exc}\n")
    except (EOFError, KeyboardInterrupt):
        if machine:
            _error("Cancelled.", "Cancelled", command)
        else:
            print("\nCancelled.", file=sys.stderr)
        return 130
    return 0

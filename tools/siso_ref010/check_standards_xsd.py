"""Validate bundled XML against its matching edition schema without network access."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import TypedDict, cast
from xml.etree import ElementTree

DATA = Path("src/siso_ref010/data")
STANDARDS = DATA / "standards"
CURRENT_SCHEMA = DATA / "SISO-REF-010.xsd"
HISTORICAL_SCHEMA_DIRECTORY = Path("tools/siso_ref010/standards-xsds")
PROVENANCE = STANDARDS / "PROVENANCE.json"


class EditionProvenance(TypedDict):
    version: int
    sha256: str
    schema_namespace: str


class XsdArtifact(TypedDict):
    file: str
    sha256: str
    schema_namespace: str


class ProvenanceRegistry(TypedDict):
    registry_schema: int
    entries: list[EditionProvenance]
    artifacts: list[XsdArtifact]
    validation_schemas: list[HistoricalSchemaRecord]


class HistoricalSchemaRecord(TypedDict):
    version: int
    path: str
    sha256: str
    source_url: str
    source_reference: str


class HistoricalSchema(HistoricalSchemaRecord):
    namespace: str


def _version(path: Path) -> int:
    match = re.fullmatch(r"v(\d+)\.xml", path.name)
    if match is None:
        raise ValueError(f"Unexpected edition filename: {path.name}")
    return int(match.group(1))


def _namespace(path: Path) -> str | None:
    root = ElementTree.parse(path).getroot()
    if root.tag.startswith("{"):
        return root.tag[1:].partition("}")[0]
    return None


def _schema_namespace(path: Path) -> str | None:
    return ElementTree.parse(path).getroot().get("targetNamespace")


def _load_registries() -> tuple[
    dict[int, EditionProvenance],
    dict[int, HistoricalSchema],
    str,
    str,
]:
    registry = cast(ProvenanceRegistry, json.loads(PROVENANCE.read_text(encoding="utf-8")))
    editions = {entry["version"]: entry for entry in registry["entries"]}
    xsd_artifact = next(
        artifact for artifact in registry["artifacts"] if artifact["file"] == "data/SISO-REF-010.xsd"
    )
    current_hash = hashlib.sha256(CURRENT_SCHEMA.read_bytes()).hexdigest()
    if current_hash != xsd_artifact["sha256"]:
        raise ValueError("Packaged namespace 2.7 XSD does not match the provenance registry")
    current_namespace = xsd_artifact["schema_namespace"]
    if _schema_namespace(CURRENT_SCHEMA) != current_namespace:
        raise ValueError("Packaged XSD namespace does not match the provenance registry")

    if registry["registry_schema"] != 2:
        raise ValueError("Unsupported SISO provenance registry schema")
    historical: dict[int, HistoricalSchema] = {}
    for row in registry["validation_schemas"]:
        if row["version"] in historical:
            raise ValueError(f"Duplicate historical XSD entry for v{row['version']}")
        if row["version"] not in editions:
            raise ValueError(f"Historical XSD manifest references unbundled v{row['version']}")
        schema_path = Path(row["path"])
        if schema_path.parent != HISTORICAL_SCHEMA_DIRECTORY or not schema_path.is_file():
            raise ValueError(f"Historical XSD is missing or escapes its directory: {schema_path}")
        digest = hashlib.sha256(schema_path.read_bytes()).hexdigest()
        if digest != row["sha256"]:
            raise ValueError(
                f"Historical XSD checksum mismatch for v{row['version']}: "
                f"expected {row['sha256']}, got {digest} ({schema_path})"
            )
        namespace = editions[row["version"]]["schema_namespace"]
        if _schema_namespace(schema_path) != namespace:
            raise ValueError(f"Historical XSD target namespace mismatch for v{row['version']}")
        historical[row["version"]] = {**row, "namespace": namespace}

    expected_historical_versions = {
        version for version, edition in editions.items() if edition["schema_namespace"] != current_namespace
    }
    if historical.keys() != expected_historical_versions:
        missing = sorted(expected_historical_versions - historical.keys())
        extra = sorted(historical.keys() - expected_historical_versions)
        raise ValueError(f"Historical XSD set mismatch; missing={missing}, extra={extra}")
    return editions, historical, xsd_artifact["schema_namespace"], xsd_artifact["sha256"]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--versions",
        type=int,
        nargs="+",
        metavar="VERSION",
        help="validate selected bundled editions; the default validates every edition",
    )
    args = parser.parse_args(argv)

    xmllint = shutil.which("xmllint")
    if xmllint is None:
        print("xmllint is required for offline XSD validation", file=sys.stderr)
        return 2

    try:
        editions, historical_schemas, current_namespace, current_sha256 = _load_registries()
    except (OSError, KeyError, ValueError, json.JSONDecodeError) as error:
        print(f"XSD verification evidence is invalid: {error}", file=sys.stderr)
        return 2

    failures = 0
    not_run = 0
    passed = 0
    all_xml_files = {_version(path): path for path in STANDARDS.glob("v*.xml")}
    if args.versions is None:
        selected_versions = sorted(all_xml_files)
    else:
        selected_versions = sorted(set(args.versions))
        unknown_versions = set(selected_versions) - editions.keys()
        if unknown_versions:
            print(
                f"Unknown bundled editions: {', '.join(map(str, sorted(unknown_versions)))}",
                file=sys.stderr,
            )
            return 2
        missing_xml = set(selected_versions) - all_xml_files.keys()
        if missing_xml:
            print(
                f"Missing bundled XML: {', '.join(f'v{version}' for version in sorted(missing_xml))}",
                file=sys.stderr,
            )
            return 2

    xml_files = tuple(all_xml_files[version] for version in selected_versions)
    for xml in xml_files:
        version = _version(xml)
        entry = editions.get(version)
        if entry is None:
            failures += 1
            print(f"FAIL v{version}: edition is missing from the provenance registry")
            continue
        source_namespace = _namespace(xml)
        xml_sha256 = hashlib.sha256(xml.read_bytes()).hexdigest()
        if xml_sha256 != entry["sha256"]:
            failures += 1
            print(f"FAIL v{version}: source XML SHA-256 does not match the provenance registry")
            continue

        historical = historical_schemas.get(version)
        if historical is not None:
            schema_path = Path(historical["path"])
            schema_namespace = historical["namespace"]
            schema_sha256 = historical["sha256"]
        elif source_namespace == current_namespace:
            schema_path = CURRENT_SCHEMA
            schema_namespace = current_namespace
            schema_sha256 = current_sha256
        else:
            not_run += 1
            print(f"NOT RUN v{version}: no schema is available for source namespace {source_namespace!r}")
            continue

        if schema_namespace != source_namespace:
            failures += 1
            print(
                f"FAIL v{version}: selected schema namespace {schema_namespace!r} does not match "
                f"source namespace {source_namespace!r}"
            )
            continue
        result = subprocess.run(
            [xmllint, "--nonet", "--noout", "--schema", str(schema_path), str(xml)],
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode:
            failures += 1
            print(f"FAIL v{version}: {result.stderr.strip() or result.stdout.strip()}")
        else:
            passed += 1
            print(
                f"PASS v{version}: XML SHA-256 {xml_sha256}; XSD SHA-256 {schema_sha256}; "
                f"namespace {schema_namespace}"
            )
    print(f"XSD editions: passed={passed}, not_run={not_run}, failures={failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())

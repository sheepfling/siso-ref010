"""Validate every packaged standard and exercise each lookup collection."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from pathlib import Path
from xml.etree import ElementTree

from dis_entity_types import (
    BUNDLED_STANDARD_VERSIONS,
    Collection,
    EntityType,
    EntityTypeAPI,
    EntityTypeCatalog,
    EntityTypePrefix,
    EntityTypeXmlParser,
    KindCode,
)
from dis_entity_types.snapshots import read_snapshot_bytes

PACKAGE = Path("src/dis_entity_types")
STANDARDS = PACKAGE / "data/standards"
ARTIFACT_FIELDS = {
    "kind",
    "file",
    "bytes",
    "sha256",
    "git_blob_sha1",
    "schema_namespace",
    "primary_source",
}
SOURCE_RECORD_FIELDS = {
    "provider",
    "repository",
    "reference",
    "path",
    "url",
    "verification",
}


def _check_checksum_manifest(entries: Mapping[int, Mapping[str, object]]) -> None:
    expected = {str(entry["file"]): str(entry["sha256"]) for entry in entries.values()}
    actual: dict[str, str] = {}
    for line in (STANDARDS / "SHA256SUMS.txt").read_text(encoding="utf-8").splitlines():
        digest, separator, name = line.partition("  ")
        if not separator or not digest or not name or name in actual:
            raise SystemExit("SHA256SUMS.txt contains a malformed or duplicate entry")
        actual[name] = digest
    if actual != expected:
        raise SystemExit("SHA256SUMS.txt disagrees with PROVENANCE.json")


def _check_source_record(source: object, label: str) -> None:
    if not isinstance(source, dict) or set(source) != SOURCE_RECORD_FIELDS:
        raise SystemExit(f"{label} does not match the standardized source record")
    if source["provider"] not in {"GitHub", "SISO", "SourceForge"}:
        raise SystemExit(f"{label} has an unsupported provider")
    if not isinstance(source["repository"], str) or not source["repository"]:
        raise SystemExit(f"{label} is missing its repository")
    if not isinstance(source["url"], str) or not source["url"].startswith("https://"):
        raise SystemExit(f"{label} needs a secure source URL")
    if not isinstance(source["path"], str) or not source["path"]:
        raise SystemExit(f"{label} is missing its upstream path")
    reference = source["reference"]
    verification = source["verification"]
    if not isinstance(reference, dict) or set(reference) != {"type", "value"}:
        raise SystemExit(f"{label} has a malformed source reference")
    if reference["type"] not in {"git-commit", "publisher-release", "svn-revision", "svn-tag"}:
        raise SystemExit(f"{label} has an unsupported reference type")
    if not isinstance(verification, dict) or set(verification) != {
        "sha256_match",
        "git_blob_sha1_match",
    }:
        raise SystemExit(f"{label} has a malformed verification record")
    if verification != {"sha256_match": True, "git_blob_sha1_match": True}:
        raise SystemExit(f"{label} has unverified source bytes")


def _prefixes(catalog: EntityTypeCatalog, collection: Collection) -> tuple[EntityTypePrefix | None, ...]:
    if collection in {Collection.COUNTRIES, Collection.KINDS}:
        return (None,)
    if collection is Collection.DOMAINS:
        kinds = tuple(dict.fromkeys(kind for kind, _ in catalog.data.domains))
        return tuple(EntityTypePrefix(kind=kind) for kind in kinds) or (EntityTypePrefix(kind=KindCode(0)),)

    parent_count = collection.parent_count
    parents = tuple(prefix for prefix in catalog.data.children_by_prefix if len(prefix) == parent_count)
    if not parents:
        parents = ((0,) * parent_count,)
    return tuple(EntityTypePrefix.from_values(tuple(int(value) for value in prefix)) for prefix in parents)


def _expected_choices(
    catalog: EntityTypeCatalog,
    collection: Collection,
    prefix: EntityTypePrefix | None,
) -> dict[int, str]:
    entity = prefix.to_entity() if prefix is not None else EntityType(0, 0, 0, 0, 0, 0, 0)
    match collection:
        case Collection.COUNTRIES:
            return catalog.get_all_countries()
        case Collection.KINDS:
            return catalog.get_all_kinds()
        case Collection.DOMAINS:
            return catalog.get_all_domains_of(entity.kind)
        case Collection.CATEGORIES:
            return catalog.get_all_categories_of(entity)
        case Collection.SUBCATEGORIES:
            return catalog.get_all_subcategories_of(entity)
        case Collection.SPECIFICS:
            return catalog.get_all_specifics_of(entity)
        case Collection.EXTRAS:
            return catalog.get_all_extras_of(entity)


def _check_version(version: int, entry: Mapping[str, object]) -> None:
    expected_path = "data/standards/editions.xz"
    if entry.get("bundle_file") != expected_path:
        raise ValueError(f"v{version}: unexpected bundled path {entry.get('bundle_file')!r}")
    path = STANDARDS / f"v{version}.xml"
    xml = path.read_bytes()
    digest = hashlib.sha256(xml).hexdigest()
    if digest != entry["sha256"]:
        raise ValueError(f"{path.name}: SHA-256 mismatch")
    git_blob_sha1 = hashlib.sha1(b"blob " + str(len(xml)).encode() + b"\0" + xml).hexdigest()
    if git_blob_sha1 != entry["git_blob_sha1"]:
        raise ValueError(f"{path.name}: Git blob SHA-1 mismatch")
    if read_snapshot_bytes(version) != xml:
        raise ValueError(f"{path.name}: decompressed bundle bytes differ from the source XML")

    standard = EntityTypeXmlParser.from_file(path)
    catalog = EntityTypeCatalog(standard)
    api = EntityTypeAPI.bundled(version)
    if standard.title != entry["title"] or standard.date != entry["edition_date"]:
        raise ValueError(f"{path.name}: embedded edition metadata disagrees with provenance")
    info = api.info()
    if info.data_version != standard.title or info.data_date != standard.date:
        raise ValueError(f"{path.name}: API info does not reflect the selected edition")
    if (
        info.counts.countries != catalog.country_count
        or info.counts.kinds != catalog.kind_count
        or info.counts.domains != catalog.domain_count
        or info.counts.categories != catalog.category_count
        or info.counts.subcategories != catalog.subcategory_count
    ):
        raise ValueError(f"{path.name}: API counts disagree with the catalog projection")

    queried: dict[str, str] = {}
    for collection in Collection:
        prefix_count = 0
        choice_count = 0
        for prefix in _prefixes(catalog, collection):
            choices = api.choices(collection, prefix)
            expected = _expected_choices(catalog, collection, prefix)
            actual = {choice.value: choice.description for choice in choices.items}
            if actual != expected:
                raise ValueError(
                    f"{path.name}: {collection.value} query disagrees with catalog projection "
                    f"for prefix {prefix!r}"
                )
            prefix_count += 1
            choice_count += len(actual)
        queried[collection.value] = f"{prefix_count} prefixes/{choice_count} choices"

    search = api.search("", limit=1)
    search_expected = catalog.search_description("")
    if search.total != len(search_expected) or search.returned > 1:
        raise ValueError(f"{path.name}: search query disagrees with catalog projection")
    if search.hits and (
        str(search.hits[0].entity),
        search.hits[0].description,
    ) != next(iter(search_expected.items())):
        raise ValueError(f"{path.name}: search result disagrees with catalog projection")
    branch = standard.entity_types[0] if standard.entity_types else None
    entity = (
        EntityType(branch.kind, branch.domain, branch.country, 0, 0, 0, 0)
        if branch is not None
        else EntityType(0, 0, 0, 0, 0, 0, 0)
    )
    description = api.describe(entity)
    if description.description != catalog.get_description_of(
        entity
    ) or description.qualified_description != catalog.get_description_of(entity, True):
        raise ValueError(f"{path.name}: describe query disagrees with catalog projection")
    print(f"OK v{version} {standard.date}: choices={queried} search/describe=OK")


def _check_artifacts(manifest: Mapping[str, object]) -> None:
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list) or len(artifacts) != 1:
        raise SystemExit("PROVENANCE.json must record the bundled XSD artifact")
    artifact = artifacts[0]
    if not isinstance(artifact, dict) or set(artifact) != ARTIFACT_FIELDS:
        raise SystemExit("bundled XSD record does not match the artifact schema")
    if artifact["kind"] != "xml-schema" or artifact["file"] != "data/SISO-REF-010.xsd":
        raise SystemExit("PROVENANCE.json has an unexpected bundled artifact")
    _check_source_record(artifact.get("primary_source"), "bundled XSD primary source")
    relative_path = Path(str(artifact["file"]))
    if relative_path.is_absolute() or ".." in relative_path.parts:
        raise SystemExit("bundled artifact path must stay inside the package")
    path = PACKAGE / relative_path
    data = path.read_bytes()
    if len(data) != artifact["bytes"]:
        raise ValueError("bundled XSD byte count disagrees with PROVENANCE.json")
    if hashlib.sha256(data).hexdigest() != artifact["sha256"]:
        raise ValueError("bundled XSD SHA-256 disagrees with PROVENANCE.json")
    git_blob_sha1 = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
    if git_blob_sha1 != artifact["git_blob_sha1"]:
        raise ValueError("bundled XSD Git blob SHA-1 disagrees with PROVENANCE.json")
    root = ElementTree.fromstring(data)
    namespace = root.attrib.get("targetNamespace")
    if namespace != artifact["schema_namespace"]:
        raise ValueError("bundled XSD namespace disagrees with PROVENANCE.json")


def main() -> int:
    manifest = json.loads((STANDARDS / "PROVENANCE.json").read_text(encoding="utf-8"))
    if (STANDARDS / "SOURCES.json").exists():
        raise SystemExit("SOURCES.json is obsolete; keep all source evidence in PROVENANCE.json")
    if manifest.get("registry_schema") != 1:
        raise SystemExit("unsupported PROVENANCE.json registry schema")
    _check_artifacts(manifest)
    entries = {
        int(entry["version"]): entry for entry in manifest["entries"] if entry.get("status") == "verified"
    }
    if set(entries) != set(BUNDLED_STANDARD_VERSIONS):
        raise SystemExit(
            f"provenance versions {sorted(entries)} do not match bundled versions "
            f"{list(BUNDLED_STANDARD_VERSIONS)}"
        )
    source_verification = manifest.get("source_verification", {})
    if source_verification.get("versions") != list(BUNDLED_STANDARD_VERSIONS):
        raise SystemExit("source verification versions do not match the bundled editions")
    for version, entry in entries.items():
        _check_source_record(entry.get("primary_source"), f"v{version} primary source")
        mirrors = entry.get("verified_mirrors")
        if not isinstance(mirrors, list):
            raise SystemExit(f"v{version} has malformed verified mirrors")
        for mirror in mirrors:
            _check_source_record(mirror, f"v{version} verified mirror")
        if not isinstance(entry.get("source_history"), list):
            raise SystemExit(f"v{version} has malformed source history")
        if any(history.get("status") != "resolved" for history in entry["source_history"]):
            raise SystemExit(f"v{version} has unresolved source research")
    _check_checksum_manifest(entries)

    xml_files = tuple(STANDARDS.glob("v*.xml"))
    actual_versions = {
        int(match.group(1))
        for path in xml_files
        if (match := re.fullmatch(r"v([0-9]+)\.xml", path.name)) is not None
    }
    if actual_versions != set(BUNDLED_STANDARD_VERSIONS) or len(xml_files) != len(actual_versions):
        raise SystemExit(
            f"bundled XML files {sorted(path.name for path in xml_files)} do not match "
            f"versions {list(BUNDLED_STANDARD_VERSIONS)}"
        )

    failures = 0
    for version in BUNDLED_STANDARD_VERSIONS:
        try:
            _check_version(version, entries[version])
        except Exception as exc:
            failures += 1
            print(f"FAIL v{version}: {type(exc).__name__}: {exc}")
    print(f"Checked {len(BUNDLED_STANDARD_VERSIONS)} editions; failures={failures}")
    return int(failures != 0)


if __name__ == "__main__":
    raise SystemExit(main())

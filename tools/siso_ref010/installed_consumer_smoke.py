"""Run a generic smoke suite against the package installed in the active environment."""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
from importlib.metadata import version as installed_version
from importlib.resources import files

from siso_ref010 import EntityType, SisoRef010API, __version__, decode_key, encode_entity
from siso_ref010.catalog import BUNDLED_STANDARD_VERSIONS
from siso_ref010.reporting import render_json, render_markdown
from siso_ref010.sources import BUNDLED_STANDARD_SOURCE


def _check_index_only_discovery() -> None:
    import siso_ref010.snapshots as snapshots
    import siso_ref010.sources as sources
    from siso_ref010.cli import main

    def fail_if_xml_is_read(*args: object, **kwargs: object) -> None:
        raise AssertionError("edition discovery attempted to load XML")

    original_reads = snapshots.read_snapshot_bytes, sources.read_snapshot_bytes
    original_verifier = snapshots._verify_pack
    try:
        snapshots.read_snapshot_bytes = fail_if_xml_is_read
        sources.read_snapshot_bytes = fail_if_xml_is_read
        snapshots._verify_pack = fail_if_xml_is_read
        editions = SisoRef010API.bundled_editions()
        assert tuple(edition.version for edition in editions) == BUNDLED_STANDARD_VERSIONS
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            assert main(["versions", "--json"]) == 0
        result = json.loads(output.getvalue())["result"]
        assert result["versions"] == list(BUNDLED_STANDARD_VERSIONS)
        assert result["default_version"] == max(BUNDLED_STANDARD_VERSIONS)
    finally:
        snapshots.read_snapshot_bytes, sources.read_snapshot_bytes = original_reads
        snapshots._verify_pack = original_verifier


def _check_all_editions() -> dict[int, str]:
    standards = files("siso_ref010").joinpath("data/standards")
    registry = json.loads(standards.joinpath("PROVENANCE.json").read_text(encoding="utf-8"))
    entries = {row["version"]: row for row in registry["entries"] if row["status"] == "verified"}
    assert tuple(sorted(entries)) == BUNDLED_STANDARD_VERSIONS
    assert registry["source_verification"]["versions"] == list(BUNDLED_STANDARD_VERSIONS)

    source_hashes: dict[int, str] = {}
    for version in BUNDLED_STANDARD_VERSIONS:
        entry = entries[version]
        payload = BUNDLED_STANDARD_SOURCE.read_xml(version)
        digest = hashlib.sha256(payload).hexdigest()
        assert digest == entry["sha256"]
        source_hashes[version] = digest

        api = SisoRef010API.bundled(version)
        report = api.inspector.report()
        assert report.identity.edition_number == version
        assert report.identity.source_sha256 == digest
        assert report.identity.provenance_status.value == "bundled_checksum_verified"
        assert all(check.status.value == "checked" for check in report.validation.semantic_checks)
        for example in report.examples:
            if example.kind.value == "enumeration_table":
                reproduced = api.inspector.enumeration_table(int(example.query))
            elif example.kind.value == "enumeration_value":
                table_uid, value = (int(part.strip()) for part in example.query.split(",", maxsplit=1))
                reproduced = api.inspector.resolve_enumeration_value(table_uid, value)
            else:
                reproduced = api.resolve_entity(example.query)
            assert reproduced == example.result
    return source_hashes


def main() -> None:
    assert __version__ == installed_version("siso-ref010")
    versions = SisoRef010API.bundled_versions().versions
    assert versions == BUNDLED_STANDARD_VERSIONS
    default_version = max(versions)
    edition = next(row for row in SisoRef010API.bundled_editions() if row.version == default_version)
    api = SisoRef010API()
    assert api.info().data_version == edition.title
    assert api.info().data_date == edition.date.isoformat()

    query = api.query_entities(limit=1)
    assert query.values
    row = query.values[0]
    fields = (*row.hierarchy_codes[:7], *(0 for _ in range(7 - len(row.hierarchy_codes[:7]))))
    entity = EntityType(*fields)
    description = api.describe(entity)
    assert decode_key(encode_entity(entity).key).entity == entity
    assert api.resolve_entity(str(entity)).matched_depth > 0

    tables = api.inspector.enumeration_tables()
    assert tables
    assert any(table.entry_count > 0 for table in tables)
    value_results = api.inspector.value_results(limit=1)
    assert value_results.total > 0 and value_results.values

    report = api.inspector.report()
    assert report.identity.edition_number == default_version
    assert report.summary is not None
    report_json = json.loads(render_json(report))
    assert report_json == report.model_dump(mode="json", by_alias=True)
    report_markdown = render_markdown(report)
    assert report_markdown

    _check_index_only_discovery()
    source_hashes = _check_all_editions()
    print(
        json.dumps(
            {
                "versions": list(versions),
                "default_version": default_version,
                "data_version": edition.title,
                "entity": str(entity),
                "description": description.model_dump(mode="json", by_alias=True),
                "report": report_json,
                "report_markdown": report_markdown,
                "source_sha256": {str(version): digest for version, digest in source_hashes.items()},
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()

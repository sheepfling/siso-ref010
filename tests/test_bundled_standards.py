import gc
from hashlib import sha256
from weakref import ref

import pytest

from siso_ref010 import (
    BUNDLED_STANDARD_VERSIONS,
    BundledStandardSource,
    EntityTypeAPI,
    EntityTypeCatalog,
    EntityTypePrefix,
    EntityTypeValueError,
    render_markdown,
)
from siso_ref010.catalog import _BUNDLED_CATALOG_DATA_CACHE, _BUNDLED_CATALOG_DATA_CACHE_LOCK
from siso_ref010.cli import main


def test_bundled_projection_cache_shares_live_data_without_retaining_released_editions():
    with _BUNDLED_CATALOG_DATA_CACHE_LOCK:
        _BUNDLED_CATALOG_DATA_CACHE.clear()
    first = EntityTypeAPI.bundled(20)
    data = first._catalog.data
    data_reference = ref(data)
    second = EntityTypeAPI.bundled(20)
    assert second._catalog.data is data

    del data, first, second
    gc.collect()
    assert data_reference() is None


def test_sequential_bundled_reports_release_each_edition_projection():
    with _BUNDLED_CATALOG_DATA_CACHE_LOCK:
        _BUNDLED_CATALOG_DATA_CACHE.clear()

    for version in BUNDLED_STANDARD_VERSIONS:
        api = EntityTypeAPI.bundled(version)
        api_reference = ref(api)
        data_reference = ref(api._catalog.data)
        report = api.inspector.report()
        assert report.report_schema_version == 1
        assert report.identity.edition_number == version
        assert report.summary is not None

        del report, api
        gc.collect()
        assert api_reference() is None
        assert data_reference() is None
        with _BUNDLED_CATALOG_DATA_CACHE_LOCK:
            assert len(_BUNDLED_CATALOG_DATA_CACHE) == 0


@pytest.mark.parametrize("version", BUNDLED_STANDARD_VERSIONS)
def test_each_bundled_standard_loads(version):
    api = EntityTypeAPI.bundled(version)
    assert api.info().data_version is not None
    assert f"v{version}" in api.info().data_version.lower()
    summary = api.inspector.summary()
    assert summary.enumeration_tables > 0
    assert summary.entity_values > 0
    assert summary.unresolved_entity_values == 0


@pytest.mark.parametrize("version", [19, 38, 35.0, "35", True])
def test_unavailable_bundled_standard_is_rejected(version):
    with pytest.raises(EntityTypeValueError) as error:
        EntityTypeCatalog.bundled(version)
    assert error.value.code == "unavailable_bundled_version"


def test_cli_can_select_bundled_standard(capsys):
    assert main(["--standard-version", "35", "info"]) == 0
    assert "Data version: SISO-REF-010-v35" in capsys.readouterr().out


def test_full_entity_code_reports_zero_extra_as_unspecified():
    resolution = EntityTypeAPI.bundled(37).resolve_entity("1.3.153.6.4.2.0")
    assert resolution.status.value == "unspecified"
    assert resolution.matched_depth == 6
    assert resolution.unspecified_components == ("extra",)
    assert resolution.unresolved_components == ()
    assert [row.description for row in resolution.matched_path] == [
        "Guided Missile Frigate (FFG)",
        "De Zeven Provincien Class",
        "F803 Tromp",
    ]


def test_bundled_source_reads_indexed_editions():
    source = BundledStandardSource()
    assert source.versions == BUNDLED_STANDARD_VERSIONS
    api = EntityTypeAPI.from_source(source, 35)
    assert api.info().data_version == "SISO-REF-010-v35"
    report = api.inspector.report()
    assert report.identity.provenance_status == "bundled_checksum_verified"
    assert report.identity.source_sha256 == sha256(source.read_xml(35)).hexdigest()

    class BundledOverride(BundledStandardSource):
        pass

    custom = EntityTypeAPI.from_source(BundledOverride(), 35)
    assert custom.inspector.report().identity.provenance_status == "unverified"


@pytest.mark.parametrize("version", BUNDLED_STANDARD_VERSIONS)
def test_inspection_contract_across_representative_editions(version):
    api = EntityTypeAPI.bundled(version)
    inspector = api.inspector
    summary = inspector.summary()
    assert summary.enumeration_tables > 0
    assert summary.enumeration_values > 0
    assert summary.unclassified_entity_rows == 0
    report = inspector.report()
    assert report.summary is not None
    assert report.report_schema_version == 1
    assert report.identity.edition_number == version
    assert report.summary.value_path_records == summary.value_path_records
    assert report.identity_diagnostics.checked
    assert report.identity_diagnostics.inspected_records == summary.value_path_records
    assert report.identity_diagnostics.repeated_uuid_occurrences == summary.repeated_uuid_occurrences
    assert (
        report.identity_diagnostics.repeated_identity_key_occurrences
        == summary.repeated_identity_key_occurrences
    )
    assert all(check.status.value == "checked" for check in report.validation.semantic_checks)
    entity_example = next(
        (item for item in report.examples if item.kind.value == "entity_resolution"),
        None,
    )
    if entity_example is not None:
        assert entity_example.query == entity_example.result.code
        assert entity_example.result.requested_depth == len(entity_example.query.split("."))
    if version == 20:
        assert report.identity.title == "SISO-REF-010-00v20-0"
        assert render_markdown(report).startswith("# SISO-REF-010 · Edition 20\n")

    for example in report.examples:
        if example.kind.value == "enumeration_table":
            result = inspector.enumeration_table(int(example.query))
        elif example.kind.value == "enumeration_value":
            table_uid, value = (int(part.strip()) for part in example.query.split(",", maxsplit=1))
            result = inspector.resolve_enumeration_value(table_uid, value)
        else:
            result = api.resolve_entity(example.query)
        assert result == example.result

    # Missing optional tables are an explicit unknown result, not an exception.
    missing = inspector.resolve_enumeration_value(2_000_000 + version, 93)
    assert missing.status.value == "unknown"
    assert missing.table is None

    nonempty_table = next(
        (
            table
            for table in inspector.enumeration_tables()
            if inspector.enumeration_rows(table.uid)
            and len(inspector.enumeration_tables_by_uid(table.uid)) == 1
        ),
        None,
    )
    assert nonempty_table is not None
    row = inspector.enumeration_rows(nonempty_table.uid)[0]
    candidate = row.value if row.value is not None else row.value_min
    assert candidate is not None
    resolved = inspector.resolve_enumeration_value(nonempty_table.uid, candidate)
    assert resolved.status.value in {"exact", "range"}
    assert resolved.matches

    for table in inspector.enumeration_tables():
        if len(inspector.enumeration_tables_by_uid(table.uid)) != 1:
            continue
        rows = inspector.enumeration_rows(table.uid)
        ranges = tuple(row for row in rows if row.value_min is not None and row.value_max is not None)
        for value_range in ranges:
            for boundary in (value_range.value_min, value_range.value_max):
                assert boundary is not None
                resolution = inspector.resolve_enumeration_value(table.uid, boundary)
                assert resolution.status.value in {"range", "ambiguous"}
                assert any(
                    match.value_min == value_range.value_min and match.value_max == value_range.value_max
                    for match in resolution.matches
                )
        if rows:
            maximum = max(
                row.value if row.value is not None else row.value_max
                for row in rows
                if row.value is not None or row.value_max is not None
            )
            outside = inspector.resolve_enumeration_value(table.uid, maximum + 1)
            assert outside.status.value == "unknown"

    category = next(
        (
            item
            for item in inspector.values(kind="entity_type")
            if item.tag in {"category", "category_range"}
            and len(item.hierarchy_codes) == 4
            and item.hierarchy_codes[2] != 0
            and item.value is not None
        ),
        None,
    )
    if category is not None:
        prefix = EntityTypePrefix.from_values(category.hierarchy_codes)
        result = api.resolve_entity(prefix)
        assert result.status.value == "partial"
        assert result.matched_depth == 4
        assert result.human_outcome == "Resolved prefix"
        assert result.not_supplied_components == ("subcategory", "specific", "extra")

    explicit_entity = next(
        (
            item
            for item in inspector.values(kind="entity_type")
            if item.tag == "extra" and len(item.hierarchy_codes) == 7 and item.value is not None
        ),
        None,
    )
    if explicit_entity is not None:
        full_code = (*explicit_entity.hierarchy_codes[:-1], explicit_entity.value)
        full_resolution = api.resolve_entity(EntityTypePrefix.from_values(full_code))
        assert full_resolution.requested_depth == 7
        assert not full_resolution.is_prefix

    page1 = inspector.search_page("", limit=3)
    page2 = inspector.search_page("", limit=3, offset=3)
    assert page1.total == page2.total == summary.enumeration_values + summary.entity_values
    assert len(page1.hits) == 3
    assert len({hit.identity for hit in page1.hits}) == 3
    assert set(hit.identity for hit in page1.hits).isdisjoint(hit.identity for hit in page2.hits)


def test_v37_report_groups_informational_findings_by_source_table():
    api = EntityTypeAPI.bundled(37)
    report = api.inspector.report()

    assert report.summary is not None
    assert report.summary.enumeration_tables == 535
    assert report.summary.value_path_records == 38_624
    assert report.diagnostics.total == 838
    assert report.diagnostics.severity_counts == {"info": 838}
    assert {
        (group.code, group.table_uid, group.table_name, group.count) for group in report.diagnostics.groups
    } == {
        ("missing_description", 75, "Emitter Name", 818),
        ("missing_description", 326, "Sensor Record-Sensor Type-Passive Sensors", 20),
    }
    assert report.diagnostics.findings == ()
    assert all("intentionally unspecified" in group.message for group in report.diagnostics.groups)
    prefix = api.resolve_entity("1.3.153.6.4.2")
    assert prefix.status.value == "partial"
    assert prefix.requested_depth == prefix.matched_depth == 6
    assert prefix.is_prefix
    assert prefix.human_outcome == "Resolved prefix"
    assert prefix.not_supplied_components == ("extra",)
    assert not prefix.unresolved_components
    assert "caller did not request" in prefix.resolution_description


def test_v37_range_lookup_includes_both_inclusive_boundaries_and_unknown_values():
    inspector = EntityTypeAPI.bundled(37).inspector

    for value in (64, 127):
        resolution = inspector.resolve_enumeration_value(3, value)
        assert resolution.status.value == "range"
        assert (resolution.matches[0].value_min, resolution.matches[0].value_max) == (64, 127)

    unknown = inspector.resolve_enumeration_value(3, 1_000_000)
    assert unknown.status.value == "unknown"
    assert unknown.matches == ()


def test_v22_duplicate_uuid_diagnostic_keeps_all_matching_records():
    inspector = EntityTypeAPI.bundled(22).inspector
    grouped = inspector.diagnostics(code="duplicate_uuid", limit=0)
    detailed = inspector.diagnostics(code="duplicate_uuid", limit=1)

    assert grouped.counts["duplicate_uuid"] == 6
    assert len(grouped.groups) >= 1
    assert detailed.total == 6
    finding = detailed.findings[0]
    uuid = finding.message.split("UUID '", 1)[1].split("'", 1)[0]
    assert len(inspector.lookup_uuid(uuid)) >= 2


def test_v20_country_alias_is_flagged_without_resolving_duplicate_code():
    inspector = EntityTypeAPI.bundled(20).inspector
    resolution = inspector.resolve_enumeration_value(29, 107)
    aliases = inspector.diagnostics(code="possible_value_alias", table_uid=29, limit=None)

    assert resolution.status.value == "ambiguous"
    assert {match.description for match in resolution.matches} == {
        "Cote D'Ivoire (aka Ivory Coast)",
        "Ivory Coast (aka Cote D'Ivoire)",
    }
    assert len({match.uuid for match in resolution.matches}) == 2
    assert aliases.total == 1
    assert "Scalar code 107" in aliases.findings[0].message
    assert "lookup remains ambiguous" in aliases.findings[0].message
    assert aliases.groups[0].severity.value == "info"


@pytest.mark.parametrize(
    ("version", "reuse_groups", "duplicate_identifier_groups", "conflict_groups"),
    [(37, 8, 0, 0), (22, 40, 6, 6)],
)
def test_identity_diagnostics_explain_repeated_uuid_semantics(
    version, reuse_groups, duplicate_identifier_groups, conflict_groups
):
    identity = EntityTypeAPI.bundled(version).inspector.identity_diagnostics()
    assert identity.checked
    assert identity.repeated_uuid_occurrences == (22 if version == 37 else 8_188)
    assert identity.repeated_identity_key_occurrences == (16 if version == 37 else 8_182)
    assert identity.source_record_reuse_groups == reuse_groups
    assert identity.duplicate_source_identifier_groups == duplicate_identifier_groups
    assert identity.conflicting_source_record_groups == conflict_groups
    if version == 22:
        conflict = next(
            group for group in identity.groups if group.classification.value == "conflicting_source_records"
        )
        assert conflict.uuid == "161ced57-39d4-4e7b-85b5-aae63524f3c2"
        assert conflict.source_record_count > 1
        assert conflict.conflict_fields
        assert conflict.sample_contexts


def test_entity_resolution_rejects_malformed_input_and_reports_unknown_supplied_components():
    api = EntityTypeAPI.bundled(37)
    with pytest.raises(ValueError):
        api.resolve_entity("1.3.not-a-number")
    unknown = api.resolve_entity("1.3.153.6.255.0")
    assert unknown.status.value == "unknown"
    assert unknown.unresolved_components == ("subcategory",)
    assert unknown.not_supplied_components == ("extra",)


def test_injected_source_and_horizontal_queries():
    class MemorySource:
        @property
        def versions(self):
            return (7,)

        def read_xml(self, version):
            assert version == 7
            return (
                b'<ebv title="CUSTOM-v7" date="2026-01-01">'
                b'<enum uid="29" name="Country">'
                b'<enumrow value="1" description="Afghanistan"/>'
                b"</enum></ebv>"
            )

    supplied = EntityTypeAPI.from_source(MemorySource(), 7)
    assert supplied.info().data_source == "supplied"
    assert supplied.info().data_version == "CUSTOM-v7"
    with pytest.raises(EntityTypeValueError) as error:
        EntityTypeAPI.from_source(MemorySource(), 8)
    assert error.value.code == "unavailable_source_version"

    by_version = {
        version: api.search("F803").total for version, api in EntityTypeAPI.iter_editions(versions=(36, 37))
    }
    assert set(by_version) == {36, 37}
    assert all(count > 0 for count in by_version.values())

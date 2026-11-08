import json
from collections import Counter

import pytest

from dis_entity_types import (
    BUNDLED_STANDARD_SOURCE,
    ChangeAssessment,
    ChangeCounts,
    ChangeReference,
    EditionChange,
    EditionDiff,
    EntityTypeAPI,
    ValueHistory,
    ValueRecord,
)
from dis_entity_types.cli import main
from dis_entity_types.comparison import _inspection_records, _load_standard, _record_changes


class MemorySource:
    def __init__(self, versions):
        self.data = versions

    @property
    def versions(self):
        return tuple(self.data)

    def read_xml(self, version):
        return self.data[version].encode()


def _standard(
    *,
    category="Old category",
    subcategory_value=3,
    subcategory="Tracked entry",
    enum_name="Example table",
    enum_value=1,
    enum_description="Old value",
    enum_uuid="enum-value-1",
    include_removed=True,
    xref_uid=91,
    annotations="",
):
    rows = (
        f'<enumrow value="{enum_value}" description="{enum_description}" uuid="{enum_uuid}"/>'
        + ('<enumrow value="2" description="Removed value" uuid="enum-value-2"/>' if include_removed else "")
        + '<enumrow_range value_min="10" value_max="11" description="Range value" uuid="enum-range"/>'
        + '<enumrow value="3" description="Referenced value" uuid="xref-value"/>'
    )
    return (
        '<ebv title="Test edition" date="2026-01-01">'
        '<enum uid="7" name="Entity Kind" size="8">'
        '<enumrow value="1" description="Platform" uuid="kind-1"/>'
        "</enum>"
        f'<enum uid="90" name="{enum_name}" size="8" uuid="enum-table-90">{annotations}{rows}</enum>'
        '<enum uid="91" name="Referenced values" size="8">'
        '<enumrow value="3" description="Referenced value" uuid="xref-value"/>'
        "</enum>"
        '<enum uid="92" name="Referenced values copy" size="8">'
        '<enumrow value="3" description="Referenced value" uuid="xref-value"/>'
        "</enum>"
        '<cet name="Entity Types">'
        '<entity kind="1" domain="1" country="1" uuid="branch-1">'
        f'<category value="2" description="{category}" uuid="category-2">'
        f'<subcategory value="{subcategory_value}" description="{subcategory}" uuid="tracked-entry"/>'
        f'<subcategory_xref xref="{xref_uid}"/>'
        "</category></entity></cet></ebv>"
    )


@pytest.fixture
def comparison_source():
    return MemorySource(
        {
            1: _standard(annotations='<description uuid="note-1">Original table note</description>'),
            2: _standard(
                category="Updated category",
                subcategory_value=4,
                enum_name="Renamed table",
                enum_description="Updated value",
                include_removed=False,
                xref_uid=91,
                annotations='<description uuid="note-1">Revised table note</description>',
            ),
        }
    )


def test_entity_history_reports_presence_and_effective_description(comparison_source):
    history = EntityTypeAPI.entity_history("1.1.1.2.4.0.0", source=comparison_source, versions=(1, 2))
    assert history.kind == "entity"
    assert [point.present for point in history.points] == [True, True]
    assert history.points[0].description == "Old category"
    assert history.points[1].description == "Tracked entry"
    assert history.points[0].matched_path == (1, 1, 1, 2)
    assert history.points[1].matched_path == (1, 1, 1, 2, 4)


def test_enumeration_history_resolves_scalar_and_range_values(comparison_source):
    value = EntityTypeAPI.enumeration_history(90, 1, source=comparison_source, versions=(1, 2))
    table = EntityTypeAPI.enumeration_history(90, source=comparison_source, versions=(1, 2))
    range_value = EntityTypeAPI.enumeration_history(90, 11, source=comparison_source, versions=(1, 2))
    assert [point.description for point in value.points] == ["Old value", "Updated value"]
    assert [point.name for point in table.points] == ["Example table", "Renamed table"]
    assert all(point.present for point in range_value.points)
    assert [point.description for point in range_value.points] == ["Range value", "Range value"]


def test_pairwise_diff_detects_add_remove_modify_move_and_table_metadata(comparison_source):
    diff = EntityTypeAPI.compare_editions(1, 2, source=comparison_source, limit=None)
    by_identity = {(change.scope, change.stable_id): change for change in diff.changes}
    assert by_identity[("entity", "category-2")].action == "modified"
    assert "description" in by_identity[("entity", "category-2")].changed_fields
    assert by_identity[("entity", "tracked-entry")].action == "recoded"
    assert by_identity[("entity", "tracked-entry")].identity_match == "uuid"
    assert by_identity[("enumeration_value", "enum-value-1")].action == "modified"
    assert by_identity[("enumeration_value", "enum-value-2")].action == "removed"
    assert by_identity[("enumeration_value", "enum-range")].action == "modified"
    assert by_identity[("enumeration_table", "enum-table-90")].action == "modified"
    assert "annotations" in by_identity[("enumeration_table", "enum-table-90")].changed_fields
    assert diff.total == sum(diff.counts.model_dump().values())
    assert diff.truncated is False
    removed = next(row for row in diff.concise().changes if row.stable_id == "enum-value-2")
    assert removed.record_before is not None
    assert removed.record_after is None
    assert removed.fields == ()


def test_diff_expands_ranges_and_tracks_cross_reference_target(comparison_source):
    changed = MemorySource(
        {
            1: _standard(xref_uid=91),
            2: _standard(xref_uid=92),
        }
    )
    diff = EntityTypeAPI.compare_editions(
        1, 2, source=changed, scope="entities", entity_prefix=(1, 1, 1, 2), limit=None
    )
    xref_rows = [change for change in diff.changes if change.after and change.after.reference_uid]
    assert xref_rows
    assert all(change.action == "modified" for change in xref_rows)
    assert all("reference_uid" in change.changed_fields for change in xref_rows)


def test_diff_distinguishes_entity_moves_from_recodes():
    source = MemorySource(
        {
            1: _standard(),
            2: _standard().replace('<category value="2"', '<category value="3"'),
        }
    )
    diff = EntityTypeAPI.compare_editions(1, 2, source=source, scope="entities", limit=None)
    by_identity = {(change.scope, change.stable_id): change for change in diff.changes}
    assert by_identity[("entity", "category-2")].action == "recoded"
    assert by_identity[("entity", "tracked-entry")].action == "moved"


def test_three_edition_changes_reconcile_add_modify_revert_and_restore():
    base = _standard()
    added = base.replace(
        "</category>",
        '<subcategory value="4" description="Added in middle" uuid="middle-addition"/></category>',
    )
    updated_addition = added.replace('description="Added in middle"', 'description="Final addition"')

    middle_to_final = EntityTypeAPI.compare_editions(
        2, 3, source=MemorySource({1: base, 2: added, 3: added}), scope="entities", limit=None
    )
    direct_add = EntityTypeAPI.compare_editions(
        1, 3, source=MemorySource({1: base, 2: added, 3: added}), scope="entities", limit=None
    )
    assert middle_to_final.changes == ()
    addition = next(row for row in direct_add.changes if row.stable_id == "middle-addition")
    assert addition.action == "added"
    assert addition.after is not None and addition.after.description == "Added in middle"

    modified_addition = EntityTypeAPI.compare_editions(
        1,
        3,
        source=MemorySource({1: base, 2: added, 3: updated_addition}),
        scope="entities",
        limit=None,
    )
    final_addition = next(row for row in modified_addition.changes if row.stable_id == "middle-addition")
    assert final_addition.action == "added"
    assert final_addition.after is not None and final_addition.after.description == "Final addition"

    modified = base.replace('description="Tracked entry"', 'description="Temporary change"')
    reverted = EntityTypeAPI.compare_editions(
        1, 3, source=MemorySource({1: base, 2: modified, 3: base}), scope="entities", limit=None
    )
    assert all(row.stable_id != "tracked-entry" for row in reverted.changes)

    removed = base.replace('<subcategory value="3" description="Tracked entry" uuid="tracked-entry"/>', "")
    restored = EntityTypeAPI.compare_editions(
        1, 3, source=MemorySource({1: base, 2: removed, 3: base}), scope="entities", limit=None
    )
    assert all(row.stable_id != "tracked-entry" for row in restored.changes)


def test_inherited_path_label_change_references_the_changed_ancestor():
    before = _standard(category="Old category")
    after = _standard(category="Renamed category")
    source = MemorySource({1: before, 2: after})
    diff = EntityTypeAPI.compare_editions(1, 2, source=source, scope="entities", limit=None)
    parent = next(row for row in diff.changes if row.stable_id == "category-2")
    child = next(row for row in diff.changes if row.stable_id == "tracked-entry")
    assert parent.origin == "direct"
    assert child.origin == "derived"
    assert child.changed_fields == ("path_labels",)
    assert child.caused_by == (
        ChangeReference(scope="entity", identifier=parent.identifier, stable_id="category-2"),
    )

    filtered = EntityTypeAPI.compare_editions(
        1,
        2,
        source=source,
        scope="entities",
        entity_prefix=(1, 1, 1, 2, 3),
        limit=None,
    )
    filtered_child = next(row for row in filtered.changes if row.stable_id == "tracked-entry")
    assert filtered_child.caused_by == child.caused_by


def test_uuid_and_numeric_code_changes_are_reported_without_guessing():
    before = _standard(enum_uuid="stable-before")
    same_code_new_uuid = before.replace('uuid="stable-before"', 'uuid="stable-after"')
    uuid_diff = EntityTypeAPI.compare_editions(
        1, 2, source=MemorySource({1: before, 2: same_code_new_uuid}), scope="enumerations", limit=None
    )
    value_change = next(row for row in uuid_diff.changes if row.scope == "enumeration_value")
    assert value_change.identity_match == "code"
    assert "uuid_changed_at_stable_code" in value_change.identity_diagnostics
    assert "same_code_different_uuid" in value_change.reason_codes
    assert "resolve_identity_manually" in value_change.recommendation_codes

    reused_code = same_code_new_uuid.replace('description="Old value"', 'description="Different meaning"')
    reuse_diff = EntityTypeAPI.compare_editions(
        1, 2, source=MemorySource({1: before, 2: reused_code}), scope="enumerations", limit=None
    )
    reused = next(row for row in reuse_diff.changes if row.scope == "enumeration_value")
    assert reused.identity_match == "code"
    assert "possible_code_reuse" in reused.identity_diagnostics
    assert "possible_code_reuse" in reused.reason_codes
    assert reused.assessment.semantic_meaning == "not_assessed"

    recoded = before.replace('value="1" description="Old value"', 'value="4" description="Old value"')
    recode_diff = EntityTypeAPI.compare_editions(
        1, 2, source=MemorySource({1: before, 2: recoded}), scope="enumerations", limit=None
    )
    recoded_value = next(row for row in recode_diff.changes if row.stable_id == "stable-before")
    assert recoded_value.action == "recoded"
    assert recoded_value.identity_match == "uuid"
    assert recoded_value.assessment.wire_encoding == "potentially_breaking"
    assert recoded_value.assessment.identifier_resolution == "breaking"


def test_duplicate_code_fallbacks_are_reported_as_ambiguous():
    before = _standard().replace(
        '</enum><enum uid="91"',
        '<enumrow value="12" description="First meaning" uuid="first-uuid"/>'
        '<enumrow value="12" description="Second meaning" uuid="second-uuid"/>'
        '</enum><enum uid="91"',
    )
    after = before.replace(
        '<enumrow value="12" description="First meaning" uuid="first-uuid"/>'
        '<enumrow value="12" description="Second meaning" uuid="second-uuid"/>',
        '<enumrow value="12" description="Replacement meaning" uuid="replacement-uuid"/>',
    )
    diff = EntityTypeAPI.compare_editions(
        1, 2, source=MemorySource({1: before, 2: after}), scope="enumerations", limit=None
    )
    ambiguous = [
        row
        for row in diff.changes
        if row.scope == "enumeration_value"
        and row.stable_id in {"first-uuid", "second-uuid", "replacement-uuid"}
    ]
    assert len(ambiguous) == 3
    assert {row.action for row in ambiguous} == {"added", "removed"}
    assert all(row.identity_match == "ambiguous_code" for row in ambiguous)
    assert all("duplicate_code" in row.identity_diagnostics for row in ambiguous)
    assert all("identity_ambiguous" in row.reason_codes for row in ambiguous)
    assert all("resolve_identity_manually" in row.recommendation_codes for row in ambiguous)


def test_duplicate_uuids_do_not_drive_identity_matching():
    before = _standard(enum_uuid="duplicate-uuid").replace('uuid="enum-range"', 'uuid="duplicate-uuid"')
    after = before.replace(
        'value="1" description="Old value" uuid="duplicate-uuid"',
        'value="4" description="Old value" uuid="duplicate-uuid"',
    )
    diff = EntityTypeAPI.compare_editions(
        1, 2, source=MemorySource({1: before, 2: after}), scope="enumerations", limit=None
    )
    ambiguous = [change for change in diff.changes if change.stable_id == "duplicate-uuid"]
    assert {change.action for change in ambiguous} == {"added", "removed"}
    assert all(change.identity_match == "ambiguous_uuid" for change in ambiguous)


def test_status_cleanup_is_quiet_and_concise_omits_raw_attribute_duplication():
    before = _standard().replace(
        '<subcategory value="3" description="Tracked entry" uuid="tracked-entry"/>',
        '<subcategory value="3" description="Tracked entry" uuid="tracked-entry" status="new"/>',
    )
    after = before.replace(' status="new"', "")
    diff = EntityTypeAPI.compare_editions(
        1, 2, source=MemorySource({1: before, 2: after}), scope="entities", limit=None
    )
    change = next(row for row in diff.changes if row.stable_id == "tracked-entry")
    concise = next(row for row in diff.concise().changes if row.stable_id == "tracked-entry")
    assert change.changed_fields == ("status", "attributes")
    assert change.compatibility == "unchanged"
    assert change.review_priority == "none"
    assert [delta.name for delta in concise.fields] == ["status"]
    assert diff.summary().status_cleanups == 1
    assert diff.summary().table_status_cleanups == 0


def test_added_enumeration_has_concise_identity_and_label():
    before = _standard().replace(
        'name="Example table" size="8"', 'name="Example table" applicability="1.2.X" size="8"'
    )
    after = before.replace(
        '<enum uid="90" name="Example table" applicability="1.2.X" size="8" uuid="enum-table-90">',
        '<enum uid="90" name="Example table" applicability="1.2.X" size="8" uuid="enum-table-90">'
        '<enumrow value="12" description="Newly added value" uuid="new-enum-value"/>',
    )
    diff = EntityTypeAPI.compare_editions(
        1, 2, source=MemorySource({1: before, 2: after}), scope="enumerations", limit=None
    )
    change = next(row for row in diff.concise().changes if row.stable_id == "new-enum-value")
    assert change.identifier == "enumeration:uuid:new-enum-value"
    assert change.label == "Newly added value"
    assert change.identity_match == "unmatched"
    assert change.assessment.wire_encoding == "unchanged"
    assert change.assessment.identifier_resolution == "additive"
    assert change.assessment.semantic_meaning == "not_assessed"
    assert change.assessment.application_migration == "not_assessed"
    assert change.review_disposition == "excluded_no_priority"
    assert change.reason_codes == ("record_added",)
    serialized = change.model_dump(mode="json")
    assert "compatibility" not in serialized
    assert set(serialized["assessment"]) == {
        "wire_encoding",
        "identifier_resolution",
        "semantic_meaning",
        "application_migration",
    }
    assert serialized["assessment"]["semantic_meaning"] == "not_assessed"
    assert change.fields == ()
    assert change.record_before is None
    assert change.record_after is not None
    assert change.record_after.label == "Newly added value"
    assert change.record_after.applicability == "1.2.X"


def test_added_enumeration_table_keeps_declared_size_and_applicability():
    before = _standard()
    after = before.replace(
        "</ebv>",
        '<enum uid="140" name="Capabilities Type" size="8" applicability="Entity"></enum></ebv>',
    )
    diff = EntityTypeAPI.compare_editions(
        1, 2, source=MemorySource({1: before, 2: after}), scope="enumerations", limit=None
    )
    concise = next(row for row in diff.concise().changes if row.identifier == "enumeration:140")
    assert concise.record_after is not None
    assert concise.record_after.table_uid == 140
    assert concise.record_after.name == "Capabilities Type"
    assert concise.record_after.size == 8
    assert concise.record_after.applicability == "Entity"


def test_mode_5_reply_width_change_is_explicitly_assessed():
    diff = EntityTypeAPI.compare_editions(
        36,
        37,
        scope="enumerations",
        enumeration_uid=350,
        limit=None,
    )
    assert len(diff.changes) == 1
    change = diff.changes[0]
    assert change.scope == "enumeration_table"
    assert change.before is not None and change.before.size == 3
    assert change.after is not None and change.after.size == 4
    assert change.assessment.wire_encoding == "potentially_breaking"
    assert change.assessment.identifier_resolution == "unchanged"
    assert change.assessment.semantic_meaning == "not_assessed"
    assert change.assessment.application_migration == "recommended"
    assert change.reason_codes == ("enumeration_declared_width_changed",)
    assert change.recommendation_codes == ("validate_enum_width_against_wire_field",)


def test_same_edition_diff_is_empty():
    xml = _standard()
    diff = EntityTypeAPI.compare_editions(1, 1, source=MemorySource({1: xml}), limit=None)
    assert diff.changes == ()
    assert diff.total == 0
    assert diff.counts == ChangeCounts()
    assert diff.schema_version == 5
    assert diff.source_sha256.from_sha256 == diff.source_sha256.to_sha256
    assert diff.summary().source_sha256 == diff.source_sha256
    assert diff.concise().schema_version == 5
    assert diff.summary().schema_version == 5
    assert diff.review_queue(limit=1).schema_version == 5


def test_baseuuid_retired_and_unmodeled_attributes_are_exposed_as_deltas():
    before = _standard().replace(
        'uuid="tracked-entry"',
        'uuid="tracked-entry" baseuuid="base-before" retired="false" variation="old"',
    )
    after = before.replace(
        'baseuuid="base-before" retired="false" variation="old"',
        'baseuuid="base-after" retired="true" variation="new"',
    )
    diff = EntityTypeAPI.compare_editions(
        1, 2, source=MemorySource({1: before, 2: after}), scope="entities", limit=None
    )
    change = next(row for row in diff.changes if row.stable_id == "tracked-entry")
    concise = next(row for row in diff.concise().changes if row.stable_id == "tracked-entry")
    deltas = {delta.name: (delta.before, delta.after) for delta in concise.fields}
    assert deltas["base_uuid"] == ("base-before", "base-after")
    assert deltas["retired"] == (False, True)
    assert deltas["attribute:variation"] == ("old", "new")
    assert "relationship" in change.categories
    assert "lifecycle" in change.categories
    assert change.assessment.wire_encoding == "unchanged"
    assert change.assessment.identifier_resolution == "potentially_breaking"
    assert change.assessment.semantic_meaning == "not_assessed"
    assert change.review_priority == "high"
    assert diff.summary().newly_retired == 1
    assert diff.summary().relationship_changes == 1

    base_only = before.replace(' retired="false" variation="old"', "")
    base_only_after = base_only.replace('baseuuid="base-before"', 'baseuuid="base-after"')
    relationship_diff = EntityTypeAPI.compare_editions(
        1,
        2,
        source=MemorySource({1: base_only, 2: base_only_after}),
        scope="entities",
        limit=None,
    )
    relationship = next(row for row in relationship_diff.changes if row.stable_id == "tracked-entry")
    assert relationship.assessment.wire_encoding == "unchanged"
    assert relationship.assessment.identifier_resolution == "potentially_breaking"
    assert relationship.assessment.application_migration == "recommended"
    assert relationship.review_priority == "medium"


def test_concise_labels_use_table_name_and_enum_identity_fallback():
    before = _standard().replace('description="Old value"', 'description=""')
    table_change = before.replace('size="8" uuid="enum-table-90"', 'size="7" uuid="enum-table-90"')
    table_diff = EntityTypeAPI.compare_editions(
        1,
        2,
        source=MemorySource({1: before, 2: table_change}),
        scope="enumerations",
        limit=None,
    )
    table = next(row for row in table_diff.concise().changes if row.scope == "enumeration_table")
    assert table.label == "Example table"
    assert table.assessment.wire_encoding == "potentially_breaking"
    assert "enumeration_declared_width_changed" in table.reason_codes
    assert "validate_enum_width_against_wire_field" in table.recommendation_codes

    value_change = before.replace('uuid="enum-value-1"', 'uuid="enum-value-1" footnote="See note"')
    value_diff = EntityTypeAPI.compare_editions(
        1,
        2,
        source=MemorySource({1: before, 2: value_change}),
        scope="enumerations",
        limit=None,
    )
    value = next(row for row in value_diff.concise().changes if row.stable_id == "enum-value-1")
    assert value.label == "Example table · UID 90 · Value 1"


def test_summary_has_scope_counts_and_snapshot_free_review_items(comparison_source):
    diff = EntityTypeAPI.compare_editions(1, 2, source=comparison_source, limit=None)
    summary = diff.summary()
    counts = summary.added_by_scope
    assert counts.entity_types + counts.enumeration_values + counts.enumeration_tables == diff.counts.added
    assert summary.report_type == "summary"
    assert summary.generator_version == diff.generator_version
    assert len(summary.review_preview) <= 10
    assert summary.review_queue_count >= len(summary.review_preview)
    unassessed = summary.unassessed_assessment_counts
    assert unassessed.wire_encoding == sum(
        change.assessment.wire_encoding == "not_assessed" for change in diff.changes
    )
    assert unassessed.identifier_resolution == sum(
        change.assessment.identifier_resolution == "not_assessed" for change in diff.changes
    )
    meaning_unassessed = summary.unassessed_semantic_meaning_by_change
    assert (
        meaning_unassessed.new_catalog_records
        + meaning_unassessed.changed_base_uuid_relationships
        + meaning_unassessed.other
        == unassessed.semantic_meaning
    )
    page_low_count = summary.low_priority_omitted_count
    assert page_low_count == diff.review_queue(limit=2).low_priority_omitted_count
    page = diff.review_queue(limit=2)
    full_page = diff.review_queue(limit=1000)
    assert page.report_type == "review_queue"
    assert page.total == full_page.total == summary.review_queue_count
    assert page.changes == full_page.changes[:2]
    assert page.limit == 2
    assert page.returned == len(page.changes) == 2
    assert page.has_more
    assert page.source_sha256 == diff.source_sha256
    assert page.generator_version == diff.generator_version
    assert page.changes[0].assessment.wire_encoding in {"breaking", "potentially_breaking"} or page.changes[
        0
    ].assessment.identifier_resolution in {"breaking", "potentially_breaking"}
    assert diff.concise().report_type == "concise"
    assert diff.concise().generator_version == diff.generator_version
    assert diff.model_dump(mode="json")["report_type"] == "audit"
    queue_preview = diff.review_queue(limit=10).changes
    assert [item.identifier for item in summary.review_preview] == [item.identifier for item in queue_preview]
    assert all(
        "before" not in item.model_dump()
        and "after" not in item.model_dump()
        and item.model_dump().get("record_before") is None
        and item.model_dump().get("record_after") is None
        for item in summary.review_preview
    )


def test_review_queue_is_compatibility_risk_first(comparison_source):
    diff = EntityTypeAPI.compare_editions(1, 2, source=comparison_source, limit=None)
    queue = diff.review_queue(limit=1000).changes

    def ranking(item):
        if item.assessment.wire_encoding in {"breaking", "potentially_breaking"}:
            return 0
        if item.review_priority == "high":
            return 1
        if item.assessment.identifier_resolution in {"breaking", "potentially_breaking"}:
            return 2
        if (
            item.assessment.semantic_meaning == "not_assessed"
            or item.assessment.application_migration == "not_assessed"
        ):
            return 3
        if item.review_priority == "medium":
            return 4
        return 5

    assert list(queue) == sorted(queue, key=ranking)
    risk_page = diff.review_queue(limit=100, compatibility="potentially_breaking")
    assert risk_page.total > 0
    assert all(item.compatibility == "potentially_breaking" for item in risk_page.changes)


def test_review_queue_prioritizes_risk_then_high_advisories_then_unassessed():
    changes = (
        EditionChange(
            action="modified",
            scope="entity",
            identifier="entity:2",
            assessment=ChangeAssessment(
                wire_encoding="unchanged",
                identifier_resolution="unchanged",
                semantic_meaning="not_assessed",
                application_migration="not_assessed",
            ),
            review_priority="medium",
        ),
        EditionChange(
            action="modified",
            scope="entity",
            identifier="entity:3",
            assessment=ChangeAssessment(
                wire_encoding="unchanged",
                identifier_resolution="unchanged",
                semantic_meaning="unchanged",
                application_migration="none",
            ),
            review_priority="high",
        ),
        EditionChange(
            action="modified",
            scope="entity",
            identifier="entity:1",
            assessment=ChangeAssessment(
                wire_encoding="potentially_breaking",
                identifier_resolution="breaking",
                semantic_meaning="not_assessed",
                application_migration="recommended",
            ),
            review_priority="medium",
        ),
    )
    diff = EditionDiff(
        from_version=35,
        to_version=37,
        scope="all",
        changes=changes,
        total=3,
        truncated=False,
        counts=ChangeCounts(modified=3),
    )
    queue = diff.review_queue(limit=10).changes
    assert [row.identifier for row in queue] == ["entity:1", "entity:3", "entity:2"]


def test_low_priority_metadata_changes_are_counted_and_filterable(monkeypatch, capsys):
    diff = EntityTypeAPI.compare_editions(35, 37, limit=None)
    summary = diff.summary()
    unassessed = summary.unassessed_semantic_meaning_by_change
    assert unassessed.new_catalog_records == 2553
    assert unassessed.changed_base_uuid_relationships == 133
    assert unassessed.other == summary.unassessed_assessment_counts.semantic_meaning - 2686
    assert summary.unassessed_assessment_counts.wire_encoding == 0
    assert summary.unassessed_assessment_counts.identifier_resolution == 0
    assert summary.low_priority_omitted_count == 7

    default_queue = diff.review_queue(limit=1000)
    low_priority = diff.review_queue(limit=100, priority="low")
    metadata = diff.review_queue(limit=100, priority="low", category="raw_metadata")
    low_ids = {change.identifier for change in low_priority.changes}
    assert low_priority.total == 7
    assert low_priority.low_priority_omitted_count == 7
    assert all(
        change.scope == "enumeration_value" and change.table_uid == 75 for change in low_priority.changes
    )
    assert any(delta.name == "metadata" for change in low_priority.changes for delta in change.fields)
    assert low_ids.isdisjoint(change.identifier for change in default_queue.changes)
    assert low_ids <= {change.identifier for change in metadata.changes}
    assert all("raw_metadata" in change.categories for change in metadata.changes)

    monkeypatch.setattr(EntityTypeAPI, "compare_editions", lambda *args, **kwargs: diff)
    assert (
        main(
            [
                "compare",
                "35",
                "37",
                "--detail",
                "review-queue",
                "--priority",
                "low",
                "--category",
                "raw_metadata",
                "--limit",
                "100",
                "--json",
            ]
        )
        == 0
    )
    output = json.loads(capsys.readouterr().out)
    assert output["result"]["total"] == 7
    assert output["result"]["low_priority_omitted_count"] == 7

    assert (
        main(
            [
                "compare",
                "35",
                "37",
                "--detail",
                "review-queue",
                "--identifier-resolution",
                "potentially_breaking",
                "--application-migration",
                "recommended",
                "--limit",
                "1",
                "--json",
            ]
        )
        == 0
    )
    dimension_filtered = json.loads(capsys.readouterr().out)["result"]
    assert dimension_filtered["total"] > 0
    assessment = dimension_filtered["changes"][0]["assessment"]
    assert assessment["identifier_resolution"] == "potentially_breaking"
    assert assessment["application_migration"] == "recommended"


def test_review_queue_numeric_identity_tie_breaker():
    def entity_change(value: int) -> EditionChange:
        record = ValueRecord(
            scope="entity",
            identifier=f"entity:{value}",
            path=(value,),
            value=1,
            description=f"Entity {value}",
        )
        return EditionChange(
            action="modified",
            scope="entity",
            identifier=record.identifier,
            changed_fields=("value",),
            assessment=ChangeAssessment(
                wire_encoding="potentially_breaking",
                identifier_resolution="breaking",
                semantic_meaning="not_assessed",
                application_migration="recommended",
            ),
            review_priority="medium",
            after=record,
        )

    diff = EditionDiff(
        from_version=35,
        to_version=37,
        scope="entities",
        changes=(entity_change(10), entity_change(2)),
        total=2,
        truncated=False,
        counts=ChangeCounts(modified=2),
    )
    assert [row.identifier for row in diff.review_queue(limit=2).changes] == ["entity:2", "entity:10"]


def test_reports_are_deterministic_for_identical_source_bytes():
    xml = _standard()
    source = MemorySource({1: xml, 2: xml.replace('description="Old value"', 'description="New value"')})
    first = EntityTypeAPI.compare_editions(1, 2, source=source, limit=None)
    second = EntityTypeAPI.compare_editions(1, 2, source=source, limit=None)
    assert first.model_dump_json() == second.model_dump_json()


def test_bundled_adjacent_snapshots_and_direct_v35_v37_target_reconcile():
    first = EntityTypeAPI.compare_editions(35, 36, limit=None)
    second = EntityTypeAPI.compare_editions(36, 37, limit=None)
    direct = EntityTypeAPI.compare_editions(35, 37, limit=None)
    width_first = second.review_queue(limit=1).changes[0]
    assert width_first.identifier == "enumeration:350"
    assert width_first.assessment.wire_encoding == "potentially_breaking"

    derived = [change for change in first.changes if change.origin == "derived"]
    direct_entity_changes = {
        change.identifier
        for change in first.changes
        if change.scope == "entity" and change.origin == "direct"
    }
    assert derived
    assert all(change.caused_by for change in derived)
    assert all(cause.identifier in direct_entity_changes for change in derived for cause in change.caused_by)

    def identity(record):
        return (record.scope, record.stable_id or record.identifier)

    middle_from_first = {identity(change.after): change.after for change in first.changes if change.after}
    middle_from_second = {
        identity(change.before): change.before for change in second.changes if change.before
    }
    shared = middle_from_first.keys() & middle_from_second.keys()
    assert len(shared) == 1722
    assert all(middle_from_first[key] == middle_from_second[key] for key in shared)

    target_standard = _load_standard(BUNDLED_STANDARD_SOURCE, 37)
    target_records = {record.identifier: record for record in _inspection_records(target_standard)}
    for change in direct.changes:
        if change.after is not None:
            assert target_records[change.after.identifier] == change.after
    assert direct.source_sha256.from_sha256 == first.source_sha256.from_sha256
    assert direct.source_sha256.to_sha256 == second.source_sha256.to_sha256


def test_all_bundled_edition_pairs_reconcile_against_adjacent_composition():
    versions = BUNDLED_STANDARD_SOURCE.versions
    records_by_version = {
        version: tuple(_inspection_records(_load_standard(BUNDLED_STANDARD_SOURCE, version)))
        for version in versions
    }

    def signature(records):
        return Counter(record.model_dump_json() for record in records)

    def apply_changes(state, changes):
        result = state.copy()
        for change in changes:
            if change.before is not None:
                before_key = change.before.model_dump_json()
                assert result[before_key] > 0
                result.subtract((before_key,))
                if result[before_key] == 0:
                    del result[before_key]
            if change.after is not None:
                result.update((change.after.model_dump_json(),))
        return result

    signatures_by_version = {version: signature(records) for version, records in records_by_version.items()}

    adjacent = {
        (from_version, to_version): _record_changes(
            records_by_version[from_version], records_by_version[to_version]
        )
        for from_version, to_version in zip(versions[:-1], versions[1:], strict=True)
    }
    for start_index, from_version in enumerate(versions):
        starting_records = records_by_version[from_version]
        assert _record_changes(starting_records, starting_records) == []
        starting_signature = signatures_by_version[from_version]
        composed_state = starting_signature
        for to_index in range(start_index + 1, len(versions)):
            to_version = versions[to_index]
            previous_version = versions[to_index - 1]
            composed_state = apply_changes(composed_state, adjacent[(previous_version, to_version)])
            target_records = records_by_version[to_version]
            target_signature = signatures_by_version[to_version]
            assert composed_state == target_signature

            direct = _record_changes(starting_records, target_records)
            direct_state = apply_changes(starting_signature, direct)
            assert direct_state == target_signature


def test_summary_and_review_queue_require_complete_diff(comparison_source):
    diff = EntityTypeAPI.compare_editions(1, 2, source=comparison_source, scope="entities", limit=1)
    with pytest.raises(ValueError, match="complete review queue"):
        diff.review_queue()


def test_entity_prefix_filter_includes_selected_code_inside_a_source_range():
    old = _standard().replace(
        '<subcategory value="3" description="Tracked entry" uuid="tracked-entry"/>',
        '<subcategory_range value_min="3" value_max="6" description="Tracked entry" uuid="tracked-entry"/>',
    )
    new = old.replace('description="Tracked entry"', 'description="Range entry"')
    diff = EntityTypeAPI.compare_editions(
        1,
        2,
        source=MemorySource({1: old, 2: new}),
        scope="entities",
        entity_prefix=(1, 1, 1, 2, 5, 0),
        limit=None,
    )
    assert any(change.stable_id == "tracked-entry" for change in diff.changes)


def test_diff_limit_and_filters_are_explicit(comparison_source):
    diff = EntityTypeAPI.compare_editions(
        1, 2, source=comparison_source, scope="enumerations", enumeration_uid=90, limit=1
    )
    assert len(diff.changes) == 1
    assert diff.total > 1
    assert diff.truncated
    with pytest.raises(ValueError, match="complete edition summary"):
        diff.summary()
    with pytest.raises(ValueError, match="cannot be combined"):
        EntityTypeAPI.compare_editions(
            1, 2, source=comparison_source, entity_prefix=(1, 1, 1), enumeration_uid=90
        )


def test_cli_history_and_compare_emit_versioned_json(monkeypatch, capsys):
    history = ValueHistory(
        kind="entity",
        target="entity:1.1.1.2.3.0.0",
        points=(),
    )
    monkeypatch.setattr(EntityTypeAPI, "entity_history", lambda *args, **kwargs: history)
    assert main(["history", "--entity", "1.1.1.2.3.0.0", "--versions", "1", "2", "--json"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["command"] == "history"
    assert output["result"]["target"] == history.target

    monkeypatch.undo()
    diff = EditionDiff(
        from_version=35,
        to_version=37,
        scope="all",
        changes=(),
        total=0,
        truncated=False,
        counts=ChangeCounts(),
    )
    monkeypatch.setattr(EntityTypeAPI, "compare_editions", lambda *args, **kwargs: diff)
    assert main(["compare", "35", "37", "--json"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["command"] == "compare"
    assert output["result"]["from_version"] == 35

    assert main(["compare", "35", "37", "--detail", "review-queue", "--limit", "1", "--json"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["result"]["report_type"] == "review_queue"
    assert output["result"]["total"] == 0

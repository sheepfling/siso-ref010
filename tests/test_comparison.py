import json
from collections import Counter
from collections.abc import Mapping
from hashlib import sha256

import pytest

from siso_ref010 import SisoRef010API
from siso_ref010.cli import main
from siso_ref010.cli.text import print_history_text
from siso_ref010.comparison import (
    ChangeAssessment,
    ChangeCounts,
    ChangeReference,
    ConciseChange,
    EditionChange,
    EditionDiff,
    ValueHistory,
    ValueRecord,
    _classify_change,
    _display_label,
    _inspection_records,
    _load_standard,
    _optional_source_bool,
    _record_changes,
)
from siso_ref010.sources import BUNDLED_STANDARD_SOURCE


class MemorySource:
    def __init__(self, versions: Mapping[int, str]) -> None:
        self.data = versions

    @property
    def versions(self) -> tuple[int, ...]:
        return tuple(self.data)

    def read_xml(self, version: int) -> bytes:
        return self.data[version].encode()


def _standard(
    *,
    category: str = "Old category",
    subcategory_value: int = 3,
    subcategory: str = "Tracked entry",
    enum_name: str = "Example table",
    enum_value: int = 1,
    enum_description: str = "Old value",
    enum_uuid: str = "enum-value-1",
    include_removed: bool = True,
    xref_uid: int = 91,
    annotations: str = "",
) -> str:
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
def comparison_source() -> MemorySource:
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


def test_entity_history_reports_presence_and_effective_description(comparison_source: MemorySource) -> None:
    history = SisoRef010API.entity_history("1.1.1.2.4.0.0", source=comparison_source, versions=(1, 2))
    assert history.kind == "entity"
    assert [point.present for point in history.points] == [True, True]
    assert history.points[0].description == "Old category"
    assert history.points[1].description == "Tracked entry"
    assert history.points[0].matched_path == (1, 1, 1, 2)
    assert history.points[1].matched_path == (1, 1, 1, 2, 4)


def test_enumeration_history_resolves_scalar_and_range_values(comparison_source: MemorySource) -> None:
    value = SisoRef010API.enumeration_history(90, 1, source=comparison_source, versions=(1, 2))
    table = SisoRef010API.enumeration_history(90, source=comparison_source, versions=(1, 2))
    range_value = SisoRef010API.enumeration_history(90, 11, source=comparison_source, versions=(1, 2))
    assert [point.description for point in value.points] == ["Old value", "Updated value"]
    assert [point.name for point in table.points] == ["Example table", "Renamed table"]
    assert all(point.present for point in range_value.points)
    assert [point.description for point in range_value.points] == ["Range value", "Range value"]


def test_history_preserves_ambiguous_entity_and_enumeration_candidates(
    capsys: pytest.CaptureFixture[str],
) -> None:
    xml = (
        '<ebv title="Ambiguous edition">'
        '<enum uid="7" name="Entity Kind"><enumrow value="1" description="Platform"/></enum>'
        '<enum uid="90" name="First table"><enumrow value="5" description="First value"/></enum>'
        '<enum uid="90" name="Second table"><enumrow value="5" description="Second value"/></enum>'
        '<cet><entity kind="1" domain="1" country="1">'
        '<category value="2" description="First category" uuid="category-first"/>'
        '<category value="2" description="Second category" uuid="category-second"/>'
        "</entity></cet></ebv>"
    )
    source = MemorySource({1: xml})

    entity_history = SisoRef010API.entity_history("1.1.1.2.0.0.0", source=source, versions=(1,))
    entity_point = entity_history.points[0]
    assert entity_point.present
    assert entity_point.match_status is not None
    assert entity_point.match_status.value == "ambiguous"
    assert entity_point.description is None
    assert entity_point.stable_id is None
    assert [row.description for row in entity_point.candidates] == [
        "First category",
        "Second category",
    ]
    print_history_text(entity_history)
    entity_text = capsys.readouterr().out
    assert "ambiguous (2 matching source rows)" in entity_text
    assert "candidate: 1.1.1.2: First category" in entity_text
    assert "candidate: 1.1.1.2: Second category" in entity_text

    enum_history = SisoRef010API.enumeration_history(90, 5, source=source, versions=(1,))
    enum_point = enum_history.points[0]
    assert enum_point.present
    assert enum_point.match_status is not None
    assert enum_point.match_status.value == "ambiguous_table"
    assert enum_point.description is None
    assert [row.description for row in enum_point.candidates] == ["First value", "Second value"]
    assert [table.name for table in enum_point.table_candidates] == ["First table", "Second table"]
    print_history_text(enum_history)
    enumeration_text = capsys.readouterr().out
    assert "candidate table: First table (UID 90)" in enumeration_text
    assert "candidate table: Second table (UID 90)" in enumeration_text
    assert "candidate: First table: table 90:5: First value" in enumeration_text
    assert "candidate: Second table: table 90:5: Second value" in enumeration_text

    table_history = SisoRef010API.enumeration_history(90, source=source, versions=(1,))
    table_point = table_history.points[0]
    assert table_point.present
    assert table_point.name is None
    assert [table.name for table in table_point.table_candidates] == ["First table", "Second table"]


def test_pairwise_diff_detects_add_remove_modify_move_and_table_metadata(
    comparison_source: MemorySource,
) -> None:
    diff = SisoRef010API.compare_editions(1, 2, source=comparison_source, limit=None)
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


def test_diff_expands_ranges_and_tracks_cross_reference_target(comparison_source: MemorySource) -> None:
    changed = MemorySource(
        {
            1: _standard(xref_uid=91),
            2: _standard(xref_uid=92),
        }
    )
    diff = SisoRef010API.compare_editions(
        1, 2, source=changed, scope="entities", entity_prefix=(1, 1, 1, 2), limit=None
    )
    xref_rows = [change for change in diff.changes if change.after and change.after.reference_uid]
    assert xref_rows
    assert all(change.action == "modified" for change in xref_rows)
    assert all("reference_uid" in change.changed_fields for change in xref_rows)


def test_diff_distinguishes_entity_moves_from_recodes() -> None:
    source = MemorySource(
        {
            1: _standard(),
            2: _standard().replace('<category value="2"', '<category value="3"'),
        }
    )
    diff = SisoRef010API.compare_editions(1, 2, source=source, scope="entities", limit=None)
    by_identity = {(change.scope, change.stable_id): change for change in diff.changes}
    assert by_identity[("entity", "category-2")].action == "recoded"
    assert by_identity[("entity", "tracked-entry")].action == "moved"


def test_three_edition_changes_reconcile_add_modify_revert_and_restore() -> None:
    base = _standard()
    added = base.replace(
        "</category>",
        '<subcategory value="4" description="Added in middle" uuid="middle-addition"/></category>',
    )
    updated_addition = added.replace('description="Added in middle"', 'description="Final addition"')

    middle_to_final = SisoRef010API.compare_editions(
        2, 3, source=MemorySource({1: base, 2: added, 3: added}), scope="entities", limit=None
    )
    direct_add = SisoRef010API.compare_editions(
        1, 3, source=MemorySource({1: base, 2: added, 3: added}), scope="entities", limit=None
    )
    assert middle_to_final.changes == ()
    addition = next(row for row in direct_add.changes if row.stable_id == "middle-addition")
    assert addition.action == "added"
    assert addition.after is not None and addition.after.description == "Added in middle"

    modified_addition = SisoRef010API.compare_editions(
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
    reverted = SisoRef010API.compare_editions(
        1, 3, source=MemorySource({1: base, 2: modified, 3: base}), scope="entities", limit=None
    )
    assert all(row.stable_id != "tracked-entry" for row in reverted.changes)

    removed = base.replace('<subcategory value="3" description="Tracked entry" uuid="tracked-entry"/>', "")
    restored = SisoRef010API.compare_editions(
        1, 3, source=MemorySource({1: base, 2: removed, 3: base}), scope="entities", limit=None
    )
    assert all(row.stable_id != "tracked-entry" for row in restored.changes)


def test_inherited_path_label_change_references_the_changed_ancestor() -> None:
    before = _standard(category="Old category")
    after = _standard(category="Renamed category")
    source = MemorySource({1: before, 2: after})
    diff = SisoRef010API.compare_editions(1, 2, source=source, scope="entities", limit=None)
    parent = next(row for row in diff.changes if row.stable_id == "category-2")
    child = next(row for row in diff.changes if row.stable_id == "tracked-entry")
    assert parent.origin == "direct"
    assert child.origin == "derived"
    assert child.changed_fields == ("path_labels",)
    assert child.caused_by == (
        ChangeReference(scope="entity", identifier=parent.identifier, stable_id="category-2"),
    )

    filtered = SisoRef010API.compare_editions(
        1,
        2,
        source=source,
        scope="entities",
        entity_prefix=(1, 1, 1, 2, 3),
        limit=None,
    )
    filtered_child = next(row for row in filtered.changes if row.stable_id == "tracked-entry")
    assert filtered_child.caused_by == child.caused_by


def test_uuid_and_numeric_code_changes_are_reported_without_guessing() -> None:
    before = _standard(enum_uuid="stable-before")
    same_code_new_uuid = before.replace('uuid="stable-before"', 'uuid="stable-after"')
    uuid_diff = SisoRef010API.compare_editions(
        1, 2, source=MemorySource({1: before, 2: same_code_new_uuid}), scope="enumerations", limit=None
    )
    value_change = next(row for row in uuid_diff.changes if row.scope == "enumeration_value")
    assert value_change.identity_match == "code"
    assert "uuid_changed_at_stable_code" in value_change.identity_diagnostics
    assert "same_code_different_uuid" in value_change.reason_codes
    assert "resolve_identity_manually" in value_change.recommendation_codes

    reused_code = same_code_new_uuid.replace('description="Old value"', 'description="Different meaning"')
    reuse_diff = SisoRef010API.compare_editions(
        1, 2, source=MemorySource({1: before, 2: reused_code}), scope="enumerations", limit=None
    )
    reused = next(row for row in reuse_diff.changes if row.scope == "enumeration_value")
    assert reused.identity_match == "code"
    assert "possible_code_reuse" in reused.identity_diagnostics
    assert "possible_code_reuse" in reused.reason_codes
    assert reused.assessment.semantic_meaning == "not_assessed"

    recoded = before.replace('value="1" description="Old value"', 'value="4" description="Old value"')
    recode_diff = SisoRef010API.compare_editions(
        1, 2, source=MemorySource({1: before, 2: recoded}), scope="enumerations", limit=None
    )
    recoded_value = next(row for row in recode_diff.changes if row.stable_id == "stable-before")
    assert recoded_value.action == "recoded"
    assert recoded_value.identity_match == "uuid"
    assert recoded_value.assessment.wire_encoding == "potentially_breaking"
    assert recoded_value.assessment.identifier_resolution == "breaking"


def test_duplicate_code_fallbacks_are_reported_as_ambiguous() -> None:
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
    diff = SisoRef010API.compare_editions(
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


def test_duplicate_uuids_do_not_drive_identity_matching() -> None:
    before = _standard(enum_uuid="duplicate-uuid").replace('uuid="enum-range"', 'uuid="duplicate-uuid"')
    after = before.replace(
        'value="1" description="Old value" uuid="duplicate-uuid"',
        'value="4" description="Old value" uuid="duplicate-uuid"',
    )
    diff = SisoRef010API.compare_editions(
        1, 2, source=MemorySource({1: before, 2: after}), scope="enumerations", limit=None
    )
    ambiguous = [change for change in diff.changes if change.stable_id == "duplicate-uuid"]
    assert {change.action for change in ambiguous} == {"added", "removed"}
    assert all(change.identity_match == "ambiguous_uuid" for change in ambiguous)


def test_status_cleanup_is_quiet_and_concise_omits_raw_attribute_duplication() -> None:
    before = _standard().replace(
        '<subcategory value="3" description="Tracked entry" uuid="tracked-entry"/>',
        '<subcategory value="3" description="Tracked entry" uuid="tracked-entry" status="new"/>',
    )
    after = before.replace(' status="new"', "")
    diff = SisoRef010API.compare_editions(
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


def test_added_enumeration_has_concise_identity_and_label() -> None:
    before = _standard().replace(
        'name="Example table" size="8"', 'name="Example table" applicability="1.2.X" size="8"'
    )
    after = before.replace(
        '<enum uid="90" name="Example table" applicability="1.2.X" size="8" uuid="enum-table-90">',
        '<enum uid="90" name="Example table" applicability="1.2.X" size="8" uuid="enum-table-90">'
        '<enumrow value="12" description="Newly added value" uuid="new-enum-value"/>',
    )
    diff = SisoRef010API.compare_editions(
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


def test_added_enumeration_table_keeps_declared_size_and_applicability() -> None:
    before = _standard()
    after = before.replace(
        "</ebv>",
        '<enum uid="140" name="Capabilities Type" size="8" applicability="Entity"></enum></ebv>',
    )
    diff = SisoRef010API.compare_editions(
        1, 2, source=MemorySource({1: before, 2: after}), scope="enumerations", limit=None
    )
    concise = next(row for row in diff.concise().changes if row.identifier == "enumeration:140")
    assert concise.record_after is not None
    assert concise.record_after.table_uid == 140
    assert concise.record_after.name == "Capabilities Type"
    assert concise.record_after.size == 8
    assert concise.record_after.applicability == "Entity"


def test_mode_5_reply_width_change_is_explicitly_assessed() -> None:
    diff = SisoRef010API.compare_editions(
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


def test_same_edition_diff_is_empty() -> None:
    xml = _standard()
    diff = SisoRef010API.compare_editions(1, 1, source=MemorySource({1: xml}), limit=None)
    assert diff.changes == ()
    assert diff.total == 0
    assert diff.counts == ChangeCounts()
    assert diff.schema_version == 5
    assert diff.source_sha256.from_sha256 == diff.source_sha256.to_sha256
    assert diff.summary().source_sha256 == diff.source_sha256
    assert diff.concise().schema_version == 5
    assert diff.summary().schema_version == 5
    assert diff.review_queue(limit=1).schema_version == 5


def test_baseuuid_retired_and_unmodeled_attributes_are_exposed_as_deltas() -> None:
    before = _standard().replace(
        'uuid="tracked-entry"',
        'uuid="tracked-entry" baseuuid="base-before" retired="false" variation="old"',
    )
    after = before.replace(
        'baseuuid="base-before" retired="false" variation="old"',
        'baseuuid="base-after" retired="true" variation="new"',
    )
    diff = SisoRef010API.compare_editions(
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
    relationship_diff = SisoRef010API.compare_editions(
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


def test_concise_labels_use_table_name_and_enum_identity_fallback() -> None:
    before = _standard().replace('description="Old value"', 'description=""')
    table_change = before.replace('size="8" uuid="enum-table-90"', 'size="7" uuid="enum-table-90"')
    table_diff = SisoRef010API.compare_editions(
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
    value_diff = SisoRef010API.compare_editions(
        1,
        2,
        source=MemorySource({1: before, 2: value_change}),
        scope="enumerations",
        limit=None,
    )
    value = next(row for row in value_diff.concise().changes if row.stable_id == "enum-value-1")
    assert value.label == "Example table · UID 90 · Value 1"


def test_summary_has_scope_counts_and_snapshot_free_review_items(comparison_source: MemorySource) -> None:
    diff = SisoRef010API.compare_editions(1, 2, source=comparison_source, limit=None)
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


def test_review_queue_is_compatibility_risk_first(comparison_source: MemorySource) -> None:
    diff = SisoRef010API.compare_editions(1, 2, source=comparison_source, limit=None)
    queue = diff.review_queue(limit=1000).changes

    def ranking(item: ConciseChange) -> int:
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


def test_review_queue_prioritizes_risk_then_high_advisories_then_unassessed() -> None:
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


def test_low_priority_metadata_changes_are_counted_and_filterable(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    diff = SisoRef010API.compare_editions(35, 37, limit=None)
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

    monkeypatch.setattr(SisoRef010API, "compare_editions", lambda *args, **kwargs: diff)
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


def test_review_queue_numeric_identity_tie_breaker() -> None:
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


def test_reports_are_deterministic_for_identical_source_bytes() -> None:
    xml = _standard()
    source = MemorySource({1: xml, 2: xml.replace('description="Old value"', 'description="New value"')})
    first = SisoRef010API.compare_editions(1, 2, source=source, limit=None)
    second = SisoRef010API.compare_editions(1, 2, source=source, limit=None)
    assert first.model_dump_json() == second.model_dump_json()


def test_bundled_adjacent_snapshots_and_direct_v35_v37_target_reconcile() -> None:
    first = SisoRef010API.compare_editions(35, 36, limit=None)
    second = SisoRef010API.compare_editions(36, 37, limit=None)
    direct = SisoRef010API.compare_editions(35, 37, limit=None)
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

    def identity(record: ValueRecord) -> tuple[str, str]:
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


@pytest.mark.all_editions
def test_all_bundled_edition_ranges_reconcile_by_adjacent_composition() -> None:
    versions = BUNDLED_STANDARD_SOURCE.versions

    def fingerprint(record: ValueRecord) -> str:
        return sha256(record.model_dump_json().encode("utf-8")).hexdigest()

    def signature(records: tuple[ValueRecord, ...]) -> Counter[str]:
        return Counter(fingerprint(record) for record in records)

    def apply_changes(
        state: Counter[str], changes: tuple[tuple[str | None, str | None], ...]
    ) -> Counter[str]:
        result = state.copy()
        for before, after in changes:
            if before is not None:
                before_key = before
                assert result[before_key] > 0
                result.subtract((before_key,))
                if result[before_key] == 0:
                    del result[before_key]
            if after is not None:
                result.update((after,))
        return result

    signatures_by_version: dict[int, Counter[str]] = {}
    adjacent: dict[tuple[int, int], tuple[tuple[str | None, str | None], ...]] = {}
    previous_version: int | None = None
    previous_records: tuple[ValueRecord, ...] | None = None
    for version in versions:
        records = tuple(_inspection_records(_load_standard(BUNDLED_STANDARD_SOURCE, version)))
        signatures_by_version[version] = signature(records)
        assert _record_changes(records, records) == []
        if previous_version is not None and previous_records is not None:
            adjacent_changes = _record_changes(previous_records, records)
            adjacent[(previous_version, version)] = tuple(
                (
                    fingerprint(change.before) if change.before is not None else None,
                    fingerprint(change.after) if change.after is not None else None,
                )
                for change in adjacent_changes
            )
        previous_version = version
        previous_records = records
    del previous_records, records

    for start_index, from_version in enumerate(versions):
        composed_state = signatures_by_version[from_version]
        for to_index in range(start_index + 1, len(versions)):
            to_version = versions[to_index]
            previous_version = versions[to_index - 1]
            composed_state = apply_changes(composed_state, adjacent[(previous_version, to_version)])
            target_signature = signatures_by_version[to_version]
            assert composed_state == target_signature


def test_summary_and_review_queue_require_complete_diff(comparison_source: MemorySource) -> None:
    diff = SisoRef010API.compare_editions(1, 2, source=comparison_source, scope="entities", limit=1)
    with pytest.raises(ValueError, match="complete review queue"):
        diff.review_queue()

    complete = SisoRef010API.compare_editions(1, 2, source=comparison_source, limit=None)
    with pytest.raises(ValueError, match="limit must be a positive integer"):
        complete.review_queue(limit=0)
    with pytest.raises(ValueError, match="limit must be a positive integer"):
        complete.review_queue(limit=True)
    with pytest.raises(ValueError, match="offset must be a nonnegative integer"):
        complete.review_queue(offset=True)


def test_comparison_and_history_reject_invalid_filters(comparison_source: MemorySource) -> None:
    invalid_comparisons = (
        {"scope": "unknown"},
        {"entity_prefix": (1, 2)},
        {"entity_prefix": (1, 2, True)},
        {"enumeration_uid": True},
        {"enumeration_uid": -1},
        {"entity_prefix": (1, 2, 3), "enumeration_uid": 90},
        {"scope": "enumerations", "entity_prefix": (1, 2, 3)},
        {"scope": "entities", "enumeration_uid": 90},
        {"limit": True},
        {"limit": -1},
    )
    for options in invalid_comparisons:
        with pytest.raises(ValueError):
            SisoRef010API.compare_editions(1, 2, source=comparison_source, **options)  # pyright: ignore[reportArgumentType] -- options deliberately contain invalid filter shapes.

    with pytest.raises(ValueError, match="unavailable"):
        SisoRef010API.compare_editions(1, 3, source=comparison_source)
    with pytest.raises(ValueError, match="At least one version"):
        SisoRef010API.entity_history("1.1.1.2.3.0.0", source=comparison_source, versions=())
    with pytest.raises(ValueError, match="must not contain duplicates"):
        SisoRef010API.entity_history("1.1.1.2.3.0.0", source=comparison_source, versions=(1, 1))
    with pytest.raises(ValueError, match="Versions must be integers"):
        SisoRef010API.entity_history("1.1.1.2.3.0.0", source=comparison_source, versions=(True,))
    with pytest.raises(ValueError, match="Unavailable versions"):
        SisoRef010API.entity_history("1.1.1.2.3.0.0", source=comparison_source, versions=(3,))
    with pytest.raises(ValueError, match="enumeration UID"):
        SisoRef010API.enumeration_history(True, source=comparison_source)
    with pytest.raises(ValueError, match="enumeration value"):
        SisoRef010API.enumeration_history(90, True, source=comparison_source)


def test_change_materiality_and_optional_boolean_normalization() -> None:
    neutral = ChangeAssessment(
        wire_encoding="unchanged",
        identifier_resolution="not_applicable",
        semantic_meaning="not_applicable",
        application_migration="none",
    )
    assert not neutral.is_material
    assert ChangeAssessment(wire_encoding="breaking").is_material
    assert ChangeAssessment(identifier_resolution="breaking").is_material
    assert ChangeAssessment(semantic_meaning="changed").is_material
    assert ChangeAssessment(application_migration="required").is_material

    assert _optional_source_bool(None) is None
    assert _optional_source_bool(" YES ") is True
    assert _optional_source_bool("false") is False
    assert _optional_source_bool("maybe") is None


def test_comparison_fallback_labels_and_table_uid_assessment() -> None:
    table = ValueRecord(scope="enumeration_table", identifier="table:7", table_uid=7)
    ranged_value = ValueRecord(
        scope="enumeration_value",
        identifier="row:7:2",
        table_uid=7,
        value_min=2,
        value_max=4,
    )
    no_value = ValueRecord(scope="enumeration_value", identifier="row:7:none", table_uid=7)
    assert _display_label(None) is None
    assert _display_label(table) == "Enumeration UID 7"
    assert _display_label(ranged_value) == "Enumeration · UID 7 · Value 2–4"
    assert _display_label(no_value) == "Enumeration · UID 7 · Value unspecified value"
    assert _display_label(ValueRecord(scope="entity", identifier="entity", path=(1, 2, 3))) == (
        "Entity type 1.2.3"
    )
    assert _display_label(ValueRecord(scope="entity", identifier="entity")) == "Entity type"

    before = ValueRecord(scope="enumeration_table", identifier="table:7", table_uid=7, name="Example")
    after = ValueRecord(scope="enumeration_table", identifier="table:8", table_uid=8, name="Example")
    classified = _classify_change(
        EditionChange(
            action="modified",
            scope="enumeration_table",
            identifier="table:7",
            changed_fields=("table_uid",),
            before=before,
            after=after,
        )
    )
    assert classified.assessment.identifier_resolution == "breaking"
    assert "enumeration_table_uid_changed" in classified.reason_codes


def test_entity_prefix_filter_includes_selected_code_inside_a_source_range() -> None:
    old = _standard().replace(
        '<subcategory value="3" description="Tracked entry" uuid="tracked-entry"/>',
        '<subcategory_range value_min="3" value_max="6" description="Tracked entry" uuid="tracked-entry"/>',
    )
    new = old.replace('description="Tracked entry"', 'description="Range entry"')
    diff = SisoRef010API.compare_editions(
        1,
        2,
        source=MemorySource({1: old, 2: new}),
        scope="entities",
        entity_prefix=(1, 1, 1, 2, 5, 0),
        limit=None,
    )
    assert any(change.stable_id == "tracked-entry" for change in diff.changes)


def test_diff_limit_and_filters_are_explicit(comparison_source: MemorySource) -> None:
    diff = SisoRef010API.compare_editions(
        1, 2, source=comparison_source, scope="enumerations", enumeration_uid=90, limit=1
    )
    assert len(diff.changes) == 1
    assert diff.total > 1
    assert diff.truncated
    with pytest.raises(ValueError, match="complete edition summary"):
        diff.summary()
    with pytest.raises(ValueError, match="cannot be combined"):
        SisoRef010API.compare_editions(
            1, 2, source=comparison_source, entity_prefix=(1, 1, 1), enumeration_uid=90
        )


def test_cli_history_and_compare_emit_versioned_json(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    history = ValueHistory(
        kind="entity",
        target="entity:1.1.1.2.3.0.0",
        points=(),
    )
    monkeypatch.setattr(SisoRef010API, "entity_history", lambda *args, **kwargs: history)
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
    monkeypatch.setattr(SisoRef010API, "compare_editions", lambda *args, **kwargs: diff)
    assert main(["compare", "35", "37", "--json"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["command"] == "compare"
    assert output["result"]["from_version"] == 35

    assert main(["compare", "35", "37", "--detail", "review-queue", "--limit", "1", "--json"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["result"]["report_type"] == "review_queue"
    assert output["result"]["total"] == 0

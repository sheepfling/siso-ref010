import json
from dataclasses import replace

import pytest

import siso_ref010.cli.app as cli
from siso_ref010 import (
    EditionReport,
    EntityTypePrefix,
    EntityTypeXmlParser,
    ReferenceCatalog,
    SisoRef010API,
    render_json,
    render_markdown,
    render_terminal,
)
from siso_ref010.cli import main
from siso_ref010.inspection import (
    EditionAudit,
    EditionExampleKind,
    _alias_description,
    _entity_depth,
    _SourceRecordSignature,
)


def _inspector_api():
    standard = EntityTypeXmlParser.from_string(
        '<ebv title="Inspection fixture" date="2026-01-02">'
        '<enum uid="7" name="Example values" applicability="1.1.X.2" size="8">'
        '<description uuid="table-note">Table context note</description>'
        '<enumrow value="8" description="Referenced value" uuid="row-8" status="active">'
        '<cr value="101"/><meta key="topic" value="fixture"/>'
        "</enumrow>"
        '<enumrow_range value_min="10" value_max="11" description="Reserved values" uuid="row-range"/>'
        "</enum>"
        '<enum uid="29" name="Country"><enumrow value="1" description="Afghanistan"/>'
        '<enumrow value="153" description="Netherlands"/></enum>'
        '<enum uid="30" name="Entity Kind"><enumrow value="1" description="Platform"/></enum>'
        '<cet name="Entity Types"><entity kind="1" domain="1" country="0">'
        '<category value="2" description="Generic category" uuid="category-2">'
        '<subcategory_range value_min="4" value_max="6" description="Ranged children" uuid="sub-range">'
        '<specific value="5" description="One specific" uuid="specific-5">'
        '<extra value="9" description="Specific extra"/></specific>'
        '</subcategory_range><subcategory_xref xref="7"/></category>'
        "</entity></cet></ebv>"
    )
    return SisoRef010API(ReferenceCatalog(standard))


def test_enumeration_table_and_row_metadata_are_inspectable():
    inspector = _inspector_api().inspector
    table = inspector.enumeration_table(7)
    assert table is not None
    assert (table.name, table.declared_size, table.entry_count, table.range_count) == (
        "Example values",
        8,
        2,
        1,
    )
    assert table.declared_size_bits == 8
    assert table.annotations[0].text == "Table context note"

    row = inspector.enumeration_rows(7, value=8)[0]
    assert row.description == "Referenced value"
    assert row.status == "active"
    assert row.uuid == "row-8"
    assert row.source.change_requests[0].minimum == 101
    assert row.source.metadata == (("topic", "fixture"),)
    assert inspector.enumeration_rows(7, value=11)[0].description == "Reserved values"


def test_inspection_result_envelopes_report_totals_and_truncation():
    inspector = _inspector_api().inspector
    tables = inspector.enumeration_table_results("example", limit=0)
    assert tables.total == 1
    assert tables.tables == ()
    assert tables.truncated

    values = inspector.value_results(kind="enumeration", table_uid=7, limit=1)
    assert values.total == 2
    assert values.returned == 1
    assert values.truncated

    matches = inspector.uuid_results("row-8")
    assert matches.total == 2
    assert matches.returned == 2
    assert not matches.truncated


def test_inspection_rejects_boolean_and_negative_numeric_filters():
    inspector = _inspector_api().inspector
    with pytest.raises(TypeError, match="table UID must be an integer"):
        inspector.enumeration_table(True)
    with pytest.raises(ValueError, match="enumeration value must be nonnegative"):
        inspector.enumeration_rows(7, value=-1)
    with pytest.raises(TypeError, match="not booleans"):
        inspector.entity_path((1, 1, 1, True))


def test_search_covers_source_metadata_and_table_annotations():
    inspector = _inspector_api().inspector
    assert inspector.search("table context note").total == 4
    assert inspector.search("row-8").hits[0].description == "Referenced value"
    page = inspector.search_page("table context note", limit=1)
    next_page = inspector.search_page("table context note", limit=1, offset=1)
    assert page.total == next_page.total == 4
    assert page.hits[0].identity != next_page.hits[0].identity
    assert "annotation" in page.hits[0].matched_fields
    assert page.hits[0].identity == inspector.search_page("table context note", limit=1).hits[0].identity
    last_page = inspector.search("table context note", limit=1, offset=3)
    assert last_page.returned == 1
    assert not last_page.truncated
    assert inspector.search("fixture").total >= 1
    assert inspector.search("xref 7").total >= 1
    assert inspector.lookup_uuid("ROW-8")[0].value == 8


def test_entity_explanation_matches_ranges_xrefs_and_generic_country():
    explanation = _inspector_api().explain_entity("1.1.153.2.5.5.0")
    assert explanation.entity == "1.1.153.2.5.5.0"
    assert explanation.description == "One specific"
    assert [row.description for row in explanation.path] == [
        "Generic category",
        "Ranged children",
        "One specific",
    ]

    referenced = _inspector_api().explain_entity("1.1.153.2.8.0.0")
    assert [row.description for row in referenced.path] == ["Generic category", "Referenced value"]
    assert referenced.path[-1].table_uid == 7
    assert referenced.path[-1].reference_source is not None
    assert referenced.resolution.status.value == "unspecified"
    assert referenced.resolution.unspecified_components == ("specific", "extra")
    assert referenced.description == "Referenced value"


def test_entity_resolution_distinguishes_exact_unspecified_partial_and_unknown():
    api = _inspector_api()
    exact = api.resolve_entity("1.1.153.2.5.5.9")
    unspecified = api.resolve_entity("1.1.153.2.5.5.0")
    partial = api.resolve_entity(EntityTypePrefix(kind=1, domain=1, country=153, category=2))
    dotted_prefix = api.resolve_entity("1.1.153.2")
    unknown = api.resolve_entity("1.1.153.2.5.5.10")
    unknown_prefix = api.resolve_entity("1.1.153.2.5.10")

    assert exact.status.value == "exact"
    assert exact.requested_depth == 7
    assert exact.matched_depth == 7
    assert not exact.is_prefix
    assert unspecified.status.value == "unspecified"
    assert unspecified.requested_depth == 7
    assert unspecified.matched_depth == 6
    assert not unspecified.is_prefix
    assert unspecified.unspecified_components == ("extra",)
    assert partial.status.value == "partial"
    assert partial.requested_depth == 4
    assert partial.matched_depth == 4
    assert partial.is_prefix
    assert "known entity path" in partial.resolution_description
    assert dotted_prefix == partial
    explained_prefix = api.explain_entity("1.1.153.2")
    assert explained_prefix.entity == "1.1.153.2"
    assert explained_prefix.resolution.is_prefix
    assert unknown.status.value == "unknown"
    assert unknown.requested_depth == 7
    assert not unknown.is_prefix
    assert unknown_prefix.status.value == "unknown"
    assert not unknown_prefix.is_prefix
    assert unknown.unresolved_components == ("extra",)
    assert "generic_country" in {mode.value for mode in unspecified.match_modes}


def test_entity_resolution_distinguishes_explicit_zero_and_ambiguous_source_rows():
    api = SisoRef010API(
        ReferenceCatalog(
            EntityTypeXmlParser.from_string(
                '<ebv><enum uid="29" name="Country"><enumrow value="1" description="A"/></enum>'
                '<enum uid="30" name="Entity Kind"><enumrow value="1" description="Platform"/></enum>'
                '<cet name="Entity Types"><entity kind="1" domain="1" country="1">'
                '<category value="0" description="Explicit zero"/>'
                '<category value="2" description="One candidate"/>'
                '<category value="2" description="Second candidate"/>'
                "</entity></cet></ebv>"
            )
        )
    )
    explicit_zero = api.resolve_entity("1.1.1.0.0.0.0")
    ambiguous = api.resolve_entity("1.1.1.2.0.0.0")
    assert explicit_zero.status.value == "unspecified"
    assert explicit_zero.matched_depth == 4
    assert explicit_zero.matched_path[0].description == "Explicit zero"
    assert ambiguous.status.value == "ambiguous"
    assert len(ambiguous.ambiguous_candidates) == 2


def test_enumeration_value_resolution_identifies_range_membership():
    inspector = _inspector_api().inspector
    exact = inspector.resolve_enumeration_value(7, 8)
    ranged = inspector.resolve_enumeration_value(7, 11)
    unknown = inspector.resolve_enumeration_value(7, 12)

    assert exact.status.value == "exact"
    assert exact.matches[0].description == "Referenced value"
    assert ranged.status.value == "range"
    assert (ranged.matches[0].value_min, ranged.matches[0].value_max) == (10, 11)
    assert unknown.status.value == "unknown"


def test_overlapping_exact_and_range_values_report_ambiguity_and_a_diagnostic():
    api = SisoRef010API(
        ReferenceCatalog(
            EntityTypeXmlParser.from_string(
                '<ebv><enum uid="7" name="Overlap">'
                '<enumrow value="1" description="Exact one"/>'
                '<enumrow_range value_min="1" value_max="3" description="Reserved"/>'
                "</enum></ebv>"
            )
        )
    )

    resolution = api.inspector.resolve_enumeration_value(7, 1)
    diagnostics = api.inspector.diagnostics(code="overlapping_values", limit=0)

    assert resolution.status.value == "ambiguous"
    assert len(resolution.matches) == 2
    assert diagnostics.total == 1
    assert diagnostics.groups[0].table_uid == 7


def test_edition_report_and_diagnostics_expose_integrity_and_source_findings():
    api = _inspector_api()
    report = api.inspector.report()
    assert report.identity.title == "Inspection fixture"
    assert len(report.identity.source_sha256 or "") == 64
    assert report.identity.provenance_status == "unverified"
    assert report.identity.package_version
    assert report.report_schema_version == 1
    assert report.validation.xml_well_formedness.value == "passed"
    assert report.validation.typed_model_validation.value == "passed"
    assert report.validation.xsd_validation.value == "not_run"
    assert report.validation.publisher_provenance.value == "unverified"
    assert report.validation.typed_model_scope
    assert report.identity.source_evidence_registry is None
    assert all(check.status.value == "checked" for check in report.validation.semantic_checks)
    assert report.summary is not None
    assert report.summary.unclassified_entity_rows == 0
    entity_example = next(example for example in report.examples if example.kind.value == "entity_resolution")
    assert entity_example.query == entity_example.result.code
    assert entity_example.result.requested_depth == len(entity_example.query.split("."))
    assert entity_example.result.is_prefix == (entity_example.result.status.value == "partial")
    assert not hasattr(entity_example, "python_expression")
    markdown = render_markdown(report)
    assert "Executable Python:" not in markdown
    assert "```python" not in markdown
    assert json.loads(render_json(report)) == report.model_dump(mode="json", by_alias=True)
    assert "SISO-REF-010" in render_terminal(report)


def test_report_renderers_handle_unavailable_sections_and_bad_example_types():
    from siso_ref010.reporting import _render_example

    report = _inspector_api().inspector.report()
    empty_diagnostics = report.diagnostics.model_copy(
        update={"total": 0, "counts": {}, "severity_counts": {}, "groups": (), "findings": ()}
    )
    unchecked_identities = report.identity_diagnostics.model_copy(
        update={"checked": False, "error": "identity collection disabled", "groups": ()}
    )
    empty_audit = EditionAudit(enumeration_tables=(), diagnostics=empty_diagnostics)
    unavailable = report.model_copy(
        update={
            "summary": None,
            "summary_error": "summary collection disabled",
            "diagnostics": empty_diagnostics,
            "identity_diagnostics": unchecked_identities,
            "examples": (),
            "audit": empty_audit,
        }
    )

    markdown = render_markdown(unavailable)
    terminal = render_terminal(unavailable)
    assert "Summary unavailable: summary collection disabled." in markdown
    assert "No diagnostic findings were reported." in markdown
    assert "No safe representative examples were available" in markdown
    assert "Identity checks were not run" in markdown
    assert "No individual diagnostic findings." in markdown
    assert "Summary unavailable: summary collection disabled" in terminal
    assert "Identity checks not run: identity collection disabled" in terminal
    assert "Individual findings (0)" in terminal

    entity_example = next(
        example for example in report.examples if example.kind is EditionExampleKind.ENTITY_RESOLUTION
    )
    bad_example = entity_example.model_copy(update={"kind": EditionExampleKind.ENUMERATION_TABLE})
    with pytest.raises(TypeError, match="Enumeration-table example"):
        _render_example(bad_example)

    table_example = next(
        example for example in report.examples if example.kind is EditionExampleKind.ENUMERATION_TABLE
    )
    value_example = next(
        example for example in report.examples if example.kind is EditionExampleKind.ENUMERATION_VALUE
    )
    with pytest.raises(TypeError, match="Enumeration-table example"):
        _render_example(table_example.model_copy(update={"result": value_example.result}))
    with pytest.raises(TypeError, match="Enumeration-value example"):
        _render_example(value_example.model_copy(update={"result": table_example.result}))
    with pytest.raises(TypeError, match="Entity-resolution example"):
        _render_example(entity_example.model_copy(update={"result": table_example.result}))

    ranged_value = _inspector_api().inspector.resolve_enumeration_value(7, 11)
    ranged_example = value_example.model_copy(update={"result": ranged_value})
    unspecified_entity = _inspector_api().resolve_entity("1.1.153.2.5.5.0")
    unspecified_example = entity_example.model_copy(update={"result": unspecified_entity})
    rendered_examples = report.model_copy(update={"examples": (ranged_example, unspecified_example)})
    assert "10–11" in render_markdown(rendered_examples)
    assert "Explicitly unspecified components: extra" in render_markdown(rendered_examples)

    unknown_kind = entity_example.model_copy(update={"kind": "future_example"})
    with pytest.raises(ValueError, match="Unsupported inspection example kind"):
        _render_example(unknown_kind)


def test_report_audit_renderers_explain_duplicate_and_conflicting_uuids():
    xml = (
        '<ebv title="Identity report" date="2026-01-02">'
        '<enum uid="7" name="Duplicate values">'
        '<enumrow value="1" description="Same label" uuid="duplicate"/>'
        '<enumrow value="1" description="Same label" uuid="duplicate"/>'
        '<enumrow value="2" description="First meaning" uuid="conflict"/>'
        '<enumrow value="3" description="Second meaning" uuid="conflict"/>'
        "</enum></ebv>"
    )
    api = SisoRef010API(ReferenceCatalog(EntityTypeXmlParser.from_string(xml)))
    report = api.inspector.report(audit=True)
    classifications = {group.classification.value for group in report.identity_diagnostics.groups}
    assert classifications == {"duplicate_source_identifier", "conflicting_source_records"}

    markdown = render_markdown(report)
    terminal = render_terminal(report)
    assert "Differing fields:" in markdown
    assert "Reference contexts" in markdown
    assert "Enumeration table inventory" in terminal
    assert "Individual findings" in terminal


def test_edition_report_v1_schema_is_generated_from_pydantic_model():
    schema = EditionReport.model_json_schema(mode="serialization", by_alias=True)

    assert "report_schema_version" in schema["required"]
    assert schema["properties"]["report_schema_version"]["const"] == 1
    assert schema["additionalProperties"] is False

    invalid = SisoRef010API(
        ReferenceCatalog(
            EntityTypeXmlParser.from_string(
                '<ebv><enum uid="7" name="A"><enumrow value="1" uuid="shared"/>'
                '<enumrow_range value_min="1" value_max="3" uuid="shared"/></enum>'
                '<enum uid="7" name="Duplicate UID"/>'
                '<cet name="Entity Types"><entity kind="1" domain="1" country="1">'
                '<category value="2"><subcategory_xref xref="999"/></category>'
                "</entity></cet></ebv>"
            )
        )
    )
    diagnostics = invalid.inspector.diagnostics(limit=None)
    codes = {finding.code for finding in diagnostics.findings}
    assert {"duplicate_table_uid", "duplicate_uuid", "overlapping_values"} <= codes
    assert "unresolved_enumeration_reference" in codes
    assert diagnostics.counts["missing_description"] >= 2
    assert diagnostics.counts["missing_uuid"] >= 1
    assert diagnostics.severity_counts["info"] >= 1
    grouped = invalid.inspector.diagnostics(limit=0, code="missing_description", table_uid=7)
    assert grouped.findings == ()
    assert grouped.total == grouped.counts["missing_description"]
    assert len(grouped.groups) == 1
    assert grouped.groups[0].table_name == "A"
    assert grouped.groups[0].count == grouped.total
    assert grouped.truncated
    assert invalid.inspector.enumeration_table(7) is None
    assert len(invalid.inspector.enumeration_tables_by_uid(7)) == 2
    duplicate_uid_result = invalid.inspector.resolve_enumeration_value(7, 1)
    assert duplicate_uid_result.status.value == "ambiguous"
    assert len(duplicate_uid_result.tables) == 2
    malformed_report = invalid.inspector.report()
    assert malformed_report.summary is None
    assert malformed_report.summary_error
    assert malformed_report.diagnostics.counts["unresolved_enumeration_reference"] == 1
    assert not malformed_report.identity_diagnostics.checked
    identity_check = next(
        check
        for check in malformed_report.validation.semantic_checks
        if check.code == "conflicting_source_records"
    )
    assert identity_check.status.value == "not_run"
    assert identity_check.finding_count is None


def test_xml_well_formedness_uses_explicit_parser_evidence_not_checksum_presence():
    parsed = EntityTypeXmlParser.from_string("<ebv/>")
    assert parsed.xml_parse_succeeded is True
    without_digest = parsed.model_copy(update={"source_sha256": None})
    assert (
        SisoRef010API(ReferenceCatalog(without_digest))
        .inspector.report()
        .validation.xml_well_formedness.value
        == "passed"
    )

    without_parse_evidence = parsed.model_copy(update={"xml_parse_succeeded": None})
    assert (
        SisoRef010API(ReferenceCatalog(without_parse_evidence))
        .inspector.report()
        .validation.xml_well_formedness.value
        == "not_run"
    )


def test_edition_summary_counts_values_and_levels_without_losing_ranges():
    summary = _inspector_api().inspector.summary()
    assert summary.title == "Inspection fixture"
    assert summary.enumeration_tables == 3
    assert summary.enumeration_values == 5
    assert summary.enumeration_ranges == 1
    assert summary.entity_levels["categories"] == 1
    assert summary.entity_levels["subcategories"] == 3
    assert summary.entity_levels["specifics"] == 3
    assert summary.unresolved_entity_values == 0
    assert summary.unclassified_entity_rows == 0
    assert summary.change_request_ranges == 1


def test_entity_search_includes_category_only_values():
    api = SisoRef010API(
        ReferenceCatalog(
            EntityTypeXmlParser.from_string(
                '<ebv><cet name="Entity Types"><entity kind="1" domain="1" country="1">'
                '<category value="2" description="Category only marker"/></entity></cet></ebv>'
            )
        )
    )
    results = api.search("category only marker")
    assert results.total == 1
    assert results.hits[0].description == "Category only marker"


def test_inspector_tracks_catalog_reinitialization_and_rejects_empty_source():
    catalog = ReferenceCatalog(EntityTypeXmlParser.from_string('<ebv title="Original"/>'))
    api = SisoRef010API(catalog)
    first = api.inspector
    replacement = EntityTypeXmlParser.from_string('<ebv title="Replacement"/>')
    catalog.initialize(replacement)
    second = api.inspector
    assert first is not second
    assert second.title == "Replacement"

    with pytest.raises(ValueError, match="No parsed SISO-REF-010 source"):
        _ = SisoRef010API(ReferenceCatalog()).inspector


def test_inspect_cli_supports_filtered_values_and_json(monkeypatch, capsys):
    api = _inspector_api()
    monkeypatch.setattr(cli, "SisoRef010API", lambda: api)

    assert (
        main(
            [
                "inspect",
                "values",
                "--kind",
                "enumeration",
                "--table-uid",
                "7",
                "--limit",
                "1",
                "--json",
            ]
        )
        == 0
    )
    result = json.loads(capsys.readouterr().out)
    assert result["command"] == "inspect.values"
    assert result["result"]["total"] == 2
    assert result["result"]["returned"] == 1
    assert result["result"]["truncated"] is True


def test_inspect_cli_searches_metadata_and_explains_entities(monkeypatch, capsys):
    api = _inspector_api()
    monkeypatch.setattr(cli, "SisoRef010API", lambda: api)

    assert main(["inspect", "search", "table context note", "--json"]) == 0
    search = json.loads(capsys.readouterr().out)
    assert search["result"]["total"] == 4
    assert search["result"]["truncated"] is False

    assert main(["inspect", "entity", "1.1.153.2.8.0.0"]) == 0
    output = capsys.readouterr().out
    assert "Generic category" in output
    assert "Referenced value" in output
    assert "Explicitly unspecified component" in output


def test_inspect_cli_resolves_ranges_and_emits_report(monkeypatch, capsys):
    api = _inspector_api()
    monkeypatch.setattr(cli, "SisoRef010API", lambda: api)
    assert main(["inspect", "value", "7", "11", "--json"]) == 0
    resolution = json.loads(capsys.readouterr().out)
    assert resolution["result"]["status"] == "range"

    assert main(["inspect", "report", "--json"]) == 0
    report = json.loads(capsys.readouterr().out)["result"]
    assert report["identity"]["source_sha256"]
    assert report["report_schema_version"] == 1
    assert report["identity"]["package_version"]
    assert report["summary"]["unclassified_entity_rows"] == 0
    assert report == json.loads(render_json(api.inspector.report()))

    assert main(["inspect", "report"]) == 0
    assert capsys.readouterr().out == render_terminal(api.inspector.report())

    assert main(["inspect", "report", "--format", "markdown"]) == 0
    assert capsys.readouterr().out == render_markdown(api.inspector.report())

    assert main(["inspect", "report", "--format", "text"]) == 0
    assert capsys.readouterr().out == render_terminal(api.inspector.report())

    assert main(["inspect", "report", "--format", "json"]) == 0
    format_json = json.loads(capsys.readouterr().out)
    assert format_json["result"] == json.loads(render_json(api.inspector.report()))

    assert main(["inspect", "report", "--audit", "--format", "markdown"]) == 0
    audit_report = api.inspector.report(audit=True)
    audit_markdown = capsys.readouterr().out
    assert audit_markdown == render_markdown(audit_report)
    assert "Individual diagnostic findings" in audit_markdown
    assert "```python" not in audit_markdown

    assert main(["inspect", "search", "row-8", "--limit", "1", "--offset", "1", "--json"]) == 0
    page = json.loads(capsys.readouterr().out)["result"]
    assert page["offset"] == 1
    assert page["hits"][0]["matched_fields"]


def test_inspect_cli_lists_annotated_tables_and_resolves_uuid(monkeypatch, capsys):
    api = _inspector_api()
    monkeypatch.setattr(cli, "SisoRef010API", lambda: api)

    assert main(["inspect", "tables", "--query", "Example values", "--json"]) == 0
    tables = json.loads(capsys.readouterr().out)
    assert tables["result"]["total"] == 1
    assert tables["result"]["tables"][0]["annotations"][0]["text"] == "Table context note"

    assert main(["inspect", "uuid", "row-8", "--json"]) == 0
    matches = json.loads(capsys.readouterr().out)
    assert matches["result"]["total"] == 2
    assert {value["kind"] for value in matches["result"]["values"]} == {
        "enumeration",
        "entity_type",
    }
    assert all(value["value"] == 8 for value in matches["result"]["values"])


def test_identity_diagnostics_classify_conflicting_uuidless_library_keys():
    api = SisoRef010API(
        ReferenceCatalog(
            EntityTypeXmlParser.from_string(
                '<ebv><cet name="Entity Types"><entity kind="1" domain="1" country="1">'
                '<category value="2" description="First definition"/>'
                '<category value="2" description="Conflicting definition"/>'
                "</entity></cet></ebv>"
            )
        )
    )
    identity = api.inspector.identity_diagnostics()
    conflict = next(group for group in identity.groups if group.uuid is None)
    assert conflict.classification.value == "conflicting_source_records"
    assert "description" in conflict.conflict_fields
    assert identity.duplicate_source_identifier_groups == 0
    assert identity.conflicting_source_record_groups == 1


def test_identity_signatures_cover_each_source_semantic_field():
    original = _SourceRecordSignature(
        tag="enumrow",
        value=1,
        value_min=None,
        value_max=None,
        description="before",
        table_uid=7,
        applicability="1.1.X.2",
        status="old",
        deprecated=False,
        footnote="a",
        attributes=(("source", "one"),),
        metadata=(("topic", "one"),),
        change_requests=((1, 2),),
    )
    changed = replace(
        original,
        tag="enumrow_range",
        value=None,
        value_min=1,
        value_max=3,
        description="after",
        table_uid=8,
        applicability="1.2.X.3",
        status="new",
        deprecated=True,
        footnote="b",
        attributes=(("source", "two"),),
        metadata=(("topic", "two"),),
        change_requests=((3, 4),),
    )
    assert set(original.differing_fields(changed)) == {
        "tag",
        "value",
        "value_min",
        "value_max",
        "description",
        "table_uid",
        "applicability",
        "status",
        "deprecated",
        "footnote",
        "attributes",
        "metadata",
        "change_requests",
    }
    assert _alias_description("Plain label") is None
    enumeration_row = _inspector_api().inspector.enumeration_rows(7)[0]
    assert _entity_depth(enumeration_row) == len(enumeration_row.hierarchy_codes)


def test_diagnostics_handle_non_numeric_entity_references_and_bad_filter_types():
    api = SisoRef010API(
        ReferenceCatalog(
            EntityTypeXmlParser.from_string(
                '<ebv><enum uid="7" name="Example">'
                '<enumrow value="1"><subcategory_xref xref="not-a-number"/></enumrow></enum>'
                '<cet name="Entity Types"><entity kind="1" domain="1" country="1">'
                '<category value="2"><subcategory_xref xref="not-a-number"/></category>'
                "</entity></cet></ebv>"
            )
        )
    )
    findings = api.inspector.diagnostics(code="unresolved_enumeration_reference", limit=None)
    assert findings.total == 2
    with pytest.raises(TypeError, match="code must be a string"):
        api.inspector.diagnostics(code=1)

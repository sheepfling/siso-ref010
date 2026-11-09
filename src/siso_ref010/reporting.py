"""Human-readable and machine-readable renderers for edition inspection reports."""

from __future__ import annotations

import json
from collections import Counter

from .inspection import (
    EditionExampleKind,
    EditionInspectionExample,
    EditionReport,
    EditionValue,
    EntityResolution,
    EnumerationTableInfo,
    EnumerationValueResolution,
)


def _md(value: object) -> str:
    """Escape source-derived text for Markdown cells and inline labels."""
    return (
        str(value)
        .replace("\\", "\\\\")
        .replace("|", "\\|")
        .replace("`", "\\`")
        .replace("\r", " ")
        .replace("\n", " ")
    )


def _edition_label(title: str, edition_number: int | None = None) -> str:
    if edition_number is not None:
        return f"Edition {edition_number}"
    suffix = title.rsplit("-v", 1)
    return f"Edition {suffix[1]}" if len(suffix) == 2 and suffix[1].isdigit() else title


def _table(headers: tuple[str, ...], rows: list[tuple[object, ...]]) -> list[str]:
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    lines.extend("| " + " | ".join(_md(value) for value in row) + " |" for row in rows)
    return lines


def _value_label(value: EditionValue) -> str:
    item = (
        str(value.value)
        if value.value is not None
        else f"{value.value_min}–{value.value_max}"
        if value.value_min is not None and value.value_max is not None
        else "no scalar code"
    )
    location = (
        f"table {value.table_uid}:{item}"
        if value.table_uid is not None
        else ".".join(map(str, value.hierarchy_codes)) or value.tag
    )
    return f"{location}: {value.description or '<no description>'}"


def _render_example(example: EditionInspectionExample) -> list[str]:
    lines = [f"### {_md(example.label)}", f"Query: `{_md(example.query)}`"]
    match example.kind:
        case EditionExampleKind.ENUMERATION_TABLE:
            if not isinstance(example.result, EnumerationTableInfo):
                raise TypeError("Enumeration-table example has an incompatible result")
            result = example.result
            width = (
                f"{result.declared_size_bits} {'bit' if result.declared_size_bits == 1 else 'bits'}"
                if result.declared_size_bits is not None
                else "unspecified"
            )
            lines.append(
                f"Table UID {result.uid}; {result.entry_count:,} value rows; "
                f"{result.range_count:,} ranges; declared width {width}."
            )
        case EditionExampleKind.ENUMERATION_VALUE:
            if not isinstance(example.result, EnumerationValueResolution):
                raise TypeError("Enumeration-value example has an incompatible result")
            result = example.result
            lines.append(f"Table {result.table_uid}, value {result.value}: **{result.status.value}**.")
            lines.extend(f"- {_value_label(value)}" for value in result.matches)
        case EditionExampleKind.ENTITY_RESOLUTION:
            if not isinstance(example.result, EntityResolution):
                raise TypeError("Entity-resolution example has an incompatible result")
            result = example.result
            outcome = (
                f"{result.matched_depth} of 7 components"
                if result.is_prefix
                else f"{result.matched_depth} of {result.requested_depth} supplied components matched"
            )
            lines.append(f"**{result.human_outcome}** — {outcome}.")
            labels = [value.description for value in result.matched_path if value.description]
            lines.append(f"Matched hierarchy: {' / '.join(labels) if labels else '<no source labels>'}.")
            for component in result.not_supplied_components:
                lines.append(f"Trailing {component.title()} component: Not supplied.")
            lines.append(
                "Unknown supplied components: "
                + (", ".join(result.unresolved_components) if result.unresolved_components else "None")
                + "."
            )
            if result.unspecified_components:
                lines.append(
                    f"Explicitly unspecified components: {', '.join(result.unspecified_components)}."
                )
        case _ as unknown:
            raise ValueError(f"Unsupported inspection example kind: {unknown!r}")
    lines.append("")
    return lines


def render_markdown(report: EditionReport) -> str:
    """Render an edition report as Markdown without embedding executable code."""
    identity = report.identity
    lines = [
        f"# SISO-REF-010 · {_edition_label(identity.title, identity.edition_number)}",
        "",
        f"**Source-declared edition date:** {_md(identity.date)}  ",
        f"**Schema namespace:** {_md(identity.namespace or 'unspecified')}  ",
        f"**Source SHA-256:** `{_md(identity.source_sha256 or 'unavailable')}`  ",
        f"**Bundled integrity:** {identity.provenance_status.value}  ",
        f"**Publisher provenance:** {report.validation.publisher_provenance.value}",
        "",
        f"Installed package `{_md(identity.package_version)}` · source evidence registry: "
        f"`{_md(identity.source_evidence_registry or 'not applicable')}`.",
        "",
        "## Validation scope",
        "",
        f"- XML well-formedness: **{report.validation.xml_well_formedness.value}**",
        f"- Typed-model validation: **{report.validation.typed_model_validation.value}**",
        f"- XSD validation: **{report.validation.xsd_validation.value}**",
        f"- Publisher provenance: **{report.validation.publisher_provenance.value}**",
        f"- Typed-model constraints: {_md(report.validation.typed_model_scope)}",
        "",
        *_table(
            ("Semantic check", "Status", "Findings", "Scope"),
            [
                (check.code, check.status.value, check.finding_count, check.description)
                for check in report.validation.semantic_checks
            ],
        ),
        "",
        "## Edition overview",
        "",
    ]
    if report.summary is None:
        lines.append(f"Summary unavailable: {_md(report.summary_error or 'unknown error')}.")
    else:
        summary = report.summary
        lines.extend(
            _table(
                ("Measure", "Count", "Definition"),
                [
                    ("Enumeration tables", f"{summary.enumeration_tables:,}", "Source table definitions"),
                    ("Enumeration values", f"{summary.enumeration_values:,}", "Scalar and ranged value rows"),
                    ("Enumeration ranges", f"{summary.enumeration_ranges:,}", "Rows with inclusive bounds"),
                    ("Value/path records", f"{summary.value_path_records:,}", "Includes hierarchy expansion"),
                    ("Distinct UUIDs", f"{summary.distinct_uuid_values:,}", "Case-insensitive source UUIDs"),
                    (
                        "Distinct library identity keys",
                        f"{summary.distinct_value_identities:,}",
                        "Library-derived grouping keys",
                    ),
                    (
                        "Attached reference records",
                        f"{summary.attached_reference_records:,}",
                        "Expanded rows with a source xref",
                    ),
                    ("Deprecated records", f"{summary.deprecated_values:,}", "Inspection record count"),
                ],
            )
        )
    diagnostics = report.diagnostics
    severity = ", ".join(f"{name} {count:,}" for name, count in diagnostics.severity_counts.items()) or "none"
    lines.extend(
        (
            "",
            "## Diagnostics",
            "",
            f"{diagnostics.total:,} findings ({severity}) in {len(diagnostics.groups):,} groups.",
        )
    )
    if diagnostics.groups:
        lines.extend(
            (
                "",
                *_table(
                    ("Severity", "Code", "Count", "Source table", "Description"),
                    [
                        (
                            group.severity.value,
                            group.code,
                            group.count,
                            f"UID {group.table_uid}: {group.table_name}"
                            if group.table_uid is not None
                            else "edition-wide",
                            group.message,
                        )
                        for group in diagnostics.groups
                    ],
                ),
            )
        )
    else:
        lines.append("No diagnostic findings were reported.")

    identity_diagnostics = report.identity_diagnostics
    lines.extend(("", "## Repeated identities", ""))
    if not identity_diagnostics.checked:
        lines.append(
            f"Identity checks were not run: {_md(identity_diagnostics.error or 'reason unavailable')}."
        )
    else:
        lines.append(
            f"{identity_diagnostics.repeated_uuid_occurrences:,} repeated UUID occurrences in "
            f"{identity_diagnostics.repeated_uuid_groups:,} UUID groups; "
            f"{identity_diagnostics.repeated_identity_key_occurrences:,} repeated library "
            "identity-key occurrences."
        )
        counts = Counter(group.classification.value for group in identity_diagnostics.groups)
        lines.extend(("", *_table(("Classification", "Groups"), sorted(counts.items()))))
        lines.append(
            f"Distinct source-row reuse groups: {identity_diagnostics.source_record_reuse_groups:,}; "
            "UUIDs assigned to multiple source rows: "
            f"{identity_diagnostics.duplicate_source_identifier_groups:,}; "
            f"conflicting source-row groups: {identity_diagnostics.conflicting_source_record_groups:,}."
        )
        lines.append(
            "UUID occurrences and repeated library identity keys can differ because each "
            "library key includes "
            "the record kind. The complete audit includes per-UUID key counts and contexts."
        )
        conflicts = [
            group
            for group in identity_diagnostics.groups
            if group.classification.value in {"duplicate_source_identifier", "conflicting_source_records"}
        ]
        for group in conflicts:
            lines.extend(("", f"- UUID `{_md(group.uuid)}`: {group.message}"))
            if group.conflict_fields:
                lines.append(f"  Differing fields: {', '.join(group.conflict_fields)}.")
            lines.extend(f"  - {_md(context)}" for context in group.sample_contexts)

    lines.extend(
        (
            "",
            "## Inspection examples",
            "",
            "Examples are selected from this edition and use reproducible queries.",
            "",
        )
    )
    if report.examples:
        for example in report.examples:
            lines.extend(_render_example(example))
    else:
        lines.append("No safe representative examples were available in this edition.")

    if report.audit is not None:
        lines.extend(
            (
                "## Complete diagnostic audit",
                "",
                "This includes the complete enumeration-table inventory and individual diagnostic findings. "
                "It is not a record-by-record dump of every catalog value or entity path.",
                "",
                "### Enumeration table inventory",
                "",
            )
        )
        tables = report.audit.enumeration_tables
        lines.extend(
            _table(
                ("UID", "Name", "Declared width", "Rows", "Ranges", "Applicability"),
                [
                    (
                        table.uid,
                        table.name,
                        f"{table.declared_size_bits} {'bit' if table.declared_size_bits == 1 else 'bits'}"
                        if table.declared_size_bits is not None
                        else "unspecified",
                        table.entry_count,
                        table.range_count,
                        table.applicability or "unspecified",
                    )
                    for table in tables
                ],
            )
        )
        detailed = report.audit.diagnostics
        lines.extend(("", f"### Individual diagnostic findings ({detailed.total:,})", ""))
        if detailed.findings:
            lines.extend(
                _table(
                    ("Severity", "Code", "Location", "Message"),
                    [
                        (finding.severity.value, finding.code, finding.location, finding.message)
                        for finding in detailed.findings
                    ],
                )
            )
        else:
            lines.append("No individual diagnostic findings.")
        lines.extend(("", "### Repeated identity evidence", ""))
        if identity_diagnostics.checked and identity_diagnostics.groups:
            lines.extend(
                _table(
                    (
                        "Identifier",
                        "Classification",
                        "Occurrences",
                        "Repeated UUIDs",
                        "Identity keys",
                        "Repeated keys",
                        "Source rows",
                        "Reference contexts",
                        "Conflict fields",
                        "Example contexts",
                    ),
                    [
                        (
                            group.uuid or group.key,
                            group.classification.value,
                            group.occurrences,
                            group.repeated_uuid_occurrences,
                            len(group.identity_keys),
                            group.repeated_identity_key_occurrences,
                            group.source_record_count,
                            group.reference_context_occurrences,
                            ", ".join(group.conflict_fields) or "none",
                            " / ".join(group.sample_contexts),
                        )
                        for group in identity_diagnostics.groups
                    ],
                )
            )
        else:
            lines.append("No repeated identities were found, or identity expansion was unavailable.")
    return "\n".join(lines).rstrip() + "\n"


def render_terminal(report: EditionReport) -> str:
    """Render a compact terminal view of an edition report."""
    identity = report.identity
    lines = [
        f"SISO-REF-010 · {_edition_label(identity.title, identity.edition_number)}",
        f"Source-declared date: {identity.date}",
        f"Package version: {identity.package_version}",
        f"Schema: {identity.namespace or 'unspecified'} · "
        f"Bundled integrity: {report.validation.bundled_integrity.value} · "
        f"Publisher provenance: {report.validation.publisher_provenance.value}",
    ]
    if report.summary is None:
        lines.append(f"Summary unavailable: {report.summary_error or 'unknown error'}")
    else:
        summary = report.summary
        lines.append(
            f"{summary.enumeration_tables:,} enumeration tables · "
            f"{summary.value_path_records:,} value/path records · "
            f"{summary.enumeration_ranges:,} ranges · "
            f"{summary.deprecated_values:,} deprecated records"
        )
    diagnostics = report.diagnostics
    severity = ", ".join(f"{name} {count:,}" for name, count in diagnostics.severity_counts.items()) or "none"
    lines.append(f"Diagnostics: {diagnostics.total:,} findings ({severity})")
    for group in diagnostics.groups:
        table = (
            f" · UID {group.table_uid}: {group.table_name}"
            if group.table_uid is not None
            else " · edition-wide"
        )
        lines.append(f"  {group.severity.value} {group.code}: {group.count:,}{table}")

    identity_checks = report.identity_diagnostics
    if identity_checks.checked:
        lines.append(
            f"Repeated identities: {identity_checks.repeated_uuid_occurrences:,} UUID occurrences in "
            f"{identity_checks.repeated_uuid_groups:,} groups; "
            f"{identity_checks.repeated_identity_key_occurrences:,} repeated identity keys"
        )
    else:
        lines.append(f"Identity checks not run: {identity_checks.error or 'reason unavailable'}")

    if report.examples:
        lines.append("Inspection examples:")
        for example in report.examples:
            status = f" [{example.status}]" if example.status else ""
            lines.append(f"  {example.query}: {example.label}{status}")

    if report.audit is not None:
        lines.extend(("", f"Enumeration table inventory ({len(report.audit.enumeration_tables):,}):"))
        for table in report.audit.enumeration_tables:
            width = (
                f"{table.declared_size_bits} {'bit' if table.declared_size_bits == 1 else 'bits'}"
                if table.declared_size_bits is not None
                else "unspecified width"
            )
            lines.append(
                f"  UID {table.uid}: {table.name} · {table.entry_count:,} rows · "
                f"{table.range_count:,} ranges · {width}"
            )
        findings = report.audit.diagnostics.findings
        lines.extend(("", f"Individual findings ({len(findings):,}):"))
        for finding in findings:
            lines.append(f"  {finding.severity.value} {finding.code}: {finding.message} [{finding.location}]")
    return "\n".join(lines) + "\n"


def render_json(report: EditionReport, *, indent: int | None = 2) -> str:
    """Serialize the presentation-independent edition report as JSON."""
    return report.model_dump_json(indent=indent, by_alias=True)


def render_json_envelope(
    report: EditionReport,
    *,
    command: str = "inspect.report",
    schema_version: int = 1,
    indent: int = 2,
) -> str:
    """Serialize a report in the CLI's versioned JSON result envelope."""
    result = json.loads(render_json(report, indent=None))
    return json.dumps(
        {"schema_version": schema_version, "command": command, "result": result},
        ensure_ascii=False,
        indent=indent,
    )

# SISO-REF-010 edition diff report schema

The edition diff has four projections under report schema version 5: `audit`,
`concise`, `summary`, and `review_queue`. Every standalone JSON projection has a
`report_type`, edition identifiers, source XML hashes, and `generator_version`.
The report schema version is independent of the installed package version.

## Assessment contract

Each change contains an `assessment` object with four independent dimensions:

| Field | Values | What it assesses |
| --- | --- | --- |
| `wire_encoding` | `unchanged`, `additive`, `potentially_breaking`, `breaking`, `not_applicable`, `not_assessed` | Whether encoded widths or numeric wire identifiers changed |
| `identifier_resolution` | Same values as `wire_encoding` | Whether this catalog resolves the same identifiers and source relationships |
| `semantic_meaning` | `unchanged`, `changed`, `not_applicable`, `not_assessed` | Whether the source establishes a meaning change |
| `application_migration` | `none`, `recommended`, `required`, `not_applicable`, `not_assessed` | What the report can say about consumer migration |

`not_assessed` means the diff cannot establish that dimension from these source
records. It is not the same as `unchanged`. `not_applicable` means the
dimension does not apply to the specific change. `application_migration` is
conservative: `recommended` asks consumers to review their use; it does not
claim that every application must change.

The XSD defines `enum/@size` as **“Enumeration size (bits).”** A change to an
enumeration table's `size` is therefore reported as a declared-width change
with `wire_encoding: "potentially_breaking"` and the reason code
`enumeration_declared_width_changed`. The table does not identify every PDU
field that consumes it, so this is not proof that a particular PDU's physical
layout changed. The recommendation `validate_enum_width_against_wire_field`
directs consumers to check the applicable protocol field definition.

The former top-level Python `compatibility` accessor remains a convenience
alias for `assessment.wire_encoding`; JSON schema v5 serializes only the
dimensioned `assessment` object. CLI `--compatibility` remains an alias for
`--wire-encoding`.

## Identity and explanation fields

`identity_match` reports `uuid`, `code`, `unmatched`, `ambiguous_uuid`, or
`ambiguous_code`. A unique UUID match takes precedence. Code fallback is used
only when the fallback identity is unique in both editions. Duplicate fallback
codes are emitted as unmatched additions/removals with `identity_match:
"ambiguous_code"`; the matcher does not choose one arbitrarily.

`identity_diagnostics` records conditions such as duplicate UUID/code values,
a UUID change at a stable code, or possible code reuse when both UUID and
description/name changed. `possible_code_reuse` is a warning for human review,
not a claim that the source authors intended to reuse the code.

`reason_codes` explain the detected condition and review decision.
`recommendation_codes` provide machine-readable next steps. New codes require
a schema-version review.

| Reason code | Meaning |
| --- | --- |
| `record_added`, `record_removed` | Catalog record appeared or disappeared |
| `entity_identifier_changed` | Entity numeric path changed |
| `enumeration_value_changed` | Enumeration numeric value or table changed |
| `enumeration_table_uid_changed` | Enumeration table UID changed |
| `enumeration_declared_width_changed` | Enumeration `size` in bits changed |
| `relationship_changed` | `base_uuid` relationship changed |
| `deprecation_introduced`, `retirement_introduced` | Record newly deprecated or retired |
| `documentation_changed` | Description, name, annotation, footnote, or path label changed |
| `source_uuid_changed`, `same_code_different_uuid` | Source UUID changed at a stable fallback code |
| `release_status_cleared` | Release-only `new` marker was removed |
| `source_metadata_changed` | Other source metadata changed |
| `inherited_path_label_changed` | Child label changed because an ancestor label changed |
| `identity_ambiguous` | Duplicate UUID or fallback code prevented a safe match |
| `possible_code_reuse` | UUID and meaning text changed at the same numeric code |
| `other_field_changed` | A change did not match a more specific rule |

| Recommendation code | Suggested action |
| --- | --- |
| `review_new_value_if_consumed` | Assess a new catalog value if the application uses it |
| `check_removed_value_references` | Check consumers for references to a removed value |
| `validate_enum_width_against_wire_field` | Compare declared enum width with the consuming protocol field |
| `review_entity_identifier_dependents` | Review data and mappings that depend on an entity identifier |
| `update_enum_value_mappings` | Update enum lookups or stored mappings |
| `review_base_relationship_dependents` | Review consumers of the changed base relationship |
| `review_deprecated_references`, `review_retired_references` | Plan use of deprecated or retired records |
| `verify_source_meaning` | Check whether source text or metadata changes meaning for consumers |
| `resolve_identity_manually` | Resolve UUID/code ambiguity using source evidence |
| `inspect_ancestor_change` | Inspect the parent change referenced by `caused_by` |

`review_disposition` is `included`, `excluded_low_priority`, or
`excluded_no_priority`; it says whether the item is in the default queue,
available through the low-priority filter, or requires another explicit
filter. `origin` distinguishes `direct` and `derived` changes.
Derived inherited path-label changes include `caused_by` references to the
direct ancestor changes when those causes can be resolved.

## Audit

`report_type: "audit"` is the complete `EditionDiff`. Each change includes
before and after `ValueRecord` snapshots, changed fields, identity evidence,
assessment dimensions, categories, reasons, recommendations, review
disposition, origin, and causal references. Source attributes, metadata,
change requests, and table annotations remain available in the snapshots.

## Concise

`report_type: "concise"` keeps identity, display label, assessment, reasons,
recommendations, origin, causal references, and meaningful field deltas.
Added records use `record_after`; removed records use `record_before`.
Modifications use `fields` deltas. Changed source attributes without a
normalized field appear as `attribute:<name>` deltas.

## Summary

`report_type: "summary"` is a bounded overview with action counts, additions
by scope, lifecycle and relationship counts, table-width changes, review
counts, and `review_preview`. It contains no full before/after snapshots.
`unassessed_assessment_counts` reports unassessed results separately for each
assessment dimension. `unassessed_semantic_meaning_by_change` distinguishes
new records and base-UUID relationship changes from other source changes.
`low_priority_omitted_count` and `explicit_filter_only_count` make default
queue exclusions visible.

## Review queue

`report_type: "review_queue"` is a separately pageable projection returned by
`EditionDiff.review_queue()`. It supports priority, wire encoding, identifier
resolution, semantic meaning, application migration, scope, action, and
category filters. The default queue includes high/medium priority changes and
changes with potentially breaking or breaking wire/identifier assessments.
Low-priority and no-priority records remain available through explicit
filters.

The default order is: wire-encoding risk; high-priority changes; identifier-
resolution risk; other changes with unassessed meaning or migration effects;
then medium-priority changes. Within each group, higher review priority,
direct origin, scope, numeric identity, stable ID, and identifier provide
deterministic tie-breakers. This puts declared enum-width changes ahead of
catalog relationship and lifecycle review items. `limit` is the requested
page size; `returned` is the number on the page; `has_more` signals another
page. Every page carries the same provenance header as other reports.

The CLI uses `compare FROM TO --detail review-queue` with `--limit`, `--offset`,
`--priority`, `--wire-encoding` (or the `--compatibility` alias),
`--identifier-resolution`, `--semantic-meaning`, `--application-migration`,
`--action`, and `--category`.

## Report bundle and evidence

The report ZIP includes a README, this schema document, and
`TEST-EVIDENCE.json`. The manifest records source XML hashes, report hashes,
implementation/test/documentation hashes, and the checks that were run. It is
evidence about a specific checkout; it does not include the implementation or
tests needed to rerun those checks.

## Reproducibility

`source_sha256.from_sha256` and `source_sha256.to_sha256` identify the exact XML
bytes compared. Report output is deterministic for the same source bytes and
comparison options.

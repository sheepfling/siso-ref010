# Edition diff reports

`EntityTypeAPI.compare_editions()` returns a typed diff with schema version 5.
Each change includes its scope, action, identity match, changed fields,
assessment, review priority, reason codes, and recommendations. Source hashes
identify the XML editions used; `generator_version` identifies the installed
package version.

## Four views

| View | Use |
| --- | --- |
| Audit | Complete before-and-after source snapshots and matching evidence. |
| Concise | Display identities and field deltas without the full snapshots. |
| Summary | Bounded counts and a short preview. |
| Review queue | Filterable, pageable changes selected for investigation. |

Use `diff.concise()`, `diff.summary()`, and `diff.review_queue()` to get those
views from the same diff. Added concise records carry `record_after`; removed
records carry `record_before`; modified records carry changed fields with
before-and-after values.

## Assessments

Each change assesses four separate questions:

| Field | Meaning |
| --- | --- |
| `wire_encoding` | Did a numeric identifier or declared width change? |
| `identifier_resolution` | Could this catalog resolve the same identifiers and relationships? |
| `semantic_meaning` | Does the source show a change in meaning? |
| `application_migration` | Does the report recommend or require consumer action? |

`not_assessed` means the source does not establish an answer. It does not mean
`unchanged`. `not_applicable` means the question does not apply to that change.
Recommendations are prompts for consumer review, not claims about every
application.

The SISO XSD defines enumeration `size` as a width in bits. A width change is
reported as potentially breaking and recommends checking the consuming
protocol field. The catalog alone cannot prove that a particular PDU layout
changed.

## Identity and derived changes

Unique UUIDs are the primary match. Numeric-code fallback is used only when the
identity is unique in both editions. Duplicate identities are reported as
ambiguous; the diff does not choose a match. `identity_diagnostics` also calls
out UUID changes at a stable code and possible code reuse.

`origin` is `direct` or `derived`. A derived path-label change includes
`caused_by` when its changed ancestor can be identified. `reason_codes` and
`recommendation_codes` explain classifications and suggested follow-up.

## Review queue and reproducibility

The default queue includes high- and medium-priority changes and changes with
breaking or unresolved identifier assessments. Low-priority and no-priority
items remain available through explicit filters. Ordering is deterministic,
with wire risks and high-priority changes first. Each page reports its offset,
requested limit, returned count, and whether more items remain.

Summaries expose low-priority exclusions and compatibility counts by dimension.
They do not contain full source snapshots. For a given pair of XML hashes and
comparison options, generated reports are deterministic.

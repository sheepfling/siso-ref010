# Python API

The library API returns typed Python values and performs no printing or process
exit. The command-line tool is a separate adapter over the same operations.

```python
from dis_entity_types import (
    Collection,
    EntityType,
    EntityTypeAPI,
    EntityTypeCatalog,
    EntityTypePrefix,
    EntityTypeStandard,
    EntityTypeXmlParser,
    decode_key,
    encode_entity,
)

api = EntityTypeAPI()
description = api.describe("1.3.153.6.4.2.0")
assert description.description == "F803 Tromp"

for hit in api.search("F803", limit=10).hits:
    print(hit.entity, hit.description)

categories = api.choices(Collection.CATEGORIES, EntityTypePrefix(kind=1, domain=4, country=153))
```

## Catalog source

| Constructor | Behavior |
| --- | --- |
| `EntityTypeAPI()` | Loads the bundled SISO-REF-010-v37 XML. |
| `EntityTypeAPI.bundled_versions()` | Returns available releases and the default without parsing XML. |
| `EntityTypeAPI.bundled(version=35)` | Loads a specific bundled edition by release number. |
| `EntityTypeAPI.from_source(source, version)` | Retrieves one edition through a `StandardSource`. |
| `EntityTypeAPI.iter_editions(source=None, versions=None)` | Lazily yields version/API pairs for the same query across releases. |
| `EntityTypeAPI.entity_history(entity, versions=None)` | Reports presence and descriptions for one entity code across releases. |
| `EntityTypeAPI.enumeration_history(uid, value=None, versions=None)` | Reports one enumeration table or value across releases. |
| `EntityTypeAPI.compare_editions(from_version, to_version, ...)` | Diffs entity values, enumeration tables, and enumeration values between releases. |
| `EntityTypeAPI.from_xml(path)` | Parses and uses another SISO-REF-010 XML file. |
| `EntityTypeAPI(catalog, query_backend=...)` | Uses an existing catalog and optionally replaces the structured query backend. |
| `EntityTypeCatalog.bundled()` | Loads the bundled XML into the lookup projection. |
| `EntityTypeCatalog.from_xml(path)` | Parses XML and builds the lookup projection. |
| `EntityTypeCatalog(standard)` | Builds the projection from an `EntityTypeStandard`. |

`StandardSource` is the retrieval boundary: it declares available `versions` and
returns the original XML bytes for `read_xml(version)`. The bundled
`BundledStandardSource` resolves edition offsets and checksums from `index.json`
and reads the compressed XZ pack. A different archive, cache, or remote source
can implement the same small protocol without changing parsing or catalog
projection.

To save an exact bundled XML edition from Python, use the public byte source:

```python
from pathlib import Path

from dis_entity_types import BUNDLED_STANDARD_SOURCE

Path("SISO-REF-010-v35.xml").write_bytes(BUNDLED_STANDARD_SOURCE.read_xml(35))
```

`iter_editions()` provides a horizontal query over releases while loading each
edition only as the iteration reaches it:

```python
from dis_entity_types import EntityTypeAPI

search_by_release = {
    version: api.search("F803") for version, api in EntityTypeAPI.iter_editions(versions=(35, 36, 37))
}
```

For a single entity code or enumeration value, use the history helpers:

```python
entity_history = EntityTypeAPI.entity_history("1.3.153.6.4.2.0", versions=(35, 36, 37))
table_history = EntityTypeAPI.enumeration_history(7, versions=(35, 36, 37))
value_history = EntityTypeAPI.enumeration_history(7, 1, versions=(35, 36, 37))
```

`EntityTypeAPI.compare_editions(35, 37)` returns deterministic `EditionChange`
records for additions, removals, modifications, moves, and recodes. `scope`
can be `all`, `entities`, or `enumerations`; `entity_prefix=(1, 3, 153)` and
`enumeration_uid=7` narrow the comparison. Results include source attributes,
metadata, UUIDs, change requests, and table annotations. Numeric ranges and
enumeration cross-references are expanded for effective entity lookups. Unique
UUIDs identify moves and recodes. Code fallback is used only when its identity
is unique in both editions. Duplicate UUIDs or codes are emitted as unmatched
additions/removals with `identity_match="ambiguous_uuid"` or
`"ambiguous_code"`; the matcher does not choose arbitrarily. A UUID change at a
stable code and possible code reuse are separately exposed in
`identity_diagnostics`.

Each change carries four independent assessments: `wire_encoding`,
`identifier_resolution`, `semantic_meaning`, and `application_migration`.
`not_assessed` is distinct from `unchanged`; the diff does not claim to know an
application's dependencies. `reason_codes` explain the detected condition,
`recommendation_codes` suggest next steps, and derived changes include
`caused_by` references to the direct ancestor change when it can be identified.
The `compatibility` Python property is an alias for `assessment.wire_encoding`.

`limit` bounds returned detail while `total`, `counts`, and `truncated` describe
the full diff. Use `diff.summary()` for aggregate counts by record scope and a
bounded review preview, or `diff.concise()` for useful identifiers and field
deltas without full source snapshots. Summaries require an untruncated diff.
Fetch review items separately with `diff.review_queue(limit=100, priority="high")`;
filters also accept wire compatibility, identifier resolution, semantic
meaning, application migration, scope, action, and category. Comparison schema
version 5 uses a `report_type` discriminator, source hashes, and
`generator_version`.

The audit projection is the default `EditionDiff` model. `diff.concise()`
returns `report_type="concise"`; additions and removals use a small typed
`record_after` or `record_before` snapshot, while modifications carry field
deltas. `diff.summary()` returns a bounded `report_type="summary"` projection.
All projections use the same comparison result and source hashes.

For source-level questions about one selected edition, `api.inspector` exposes
table listings, scalar and range rows, source metadata, UUID lookup, text search,
and the source rows that explain an entity hierarchy path:

```python
api = EntityTypeAPI.bundled(37)
summary = api.inspector.summary()
table = api.inspector.enumeration_table(7)
deprecated = api.inspector.values(deprecated=True)
matches = api.inspector.search("reserved", limit=50)
uuid_matches = api.inspector.lookup_uuid("a-source-uuid")
explanation = api.explain_entity("1.3.153.6.4.2.0")
```

`EditionValue` preserves the source tag, UUID, status, deprecation flag,
footnote, attributes, metadata, change requests, table annotations, and resolved
cross-reference context. Ranges stay represented as ranges in inspection
results; entity lookup explanations select the matching code from a range.

File APIs accept strings and `os.PathLike[str]` values, then normalize them to
`Path` internally. Parse the source directly with `EntityTypeXmlParser.from_file(path)` or
`.from_string(xml)`. These return an `EntityTypeStandard` that retains the
enumeration tables and Entity Types hierarchy. The catalog is a derived view
for entity lookups; it does not replace the source model. Details are in the
[XML parser guide](parser.md).

Catalog hierarchy methods accept one `EntityType` prefix, with unused trailing
fields set to zero. For example, categories are selected with
`EntityType(1, 4, 153, 0, 0, 0, 0)`; this keeps parent field order in one model.
The high-level `choices()` API accepts named `EntityTypePrefix` fields so parent
order is explicit.

## Operations

| Operation | Return type | Behavior |
| --- | --- | --- |
| `api.describe(entity)` | `EntityDescription` | Accepts an `EntityType` or seven-field decimal string. |
| `api.search(query, *, limit=None)` | `SearchResults` | Case-insensitive search over category through extra descriptions. |
| `api.query_entities(...)` | `EntityQueryResults` | Filters source entity records by independent code fields and optional text, with pagination. |
| `api.warmup()` | `EntityQueryWarmup` | Builds the selected backend's query indexes before latency-sensitive requests. |
| `api.choices(collection, prefix=None)` | `Choices` | Returns choices beneath a validated `EntityTypePrefix`. |
| `api.explain_entity(entity)` | `EntityExplanation` | Returns the resolved description and source rows for a full code or prefix. |
| `api.resolve_entity(entity)` | `EntityResolution` | Resolves a typed entity/prefix or a dotted string containing one through seven fields. |
| `api.inspector` | `EditionInspector` | Queries enumeration and entity values with their metadata. |
| `api.info()` | `CatalogInfo` | Reports package/source versions, attribution, and `CatalogCounts`. |
| `encode_entity(entity)` | `EntityEncoding` | Encodes an entity without loading the catalog. |
| `decode_key(key)` | `EntityEncoding` | Decodes signed/unsigned integer, decimal, or `0x` key. |

`api.search()` matches text in entity descriptions. `api.resolve_entity()` and
`api.explain_entity()` resolve one full code or a contiguous leading prefix.
`api.choices()` lists children under that same hierarchy prefix; prefixes always
start at `kind` and continue in field order. For independent field filters, use
`api.query_entities()`:

```python
api = EntityTypeAPI.bundled()
matches = api.query_entities(country=153, text="Tromp", limit=20, offset=0)
for row in matches.values:
    print(row.hierarchy_codes, row.description)
```

Each code field is optional and exact. A code falling inside a source range
matches that range row. Country-zero source rows are included for nonzero
country filters because they are generic entries; their returned
`hierarchy_codes` preserve the source country value of zero. Results are source
records at their recorded hierarchy depth, not synthesized full seven-field
codes. The field keyword names are `entity_kind`, `domain`, `country`,
`category`, `subcategory`, `specific`, and `extra`. `text` matches descriptions,
hierarchy labels, and code values. Results report the selected edition, total
matches, returned count, and truncation state. Pagination uses `limit` and
`offset`.

`api.inspector.values(kind="entity_type")` selects entity hierarchy records;
`kind` here distinguishes entity records from enumeration records, not the DIS
entity-kind field.

The default structured-query backend is `MappingEntityQueryBackend`. Implement
the `EntityQueryBackend` protocol and pass it to `EntityTypeAPI` (or its
`bundled()`, `from_xml()`, and `from_source()` constructors) to replace query
execution. A backend receives the selected `EditionInspector` and an
`EntityQueryRequest`, and returns an `EntityQueryPage` containing the total
count and requested source records. The inspector exposes the parsed standard
and cached source records; `StandardSource` remains the separate boundary for
obtaining XML bytes.

Call `api.warmup()` before serving latency-sensitive or repeated entity queries.
It builds the selected backend's indexes and returns an `EntityQueryWarmup`
summary. The default in-memory backend reports its indexed entity-row count.
Without explicit warmup, that backend scans source records, caches the last identical query, and does not build an
index on the first request. Warmup covers structured entity queries; it does
not precompute every qualified description or hierarchy-choice cache.

`KindCode`, `CountryCode`, `DomainCode`, and the hierarchy code types are
`NewType` wrappers. They remain integers at runtime while keeping different
code domains separate in typed mappings and function signatures.

```python
from dis_entity_types import CountryCode, EntityTypeCatalog, KindCode

catalog = EntityTypeCatalog.bundled()
countries: dict[CountryCode, str] = catalog.get_all_countries()
kinds: dict[KindCode, str] = catalog.get_all_kinds()
country_name = catalog.get_country_name(CountryCode(153))
historical_api = EntityTypeAPI.bundled(version=35)
```

`EntityTypeAPI.bundled_versions()` lists the editions available to select and
reports v37 as the default without loading any standard XML. The exported
`BUNDLED_STANDARD_VERSIONS` tuple is also available. Versions are reported from
each XML file's own title and date after selection.

`EntityType` fields already carry their matching code types, so a decoded
entity can be passed directly to the corresponding lookup.
`dis_entity_types.model.create_key()` accepts named, field-specific code types.
Constructing a `NewType` from an integer marks its meaning for the type
checker; runtime bounds validation is provided by `EntityType`.

Domains depend on entity kind. `get_all_domains()` therefore returns a mapping
keyed by `(KindCode, DomainCode)` pairs, while `get_all_domains_of(kind)` returns
the narrower `dict[DomainCode, str]` for one kind.

The collection parent order is:

| Collection | Parents |
| --- | --- |
| `countries`, `kinds` | none |
| `domains` | kind |
| `categories` | kind, domain, country |
| `subcategories` | kind, domain, country, category |
| `specifics` | kind, domain, country, category, subcategory |
| `extras` | kind, domain, country, category, subcategory, specific |

Both the `Collection` enum and its exact string values are accepted. Parent
fields must fit their DIS wire widths; booleans are not integer codes. Generic
country-zero choices are merged with country-specific choices in source order.

## Results and JSON output

Result values are frozen Pydantic models. Collections in `SearchResults` and
`Choices` are tuples. Use `model_dump(mode="json", by_alias=True)` for JSON output.
The nested `entity` value is serialized as its seven named integer fields. Entity
keys are decimal strings so JavaScript cannot round a 64-bit value; Python
properties remain exact integers.

`EntityType` is also a frozen Pydantic model. Its `model_dump()` output contains
the seven numeric fields; `to_key()`, `to_bytes()`, and `to_string()` provide the
protocol-specific encodings.

`SearchResults` reports total matches separately from returned hits. A
`limit=None` returns all hits; `limit=0` returns no hits while preserving the
total. Booleans are rejected as limits even though Python treats them as
integers. The CLI uses `--limit 0` to request all hits.

## Unknown values and provenance

Unknown but in-range entity codes can be represented. Lookups return an
`Unknown ...` label when no source description applies, and a short description
of `"-"` when no hierarchy level resolves.

`api.info()` returns `CatalogInfo` with fixed `CatalogCounts` fields and reads
`data_version` and `data_date` from the parsed XML. A supplied
catalog reports `data_source` as `supplied`; `EntityTypeAPI.from_xml(path)`
reports that path. `EntityTypeAPI.from_source(source, version)` reports
`bundled` for the packaged source and `supplied` for another source.
`EntityTypeAPI()` reports `bundled`. JSON serialization is an output
representation and is not accepted as catalog input.

Package exceptions retain normal `ValueError`, `TypeError`, or `IndexError`
compatibility and expose a stable `code` plus a `context` mapping for the
offending field, value, and expected bounds or type where applicable.

The source attribution recorded in the recovery materials is
`Reprinted with permission from SISO Inc.`. See the
[SISO source and redistribution notice](../src/dis_entity_types/data/standards/LICENSE_NOTICE.md)
before redistributing bundled standard data; the notice does not itself grant
redistribution rights.

## Inspecting an edition

`api.inspector` operates on the same parsed edition used by the lookup API. It
keeps enumeration rows, hierarchy rows, ranges, cross-reference targets, and
source metadata available together:

```python
api = EntityTypeAPI.bundled(version=37)
inspector = api.inspector

summary = inspector.summary()
edition_report = inspector.report()
diagnostics = inspector.diagnostics(limit=100, offset=0)
country_tables = inspector.enumeration_tables("country")
country = inspector.enumeration_table(29)
afghanistan = inspector.enumeration_rows(29, value=1)[0]

protocol_93 = inspector.resolve_enumeration_value(3, 93)
matches = inspector.search("Netherlands", limit=10, offset=0)
uuid_matches = inspector.lookup_uuid("a-source-row-uuid")
entity = api.explain_entity("1.3.153.6.4.2.0")
resolution = api.resolve_entity("1.3.153.6.4.2.0")
```

Render a report without introducing presentation code into the data model:

```python
from dis_entity_types.reporting import render_markdown

report_markdown = render_markdown(inspector.report())
audit_markdown = render_markdown(inspector.report(audit=True))
```

`EditionSummary` reports table and row counts, ranges, entity counts by
category/subcategory/specific/extra level, deprecated records, UUID coverage,
distinct UUID and library identity counts, hierarchy reference contexts, and
change-request entries. `value_path_records` adds enumeration records to
expanded entity path/value records. These are inspector records: an
enumeration row referenced in an entity hierarchy can be counted in its table
and again in one or more hierarchy contexts. Distinct identity keys are
library-derived comparison keys, not proof of unique publisher definitions.
`unclassified_entity_rows` counts source records whose level could not be
classified; it does not count failed lookup requests.

`EditionReport` combines the summary with source identity, the exact XML
SHA-256, the selected bundled edition number when available, the installed
package version, validation scopes, grouped diagnostics, and structured
inspection examples. The original title and date remain the values declared by
the source XML; renderers may use the selected edition number for a concise
heading. The examples contain queries and typed results, not code snippets.
XML well-formedness is `passed` only when the parser records successful XML
parsing; a source checksum alone does not imply that parsing was run.
Typed-model validation covers Pydantic field parsing and declared bounds,
scalar/range shape, and ordered change-request ranges. It does not imply XSD or
cross-reference validation. XSD validation is `not_run` by the API report.
Bundled archive and payload hashes are reported separately from publisher
provenance, which remains `unverified`. Caller-supplied XML also reports
unverified bundled integrity. Bundled reports identify the local
`data/standards/PROVENANCE.json` source-evidence registry; that registry records
byte comparisons and source references, not publisher authentication.
From the repository root, `python -m tools.check_standards_xsd` is a separate
offline validation operation. It runs `xmllint --nonet` only when an edition's
namespace matches a packaged schema. The current schema is namespace 2.7:
v30–v37 are validated, while v20–v29 are not run because their matching schemas
are not bundled. This build/evaluation check is not embedded into an
`EditionReport`; that report describes only validation performed or evidence
available to its own inspection call. The evaluation record includes the
validator, schema hash, source hashes, and execution environment.

The report's serialized data has its own `report_schema_version`, currently
`1`, independent of the installed package version, source edition number, and
the CLI JSON envelope's `schema_version`. Within report schema version 1,
consumers should tolerate additional fields. Renamed or removed fields, changed
field types or meanings, and incompatible status values require a new report
schema version. The CLI envelope version describes the outer command/result
wrapper; it does not replace the report's version.
The report model is independent of presentation. `dis_entity_types.reporting`
provides `render_terminal(report)`, `render_markdown(report)`, and
`render_json(report)`. Pass `audit=True` to `inspector.report()` to include an
`EditionAudit` with every enumeration-table definition and individual
diagnostic finding; it does not dump every value or entity path. Executable
Python examples belong in a separate tutorial or showcase.
`EditionInspector.diagnostics()` checks
unresolved enumeration references, repeated table UIDs and source IDs,
duplicate UUIDs, overlapping values/ranges, and missing row descriptions or
UUIDs. It returns aggregate groups by severity, code, and source table, along
with a bounded page of individual findings. The groups and counts cover the
full filtered set; pagination applies only to `findings`. `limit=0` requests no
individual findings, while `limit=None` requests all of them. Use `code`,
`table_uid`, and `severity` to filter. A missing description is informational and may be
intentional in the source. If a malformed cross-reference prevents row
expansion, raw-source diagnostics remain available and the report marks its
summary unavailable.

`EditionReport.validation.semantic_checks` lists each semantic check that ran
and its finding count; a zero means that check ran and found nothing.
`EditionInspector.identity_diagnostics()` explains repeated UUID and library
identity counts. Each group distinguishes one XML source row expanded into
multiple hierarchy contexts, a UUID reused by multiple source rows, conflicting
source-row fields, and UUID-less library-key collisions. `source_record_count`
counts distinct parsed XML source objects; `reference_context_occurrences`
counts expanded records carrying a hierarchy cross-reference. Identity checks
are marked `not_run` when unresolved source references prevent expansion.
Repeated UUID occurrences and repeated library identity-key occurrences need
not match: library keys include the record kind, so one UUID may map to more
than one library key across enumeration and entity contexts.

`enumeration_tables()` optionally filters table names and applicability text.
`EnumerationTableInfo.declared_size_bits` is the source-declared bit width,
not the row count. `enumeration_table(uid)` returns a table only when its UID
is unique; `enumeration_tables_by_uid(uid)` exposes all definitions when a
collision exists. `enumeration_rows(uid, value=...)` returns the source row
covering one value, including range membership. `resolve_enumeration_value(uid,
value)` returns `exact`, `range`, `ambiguous`, or `unknown`, with all matching
rows and table definitions.

`values()` can filter by value kind, table UID, status, or deprecated flag. Use
`enumeration_table_results()`, `value_results()`, and `uuid_results()` when a
result should include total, returned, and truncated counts. `search()` has
stable ordering and accepts `limit` and `offset`; every hit includes
`matched_fields` describing which fields matched. Entity search through
`EntityTypeAPI.search()` includes category-level descriptions as well as
deeper hierarchy values.

`api.resolve_entity()` accepts a seven-field entity code or a shorter dotted
string such as `1.3.153.6.4.2`; the shorter string is treated as a prefix.
It returns an explicit `EntityResolution` with `exact`,
`unspecified`, `partial`, `unknown`, or `ambiguous` status, requested and
matched depths, matched path, match modes, unresolved components, and a
human-readable resolution description. A successful shorter lookup keeps the
programmatic `partial` status for compatibility and exposes `human_outcome` as
`Resolved prefix`; `not_supplied_components` lists trailing fields the caller
did not provide. Explicitly unspecified zero components and unknown supplied
values remain separate. `is_prefix` is true only when every
supplied component matched and the caller supplied fewer than seven fields.
An unknown short input therefore is not presented as a successfully resolved
prefix. A zero-filled component with no source row is reported as unspecified;
an explicit zero-valued row remains a matched source row. Nonzero codes
without a source match are unknown. `api.explain_entity()` returns the same
resolution alongside its source rows. It accounts for generic-country rows,
ranges, and subcategory enumeration cross-references. Use
`inspector.entity_path()` directly when only contributing rows are needed.

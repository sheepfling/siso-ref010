# Python API

The Python API returns typed values. It does not print or exit the process.

```python
from siso_ref010 import EntityTypeAPI

api = EntityTypeAPI.bundled(37)
description = api.describe("1.3.153.6.4.2.0")
print(description.description)

for hit in api.search("F803", limit=10).hits:
    print(hit.entity, hit.description)
```

## Editions and sources

The default API uses the newest bundled edition. List and select editions with:

```python
from siso_ref010 import EntityTypeAPI

available = EntityTypeAPI.bundled_versions()
print(available.versions, available.default_version)

api = EntityTypeAPI.bundled(35)
print(api.info().data_version, api.info().data_date)
```

`EntityTypeAPI.from_xml(path)` loads another XML file. `from_source(source,
version)` retrieves one edition through a `StandardSource`. Implement that small
protocol to use a local archive, cache, or remote source. `iter_editions()`
loads each selected edition as it is reached:

```python
for version, edition_api in EntityTypeAPI.iter_editions(versions=(35, 36, 37)):
    print(version, edition_api.search("F803").total)
```

The bundled source also returns the original XML bytes. Save one edition with
`BUNDLED_STANDARD_SOURCE.read_xml(35)`.

## Look up entity types

`describe()` resolves a full seven-field DIS entity type. `search()` searches
descriptions. Use `query_entities()` for independent code filters and
pagination:

```python
matches = api.query_entities(country=153, text="Tromp", limit=20, offset=0)
for row in matches.values:
    print(row.hierarchy_codes, row.description)
```

`resolve_entity()` accepts a full code or a leading prefix. Its result
distinguishes exact, partial, unspecified, unknown, and ambiguous values.
`choices()` lists child values under an `EntityTypePrefix`; `explain_entity()`
shows the source rows behind a lookup.

The `EntityType` model uses named code types for each field. `encode_entity()`
and `decode_key()` convert between entity types and DIS keys. Both the model
and `create_key()` reject values outside their wire-field widths.

## Inspect enumerations

Use `api.inspector` to list tables, inspect source rows and metadata, search, or
resolve values by table UID. To avoid requiring a table UID, resolve by its
exact human-readable name:

```python
result = api.resolve_enumeration("DIS-PDU Type", 1)
match = result.match
if match is None:
    print(result.status.value)
else:
    print(match.description)
```

The result reports missing or duplicate table names, exact values, ranges,
overlaps, and unknown values. `result.match` returns the single exact or range
row when unambiguous; otherwise it is `None`, and `result.status` explains why.

`api.inspector.report()` returns a Pydantic `EditionReport` with the edition
identity, counts, validation scopes, diagnostics, and examples. Pass
`audit=True` to include the table inventory and individual diagnostic findings.
Use the model's Pydantic methods to serialize or generate its JSON Schema:

```python
report = api.inspector.report()
payload = report.model_dump(mode="json", by_alias=True)
schema = type(report).model_json_schema(mode="serialization", by_alias=True)
```

`report_schema_version` versions the report contract. The CLI's outer JSON
envelope has a separate `schema_version`.

## Compare editions

History helpers track an entity, enumeration table, or enumeration value:

```python
entity = EntityTypeAPI.entity_history("1.3.153.6.4.2.0")
table = EntityTypeAPI.enumeration_history(7)
value = EntityTypeAPI.enumeration_history(7, 1)
```

`EntityTypeAPI.compare_editions(35, 37)` returns changes with typed identities,
field deltas, source evidence, and separate assessments for wire encoding,
identifier resolution, meaning, and application migration. Use
`diff.summary()`, `diff.concise()`, and `diff.review_queue()` for smaller views.
The comparison contract is described in the [edition diff reference](siso-diff-schema.md).

## Source model and results

`EntityTypeXmlParser.from_file(path)` and `.from_string(xml)` return a frozen
Pydantic `EntityTypeStandard`. It retains the parsed enumeration tables,
hierarchy, ranges, cross-references, annotations, and source metadata.
`EntityTypeCatalog` is the lookup projection built from that source model.

API results are frozen Pydantic models. Serialize them with
`model_dump(mode="json", by_alias=True)`. DIS code fields use `NewType` aliases
such as `KindCode` and `CountryCode`, which remain integers at runtime but keep
different code domains distinct for type checkers.

`api.info()` reports the selected edition's title and date. The bundled edition
set is available through `EntityTypeAPI.bundled_versions()`; there is no single
data-version constant because an API instance can select different editions.

Package errors remain compatible with `ValueError`, `TypeError`, and
`IndexError` where applicable. They also provide a stable `code` and structured
`context` for the invalid input.

The code is licensed under Apache-2.0. The SISO source data has separate terms;
see the [data notice](../src/siso_ref010/data/standards/LICENSE_NOTICE.md) and
[provenance registry](provenance.md) before redistributing it.

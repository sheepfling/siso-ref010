# Python API

`SisoRef010API` is the main entry point. It returns frozen Pydantic models and
does not print or exit the process.

```python
from siso_ref010 import SisoRef010API

api = SisoRef010API.bundled(37)
entity = api.describe("1.3.153.6.4.2.0")
print(entity.description)
```

## Choose an edition

The default is the newest bundled edition. List editions, select one, or use a
custom XML source:

```python
available = SisoRef010API.bundled_versions()
api = SisoRef010API.bundled(35)
custom = SisoRef010API.from_xml("./SISO-REF-010.xml")
```

`SisoRef010API.from_source(source, version)` loads an edition through a
`StandardSource`. `iter_editions(versions=...)` yields selected editions one at
a time.

## Look up and inspect

| Need | Method |
| --- | --- |
| Describe an entity code | `api.describe(code)` |
| Resolve a full code or prefix | `api.resolve_entity(code)` |
| Filter by independent DIS fields | `api.query_entities(country=153, text="Tromp")` |
| Search entity descriptions | `api.search("F803")` |
| List valid hierarchy choices | `api.choices(collection, prefix)` |
| Explain the source rows behind a code | `api.explain_entity(code)` |
| Inspect edition tables, rows, and diagnostics | `api.inspector` |
| Resolve an enumeration by name | `api.resolve_enumeration("PDU Type", 1)` |

`describe()` requires a complete seven-field entity code. Use `resolve_entity()`
or `explain_entity()` when you have a shorter prefix.

Resolution results distinguish exact, partial, unspecified, unknown, and
ambiguous values. An ambiguous lookup returns its candidates instead of
choosing one.

`resolve_enumeration_value()` distinguishes a missing UID (`table_not_found`),
a duplicated UID (`ambiguous_table`), an absent value in a known table
(`unknown`), and multiple matching rows (`ambiguous_value`). Its `table` field
is set only for a unique UID; `tables` and `matches` preserve the alternatives.
Name-based resolution returns one value result per distinct UID.
For table-only lookup, `api.inspector.enumeration_tables_by_uid(uid)` returns
zero, one, or several definitions; `enumeration_table(uid)` returns a table
only when the UID is unique.

`describe()` raises `ambiguous_entity_description` when its code maps to
multiple source rows. Use `resolve_entity()` or `explain_entity()` to inspect
those candidates. `choices()` keeps duplicate hierarchy codes as separate
items and marks each one with `ambiguous=True`.
Country choices preserve duplicate numeric codes in the same way. The catalog's
`get_country_name()` and `get_all_countries()` raise `ambiguous_country_name`
when the selected edition assigns multiple source descriptions to a code;
`api.choices("countries")` keeps all of those candidates.
For hierarchy choices, rows are overlaid per code in source order. When a code
appears in both the requested country and country zero, the scope whose latest
source row occurs later wins; duplicate rows in that winning scope remain
visible as ambiguous candidates. Codes found in only one scope remain
available. `choices()`, `resolve_entity()`, and `describe()` use this same rule.
Kind and domain choices also preserve duplicate codes. Their catalog dictionary
getters raise `ambiguous_enumeration_name` when a code has multiple source rows.

Description search returns one hit per entity code. For an ambiguous code,
`SearchHit.description` is `None`, `candidate_descriptions` contains every
source description, and `ambiguous` is `True`; the query may match any of those
candidate descriptions.
At the lower-level catalog, `search_descriptions()` returns every candidate;
the singular `search_description()` returns strings only for unambiguous codes
and raises `ambiguous_entity_description` if a match has multiple candidates.
Use the plural method when you want all alternatives in one result.

## Compare editions

```python
history = SisoRef010API.entity_history("1.3.153.6.4.2.0")
diff = SisoRef010API.compare_editions(35, 37)
summary = diff.summary()
changes = diff.concise()
queue = diff.review_queue(limit=50)
```

`EditionDiff` is the complete audit model. Its methods return the summary,
concise, and pageable review-queue Pydantic models.

History points include `match_status`. When a code or table UID is ambiguous,
they retain the matching source rows in `candidates` or `table_candidates`
instead of selecting one description or identifier.

## Serialize results

```python
payload = changes.model_dump(mode="json", by_alias=True)
schema = type(changes).model_json_schema(mode="serialization", by_alias=True)
```

The report models contain their report type and schema version. The Python
models are the source for generated JSON Schema; the project does not maintain
a separate handwritten schema file.

`EntityTypeXmlParser.from_file(path)` and `.from_string(xml)` return a frozen
`EntityTypeStandard` that retains source attributes, hierarchy, ranges,
cross-references, annotations, and copyright text. `ReferenceCatalog` projects
that source model into lookup indexes.

Entity fields use distinct integer `NewType` aliases such as `KindCode` and
`CountryCode`. `EntityType.to_key()`, `to_bytes()`, `encode_entity()`, and
`decode_key()` provide DIS encoding operations and enforce field widths.

Package errors inherit from familiar `ValueError`, `TypeError`, or `IndexError`
classes and include a stable error code and structured context.

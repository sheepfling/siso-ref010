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

`describe()` raises `ambiguous_entity_description` when its code maps to
multiple source rows. Use `resolve_entity()` or `explain_entity()` to inspect
those candidates. `choices()` keeps duplicate hierarchy codes as separate
items and marks each one with `ambiguous=True`.

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

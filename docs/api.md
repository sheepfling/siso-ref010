# Python API

The importable API and command-line application are separate components. Neither
requires the other to be invoked. There is no HTTP server, web framework, subprocess
call, printing or process exit in the Python API.

## Supported import surfaces

```python
# High-level application API: the same operations the CLI uses.
from siso_entity_type.api import (
    EntityTypeAPI,
    Collection,
    encode_entity,
    decode_key,
)

# Lower-level model, catalog, XML conversion and upstream-compatible API.
from siso_entity_type import (
    SisoEnum,
    SisoEnums,
    EntityKind,
    EntityDomain,
    SisoEnumsParser,
    SisoEnumsFactory,
    ParseError,
)
```

`EntityTypeAPI` is also exported from the package root. Public façade names are
listed in `siso_entity_type.api.__all__`. Treat underscored names as private.
The package ships `py.typed`; public methods and result models are annotated and
checked with strict Pyright. `examples/api_usage.py` is an executable example.

## Quick start

```python
api = EntityTypeAPI()  # Load the pinned bundled catalog once; reuse this instance.
result = api.describe("1.3.153.6.4.2.0")
assert result.description == "F803 Tromp"
print(result.qualified_description)

hits = api.search("F803", limit=10)
for hit in hits.hits:
    print(hit.entity, hit.description)

for choice in api.choices(Collection.CATEGORIES, 1, 4, 153).items:
    print(choice.value, choice.description)
```

The façade delegates lookup and parsing to the original parity-tested model and
catalog. It adds no second copy of the lookup algorithms. The CLI imports these
same functions and only handles argument parsing, interaction, formatting and
process status.

## Methods and return contracts

| Operation | Return type | Behavior |
| --- | --- | --- |
| `EntityTypeAPI()` | API instance | Uses bundled v35 data. Loads once per instance. |
| `EntityTypeAPI(catalog)` | API instance | Uses an existing `SisoEnums`; reports provenance as supplied. |
| `EntityTypeAPI.from_json(path)` | API instance | Loads a custom four-map JSON file. |
| `api.describe(entity)` | `EntityDescription` | Accepts a `SisoEnum` or seven-field decimal string. |
| `api.search(query, *, limit=None)` | `SearchResults` | Case-insensitive substring search of leaf descriptions. |
| `api.choices(collection, *parents)` | `Choices` | Validates parent count, integer types and wire ranges. |
| `api.info()` | `CatalogInfoJSON` | Version, source, actual counts and known data provenance. |
| `encode_entity(entity)` | `EntityEncoding` | Same entity input as describe; no catalog loaded. |
| `decode_key(key)` | `EntityEncoding` | Signed/unsigned integer, decimal string or `0x` string. |

`SisoEnumsParser.from_file(path)` / `.from_string(xml)` and the equivalent
`SisoEnumsFactory.create_from_file` / `.create_from_string` form the XML API.
They return a parser with `to_data()` and `write_output_files(folder)` methods.
Only the explicitly named write method writes files. Normal lookup/encode/decode
and in-memory parser operations do not alter external state.

### Result models

Results are frozen dataclasses, with immutable tuples for collections:

- `EntityDescription`: `entity: SisoEnum`, `description`, `qualified_description`,
  `country_name`, `kind_name`, `domain_name`.
- `SearchResults`: `query`, `total`, `hits: tuple[SearchHit, ...]`, `limit` and a
  computed `truncated` property. `SearchHit` holds `entity` and `description`.
- `Choices`: `collection: Collection`, `parents: tuple[int, ...]`,
  `items: tuple[Choice, ...]`. Each `Choice` has `value` and `description`.
- `EntityEncoding`: `entity`, computed integer `key` and `unsigned_key`, and
  `wire_bytes: bytes` containing exactly eight network-order bytes.

Each result has a typed `to_dict()` returning a new JSON-compatible dictionary.
An entity encoding includes both a seven-field text form and a `fields` object.
All 64-bit keys in JSON are **decimal strings**, protecting them from JavaScript
floating-point truncation. Python properties remain exact integers.

### Search limits and unknown values

`limit=None` returns all matching hits. `limit=0` returns no hits while preserving
the total count. Negative, boolean and noninteger limits are rejected. This is a
normal Python slicing/count contract. The CLI's legacy `--limit 0` convention
means all results, so the CLI translates it to `None` before calling the API.

No matches return an empty tuple and total 0, not an exception. A syntactically
valid unknown leaf can resolve a generic-country or less-specific ancestor
description. The short description is `"-"` only if no fallback resolves;
unresolved components use `Unknown ...` labels. Unsupported but valid hierarchy
queries can still inherit country-0 choices; otherwise they return empty choices. Unknown domain codes remain valid numeric wire fields; the
platform-domain enum does not cover every munition/supply domain.

### Hierarchy parents

| Collection | Parents, in order |
| --- | --- |
| `countries` | none |
| `kinds` | none |
| `domains` | kind |
| `categories` | kind, domain, country |
| `subcategories` | kind, domain, country, category |
| `specifics` | kind, domain, country, category, subcategory |
| `extras` | kind, domain, country, category, subcategory, specific |

Both the `Collection` enum and these exact string values are accepted. Country
is 0..65535; other parent fields are 0..255. Booleans are not integer codes.
The original lower-level catalog methods retain upstream compatibility behavior;
new code should use `api.choices` when it wants validated queries.

### Custom data and provenance

```python
custom_api = EntityTypeAPI.from_json("output/siso-enums.json")
assert custom_api.info()["data_version"] is None
```

A custom JSON file does not carry a standard-version metadata field, so the API
does not falsely label it v35. Code provenance still reports the pinned upstream
commit. The caller can separately retain the XML parser's `title` and `date`.
A supplied catalog is borrowed; changing that catalog changes subsequent API
results. Its provenance remains `supplied`, never automatically `bundled`.

## Exceptions and side effects

- `ValueError`: malformed entity strings, out-of-range keys/fields, invalid JSON
  shape, invalid collection/parent count or search limit.
- `TypeError`: invalid entity/field/key/query types, including boolean wire fields.
- `ParseError` (a `ValueError` subclass): invalid/unsupported XML, required values
  missing, or prohibited DTD/entity declarations.
- `OSError` subclasses: file access failures. `json.JSONDecodeError` is a
  `ValueError` for invalid JSON syntax.

There are no diagnostic prints, CLI imports or `sys.exit` calls in this API.
Catch exceptions in your own application. Public signatures and JSON schemas
are documented here; intentional release changes are recorded in `CHANGELOG.md`.
See `compatibility.md` for the pinned upstream behavior and deliberate differences.

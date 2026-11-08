# dis-entity-types

A typed Python toolkit for SISO-REF-010. It bundles verified XML editions v20–v37
in a compact compressed archive, loads the selected edition on demand, parses it
into a structured Python model, and derives DIS entity
lookup, search, and encoding operations from the selected edition. It is an
independent project, not an official SISO release.

**Private review candidate; not released.** The bundled source is
SISO-REF-010-v37, dated 2026-05-25. The derived catalog currently contains 279
countries, 11 entity kinds, 68 kind/domain pairs, 1,889 categories, and 25,473
deeper entries, including values supplied through XML cross-references.

See [source provenance and hashes](docs/provenance.md) and the
[SISO source and redistribution notice](src/dis_entity_types/data/standards/LICENSE_NOTICE.md).

## Install locally

```sh
python -m pip install .
python -m pip install -e '.[dev]'
```

Python 3.11 or newer is supported. Pydantic v2 is the sole runtime dependency
and validates and serializes the structured models. Runtime use does not access
the network.

## What can I query?

The package reads SISO-REF-010 editions: the bundled v20–v37 XML, or another
edition supplied as XML. Choose the surface based on the question:

| Question | Python | CLI | What it searches or returns |
| --- | --- | --- | --- |
| What does an entity code mean? | `api.describe(code)` | `describe CODE` | Full or partial seven-field DIS entity code and its hierarchy description. |
| Which entity records fit code filters? | `api.query_entities(country=153, text="Tromp")` | `--warmup query --country 153 --text Tromp` | Combine any DIS fields independently; choose an edition, warm indexes, and page results. |
| Which descriptions or hierarchy choices match? | `api.search(text)`, `api.choices(collection, prefix)` | `search TEXT`, `list COLLECTION PARENTS...` | Search entity descriptions, or list valid children under a contiguous hierarchy prefix. |
| What is in the source edition? | `api.inspector` | `inspect ...` | Enumeration tables and values, ranges, UUIDs, source metadata, diagnostics, and the source rows behind an entity path. |
| How did a value change by release? | `entity_history(...)`, `enumeration_history(...)` | `history ...` | Presence and descriptions across selected bundled editions. |
| What changed between two releases? | `api.compare_editions(...)` | `compare FROM TO` | Added, removed, modified, moved, and recoded entity or enumeration records, with summary, audit, and review-queue views. |
| Can I read or export the original XML? | `EntityTypeXmlParser`, `BUNDLED_STANDARD_SOURCE` | `--xml PATH`, `dump VERSION` | Structured source model for a supplied file, or original bundled XML bytes. |
| How is an entity encoded on the wire? | `EntityType.to_key()`, `to_bytes()`, `encode_entity()`, `decode_key()` | `key CODE`, `key --decode KEY` | DIS entity key and byte representations. |

The [API reference](docs/api.md) and [CLI guide](docs/cli.md) give parameter,
filter, and output details. CLI JSON is versioned machine output; JSON is not an
alternate catalog input format.

## Use the Python API

```python
from dis_entity_types import EntityType, EntityTypeAPI, EntityTypeCatalog

api = EntityTypeAPI()
result = api.describe("1.3.153.6.4.2.0")
print(result.qualified_description)

for hit in api.search("F803", limit=10).hits:
    print(hit.entity, hit.description)

catalog = EntityTypeCatalog.bundled()
entity = EntityType.from_string("1.3.153.6.4.2.0")
assert catalog.get_country_name(entity.country) == "Netherlands (NLD)"
assert entity.to_bytes() == bytes.fromhex("0103009906040200")
```

`EntityType` and API results are immutable Pydantic models. Use
`model_dump(mode="json", by_alias=True)` for the JSON API representation.
`EntityType.to_key()` and `to_bytes()` encode the DIS wire forms. JSON is not
used as an alternate catalog input format.
See the [Python API reference](docs/api.md).

## Read the standard as structured data

```python
from dis_entity_types import EntityTypeCatalog, EntityTypeXmlParser

standard = EntityTypeXmlParser.from_file("SISO-REF-010.xml")
print(standard.title, standard.date)

entity_kinds = standard.enumeration("Entity Kind")
for row in entity_kinds.entries:
    print(row.value, row.description, row.source.get("uuid"))

catalog = EntityTypeCatalog(standard)
print(catalog.search_description("F803"))
```

`EntityTypeStandard` keeps enumeration tables, the Entity Types hierarchy,
revision and copyright metadata, entry ranges, XML attributes, metadata, change
requests, and resolvable cross-references. Pydantic validates each model as the
XML is mapped into it and can serialize the complete structure with
`model_dump(mode="json")`. The catalog is a derived convenience view over that
source model. See the [XML parser guide](docs/parser.md).

## Command line

```sh
dis-entity-types describe 1.3.153.6.4.2.0 --qualified
dis-entity-types search 'F803 Tromp'
dis-entity-types list categories 1 4 153
dis-entity-types key 1.2.225.7.8.7.1
dis-entity-types key --decode 72621510476957441
dis-entity-types info
```

Use `--json` for versioned machine output. To use a different standard file,
put `--xml PATH` before the command, for example:

```sh
dis-entity-types --xml ./SISO-REF-010.xml info --json
dis-entity-types --xml ./SISO-REF-010.xml search 'Tromp'
```

The package bundles historical editions v20 through v37. Select one by release
number with `--standard-version 35`; v37 remains the default. See
`dis-entity-types versions` for available editions and the default.

See the [command-line reference](docs/cli.md).

## Develop

The edition XML files are tracked verbatim in Git. Build the ignored XZ runtime
bundle before running the package, tests, or build commands:

```sh
python -m tools.build_standards_pack
git diff --exit-code -- src/dis_entity_types/data/standards/index.json
ruff check .
ruff format --check .
pyright
for xml in src/dis_entity_types/data/standards/v3[0-7].xml; do
  xmllint --nonet --noout --schema src/dis_entity_types/data/SISO-REF-010.xsd "$xml" || exit 1
done
python -m tools.check_bundled_standards
python -m pytest -q
python -m build
```

The bundled-edition check parses every XML, verifies its provenance, and
compares API queries with the source projection for every available hierarchy
prefix. The included v2.7 XSD also validates editions v30 through v37, which
use that schema namespace. Historical editions use older namespaces and are
validated by the parser because their XSD files are not bundled. CI also
checks the installed distribution. See the [code layout](docs/architecture.md)
and [CHANGELOG.md](CHANGELOG.md) for the current rework.

# siso-ref010

A typed Python toolkit for SISO-REF-010. It bundles verified XML editions v20–v37
in a compact compressed archive, loads the selected edition on demand, parses it
into a structured Python model, and derives DIS entity
lookup, search, and encoding operations from the selected edition. It is an
independent project, not an official SISO release.

**Private review candidate; not released.** The bundled source is
SISO-REF-010-v37, dated 2026-05-25. The derived catalog currently contains 279
countries, 11 entity kinds, 68 kind/domain pairs, 1,889 categories, and 25,473
deeper entries, including values supplied through XML cross-references.

The package code is MIT licensed ([LICENSE](LICENSE)). The bundled SISO XML
editions retain their own source terms; see the [edition provenance registry](src/siso_ref010/data/standards/PROVENANCE.json)
and [source notice](SISO-DATA-NOTICE.txt).
The current implementation checks and remaining public-release gates are in
[MVP release readiness](docs/release-readiness.md).

## Quick start

From the repository root, install the package and try a lookup:

```sh
python -m pip install .
python -m siso_ref010 versions
python -m siso_ref010 --standard-version 37 describe 1.3.153.6.4.2.0
```

The same lookup in Python:

```python
from siso_ref010 import SisoRef010API

api = SisoRef010API.bundled(37)
entity = api.describe("1.3.153.6.4.2.0")
print(entity.description)
```

For scripts and agents, add `--json` to a CLI command. Successful output has a
versioned `result` envelope; structured errors go to stderr. Pin an edition
with `--standard-version` so repeated runs use the same source.

Python 3.11 or newer is supported. Pydantic v2 is the sole runtime dependency.
Runtime use does not access the network. For development, install with
`python -m pip install -e '.[dev]'`.

## What can I query?

The package reads SISO-REF-010 editions: the bundled v20–v37 XML, or another
edition supplied as XML. Choose the surface based on the question:

| Question | Python | CLI | What it searches or returns |
| --- | --- | --- | --- |
| What does a complete entity code mean? | `api.describe(code)` | `describe CODE` | Description for a complete seven-field DIS entity code. |
| How does an entity-code prefix resolve? | `api.resolve_entity(prefix)`, `api.explain_entity(prefix)` | `inspect entity PREFIX` | Resolve one to seven leading fields and report matched, unspecified, or unresolved components. |
| Which entity records fit code filters? | `api.query_entities(country=153, text="Tromp")` | `--warmup query --country 153 --text Tromp` | Combine any DIS fields independently; choose an edition, warm indexes, and page results. |
| Which descriptions or hierarchy choices match? | `api.search(text)`, `api.choices(collection, prefix)` | `search TEXT`, `list COLLECTION PARENTS...` | Search entity descriptions, or list valid children under a contiguous hierarchy prefix. |
| What is in the source edition? | `api.inspector` | `inspect ...` | Enumeration tables and values, ranges, UUIDs, source metadata, diagnostics, and the source rows behind an entity path. |
| How did a value change by release? | `entity_history(...)`, `enumeration_history(...)` | `history ...` | Presence, resolution status, and descriptions across selected bundled editions; ambiguous matches retain their candidates. |
| What changed between two releases? | `api.compare_editions(...)` | `compare FROM TO` | Added, removed, modified, moved, and recoded entity or enumeration records, with summary, audit, and review-queue views. |
| Can I read or export the original XML? | `EntityTypeXmlParser`, `BUNDLED_STANDARD_SOURCE` | `--xml PATH`, `dump VERSION` | Structured source model for a supplied file, or original bundled XML bytes. |
| How is an entity encoded on the wire? | `EntityType.to_key()`, `to_bytes()`, `encode_entity()`, `decode_key()` | `key CODE`, `key --decode KEY` | DIS entity key and byte representations. |

The [API reference](docs/api.md) and [CLI guide](docs/cli.md) give parameter,
filter, and output details. CLI JSON is versioned machine output; JSON is not an
alternate catalog input format.

## More Python examples

```python
from siso_ref010 import EntityType, ReferenceCatalog, SisoRef010API

api = SisoRef010API.bundled(37)
result = api.describe("1.3.153.6.4.2.0")
print(result.qualified_description)

for hit in api.search("F803", limit=10).hits:
    print(hit.entity, hit.description)

catalog = ReferenceCatalog.bundled()
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
from siso_ref010 import EntityTypeXmlParser, ReferenceCatalog

standard = EntityTypeXmlParser.from_file("SISO-REF-010.xml")
print(standard.title, standard.date)

entity_kinds = standard.enumeration("Entity Kind")
for row in entity_kinds.entries:
    print(row.value, row.description, row.source.get("uuid"))

catalog = ReferenceCatalog(standard)
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
siso-ref010 describe 1.3.153.6.4.2.0 --qualified
siso-ref010 search 'F803 Tromp'
siso-ref010 list categories 1 4 153
siso-ref010 key 1.2.225.7.8.7.1
siso-ref010 key --decode 72621510476957441
siso-ref010 info
```

Use `--json` for versioned machine output. To use a different standard file,
put `--xml PATH` before the command, for example:

```sh
siso-ref010 --xml ./SISO-REF-010.xml info --json
siso-ref010 --xml ./SISO-REF-010.xml search 'Tromp'
```

The package bundles historical editions v20 through v37. Select one by release
number with `--standard-version 35`; v37 remains the default. See
`siso-ref010 versions` for available editions and the default.

See the [command-line reference](docs/cli.md).

## Try the consumer example

The [consumer integration example](docs/consumer-integration.md) shows how an
application can inspect an Entity Type code with a selected edition. Run
`python -m examples.entity_type_consumer` from this checkout.

## Develop

The edition XML files are tracked verbatim in Git. Source and editable installs
generate the ignored XZ runtime bundle automatically; the index is checked in
so CI can detect source or pack drift. Set up a virtual environment, activate
it, then install the development tools and run the full local gate. From the
repository root, create the environment:

```sh
python -m venv .venv
```

Activate it in your shell:

```sh
source .venv/bin/activate
```

In Windows PowerShell, use:

```powershell
.\.venv\Scripts\Activate.ps1
```

Then run:

```sh
python -m pip install -e '.[dev]'
python -m tools.ci
```

The full local gate verifies all 18 editions and applicable XSDs, runs every
test including the exhaustive edition checks, checks Markdown and repository
links, runs Ruff and Pyright, and builds and verifies both wheel and
source-distribution installs. XSD validation needs `xmllint` from libxml2. See
[MVP release readiness](docs/release-readiness.md) for prerequisites and the
hosted CI edge profile, [code layout](docs/architecture.md), and
[CHANGELOG.md](CHANGELOG.md) for the current rework.

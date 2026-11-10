# siso-ref010

An independent, offline Python toolkit for SISO-REF-010 and DIS Entity Types.
Choose a standard edition, look up or query its entity codes, inspect its
enumerations, and compare changes across editions.

This repository is in pre-release hardening. The Python package code is MIT
licensed; bundled SISO XML keeps its own source terms. See the
[provenance registry](src/siso_ref010/data/standards/PROVENANCE.json),
[source notice](SISO-DATA-NOTICE.txt), and [release readiness](docs/release-readiness.md).

## Quick start

Install from a checkout. Python 3.11 or newer is required. The default is the
newest bundled edition; pass `--standard-version` when your application needs a
specific source snapshot:

```sh
python -m pip install .
python -m siso_ref010 versions
python -m siso_ref010 describe 1.3.153.6.4.2.0
```

The same lookup through the supported Python API:

```python
from siso_ref010 import SisoRef010API

api = SisoRef010API()
entity = api.describe("1.3.153.6.4.2.0")
print(entity.description)
```

To discover editions without loading their XML, run
`python -m siso_ref010 versions` or use `SisoRef010API.bundled_editions()` for
the indexed title, date, source hash, and byte length. Selecting an edition parses it when you request
`SisoRef010API.bundled(version)`. Pin the edition when an application needs a
reproducible source snapshot or has agreed on a specific standard edition.

## Common tasks

| Question | Python | CLI |
| --- | --- | --- |
| What does this complete entity code mean? | `api.describe(code)` | `describe CODE` |
| How does a shorter prefix resolve? | `api.resolve_entity(prefix)` | `inspect entity PREFIX` |
| Which records match these fields? | `api.query_entities(country=153, text="Tromp")` | `query --country 153 --text Tromp` |
| What changed between editions? | `api.compare_editions(35, 37)` | `compare 35 37` |

Pin the edition in scripts and automated runs. The default is the newest
bundled edition. CLI output is human-readable by default; add `--json` for the
versioned machine-readable contract. See the [Python API](docs/api.md) and
[CLI guide](docs/cli.md).

## Inspect source XML

The package bundles original XML for editions v20–v37 in a compressed archive.
It can also parse an XML file supplied by the caller. This example reads a
bundled edition and builds the optional lookup catalog:

```python
from siso_ref010.catalog import ReferenceCatalog
from siso_ref010.parsing import EntityTypeXmlParser
from siso_ref010.sources import BUNDLED_STANDARD_SOURCE

standard = EntityTypeXmlParser.from_bytes(BUNDLED_STANDARD_SOURCE.read_xml(37))
entity_kinds = standard.enumeration("Entity Kind")
catalog = ReferenceCatalog(standard)
print(entity_kinds.entries[0].description)
print(catalog.search_description("F803"))
```

The [parser guide](docs/parser.md) describes the retained source model. Use
`python -m siso_ref010 dump 37 --output edition-v37.xml` to export the original
XML bytes.

## Development

Create and activate a virtual environment, then install the development
dependencies and run the local gate:

```sh
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
python -m tools.ci
```

The full local gate checks all bundled editions and applicable XSDs, runs the
test suite and static checks, and verifies wheel and source-distribution
installs offline. XSD validation requires `xmllint` from libxml2. See the
[release checklist](docs/release-readiness.md),
[source provenance](docs/provenance.md),
[consumer example](docs/consumer-integration.md),
[architecture](docs/architecture.md), and [changelog](CHANGELOG.md).

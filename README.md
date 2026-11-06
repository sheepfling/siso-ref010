# dis-entity-types (proposed distribution name)

A typed, zero-runtime-dependency Python 3.11+ implementation of the **library, XML parser,
and picker workflows** in
[TNO-MST/siso-entity-type](https://github.com/TNO-MST/siso-entity-type/tree/bb195c647b6f9c4b7bea4e5a10e6c560a0b0bceb),
pinned to commit `bb195c647b6f9c4b7bea4e5a10e6c560a0b0bceb` (upstream packages 1.0.3).
This independent port has its own version, 0.2.0. It has not been published to PyPI.
It is not affiliated with or endorsed by SISO or TNO.

**Private review candidate, not cleared for public distribution.** The proposed
PyPI name is `dis-entity-types`; `siso_entity_type` remains the import namespace
for compatibility with the earlier local bundle. Both `dis-entity-types` and
`siso-entity-type` invoke the CLI. See [the release plan](docs/publishing.md) for
name checks, licensing gates, and the proposed Trusted Publishing setup.
Do not install a same-named package from a public index as if it were this project.

The bundled data is the original **SISO-REF-010-v35, dated 2025-04-27**, not a claim
about the newest SISO standard. It includes 279 countries, 10 kinds, 68 kind/domain
pairs, 1,867 categories, and 24,637 subcategory/specific/extra records.

The application code executes directly in Python, not through a JavaScript wrapper
or transpiled runtime. A native **Tkinter desktop picker** now implements ID entry,
cascading/filtered selections, description search, result selection, clipboard copy,
and reset alongside the terminal picker. Tk is an optional system/Python component.
See [GUI usage](docs/gui.md), [scope](docs/compatibility.md), and
[code/data provenance](docs/code-provenance.md).

## Install locally

```sh
python -m pip install .
# Or build and install the local wheel:
python -m build
python -m pip install dist/dis_entity_types-0.2.0-py3-none-any.whl
```

No network access is used at runtime. Python 3.11+ is the supported language target;
the test suite passed on Linux Python 3.11.17, 3.12.14, 3.13.5, and 3.14.8.
The initial PR CI also passed on Windows and macOS. See the PR for the latest
commit-specific results, including the added GUI checks.

## Python API, CLI, and desktop picker

- **Python API:** `from siso_entity_type.api import EntityTypeAPI` provides typed,
  immutable results for describe/search/hierarchy queries. No printing or exits.
  Full contracts and examples: [API reference](docs/api.md).
- **CLI:** `siso-entity-type` or `python -m siso_entity_type` calls the same API.
  Use `--text` for human output or `--json` for versioned machine output.
  Commands, schemas and exit codes: [CLI reference](docs/cli.md).
- **Desktop picker:** `dis-entity-types gui` or `dis-entity-types-gui` launches a
  native Tk window. It uses the same Python API, with no browser, JavaScript,
  Node, web server, or network connection. [GUI reference](docs/gui.md).

```python
from siso_entity_type.api import EntityTypeAPI

api = EntityTypeAPI()
result = api.describe("1.3.153.6.4.2.0")
print(result.qualified_description)
for hit in api.search("F803", limit=10).hits:
    print(hit.entity, hit.description)
```

## Lower-level Python API

```python
from siso_entity_type import EntityKind, SisoEnum, SisoEnums

catalog = SisoEnums.bundled()
entity = SisoEnum.from_string("1.3.153.6.4.2.0")
assert entity.get_kind() is EntityKind.PLATFORM
assert catalog.get_country_name(entity) == "Netherlands (NLD)"
assert catalog.search_description("F803") == {"1.3.153.6.4.2.0": "F803 Tromp"}

print(catalog.get_description_of(entity, fully_qualified=True))
# Guided Missile Frigate (FFG) / De Zeven Provincien Class / F803 Tromp

key = entity.to_key()  # Exact Python int; signed like long.js
unsigned = entity.to_key(signed=False)
wire = entity.to_bytes()  # Eight bytes, big-endian, >BBHBBBB
assert SisoEnum.from_key(key) == entity
assert SisoEnum.from_bytes(wire) == entity

categories = catalog.get_all_categories_of(1, 4, 153)
subcategories = catalog.get_all_subcategories_of(1, 4, 153, 5)
```

Entity fields are immutable and validate the DIS widths: country is 16-bit and
all other fields are 8-bit. Unknown but in-range codes can be represented. Entity
kind/domain convenience enums do not constrain the raw fields. The domain enum is
for platform domains; munition and supply codes are interpreted by the catalog.

`SisoEnums(data)` loads a four-map upstream-format dictionary; `SisoEnums.from_json(path)`
loads an alternative snapshot. `SisoEnums()` starts empty until `initialize(data)`.
Initializing is synchronous and replaces the dataset. Snake-case names are the
primary Python API. Camel-case aliases for the lookup/model/factory API ease
migration; see the compatibility document for exceptions.

## Command line

```sh
siso-entity-type describe 1.3.153.6.4.2.0 --qualified
siso-entity-type search 'F803 Tromp'
siso-entity-type list domains 1
siso-entity-type list categories 1 4 153
siso-entity-type list subcategories 1 4 153 5
siso-entity-type key 1.2.225.7.8.7.1
siso-entity-type key --decode 72621510476957441
siso-entity-type pick
dis-entity-types gui
siso-entity-type info
```

`python -m siso_entity_type` is equivalent. Parent fields for `list` are, in order,
kind, domain, country, category, subcategory, specific; supply only the parents
needed for that collection. `search` displays at most 20 hits by default; use
`--limit 0` for all. Global `--data PATH` must precede the subcommand.
The terminal picker follows country → kind → domain → category → subcategory →
specific → extra and accepts 0 for unspecified values. Ctrl-C/Ctrl-D cancels.

## Parse another SISO XML file

```python
from siso_entity_type import SisoEnumsFactory, SisoEnums

parsed = SisoEnumsFactory.create_from_file("SISO-REF-010.xml")
catalog = SisoEnums(parsed.to_data())
parsed.write_output_files("output")  # output/siso-enums.json
```

```sh
siso-entity-type parse SISO-REF-010.xml --output output
siso-entity-type --data output/siso-enums.json search 'Tromp'
```

The parser extracts the same entity-type subset as upstream, including its chosen
country/domain/life-form UID tables and CET hierarchy. It is not a full SISO schema
validator, and it does not extract every unrelated SISO enumeration or bitfield.
DTD/entity declarations are rejected. UTF-8 XML and namespaces are supported.
The parser also exposes typed incremental specific/extra insertion and a native
JSON-interchange converter/validator. See [parser reference](docs/parser.md).
Deprecated rows are retained, matching upstream. Optional `qualified=True` or
CLI `parse --qualified` stores joined descriptions instead of the default leaf names.

## Verify and develop

```sh
python -m pip install -e '.[dev]' pytest-cov
python -m pytest -q
pyright
ruff check .
ruff format --check .
python -m build
python tools/check_installed.py dist/dis_entity_types-0.2.0-py3-none-any.whl
```

`pyright` runs in strict mode over all runtime modules; the package includes
`py.typed`. Tests cover the full pinned XML/JSON parity, original upstream examples,
executed TypeScript reference outputs, random full-width wire roundtrips, malformed
input, generic-country precedence, initialization/cache replacement, parser safety,
and CLI/picker flows. See [verification](docs/verification.md) for measured scope.

To regenerate the TypeScript reference fixture, use the bundled source snapshot:

```sh
cd tools/oracle
npm ci --ignore-scripts
node regenerate.mjs
```

Node and the exact locked development dependencies are needed only for regenerating
that fixture. Running the Python test suite does not require Node or network access.

## Licensing and provenance

A different license for newly authored code is under consideration; this review
has not changed the current licensing. Native Python syntax does not by itself
prove copyright independence from referenced source. Required attribution and
separate SISO notices remain intact. See [the provenance inventory](docs/code-provenance.md).

The distribution metadata declares `Apache-2.0 AND LicenseRef-SISO-Data`: Apache
for the software, with the separate SISO notice for the included material. The
custom identifier refers to `SISO-DATA-NOTICE.txt`; it is not an OSI license or
clearance for unrestricted commercial reuse.

The code derives from TNO's **Apache-2.0** software. The original license, TNO
copyright, pinned source attribution, and modified-work notice are retained.

**Reprinted with permission from SISO Inc.**

The SISO data/source material is separately copyright © 2025 SISO Inc. Its embedded
notice gives broad attributed reuse for *Schema and API*, but limits *Documentation*
reuse to noncommercial purposes absent written permission. These are distinct from
the code license. No blanket commercial-use clearance for documentation is claimed.
Read [SISO-DATA-NOTICE.txt](SISO-DATA-NOTICE.txt), [NOTICE](NOTICE), and
[provenance](docs/provenance.md) before redistributing or using the material commercially.

See [CHANGELOG.md](CHANGELOG.md) for the additive CLI/API update.

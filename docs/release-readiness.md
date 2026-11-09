# MVP release readiness

This page summarizes implementation checks and source terms a publisher must
review. Passing code and packaging checks does not review the terms in the
included SISO source editions.

## Implemented and locally verifiable

- The repository tracks the original XML source files. Source and editable
  builds create the ignored solid XZ payload from those files; a source archive
  carries the compressed payload, not the individual edition XML files.
- The build validates the compressed payload recorded in an sdist when the raw
  source XML is not present. CI installs from both the wheel and the sdist in a
  fresh offline environment.
- `EntityType` and `create_key()` reject values outside each DIS field width.
  The wire-byte test includes a separately published DIS entity type example
  (M1A2) and checks the exact network-byte representation.
- Enumeration tables and values can be found by exact human-readable table
  name through both the Python API and `inspect resolve`. Duplicate names and
  duplicate table identifiers are returned as ambiguous rather than guessed.
- Each retrieved bundled XML is checked against the per-edition SHA-256 in the
  index. The index also fingerprints the compressed archive.

## Run the full local gate

From the repository root, install the development environment and run the full gate:

```sh
python -m pip install -e '.[dev]'
python -m tools.ci
```

Activate the development environment before running these commands so `python`, `rumdl`, and the
pre-commit hook use the installed development dependencies. The full gate checks all 18 bundled
editions and all applicable XSDs, runs the complete test suite with the coverage threshold, checks
Markdown and repository links, runs Ruff and Pyright, and validates wheel and source-distribution
installs offline. XSD validation requires `xmllint` from libxml2; isolated package checks download
their temporary wheelhouse when it is not already available through pip's cache.

Hosted CI uses narrower profiles at the supported Python endpoints, 3.11 and 3.14. The `edge`
profile checks SISO v20 and v37, runs tests outside the all-edition sweep, and builds both
distributions; `quality` checks Markdown, static quality, and endpoint XSDs. The full local gate
also tests every edition and validates wheel and source-distribution installs offline. Use
`python -m tools.ci --help` to see the CI profiles. To install the read-only Markdown check as a
local commit hook, run `python -m pre_commit install` once.

The network-backed upstream byte recheck is separate:

```sh
python -m tools.check_standards_provenance
```

It verifies the registered SHA-256 and Git blob SHA-1 against each available
source, and uses a recorded mirror if the primary URL is unavailable. A byte
match does not authenticate the publisher or grant redistribution rights.

`python -m tools.benchmark_snapshot_loading` measures cold retrieval and API
construction for selected editions. It uses fresh subprocesses and prints
machine-local timings. The XZ stream is solid, so seeking to an older edition
may decompress preceding stream content first.

## Gates before a public release

### Review source terms before publishing

Each edition's XML contains its source copyright and terms. Review the exact
text for the editions and artifacts being distributed, and preserve the
associated source notices. The repository notice points to that text; it does
not summarize or replace it. The Python code license is separate from the
terms embedded in the SISO source files.

### XSD validation — all editions covered by source-matched schemas

The offline validation tool checks v20–v29 against version-matched maintainer
schemas and v30–v37 against the packaged v2.7 XSD. The historical schemas are
validation inputs under `tools/standards-xsds`; they are not added to the
runtime wheel. The tool verifies their registry hashes and namespaces before
validating each XML. This establishes source-to-schema consistency and
well-formed schema validation, not publisher authentication or redistribution
permission.

### Independent protocol coverage — narrow but useful

The [OpenDIS M1A2 example](https://github.com/open-dis/dis-tutorial/blob/master/EntityStatePDUs.md)
independently supplies the known entity code, and the [OpenDIS Python
serializer](https://github.com/open-dis/open-dis-python/blob/master/opendis/dis7.py)
shows the DIS field order and widths. Together they ground one golden vector;
they are not broad certification against a DIS implementation. Add independent
vectors for additional field boundaries and representative codes before making
wider interoperability claims.

### API compatibility commitment — establish at 0.1.0

Python results are frozen Pydantic models. CLI JSON has an outer envelope
version, and edition-diff projections carry their own schema version. Treat
those documented contracts as the compatibility surface; increment the relevant
schema version for incompatible serialized changes. The first public release
should state the supported Python API and CLI compatibility policy explicitly.

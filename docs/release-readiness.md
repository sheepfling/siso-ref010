# MVP release readiness

This page separates implemented safeguards from release gates that still need
external evidence. Passing the code and packaging checks does not settle the
redistribution terms for SISO source material.

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

Run the local checks from the repository environment with module commands:

```sh
python -m tools.build_standards_pack
python -m tools.check_bundled_standards
python -m tools.check_standards_xsd
python -m pytest -q
python -m ruff check .
python -m ruff format --check .
python -m pyright
python -m build
```

The network-backed upstream byte recheck is separate:

```sh
python -m tools.check_standards_provenance
```

It verifies the registered SHA-256 and Git blob SHA-1 against each available
source, and uses a recorded mirror if the primary URL is unavailable. A byte
match does not authenticate the publisher or grant redistribution rights.

`python -m tools.benchmark_snapshot_loading` measures cold retrieval and full
API construction for v37, v30, and v20. It uses fresh subprocesses for each
sample and reports timings for the current machine; they are observations, not
performance guarantees. The [current measured run](contributing/snapshot-loading.md)
records the method and environment. The XZ stream is solid: seeking to an older edition is
logical random access, and may decompress the preceding stream content first.

## Gates before a public release

### SISO data redistribution terms — unresolved

The repository preserves the attribution carried by the recovered source and
records source provenance. Neither action establishes permission to redistribute
the XML or XSD in a public wheel or source archive. Confirm the terms for every
edition and artifact with the relevant rights holder and record the result
before publishing a distribution containing the data. Keep code and data terms
distinct; do not interpret the source attribution as a license grant.

The Python library code is under Apache-2.0, with the license text included in
the repository and distributions. That code license does not cover the
separately sourced SISO XML or XSD.

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

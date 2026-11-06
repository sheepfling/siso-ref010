# Code and data provenance inventory

The application is implemented in native Python. There is no JavaScript engine,
Node subprocess, transpiled application code, or foreign-runtime bridge in
`src/siso_entity_type`. This describes the implementation language, not a claim
that the project was developed without consulting upstream source.

## Authored Python application code

- `model.py`, `catalog.py`, `parser.py`, and `utils.py` reimplement upstream
  library/parser behavior using Python integers, dataclasses, dictionaries,
  ElementTree, and explicit validation. The upstream source was consulted.
  Existing adaptation notices remain; this is not represented as clean-room work.
- `api.py` and `cli.py` provide newly authored typed application contracts and
  command-line behavior over that implementation.
- `picker.py` and `gui.py` provide a newly authored Python state model and native
  Tk view for the original picker's functional workflow. No Vue or browser code
  is executed. Tk is a standard-library interface to the platform's Tcl/Tk GUI
  toolkit, not an embedded JavaScript UI.
- `xml_types.py` is a handwritten Python JSON shape validator/converter and typed
  record layer, informed by the upstream public interchange structures. It does
  not execute or transpile the generated TypeScript converter. Its normalization
  choices and differences are documented in [parser.md](parser.md).

These descriptions identify implementation provenance. They do not certify that
all source-informed code is copyright-independent or remove applicable notices.

## Reference material and data

- `vendor/upstream` currently preserves byte-copied TypeScript/source references.
  `tools/oracle` is the historical Node-based reference-output generator. Neither
  is imported or run by the application. The original source remains Apache-2.0;
  retained copies must keep its license and attribution. Removal from the current
  review tree has not yet been approved.
- `tests/fixtures/upstream-oracle.json` records captured outputs of the pinned
  upstream implementation. Tests consume it as frozen data, not executable code.
  It must not be regenerated from the Python implementation and then presented
  as an independent reference.
- The SISO XML and descriptive JSON are reference data, not newly authored source.
  `python tools/rebuild_catalog.py --check` runs the Python parser and produces
  byte-identical catalog JSON from the XML. Regeneration changes neither the
  source authorship of those descriptions nor their applicable terms.

## License decision

The current software license and notices have not been changed. A different
license for eligible newly authored code is under consideration, but none has
been selected or applied. Before a change, identify any retained copied or
adapted material, preserve its obligations, and decide what can legitimately
receive the chosen license. The current metadata separately identifies the
SISO material. The data notice's Schema/API and Documentation terms remain
relevant regardless of the Python source license.

This inventory is an engineering provenance record, not legal clearance.

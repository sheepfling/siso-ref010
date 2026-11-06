# Review preparation (unreleased)

- Propose `dis-entity-types` as the distribution name; retain `siso_entity_type` imports.
- Add an equivalent `dis-entity-types` CLI command and package metadata.
- Distinguish Apache software and separately licensed SISO data in metadata.
- Add CI and a gated Trusted Publishing plan; no publishing workflow is enabled.

# Changelog

## 0.2.0

- Explicit `siso_entity_type.api` application API with `EntityTypeAPI`, immutable
  typed results, JSON-safe `to_dict()` views and encoding helpers.
- CLI describe/search/list/key/info/pick now delegate to the shared API.
- Consistent opt-in `--text` and versioned `--json` modes, including structured
  noninteractive errors and JSON-safe 64-bit string keys.
- Validated hierarchy queries reject booleans and out-of-range parent fields.
- `--data PATH info` now reports actual custom catalog counts and does not claim the
  bundled v35 provenance for an arbitrary JSON file.
- Dedicated API and CLI references, executable API example, parity tests and
  reproducible offline installed-wheel consumer checks.
- Original 0.1.0 core library/parser interfaces and default CLI rendering retained.

## 0.1.0

Initial Python library/parser port, terminal picker, pinned v35 data, upstream
reference fixture, tests, source distribution and wheel. The original delivery
remains available separately.

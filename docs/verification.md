# Verification record

The initial port was validated on Linux with Python 3.11.17, 3.12.14, 3.13.5,
and 3.14.8; the original TypeScript oracle was executed with Node 24.22.1.
The initial GitHub CI also passed on Windows and macOS at commit
`f346de4f167e9cbb51ca9919414ca0ea37902d77` (run `42169259894`). This is measured pinned-revision parity, not an assertion of
complete behavior equivalence on every future or malformed input.

## Native Python completion checks

The added desktop picker, incremental parser APIs, and JSON shape converter were
checked locally on Python 3.12.14: **217 tests passed, 3 real-Tk tests skipped**
because this host has no graphical display. Ruff lint/format and strict Pyright
passed. The Python-only catalog rebuild matched the bundled JSON byte for byte
(SHA-256 `e215511c87c6cb5dbe8bb0f909ae225f84c34a707d17176a00ef34e32c453e6b`).
The wheel and source distribution built successfully.

CI now runs coverage under `xvfb-run` with `SISO_REQUIRE_GUI_TESTS=1`, so missing Tk
or a display fails instead of silently skipping the real widget tests. These
exercise repeated/invalid ID loads, cascading selections, result selection,
clipboard copy, stale-query cancellation, reset, and repeated close. This is
automated widget testing, not a claim of manual visual QA on all platforms.
The [draft PR](https://github.com/sheepfling/dis-entity-types/pull/1) is the source
for exact-commit CI results.

Runtime tests reject non-stdlib runtime imports and subprocess/foreign-runtime
bridges. The installed-wheel smoke test restricts PATH to its fresh Python virtual
environment, verifies lazy Tk import, and exercises the added typed parser records.
Python can regenerate the production catalog without Node. The optional historical
oracle generator and the Pyright development checker still use Node; neither is
an application runtime dependency.

## Initial review preparation checks

The renamed `dis-entity-types` candidate was rechecked on Python 3.12.14:
140 tests, Ruff lint/format, strict Pyright, wheel/sdist build, strict Twine
metadata validation, and fresh-wheel consumer checks for both CLI names.
The full 140-test suite also passed locally on Python 3.11.17, 3.13.5, and
3.14.8, and all 140 tests passed from the rebuilt source distribution on 3.12.14.
The proposed GitHub matrix covers Python 3.11–3.14 on Linux and 3.12 on
Windows/macOS. All seven initial CI jobs succeeded for the initial revision noted above.
Byte-preserved fixture attributes protect upstream hashes from checkout
line-ending conversion. No package-index upload was performed.

## Initial port results

- **140 pytest tests passed**, including all tests below.
- **Strict Pyright:** 0 errors, 0 warnings, covering runtime modules and the API example.
- **Installed-package type completeness:** 100% (477 exported symbols with known
  types, 0 ambiguous, 0 unknown), using `pyright --verifytypes` in the activated
  environment containing the installed wheel.
- **Ruff:** lint and formatting checks passed.
- **Statement coverage:** 99% as reported by pytest-cov (957 of 960 statements).
  The application API reached 100% statement coverage. The two-line `__main__.py`
  launcher and the compatibility CLI picker wrapper were outside that coverage
  run; the installed launcher is tested separately. This is not branch coverage
  or a proof of correctness.
- Source distribution and platform-independent wheel built successfully. The wheel
  was installed without dependencies into a fresh virtual environment and checked
  from outside the source tree: imports, bundled data, wire roundtrip, module CLI
  and console entry point all passed. Wheel contents include `py.typed` and all
  three license/notice files; the large XML fixture and vendor source are excluded.
- `tools/check_installed.py` reproducibly creates a fresh virtual environment,
  installs only the wheel offline, clears source-path overrides, and exercises
  imports, typed resources, API calls, console/module commands, JSON equality and
  malformed-input exit/stderr behavior from outside the source tree.
- New API/CLI regression tests cover immutable typed results, query validation,
  all hierarchy levels, custom-data provenance, exact integer-to-string encoding,
  JSON/text parity, structured errors, output-mode overrides, option terminators,
  picker output separation and cancellation. Independent review findings about
  error formatting and fallback documentation were corrected and tested.
- Full XML extraction equals every key/value and insertion order in upstream JSON:
  **24,637** subcategory/specific/extra rows, **1,867** category rows,
  **279** country rows, **68** domain rows; **10** kinds are parsed separately.
- Pinned JSON and XML bytes match their upstream Git blob hashes.
- Actual pinned TypeScript modules were transpiled and executed using locked
  TypeScript 5.9.2, long.js 5.3.2, debug 4.4.1 and fast-xml-parser 5.2.5.
- Python matches all **26,472 unique upstream category/subcategory keys** for
  key decoding, entity text, re-encoding and short descriptions.
- Python matches **546 detailed and unknown-country fallback cases**, including
  fully qualified text and country/kind/domain names; **364 hierarchy collection
  cases**, all 11 tested kind-domain lookups, complete composite domain mapping,
  and four search queries match the executed TypeScript fixture.
- The TypeScript parser also regenerates the original JSON in exact map order.
- **10,000 seeded random 64-bit keys** round-trip through Python integers, entity
  text and eight-byte network-order representations. Boundary/signed cases tested.
- Original upstream fixtures include F803 Tromp, MC-12W/MC-12S, Netherlands
  submarine classes, life-form categories, ballistic descriptions, and unknown
  specificity fallback.
- Adversarial tests cover malformed/coercible input, 64-bit bounds, booleans,
  empty search, missing data maps, noncanonical keys, reinitialization and stale
  caches, returned-map isolation, reversed generic/country collision order,
  singleton and namespaced XML, missing descriptions, DTD/entity rejection,
  wildcard applicability, deprecated retention, custom data files, CLI failures,
  terminal picker invalid choices, and cancellation.

## Reproduce

```sh
xvfb-run -a python -m pytest -q --cov=siso_entity_type --cov-report=term-missing
python tools/rebuild_catalog.py --check
pyright
ruff check .
ruff format --check .
python -m build
python tools/check_installed.py dist/dis_entity_types-0.2.0-py3-none-any.whl
# With the wheel and Pyright installed in an activated virtual environment:
pyright --verifytypes siso_entity_type --ignoreexternal
```

The oracle file records outputs of actual upstream code rather than a Python
reimplementation used as its own reference. `tools/oracle/regenerate.mjs` recompiles
the bundled original TypeScript snapshot and repeats that measurement. Only import
resolution is adapted; algorithmic source is unchanged. The source tree hashes
are retained in `vendor/upstream/git-tree.json`.

Known intentional differences and native GUI scope are listed in
[compatibility.md](compatibility.md). In particular, typed validation deliberately
does not reproduce JavaScript's malformed-number coercion.

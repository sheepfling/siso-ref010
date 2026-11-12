# Cold-start performance

## Scope and decision

This study covers the initial streaming and request-sharing change at commit
`b61218e`. Later field-tracking compaction and tag sharing are measured separately
in [exact lookups and steady-state memory](lookup-performance.md). Keep those
matched comparisons separate from the initial measurements below.

The parser now projects completed enumeration tables and entity branches while
reading XML, releasing their temporary XML subtrees immediately. Identical
immutable change-request annotations are shared only within that parse. The
public Pydantic models, eager catalog construction, query API, source ordering,
validation and exact-source retrieval remain unchanged.

This avoids retaining the complete ElementTree alongside every source model.
It also avoids constructing thousands of duplicate change-request models:
v37 contains 28,835 request occurrences but 3,662 distinct numeric ranges.
Repeated occurrences remain present in their original order.

No persistent derived cache was added. The existing snapshot pack, index,
source XML and source/pack SHA-256 checks are unchanged. No pickle, JSON cache,
or other deserialization shortcut bypasses validation. Any future persistent
representation must include its schema version and exact source SHA-256,
reject stale/incomplete data, and retain the original XML bytes separately.

## Reproduce the measurements

Use the same Python/Pydantic versions and machine for each checkout. Build the
verified snapshot pack first if it is absent:

```sh
python -m tools.siso_ref010.build_standards_pack
python -m tools.siso_ref010.benchmark_cold_start \
  --versions 20 29 37 --iterations 3 \
  --strategies tree tree-shared stream --output cold-start.json
```

Every sample runs in a fresh interpreter. Untraced wall timings and traced
allocation measurements use separate processes, so tracing overhead is never
reported as normal latency. Retained allocations are measured after explicit
garbage collection. Each stage's peak includes earlier live allocations;
values are cumulative, not additive. RSS is the operating system's process
high-water mark, not retained Python memory, and is unavailable on Windows.

The baseline is commit `024ca4d`. The same benchmark module was copied into a
detached local baseline worktree and run with `--strategies stream` there and
in the modified checkout. In baseline output that strategy label means the
installed public parser, which was still tree-based. Baseline and candidate
both use the actual `EntityTypeXmlParser.from_bytes` implementation, not a
reconstruction. Both runs use three samples per edition per measurement mode.

The pipeline tool separates decompression/verification, XML/source models,
catalog projection, first description lookup, and structured-query warmup.
The streaming path interleaves XML parsing and model projection, so its combined
time is intentionally not split artificially. The tree alternatives additionally
separate XML parsing and source-model projection for diagnosis.

The `process_elapsed_ms` field includes diagnostic collections, result hashing,
full-model serialization and process teardown. It is **not** API startup
latency. Five interleaved before/after runs of the existing
`benchmark_snapshot_loading --child api --version VERSION` operation measure
actual API construction including imports but excluding interpreter startup,
without those diagnostic operations in the measured interval.

## Results

Measured on 2026-11-11, macOS 26.6.2 arm64, CPython 3.13.18 and Pydantic 2.14.3.
These are local medians, not cross-platform performance guarantees.

Actual API construction, five interleaved fresh-process samples, milliseconds:

| Edition | Before | After | Reduction |
| --- | ---: | ---: | ---: |
| v20 | 785.49 | 752.56 | 4.2% |
| v29 | 954.54 | 930.44 | 2.5% |
| v37 | 627.24 | 553.33 | 11.8% |

Construction allocation peak and retained allocations after catalog projection,
three traced samples, MiB. These include imports and the cached source bytes:

| Edition | Peak before | Peak after | Retained before | Retained after |
| --- | ---: | ---: | ---: | ---: |
| v20 | 81.66 | 79.51 | 79.60 | 77.45 |
| v29 | 141.66 | 110.46 | 117.35 | 108.00 |
| v37 | 171.94 | 130.17 | 115.82 | 103.17 |

For v37 this is a 24.3% reduction in construction allocation peak and 10.9% in
retained allocations. Older v20's range expansion and decompressor memory remain
dominant, so its overall peak improves only 2.6%.

The v37 pipeline breakdown below uses separate untraced samples and forced
collections between stages. Do not add it up to reconstruct the API timing above:

| Stage | Before ms | After ms |
| --- | ---: | ---: |
| Decompress and verify XML | 47.83 | 46.37 |
| Parse XML and construct source models | 392.69 | 329.54 |
| Project catalog | 72.10 | 80.00 |
| First description lookup | 0.17 | 0.17 |
| Query warmup | 136.77 | 141.82 |

The first lookup has not inherited deferred parser work. Query warmup still
retains substantial memory: v37 totals 205.82 MiB before versus 193.17 MiB after;
its stage allocation peak is 215.80 versus 203.15 MiB. Warmup latency is not an
improvement claimed by this patch. The measured v37 catalog-projection timing
also rose, while overall API construction fell.

Untraced process peak RSS at catalog construction fell from 226.16 to 164.80 MiB
for v37. RSS is allocator/OS-sensitive: after v29 warmup it rose from 301.03 to
328.64 MiB even though retained traced allocations fell. Do not interpret the
Python allocation savings as a universal RSS guarantee.

Raw samples, ranges and source/model fingerprints:

- [Actual API construction](benchmarks/cold-start-api.json).
- [Unmodified baseline pipeline](benchmarks/cold-start-before.json).
- [Modified pipeline](benchmarks/cold-start-after.json).
- [Diagnostic alternatives](benchmarks/cold-start.json).

## Alternatives and tradeoffs

- **Full tree, unshared requests:** reference decomposition of the previous
  strategy. It retains the XML tree and every repeated request model at once.
  This diagnostic projection omits declaration scanning and some source hashing;
  use the actual baseline run for before/after claims.
- **Full tree, shared requests:** lowers retained model memory and avoids repeated
  annotation validation. This is the fastest diagnostic projection, but it still
  retains the entire XML tree during model construction.
- **Streaming, shared requests (selected):** reduces both temporary tree memory
  and duplicate retained models. Event handling adds some overhead relative to
  the sharing-only alternative, in return for lower construction peak memory.
  It does not defer the cost to the first lookup or change `catalog.standard`.
- **Lazy models or a compiled cache:** not selected. They would require broader
  API/lifetime changes or a new validated, versioned persistent format. The
  selected implementation improves the current path without those risks.

Historical editions still spend substantial time expanding ranges into catalog
indexes. Query warmup also remains a significant allocation cost. Neither
compression layout nor query-index representation changed in this patch.

## Correctness and verification

The golden model digests in `tests/fixtures/standard-model-digests.json` were
captured from the unmodified baseline for all 18 bundled editions. Tests compare
the complete serialized source model and exact original XML SHA-256, including
attributes, metadata, ranges, duplicates, cross-references and ordering. This
is stronger than checking counts or a few successful lookups alone.

Additional regressions cover preferred/fallback entity-table selection,
unselected invalid tables, metadata after streamed branches, namespaces,
non-ASCII text, encoding declarations, repeated immutable requests, parse-local
sharing and stream boundaries. Projection errors are deferred so malformed XML
and wrong-root errors retain precedence, and ignored tables cannot introduce
recursion errors that the original parser did not raise.

An independent differential review compared more than 1,000 generated cases
against the original parser, including error text/context. Its one deep-nesting
finding was fixed and covered by regressions. No outstanding concrete
correctness finding remained.

Final local verification:

- 433 tests passed on Python 3.14.10, with 98.55% runtime statement coverage.
- All 18 bundled-edition lookup/choice checks and all 18 XSD validations passed.
- Ruff, formatting, production/test Pyright, pre-commit, repository hygiene,
  Markdown checks and unchanged snapshot-index checks passed.
- Offline wheel and sdist builds, the wheel build from the sdist, strict Twine
  checks and required package-content checks passed using installed Python 3.13
  build dependencies. No dependency download was attempted for these checks.
- Installed consumer/API and CLI smoke checks passed in a new application
  environment using preinstalled system dependencies. This was not a fresh
  dependency installation.
- The normal aggregate gate reached packaging but its isolated build dependency
  download was blocked by network policy at PyPI. It was not retried. A completely
  fresh dependency installation therefore remains unverified.

These measurements do not constitute a release approval or verify a published
package version.

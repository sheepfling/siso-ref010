# Cold-start performance

## Parser strategy and compatibility

The parser projects completed enumeration tables and entity branches while
reading XML, releasing their temporary XML subtrees immediately. This avoids
retaining the complete ElementTree alongside every source model. Catalog
construction remains eager; work is not deferred to the first lookup.

A parse-local cache validates each distinct change-request range once and copies
that validated template for every occurrence. Only immutable scalar values are
reused. Although source models are frozen, Pydantic exposes mutable field-tracking
sets, so separate source occurrences must not share model instances or those sets.
Repeated occurrences and their original ordering are preserved.

Entry tags share immutable strings within a parse. Shallow public copies of
`ReferenceEntry` models compact validated field-tracking sets on supported
CPython/Pydantic versions without sharing the sets themselves. This is an
implementation-dependent memory tradeoff, not a universal saving or a validation
shortcut. Enumeration tables and entity branches do not need that extra copy;
the optimization is limited to the numerous entry models where it is material.

No persistent derived cache was added. The existing snapshot pack, index,
source XML and source/pack SHA-256 checks are unchanged. Any future persistent
representation must include its schema version and exact source SHA-256,
reject stale or incomplete data, and retain the original XML bytes separately.

## Reproduce the measurements

Use identical Python/Pydantic versions and machine conditions for both checkouts.
Build the verified snapshot pack first if it is absent. Keep generated results
in the ignored local output directory, not in source control:

```sh
mkdir -p .local/benchmarks
python -m tools.siso_ref010.build_standards_pack
python -m tools.siso_ref010.benchmark_cold_start \
  --iterations 3 --strategies tree tree-cached stream \
  --output .local/benchmarks/cold-start.json
```

Edition defaults come from the bundled index: oldest, middle, and newest.
`--versions` selects a targeted set. The diagnostic alternatives are a complete
XML tree with uncached request validation (`tree`), a complete tree with cached
validation and independent request models (`tree-cached`), and the production
streaming parser (`stream`). They help identify costs; they are not substitutes
for running the actual baseline and candidate implementations.

For a before/after comparison, run the same harness against both checkouts and
record interpreter, dependency, source and parser identity. Keep raw samples as
pull-request or local run artifacts. Summarize measured changes and tradeoffs in
the relevant pull request rather than accumulating machine-specific reports here.

Every sample runs in a fresh interpreter. Normal latency comes from untraced
processes; allocation measurements run separately with tracing. Retained
allocations are measured after explicit garbage collection. Each stage's peak
includes earlier live allocations: values are cumulative, not additive. This
pipeline tool reports process lifetime peak RSS, not current resident memory.

The pipeline separates decompression/verification, XML/source models, catalog
projection, first description lookup, and structured-query warmup. Streaming
interleaves parsing and projection, so those costs are not split artificially.
`process_elapsed_ms` also includes diagnostic collections, result hashing,
full-model serialization and teardown; it is not API startup latency.

Use [exact lookup and steady-state measurements](lookup-performance.md) to track
first and repeated public lookups, current RSS and retained Python allocations,
with and without query-index warmup. Report loading costs as well as memory gains;
keep single-query usage separate from the larger warmed working set.

## Correctness checks

`tests/fixtures/standard-model-digests.json` is a regression oracle for the parsed
model, not another source-integrity registry. It stores SHA-256 hashes of complete
`EntityTypeStandard.model_dump_json()` output recorded from the original parser
at the commit named in the fixture. These detect changes to attributes, metadata,
ranges, duplicates, cross-references and ordering even when a few lookups agree.
Do not regenerate them from a candidate merely to make a failing test pass.

Raw XML hashes have one authority: the bundled source index. Snapshot loading
verifies those hashes; the parser regression also checks that the returned source
hash describes the exact input bytes. The model fixture does not duplicate them.

Focused tests cover preferred/fallback entity-table selection, ignored invalid
records, metadata after streamed branches, namespaces, non-ASCII text, encoding
declarations, independent change-request bookkeeping, stream boundaries and
validation-error precedence. Run the full local gate described in the
[development instructions](../README.md#development) before proposing changes.

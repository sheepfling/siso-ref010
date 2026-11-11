# Exact lookup and steady-state memory benchmark

Run from the repository root with the same Python executable for every comparison:

```sh
PYTHONPATH="$PWD/src:$PWD" python3.13 tools/siso_ref010/benchmark_steady_state.py \
  --warmup --output lookup-memory.json
```

Defaults select the oldest, middle, and newest editions from the selected
checkout's bundled index (currently 20, 29, and 37), with three fresh-process
samples per measurement mode and edition, and 10,000 repeated calls per sample. `--versions`, `--iterations`,
`--lookups`, and `--code` override these. The default seven-field exact entity code,
`1.2.225.7.8.7.1`, is present in all three representative editions.

Use the **same benchmark script** against another local checkout:

```sh
PYTHONPATH="$PWD/src:$PWD" python3.13 tools/siso_ref010/benchmark_steady_state.py \
  --checkout /path/to/baseline --warmup --output baseline-lookup-memory.json
```

The script starts a new interpreter for each sample and sets that child's
`PYTHONPATH` to the selected checkout's `src` and root directories. No network,
installation, or checkout mutation is required. Keep the machine otherwise idle
and run comparisons sequentially, using identical interpreter and arguments.

## What the results mean

- `load` includes the public bundled-source load and catalog construction, after
  runtime imports. `first_lookup` is the first `api.describe(code).description`
  call against that loaded API. It excludes load time and has no preceding query.
- `repeated_lookup` invokes the public `api.describe(code)` string-input API in a
  tight loop, discarding results. `amortized_lookup_us` divides one batch duration
  by the call count. It includes string parsing and result construction, not just
  internal dictionary access. It is not a per-request percentile or mixed-code
  workload. A single first-call duration is inherently noisier than batch timing.
- `--warmup` additionally builds structured-query indexes with `api.warmup()` and
  repeats the same exact-code lookup batch afterward. Without this flag, no
  structured-query warmup is performed.
- `elapsed_ms` and `amortized_lookup_us` come **only from untraced processes**.
  Traced samples explicitly set both fields to null.
- `process_current_rss_mib` is current process resident memory after each stage.
  macOS uses `mach_task_basic_info`; Linux uses `/proc/self/statm`. Unsupported
  systems or unavailable measurements return null, never substitute peak RSS.
- `process_peak_rss_mib` is the process lifetime resident high-water mark. It
  cannot show memory released after loading. Both RSS values include the Python
  interpreter, dependencies, native allocations and allocator-retained pages.
- `traced_retained_mib` is currently live Python-traced allocation size after
  collection. Tracing begins before runtime imports. `traced_stage_peak_mib` is
  the absolute traced high-water allocation size since resetting the peak before
  that stage, including allocations retained from earlier stages. It is **not**
  incremental allocation volume or process RSS.

Garbage collection runs before and after each stage, outside timed regions.
The API stays alive throughout the sample; repeated lookup results are discarded.
The first description string remains available for validation. Measurements
include a small amount of benchmark bookkeeping. Tracing itself increases RSS,
so summaries use only **untraced RSS**, while allocation summaries use traced
processes. Raw traced RSS remains explicitly identified by `traced: true`.

## Reproducibility and interpretation

The versioned JSON schema contains configuration, raw samples, and per-edition,
per-stage median/min/max/sample-count summaries. Each sample records Python,
Pydantic, platform, exact Git revision, dirty status, and loaded runtime module
paths and SHA-256 hashes. The report also hashes the benchmark script itself.
Dirty status includes untracked files; hashes identify the actual loaded code
when the revision alone is insufficient. Do not edit a checkout during a run.

Compare load time, first-call time, repeated-call time, and current RSS separately.
A lower load peak is not evidence of a smaller retained working set. This tool
records trends, not pass/fail thresholds: shared-machine noise and dependency
changes must be checked before treating small differences as regressions.

## Ongoing performance checks

For every loading or memory change, compare the previous revision with the
candidate using the same harness, interpreter, dependency versions, source data,
and installed-distribution metadata. Run sequentially on an otherwise idle host.
Record load time, the first exact lookup, repeated exact lookup batches, current
RSS and retained Python allocations before and after structured-query warmup.
Keep raw samples and report regressions and tradeoffs alongside improvements.
Use the index-derived oldest/middle/newest representative set, and add targeted editions
when a change warrants them. Do not impose hard cross-platform thresholds or
claim universal speedups from local measurements.

## Recorded compact-model comparison

These are same-harness medians from three fresh-process samples per edition and
mode, Python 3.13.18 / Pydantic 2.14.3 on macOS ARM64. Baseline is commit
`b61218e`; candidate is that revision with compact independent model field sets
and parse-local tag sharing. Candidate was dirty; the exact parser SHA-256 and
other runtime module hashes are in each raw sample. Only the parser hash differs
between their loaded package modules.

Raw samples, ranges, and provenance:

- [Baseline report](benchmarks/steady-state-b61218e.json)
- [Candidate report](benchmarks/steady-state-compact-models.json)

Both reports retain the identical hash of the exact measured benchmark. A later
CLI-only change derives equivalent edition defaults from the target index rather
than hard-coding them; measurement functions and these recorded results are
unchanged, and the recorded hashes were not relabeled. Each sample records exact source
XML hashes and sizes, collected after the measured stages. Pack and decompressed
edition hashes were also independently verified afterward; source bytes match.
Identical ignored `src/siso_ref010.egg-info` was present in both checkouts so the
package-version import follows the same path. Import retained allocations match
within about 1 KiB. Checked-in reports normalize personal checkout prefixes to
`<baseline>` or `<candidate>`, retaining source-relative paths and all hashes.
Their `artifact_notes` describe this normalization and post-run pack verification.
All values below are absolute totals from this harness, not older cold-start
reports. Arrows indicate baseline to candidate.

### Lookup-only state

| Edition | Load ms | First lookup ms | Repeated lookup µs | Current RSS MiB | Retained Python MiB |
| --- | --- | --- | --- | --- | --- |
| 20 | 615.9 → 633.7 | 0.143 → 0.143 | 29.24 → 29.78 | 186.69 → 180.17 | 79.44 → 73.48 |
| 29 | 733.3 → 764.3 | 0.148 → 0.148 | 28.44 → 28.92 | 218.20 → 207.75 | 109.99 → 100.37 |
| 37 | 417.4 → 442.2 | 0.157 → 0.151 | 28.29 → 28.46 | 167.75 → 155.56 | 105.15 → 93.68 |

RSS and retained values above are after the repeated lookup batch, before any
structured-query warmup. The raw report also gives memory after load and the
first lookup.

### Structured-query warmed state

| Edition | Repeated lookup µs | Current RSS MiB | Retained Python MiB |
| --- | --- | --- | --- |
| 20 | 28.47 → 29.13 | 266.83 → 260.22 | 154.49 → 148.53 |
| 29 | 28.27 → 28.61 | 331.66 → 321.27 | 214.67 → 205.05 |
| 37 | 27.39 → 27.54 | 267.38 → 255.27 | 195.15 → 183.68 |

Lookup-only repeated latency medians rise about 1.8%, 1.7%, and 0.6% for v20,
v29, and v37; these small changes need more samples before a strong conclusion.
Load medians rise about 2.9%, 4.2%, and 5.9% respectively. Lookup-only retained
Python allocations fall about 5.96, 9.62, and 11.47 MiB; current RSS falls about
6.52, 10.45, and 12.19 MiB. This is a retained-memory improvement with a modest
loading-time cost, not a speedup claim. Warming query indexes adds substantial
memory in both versions, so this cost stays separate from exact-lookup-only
usage. Three local samples establish a useful baseline, not a universal guarantee.

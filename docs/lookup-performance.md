# Exact lookup and steady-state memory benchmark

Run from the repository root with the same Python executable for every comparison:

```sh
mkdir -p .local/benchmarks
PYTHONPATH="$PWD/src:$PWD" python3.13 tools/siso_ref010/benchmark_steady_state.py \
  --warmup --output .local/benchmarks/candidate-lookup-memory.json
```

Defaults select the oldest, middle, and newest editions from the selected
checkout's bundled index (currently 20, 29, and 37), with three fresh-process
samples per measurement mode and edition, and 10,000 repeated calls per sample. `--versions`, `--iterations`,
`--lookups`, and `--code` override these. The default seven-field exact entity code,
`1.2.225.7.8.7.1`, is present in all three representative editions.

Use the **same benchmark script** against another local checkout:

```sh
PYTHONPATH="$PWD/src:$PWD" python3.13 tools/siso_ref010/benchmark_steady_state.py \
  --checkout /path/to/baseline --warmup --output .local/benchmarks/baseline-lookup-memory.json
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
Keep raw samples in the ignored `.local/benchmarks/` directory, not in source
control. Attach run artifacts and summarize regressions and tradeoffs in the
relevant pull request; repository documentation describes the method rather than
accumulating machine-specific results.
Use the index-derived oldest/middle/newest representative set, and add targeted editions
when a change warrants them. Do not impose hard cross-platform thresholds or
claim universal speedups from local measurements.

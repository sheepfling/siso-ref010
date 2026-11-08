# Entity query performance notes

These notes record the November 2026 investigation into structured entity
queries. The main target was the Python API: a fast first query and fast
repeated queries over a mostly static edition. Timings below are observations
from local runs, not guarantees or a controlled comparison across machines.

## What we found

Edition v37 contained 27,390 source entity records in the local benchmark.
Before the change, a first `query_entities(country=153, text="Tromp")` call
without warmup took roughly 230 ms after API construction. The scan first
materialized an `EditionValue` for every entity record, even though only two
records matched.

The current cold query traverses source records and constructs result models
only for the requested page. A later local run measured about 24–25 ms for the
same query after construction. The mapping backend also retains its most
recent request and page, scoped to the same standard object; an identical
repeat measured about 0.022 ms. The cache holds one request, so changing
filters or pagination replaces it.

For varied repeated queries, `api.warmup()` explicitly builds in-memory field
indexes. A local run measured indexed queries around 0.18–0.35 ms. Warmup
itself takes time and materializes the full entity record set. Actual cost
varies with the source and machine.

A persistent SQLite backend was prototyped and removed. In one local run its
initial cache build took about 490 ms, the first query with cache verification
25 ms, and a later query 11 ms. It added persistent files, schema and source
identity checks, and rebuild handling. It also left API construction's XML
parsing and catalog projection in place. That tradeoff did not justify keeping
it for the current API workload. The query backend protocol remains available
for another implementation if a measured workload calls for one.

## What remains

Fresh-process API construction still reads and parses the source and builds
its catalog projection. Observed construction times varied substantially
between runs. The two most recently used bundled catalog projections are cached
within the process, so later API instances can reuse them. Query warmup and the
last-query cache do not eliminate the first construction cost.

If startup across many short-lived processes becomes important, evaluate a
persistent representation that covers source loading and projection as well
as queries. Tie any derived data to the exact source digest and representation
version, define how invalid or incomplete data is rebuilt, and measure the
full path from process start to result. Integrity checks alone do not establish
that a deliberately modified cache is authentic.

Run `python -m tools.benchmark_entity_queries --iterations 100` from the
repository environment to compare local construction, a first query, warmup,
and indexed queries with a scan. Record the edition, machine, Python version,
query filters, process/cache state, and whether construction is included when
comparing future changes. Check result parity for ranges, generic country rows,
cross-references, text, ordering, and pagination alongside performance.

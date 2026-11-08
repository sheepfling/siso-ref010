# Command line

Install the package, then use `siso-ref010` or the equivalent
`python -m siso_ref010` entry point.

```sh
siso-ref010 --help
siso-ref010 describe 1.3.153.6.4.2.0 --qualified
siso-ref010 search 'F803 Tromp'
siso-ref010 query --country 153 --text Tromp --limit 20
siso-ref010 --standard-version 35 --warmup query --entity-kind 1 --country 153 --offset 20 --limit 20 --json
siso-ref010 list categories 1 4 153
siso-ref010 key 1.2.225.7.8.7.1
siso-ref010 key --decode 72621510476957441
siso-ref010 info
siso-ref010 history --entity 1.3.153.6.4.2.0 --versions 35 36 37
siso-ref010 history --enum-uid 7 --value 1
siso-ref010 compare 35 37
siso-ref010 compare 35 37 --material-only
siso-ref010 compare 35 37 --scope enumerations --enum-uid 7 --detail concise --json
siso-ref010 compare 35 37 --detail audit --json
siso-ref010 compare 35 37 --detail review-queue --priority high --limit 25 --json
siso-ref010 compare 35 37 --detail review-queue --priority low --category raw_metadata --json
siso-ref010 compare 35 37 --detail review-queue --wire-encoding potentially_breaking --json
siso-ref010 compare 35 37 --detail review-queue --application-migration recommended --json
siso-ref010 --standard-version 37 inspect summary
siso-ref010 --standard-version 37 inspect report --json
siso-ref010 --standard-version 37 inspect diagnostics
siso-ref010 --standard-version 37 inspect diagnostics --details --limit 100
siso-ref010 inspect tables --query country --json
siso-ref010 inspect values --kind enumeration --table-uid 7 --limit 25
siso-ref010 inspect value 3 93 --json
siso-ref010 inspect resolve 'DIS-PDU Type' 1 --json
siso-ref010 inspect search 'reserved values' --limit 25 --offset 0
siso-ref010 inspect uuid a-source-uuid --json
siso-ref010 inspect entity 1.3.153.6.4.2.0
```

Human-readable output is the default. Add `--json` for a versioned JSON result
or `--text` to force text output. These flags work before or after the
subcommand; a subcommand flag overrides the global flag. Help and version output
are always text.

The bundled XML is used by default. Supply another SISO-REF-010 XML file with
global `--xml PATH` before the command:

```sh
siso-ref010 --xml ./SISO-REF-010.xml info --json
siso-ref010 --xml ./SISO-REF-010.xml describe 1.3.153.6.4.2.0
siso-ref010 --standard-version 35 info --json
siso-ref010 versions
```

`--standard-version` selects a bundled SISO-REF-010 edition by release number.
The bundled default is v37. Use `--xml` for an edition that is not bundled;
these two source options cannot be combined.
Run `siso-ref010 versions` to list the bundled editions and default.

## Exporting original XML

`dump` writes the original XML bytes from the compressed pack. Send one edition
to stdout for redirection, write one file with `--output`, or extract every
bundled version into a directory:

```sh
siso-ref010 dump 35 > SISO-REF-010-v35.xml
siso-ref010 dump 35 --output ./SISO-REF-010-v35.xml
siso-ref010 dump --all --output-dir ./siso-ref-010
```

The command refuses to overwrite existing files. `dump` emits raw XML, so it
does not support JSON output mode.

JSON is an output format. The CLI does not import or export a flattened JSON
catalog. `info` reports the source title and date parsed from the XML.

Search returns at most 20 results by default. Use `--limit 0` for all matches.
`search QUERY` is a case-insensitive text search over entity descriptions.
`query` filters source entity records by any combination of DIS code fields and
optional text. `--entity-kind`, `--domain`, `--country`, `--category`,
`--subcategory`, `--specific`, and `--extra` are independent equality filters;
they do not require preceding hierarchy fields. A filter value that falls inside
a source range matches its range row. Country-zero rows are included when a
nonzero country is selected because the standard uses those rows generically.
Use `--text` to match description, hierarchy-label, or code text, and `--limit`
plus `--offset` for pagination. `--standard-version` or `--xml` selects the
single edition being queried.
Add global `--warmup` before the command to build the selected edition's entity
query index in the same process before running the command. This keeps the
prepared cache available to that command; a separate warmup process would exit
and discard its in-memory cache. Without `--warmup`, `query` uses a direct scan
instead of building an index during the request. For machine output, warmup status is omitted
from stdout so the command still emits one JSON result.

`inspect search QUERY` searches source descriptions and metadata. The
`inspect entity CODE` command resolves one full code or contiguous prefix and
explains its source path.

`list COLLECTION PARENTS...` filters by the leading fields of the entity
hierarchy, in order: kind, domain, country, category, subcategory, specific.
For example, `list categories 1 4 153` returns categories for that exact
kind/domain/country prefix. In `inspect values`, `--kind` selects the source
record type (`entity_type` or `enumeration`); it does not filter on the DIS
entity kind code.

`history` reports whether an entity code or enumeration value is present and
its description in each selected release. Enumeration table history omits
`--value`; add it to track one table member. Versions default to every bundled
edition.

`inspect` examines one selected edition. Choose it with global `--standard-version`
or `--xml` before the command. `inspect summary` counts tables, value/path
records, ranges, UUID identities, hierarchy references, and hierarchy levels.
`inspect report` gives a concise edition overview with the source XML hash,
selected edition number, installed package version, validation scopes, grouped
diagnostics, and structured edition-backed examples without Python snippets.
The report JSON includes `report_schema_version`; the outer CLI result envelope
has a separate `schema_version`. It shows which semantic checks ran and whether repeated identities
come from hierarchy expansion, duplicate source identifiers, or conflicting
source rows. It labels XSD validation as `not_run` and publisher provenance as
`unverified`; bundled checksum verification does not authenticate the publisher.
XML well-formedness is `passed` only when successful parsing was recorded; it
is independent of whether a source hash is available. The offline
`tools.check_standards_xsd` command is a separate validation run and does not
change the runtime report's XSD status.
The default is readable terminal output. Add `--format markdown` or
`--format json` to select a report renderer. Add `--audit` to include the full
enumeration-table inventory and individual diagnostic findings; the audit is
not a record-by-record dump of all values and entity paths.
`inspect diagnostics` groups unresolved references, duplicate identifiers,
overlapping values, and missing row metadata by severity, diagnostic code, and
source table. Add `--details` to list individual findings; use `--code`,
`--table-uid`, and `--severity` to filter groups and detailed rows. Missing
descriptions are informational because some may be intentionally unspecified.
`inspect tables` lists table declarations, declared width in bits, applicability,
and annotations; `--query` filters names and applicability.
`inspect values` lists source rows and accepts `--kind`, `--table-uid`, `--status`,
`--deprecated`, and `--not-deprecated` filters. `inspect value UID CODE` resolves
an exact value or reports the range containing it. `inspect search QUERY` searches
descriptions and source metadata in deterministic order; use `--offset` and
`--limit` for pages. Hits include the matched fields. `inspect uuid UUID` returns
all matching records. `inspect entity CODE` accepts a dotted full code or shorter
prefix and shows a human-readable outcome such as `Resolved prefix`, matched
hierarchy, trailing fields not supplied, explicitly unspecified fields, and
unknown supplied components. Value and search result
limits default to 100; `--limit 0` returns all. JSON results include the edition
identity and total/returned/truncated counts where applicable.
`inspect resolve NAME VALUE` resolves against an exact enumeration table name,
ignoring case and outer whitespace. It reports all candidates when names or
table identities are ambiguous rather than selecting one implicitly. Use
`inspect value UID VALUE` when the UID is already known.

`compare FROM TO` prints a human-readable summary by default. The summary
highlights newly deprecated records, table-size changes, release-status
cleanups, and inherited path-label changes. Use `--detail concise` for useful
identifiers and changed field values, or `--detail audit --json` for complete
before/after snapshots. JSON defaults to the audit view; `--detail summary`
selects the aggregate summary. `--material-only` hides changes assessed as
non-material across all dimensions. Detailed output is capped at 100 records by
default; use `--limit 0` for all results. Review-queue pages accept
`--offset`, `--priority`, `--wire-encoding` (with `--compatibility` as an alias),
`--identifier-resolution`, `--semantic-meaning`, `--application-migration`,
`--action`, and `--category`; `--limit 0` returns the remaining filtered queue.
Unique UUIDs identify recodes and moves. Code fallback must be unique in both
editions; duplicate codes are reported as ambiguous additions/removals.
Comparison schema version 5 includes an `assessment` object, reason and
recommendation codes, causal references, source hashes, and `generator_version`,
the installed package version. The schema version is independent from the
package version. Projection contracts are documented in [the diff schema
reference](siso-diff-schema.md).

The default review queue orders wire-encoding risks first, then high-priority
changes, identifier-resolution risks, other unassessed changes, and
medium-priority changes. Low-priority and no-priority changes remain available
through explicit filters. Assessments separate encoded representation,
identifier resolution, source meaning, and application migration;
`not_assessed` is not treated as `unchanged`. Each queue record includes
reason codes and recommendations that explain its review priority. For
enumeration `size` changes, the XSD defines the field as a width in bits; the
report flags potential wire impact and recommends checking the consumer
protocol field before asserting a packet-layout change.

From the repository root, package adjacent and direct comparison reports in a
clean, deterministic ZIP with a README, schema reference, and test-evidence
manifest:

```sh
python -m tools.build_diff_reports
python -m tools.package_diff_reports --output .local/siso_diff_v4.zip
```

List parent order and JSON result fields are documented in the
[Python API reference](api.md).

## Errors and exit status

| Result | Status | Output |
| --- | ---: | --- |
| Success | 0 | Result on stdout |
| Invalid arguments, data, or files | 2 | Error on stderr |
| Interrupted | 130 | Interruption on stderr |

In JSON mode, errors use a versioned JSON envelope on stderr. Package errors
also include a stable `code` and structured `context` alongside the readable
message.

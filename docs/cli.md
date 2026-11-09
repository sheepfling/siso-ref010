# Command line

Use `siso-ref010` or `python -m siso_ref010`. Start with help, list the editions,
then look up a code:

```sh
siso-ref010 --help
siso-ref010 versions
siso-ref010 describe 1.3.153.6.4.2.0
```

For scripts and agents, add `--json` to get a versioned result envelope. Pin
the edition for reproducible lookups:

```sh
python -m siso_ref010 --standard-version 37 describe 1.3.153.6.4.2.0 --json
```

Successful output has `schema_version`, `command`, and `result`. Errors go to
stderr with an `error` object containing a message and, when available, a
stable error code and context.

## Choose an edition

The bundled default is the newest edition. Select another bundled edition with
`--standard-version`; load a separate XML file with `--xml`:

```sh
siso-ref010 --standard-version 35 info
siso-ref010 --xml ./SISO-REF-010.xml describe 1.3.153.6.4.2.0
siso-ref010 dump 35 --output ./SISO-REF-010-v35.xml
siso-ref010 dump --all --output-dir ./siso-ref-010
```

`dump` writes the original XML bytes and refuses to overwrite existing files.
`--xml` and `--standard-version` cannot be combined.

## Query values

`query` filters source entity records by any combination of DIS fields and
optional text. Field filters are independent; they do not require parent
fields. Results support `--limit` and `--offset`.

```sh
siso-ref010 query --country 153 --text Tromp --limit 20
siso-ref010 list categories 1 4 153
siso-ref010 inspect resolve 'DIS-PDU Type' 1
siso-ref010 inspect value 3 93
siso-ref010 inspect search reserved --limit 25
```

Use `inspect summary`, `inspect tables`, `inspect values`, `inspect uuid`, and
`inspect entity` to explore a selected edition. `inspect report` gives a
readable overview; add `--audit` to include the full table inventory and
individual diagnostic findings. Use `--format json` or `--format markdown` to
choose a report format.

`search` searches entity descriptions. `inspect search` searches source
descriptions and metadata. `inspect resolve NAME VALUE` resolves an
enumeration by its exact table name and reports ambiguity rather than guessing.

## Histories and differences

Track an entity or enumeration value across releases, or compare two editions:

```sh
siso-ref010 history --entity 1.3.153.6.4.2.0
siso-ref010 history --enum-uid 7 --value 1 --versions 35 36 37
siso-ref010 compare 35 37
siso-ref010 compare 35 37 --detail concise --json
siso-ref010 compare 35 37 --detail audit --json
siso-ref010 compare 35 37 --detail review-queue --priority high --json
```

The default comparison output is a summary. Concise output shows field changes;
audit output includes before-and-after source records. Review queues support
filters for priority, assessment, scope, action, and category. See the [diff
reference](siso-diff-schema.md) for the report contract.

## Output and errors

Human-readable text is the default. Add `--json` for a versioned JSON envelope.
JSON is an output format; the CLI does not load a flattened JSON catalog.

| Exit code | Meaning |
| ---: | --- |
| `0` | Success |
| `2` | Invalid arguments, data, or files |
| `130` | Interrupted |

Errors go to stderr. JSON errors include a stable error code and structured
context.

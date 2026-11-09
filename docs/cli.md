# Command line

Run `siso-ref010` or `python -m siso_ref010`. Start with help:

```sh
python -m siso_ref010 --help
python -m siso_ref010 versions
python -m siso_ref010 --standard-version 37 describe 1.3.153.6.4.2.0
```

Use `--standard-version VERSION` to choose a bundled edition, or `--xml PATH`
to read a separate XML file. `--warmup` builds entity-query indexes before a
query. The default edition is the newest one in the bundle.

## Commands

| Command | Purpose |
| --- | --- |
| `describe CODE` | Describe a full or partial DIS entity code. |
| `query [filters]` | Filter by any combination of entity fields and text. |
| `search TEXT` | Search entity descriptions. |
| `list COLLECTION [PARENTS...]` | List choices below an entity prefix. |
| `inspect ...` | Inspect source tables, values, ranges, UUIDs, or diagnostics. |
| `history ...` | Follow an entity or enumeration value across editions. |
| `compare FROM TO` | Summarize or inspect differences between editions. |
| `key VALUE` | Encode or decode a DIS entity key. |
| `dump VERSION` | Write the original XML bytes for an edition. |

Use `inspect report --format markdown` for a readable edition report, and add
`--audit` to include source rows and individual findings. Comparison output
defaults to a summary; select `--detail concise`, `audit`, or `review-queue` for
more detail. The review queue supports filters such as `--priority high`,
`--scope enumeration_table`, and `--category relationship`.

## Output

Human-readable text is the default. Add `--json` for a machine-readable result
with `schema_version`, `command`, and `result` fields. Errors go to stderr; JSON
errors use the same versioned envelope and include a stable error code when
available. The JSON output is generated from the Python Pydantic result models.
Description search labels duplicate entity codes as ambiguous and displays all
source-description candidates.

The executable CLI writes text and JSON to stdout/stderr as UTF-8 on all
supported Python versions. Redirected output can therefore be decoded as UTF-8
even on Python versions before 3.15, whose default text encoding may depend on
the system locale.

```sh
python -m siso_ref010 --standard-version 37 describe 1.3.153.6.4.2.0 --json
python -m siso_ref010 compare 35 37 --detail review-queue --priority high --json
```

See `python -m siso_ref010 COMMAND --help` for command-specific options.

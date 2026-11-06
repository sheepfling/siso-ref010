# Command-line interface

Install the wheel or source package, then use either equivalent entry point:

```sh
siso-entity-type --help
python -m siso_entity_type --help
```

Every subcommand has `--help`. The top-level help points to the Python API.
Global `--data PATH` must appear before the subcommand. It applies to describe,
search, list, pick and info. Key conversion needs no catalog; parse uses its XML
input and ignores `--data`.

## Commands

```sh
siso-entity-type describe 1.3.153.6.4.2.0 --qualified --text
siso-entity-type search 'F803 Tromp' --text
siso-entity-type list categories 1 4 153 --text
siso-entity-type key 1.2.225.7.8.7.1 --text
siso-entity-type key --decode 72621510476957441 --json
siso-entity-type parse SISO-REF-010.xml --output output --json
siso-entity-type --data output/siso-enums.json info --json
siso-entity-type pick
```

For hierarchy parent order, see the table in `api.md`. Search defaults to 20
results; `--limit 0` returns all. The parser's `--qualified` option stores joined
rather than leaf descriptions. `describe --qualified` changes text/default output;
JSON always includes both short and qualified descriptions.

## Output modes

- `--text`: human-readable lines for every command.
- `--json`: a versioned machine-readable envelope for every successful command.
- No flag: preserves the original 0.1.0 presentation (description/decoded key/path
  as text, search/list/info/encoded key as JSON). For automation, explicitly use
  `--json` rather than relying on this legacy presentation.

`--text` and `--json` can appear before or after the subcommand. A subcommand flag
can override a global flag. `--help` and `--version` always use ordinary text.

Example:

```sh
siso-entity-type key 1.2.225.7.8.7.1 --json
```

```json
{
  "schema_version": 1,
  "command": "key",
  "result": {
    "entity": "1.2.225.7.8.7.1",
    "fields": {
      "kind": 1, "domain": 2, "country": 225, "category": 7,
      "subcategory": 8, "specific": 7, "extra": 1
    },
    "key": "72621510476957441",
    "unsigned_key": "72621510476957441",
    "wire_hex": "010200e107080701"
  }
}
```

`result` is exactly the corresponding API result's `to_dict()` for describe,
search, list and key, or `api.info()` for info. Parse returns output path,
source title/date and extracted counts. Pick returns an entity description.
Search includes total/returned counts, effective limit, truncation and hits.
The schema version protects the envelope contract. Consumers should tolerate
additional result fields and inspect the version before handling an incompatible
future schema. Decimal keys are strings, never approximate JSON numbers.

## stdout, stderr and process status

| Condition | Status | stdout | stderr |
| --- | --- | --- | --- |
| Successful operation | 0 | result | normally empty |
| Unknown valid entity / no search matches | 0 | fallback or `-` / empty matches | empty |
| Invalid arguments, malformed input, file failure | 2 | empty | error |
| Interactive cancellation (Ctrl-C/Ctrl-D) | 130 | no result | cancellation |

In JSON mode errors have this shape on stderr:

```json
{"schema_version": 1, "command": "describe", "error": {"type": "ValueError", "message": "..."}}
```

Argument-parser failures can report `command: null`. In `pick --json`, interactive
choices and prompts go to stderr, leaving stdout as one JSON document on success.
If selection fails or is cancelled, stderr can contain those preceding prompts
as well as the final error record. Noninteractive command errors contain only
one JSON error document. Search truncation notices in text/legacy modes go to
stderr; JSON mode carries the truncation flag in its result instead.

The CLI is a local adapter over the importable API. It is not an HTTP service or
a replacement for the upstream Vue graphical application.


## Native graphical picker

`dis-entity-types gui` launches the Python/Tk desktop picker. Global `--data PATH`
also works for custom catalogs. `dis-entity-types-gui` and
`python -m siso_entity_type.gui` launch the bundled-data picker directly.
The GUI does not produce JSON; use the existing describe/search/list commands
for machine output. Missing Tk or display support returns a readable error
and exit code 2. No GUI import is needed for ordinary API/CLI use.
See [gui.md](gui.md).

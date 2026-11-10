# Development tools

Tools are grouped by the system they serve:

## `tools.siso_ref010`

These maintain or verify this library's edition data, package, public APIs, and
performance. Examples include:

- `build_standards_pack`: generate or check the compressed editions pack.
- `check_bundled_standards`, `check_bundled_edges`, and `check_standards_xsd`:
  validate bundled edition data and API behavior.
- `check_standards_provenance`: compare local editions with recorded upstream
  sources.
- `check_installed` and `installed_consumer_smoke`: verify built distributions.
- `build_diff_reports` and `package_diff_reports`: generate comparison
  artifacts.
- `benchmark_entity_queries` and `benchmark_snapshot_loading`: measure library
  query and loading behavior.
- `standard_metadata`: typed models shared by the metadata tools.

Run a tool from the repository root with `python -m`, for example:

```sh
python -m tools.siso_ref010.check_bundled_standards
python -m tools.siso_ref010.build_standards_pack --check
```

Historical XSD inputs used by the library checks are in
`tools/siso_ref010/standards-xsds/`.

## `tools.repo_hygiene`

These check repository-wide conventions and generated-file hygiene. This
includes `check_repository_hygiene`, its acknowledgement baseline, and the
Markdown/link checker invoked by pre-commit.

```sh
python -m tools.repo_hygiene.check_repository_hygiene
python -m tools.repo_hygiene.check_markdown
```

## Shared orchestration

`tools.ci` coordinates repository checks and package verification. It remains
at the top level because it runs both tool groups along with pytest, Ruff, and
Pyright.

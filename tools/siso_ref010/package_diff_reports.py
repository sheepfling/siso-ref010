"""Package generated SISO edition-diff reports without OS metadata."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from pydantic import TypeAdapter

from siso_ref010.comparison import ConciseEditionDiff, EditionDiff, EditionDiffSummary, ReviewQueuePage

_REPORT_PATTERN = re.compile(
    r"siso-ref-010-v\d+-to-v\d+-(?:diff(?:-(?:concise|summary|review-queue))?\.json|summary\.txt)"
)
EVIDENCE_FILE = "siso-diff-test-evidence.json"
README = """# SISO-REF-010 edition diff reports

This archive contains the selected JSON report projections and text summaries
for the chosen edition pairs. Projections can include audit, concise, summary,
and review-queue views.

The schema is generated from the report models. A test-evidence manifest is
included when one is present in the report directory. Reports carry source and
generator metadata.

From the repository root, generate selected comparisons with for example
`python -m tools.siso_ref010.build_diff_reports --pair 35:36 --pair 36:37 --pair 35:37`,
then package the generated files with
`python -m tools.siso_ref010.package_diff_reports`.
"""


def _write_entry(archive: ZipFile, name: str, content: bytes) -> None:
    info = ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = ZIP_DEFLATED
    info.external_attr = 0o100644 << 16
    archive.writestr(info, content)


def _report_schema() -> bytes:
    """Generate JSON Schema from the Pydantic models that produce each view."""
    adapter = TypeAdapter(EditionDiff | ConciseEditionDiff | EditionDiffSummary | ReviewQueuePage)
    schema = adapter.json_schema(mode="serialization", by_alias=True)
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["title"] = "SISO-REF-010 Edition Diff Reports"
    schema["description"] = "Audit, concise, summary, and pageable review queue reports."
    return (json.dumps(schema, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def package_reports(reports_dir: Path, output: Path) -> tuple[str, ...]:
    """Package generated edition-pair reports, schema, and optional evidence."""
    reports = tuple(
        sorted(
            path for path in reports_dir.iterdir() if path.is_file() and _REPORT_PATTERN.fullmatch(path.name)
        )
    )
    if not reports:
        raise FileNotFoundError(f"No edition-diff reports found in {reports_dir}")
    output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output, "w") as archive:
        _write_entry(archive, "README.md", README.encode("utf-8"))
        _write_entry(archive, "SCHEMA.json", _report_schema())
        evidence = reports_dir / EVIDENCE_FILE
        names = ["README.md", "SCHEMA.json"]
        if evidence.is_file():
            _write_entry(archive, "TEST-EVIDENCE.json", evidence.read_bytes())
            names.append("TEST-EVIDENCE.json")
        for path in reports:
            _write_entry(archive, path.name, path.read_bytes())
            names.append(path.name)
    return tuple(names)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reports-dir", type=Path, default=Path(".local"))
    parser.add_argument("--output", type=Path, default=Path(".local") / "siso_diff.zip")
    args = parser.parse_args()
    package_reports(args.reports_dir, args.output)
    print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

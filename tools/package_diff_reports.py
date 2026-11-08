"""Package generated SISO edition-diff reports without OS metadata."""

from __future__ import annotations

import argparse
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

PACKAGE_REVISION = 4
SCHEMA = Path("docs/siso-diff-schema.md")
EVIDENCE_FILE = "siso-diff-test-evidence.json"
REPORTS = (
    "siso-ref-010-v35-to-v36-diff.json",
    "siso-ref-010-v35-to-v36-diff-concise.json",
    "siso-ref-010-v35-to-v36-diff-summary.json",
    "siso-ref-010-v35-to-v36-diff-review-queue.json",
    "siso-ref-010-v35-to-v36-summary.txt",
    "siso-ref-010-v36-to-v37-diff.json",
    "siso-ref-010-v36-to-v37-diff-concise.json",
    "siso-ref-010-v36-to-v37-diff-summary.json",
    "siso-ref-010-v36-to-v37-diff-review-queue.json",
    "siso-ref-010-v36-to-v37-summary.txt",
    "siso-ref-010-v35-to-v37-diff.json",
    "siso-ref-010-v35-to-v37-diff-concise.json",
    "siso-ref-010-v35-to-v37-diff-summary.json",
    "siso-ref-010-v35-to-v37-diff-review-queue.json",
    "siso-ref-010-v35-to-v37-summary.txt",
)
README = """# SISO-REF-010 edition diff reports

This archive contains audit, concise, summary, and separately pageable review
queue JSON reports plus human-readable summaries for v35 to v36, v36 to v37,
and the direct v35 to v37 comparison.

This is report-bundle package revision 4 (`siso_diff_v4.zip`). Its JSON reports
use report schema version 5. These version numbers are independent. Each JSON
report's `generator_version` records the installed siso-ref010 package
version. `SCHEMA.md` documents the report projections and pagination policy;
`TEST-EVIDENCE.json` records report, implementation, and test hashes plus the
checks performed. Audits are complete and source hashes identify the exact XML
bytes compared. The bundled XSD defines enumeration `size` values in bits; the
reports flag changes to that declared width for protocol-field review.

From the repository root, regenerate reports with
`python -m tools.build_diff_reports`, then package them with
`python -m tools.package_diff_reports`.
"""


def _write_entry(archive: ZipFile, name: str, content: bytes) -> None:
    info = ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = ZIP_DEFLATED
    info.external_attr = 0o100644 << 16
    archive.writestr(info, content)


def package_reports(reports_dir: Path, output: Path) -> None:
    """Write a deterministic ZIP containing only named reports and evidence."""
    missing = [name for name in REPORTS if not (reports_dir / name).is_file()]
    if not (reports_dir / EVIDENCE_FILE).is_file():
        missing.append(EVIDENCE_FILE)
    if missing:
        raise FileNotFoundError(f"Missing report files in {reports_dir}: {', '.join(missing)}")
    output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output, "w") as archive:
        _write_entry(archive, "README.md", README.encode("utf-8"))
        _write_entry(archive, "SCHEMA.md", SCHEMA.read_bytes())
        _write_entry(archive, "TEST-EVIDENCE.json", (reports_dir / EVIDENCE_FILE).read_bytes())
        for name in REPORTS:
            _write_entry(archive, name, (reports_dir / name).read_bytes())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reports-dir", type=Path, default=Path(".local"))
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(".local") / f"siso_diff_v{PACKAGE_REVISION}.zip",
    )
    args = parser.parse_args()
    package_reports(args.reports_dir, args.output)
    print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Generate the v35/v36/v37 JSON and terminal report projections."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from siso_ref010 import SisoRef010API
from siso_ref010.cli import render_diff_summary

PAIRS = ((35, 36), (36, 37), (35, 37))


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def build_reports(output_dir: Path) -> tuple[Path, ...]:
    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for from_version, to_version in PAIRS:
        stem = f"siso-ref-010-v{from_version}-to-v{to_version}"
        diff = SisoRef010API.compare_editions(from_version, to_version, limit=None)
        summary = diff.summary()
        review_limit = max(summary.review_queue_count, 1)
        queue = diff.review_queue(limit=review_limit)
        projections = (
            (f"{stem}-diff.json", diff),
            (f"{stem}-diff-concise.json", diff.concise()),
            (f"{stem}-diff-summary.json", summary),
            (f"{stem}-diff-review-queue.json", queue),
        )
        for filename, projection in projections:
            path = output_dir / filename
            _write_json(path, projection)
            written.append(path)
        summary_path = output_dir / f"{stem}-summary.txt"
        summary_path.write_text(render_diff_summary(diff), encoding="utf-8")
        written.append(summary_path)
    return tuple(written)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path(".local"))
    args = parser.parse_args()
    written = build_reports(args.output_dir)
    print(f"Wrote {len(written)} reports to {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

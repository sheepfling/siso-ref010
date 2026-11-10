"""Generate JSON and terminal report projections for selected edition pairs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from siso_ref010 import SisoRef010API
from siso_ref010.cli import render_diff_summary


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _parse_pair(value: str) -> tuple[int, int]:
    parts = value.split(":")
    if len(parts) != 2:
        raise ValueError("expected FROM:TO")
    try:
        return int(parts[0]), int(parts[1])
    except ValueError as error:
        raise ValueError("edition numbers must be integers") from error


def build_reports(
    output_dir: Path,
    pairs: tuple[tuple[int, int], ...],
) -> tuple[Path, ...]:
    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for from_version, to_version in pairs:
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
    parser.add_argument(
        "--pair",
        action="append",
        required=True,
        metavar="FROM:TO",
        help="edition pair to report; repeat to select several",
    )
    args = parser.parse_args()
    try:
        pairs = tuple(_parse_pair(pair) for pair in args.pair)
    except ValueError as error:
        parser.error(f"--pair must use FROM:TO edition numbers: {error}")
    written = build_reports(args.output_dir, pairs)
    print(f"Wrote {len(written)} reports to {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

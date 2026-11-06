"""Rebuild the pinned catalog using only this repository's Python parser.

Run `python tools/rebuild_catalog.py --check` to compare without writing.
Use `--output PATH` to write the generated JSON to an explicit destination.
This generates a representation of SISO data; it does not create new data rights.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from siso_entity_type.parser import SisoEnumsParser  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xml", type=Path, default=ROOT / "tests/fixtures/siso-ref-010-v35.xml")
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--check", action="store_true", help="Compare the bundled JSON without writing")
    action.add_argument("--output", type=Path, help="Write generated JSON to this path")
    args = parser.parse_args()
    parsed = SisoEnumsParser.from_file(args.xml)
    generated = json.dumps(parsed.to_data(), ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    digest = hashlib.sha256(generated).hexdigest()
    if args.check:
        reference = ROOT / "src/siso_entity_type/data/siso-enums.json"
        if generated != reference.read_bytes():
            print(f"Generated data differs from {reference}", file=sys.stderr)
            return 1
        print(f"Python-generated catalog matches bundled bytes. SHA-256: {digest}")
        return 0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(generated)
    print(f"Wrote {args.output}. SHA-256: {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

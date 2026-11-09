"""Build the compressed edition pack from provenance-verified repository XMLs."""

from __future__ import annotations

import json
import lzma
import xml.etree.ElementTree as ET
from hashlib import sha1, sha256
from pathlib import Path
from typing import TypedDict

DATA = Path("src/siso_ref010/data/standards")
FORMAT = "siso-ref010-snapshot-pack-1"


class PackedEdition(TypedDict):
    version: int
    date: str
    sha256: str
    size: int
    offset: int
    title: str
    source_file: str


def build(preset: int = 9) -> tuple[int, int]:
    manifest = json.loads((DATA / "PROVENANCE.json").read_text(encoding="utf-8"))
    editions: list[PackedEdition] = []
    payloads: list[bytes] = []
    entries = sorted(
        (row for row in manifest["entries"] if row.get("status") == "verified"),
        key=lambda row: int(row["version"]),
        reverse=True,
    )
    for row in entries:
        version = int(row["version"])
        path = DATA / f"v{version}.xml"
        payload = path.read_bytes()
        if sha256(payload).hexdigest() != row["sha256"]:
            raise ValueError(f"v{version}: source XML SHA-256 differs from provenance")
        blob_sha1 = sha1(b"blob " + str(len(payload)).encode() + b"\0" + payload).hexdigest()
        if blob_sha1 != row["git_blob_sha1"]:
            raise ValueError(f"v{version}: source XML Git blob SHA-1 differs from provenance")
        root = ET.fromstring(payload)
        expected_title = str(row["title"])
        edition_date = root.get("date")
        if (
            not isinstance(edition_date, str)
            or root.get("title") != expected_title
            or edition_date != row["edition_date"]
        ):
            raise ValueError(f"v{version}: embedded edition metadata differs from provenance")
        editions.append(
            {
                "version": version,
                "date": edition_date,
                "sha256": row["sha256"],
                "size": len(payload),
                "offset": sum(len(item) for item in payloads),
                "title": expected_title,
                "source_file": f"xml/v{version}.xml",
            }
        )
        payloads.append(payload)

    if not editions:
        raise ValueError("No provenance-verified standards were found")
    pack = lzma.compress(b"".join(payloads), preset=preset)
    index = {
        "format": FORMAT,
        "latest_version": int(editions[0]["version"]),
        "verified_scope": (
            "byte-identical to locally provenance-verified source XML; not publisher-signed authenticity"
        ),
        "raw_size": sum(map(len, payloads)),
        "pack_size": len(pack),
        "pack_sha256": sha256(pack).hexdigest(),
        "editions": editions,
    }
    (DATA / "editions.xz").write_bytes(pack)
    (DATA / "index.json").write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")
    return len(editions), len(pack)


if __name__ == "__main__":
    count, size = build()
    print(f"Packed {count} editions into {size:,} bytes")

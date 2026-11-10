"""Build the compressed edition pack from provenance-verified repository XMLs."""

from __future__ import annotations

import argparse
import json
import lzma
import xml.etree.ElementTree as ET
from hashlib import sha1, sha256
from pathlib import Path

from tools.siso_ref010.standard_metadata import PackedEdition, ProvenanceRegistry, StandardPackIndex

DATA = Path("src/siso_ref010/data/standards")
FORMAT = "siso-ref010-snapshot-pack-1"


def pack_is_current(data_dir: Path = DATA) -> bool:
    """Check source and pack fingerprints without parsing XML or recompressing."""
    try:
        manifest = ProvenanceRegistry.model_validate_json((data_dir / "PROVENANCE.json").read_bytes())
        index = StandardPackIndex.model_validate_json((data_dir / "index.json").read_bytes())
        pack_path = data_dir / "editions.xz"
        pack_digest = sha256()
        pack_size = 0
        with pack_path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                pack_digest.update(block)
                pack_size += len(block)
    except (OSError, ValueError, TypeError):
        return False

    if index.pack_size != pack_size or index.pack_sha256 != pack_digest.hexdigest():
        return False

    source_rows = sorted(manifest.entries, key=lambda row: row.version, reverse=True)
    if len(source_rows) != len(index.editions):
        return False

    offset = 0
    for source, indexed in zip(source_rows, index.editions, strict=True):
        try:
            version = source.version
            payload = (data_dir / f"v{version}.xml").read_bytes()
            digest = sha256(payload).hexdigest()
            blob_digest = sha1(b"blob " + str(len(payload)).encode() + b"\0" + payload).hexdigest()
            expected = {
                "version": version,
                "date": source.edition_date,
                "sha256": source.sha256,
                "size": len(payload),
                "offset": offset,
                "title": source.title,
                "source_file": f"xml/v{version}.xml",
            }
        except (KeyError, OSError, TypeError, ValueError):
            return False
        if (
            digest != source.sha256
            or blob_digest != source.git_blob_sha1
            or indexed != PackedEdition.model_validate(expected)
        ):
            return False
        offset += len(payload)

    return index.raw_size == offset


def build(preset: int = 9) -> tuple[int, int]:
    manifest = ProvenanceRegistry.model_validate_json((DATA / "PROVENANCE.json").read_bytes())
    editions: list[PackedEdition] = []
    payloads: list[bytes] = []
    entries = sorted(
        manifest.entries,
        key=lambda row: row.version,
        reverse=True,
    )
    for row in entries:
        version = row.version
        path = DATA / f"v{version}.xml"
        payload = path.read_bytes()
        if sha256(payload).hexdigest() != row.sha256:
            raise ValueError(f"v{version}: source XML SHA-256 differs from provenance")
        blob_sha1 = sha1(b"blob " + str(len(payload)).encode() + b"\0" + payload).hexdigest()
        if blob_sha1 != row.git_blob_sha1:
            raise ValueError(f"v{version}: source XML Git blob SHA-1 differs from provenance")
        root = ET.fromstring(payload)
        expected_title = row.title
        edition_date = root.get("date")
        if (
            not isinstance(edition_date, str)
            or root.get("title") != expected_title
            or edition_date != row.edition_date
        ):
            raise ValueError(f"v{version}: embedded edition metadata differs from provenance")
        editions.append(
            PackedEdition(
                version=version,
                date=edition_date,
                sha256=row.sha256,
                size=len(payload),
                offset=sum(len(item) for item in payloads),
                title=expected_title,
                source_file=f"xml/v{version}.xml",
            )
        )
        payloads.append(payload)

    if not editions:
        raise ValueError("No provenance-verified standards were found")
    pack = lzma.compress(b"".join(payloads), preset=preset)
    index = StandardPackIndex(
        format=FORMAT,
        latest_version=editions[0].version,
        verified_scope=(
            "byte-identical to locally provenance-verified source XML; not publisher-signed authenticity"
        ),
        raw_size=sum(map(len, payloads)),
        pack_size=len(pack),
        pack_sha256=sha256(pack).hexdigest(),
        editions=editions,
    )
    (DATA / "editions.xz").write_bytes(pack)
    (DATA / "index.json").write_text(
        json.dumps(index.model_dump(mode="json"), indent=2) + "\n", encoding="utf-8"
    )
    return len(editions), len(pack)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="check whether the existing compressed pack matches the verified sources",
    )
    args = parser.parse_args()
    if args.check:
        current = pack_is_current()
        print("Standards pack is current" if current else "Standards pack needs rebuilding")
        return 0 if current else 1
    count, size = build()
    print(f"Packed {count} editions into {size:,} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

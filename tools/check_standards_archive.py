"""Check recovered SISO-REF-010 XML editions against their provenance manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile

from siso_ref010 import EntityTypeCatalog, EntityTypeXmlParser


def check_archive(path: Path) -> int:
    """Validate archive hashes and confirm each XML parses into a catalog."""
    failures = 0
    with ZipFile(path) as archive:
        manifest = json.loads(archive.read("PROVENANCE.json"))
        for entry in manifest["entries"]:
            version = entry["version"]
            if entry["status"] != "verified":
                print(f"SKIP v{version}: {entry['status']}")
                continue

            xml = archive.read(entry["file"])
            digest = hashlib.sha256(xml).hexdigest()
            try:
                if digest != entry["sha256"]:
                    raise ValueError(f"SHA-256 mismatch: {digest}")
                standard = EntityTypeXmlParser.from_string(xml.decode("utf-8-sig"))
                if standard.title != entry["title"]:
                    raise ValueError(f"title mismatch: {standard.title!r}")
                if standard.date != entry["edition_date"]:
                    raise ValueError(f"date mismatch: {standard.date!r}")
                catalog = EntityTypeCatalog(standard)
            except Exception as exc:
                failures += 1
                print(f"FAIL v{version}: {type(exc).__name__}: {exc}")
                continue

            print(
                f"OK v{version} {standard.date}: countries={catalog.country_count} "
                f"kinds={catalog.kind_count} domains={catalog.domain_count} "
                f"categories={catalog.category_count} subcategories={catalog.subcategory_count}"
            )

    print(f"Result: {failures} failure(s)")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path, help="Recovered XML archive containing PROVENANCE.json")
    return int(check_archive(parser.parse_args().archive) != 0)


if __name__ == "__main__":
    raise SystemExit(main())

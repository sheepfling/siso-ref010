"""Validate bundled XML with the matching packaged XSD when available."""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path
from xml.etree import ElementTree

STANDARDS = Path("src/dis_entity_types/data/standards")
SCHEMA = Path("src/dis_entity_types/data/SISO-REF-010.xsd")


def _namespace(path: Path) -> str | None:
    root = ElementTree.parse(path).getroot()
    if root.tag.startswith("{"):
        return root.tag[1:].partition("}")[0]
    return None


def _version(path: Path) -> int:
    match = re.fullmatch(r"v(\d+)\.xml", path.name)
    if match is None:
        raise ValueError(f"Unexpected edition filename: {path.name}")
    return int(match.group(1))


def main() -> int:
    xmllint = shutil.which("xmllint")
    if xmllint is None:
        print("xmllint is required for offline XSD validation", file=sys.stderr)
        return 2
    schema_namespace = ElementTree.parse(SCHEMA).getroot().get("targetNamespace")
    failures = 0
    not_run = 0
    passed = 0
    for xml in sorted(STANDARDS.glob("v*.xml"), key=_version):
        version = _version(xml)
        source_namespace = _namespace(xml)
        if source_namespace != schema_namespace:
            not_run += 1
            print(
                f"NOT RUN v{version}: source namespace {source_namespace!r} does not match "
                f"the packaged XSD namespace {schema_namespace!r}; no matching XSD is bundled"
            )
            continue
        result = subprocess.run(
            [xmllint, "--nonet", "--noout", "--schema", str(SCHEMA), str(xml)],
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode:
            failures += 1
            print(f"FAIL v{version}: {result.stderr.strip() or result.stdout.strip()}")
        else:
            passed += 1
            print(f"PASS v{version}: validated against matching namespace {schema_namespace}")
    print(f"XSD editions: passed={passed}, not_run={not_run}, failures={failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Compare bundled edition bytes with their recorded HTTPS upstream sources.

This verifies byte identity against the registry. It does not verify a publisher
signature or authenticate a hosting account.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from io import BytesIO
from pathlib import Path
from typing import TypedDict, cast
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from zipfile import BadZipFile, ZipFile

REGISTRY = Path("src/siso_ref010/data/standards/PROVENANCE.json")
MAX_DOWNLOAD_BYTES = 50 * 1024 * 1024
ALLOWED_HOSTS = {
    "downloads.sourceforge.net",
    "raw.githubusercontent.com",
    "sourceforge.net",
    "svn.code.sf.net",
    "sisostandards.org",
    "www.sisostandards.org",
}


class SourceLocation(TypedDict):
    provider: str
    repository: str
    path: str
    url: str


class EditionSource(TypedDict):
    version: int
    bytes: int
    sha256: str
    git_blob_sha1: str
    primary_source: SourceLocation
    verified_mirrors: list[SourceLocation]


class SourceRegistry(TypedDict):
    entries: list[EditionSource]


def _read_https(url: str) -> tuple[bytes, str]:
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS:
        raise ValueError(f"Source URL uses an unapproved host or scheme: {url}")
    request = Request(url, headers={"User-Agent": "siso-ref010-provenance-check/1"})
    with urlopen(request, timeout=60) as response:
        final_url = response.geturl()
        final_host = urlsplit(final_url).hostname
        if final_host not in ALLOWED_HOSTS:
            raise ValueError(f"Source redirected to an unapproved host: {final_url}")
        payload = response.read(MAX_DOWNLOAD_BYTES + 1)
    if len(payload) > MAX_DOWNLOAD_BYTES:
        raise ValueError(f"Source download exceeds {MAX_DOWNLOAD_BYTES} bytes: {url}")
    return payload, final_url


def _git_blob_sha1(payload: bytes) -> str:
    header = f"blob {len(payload)}\0".encode("ascii")
    return hashlib.sha1(header + payload).hexdigest()


def _edition_payload(payload: bytes, url: str, expected_sha256: str) -> tuple[bytes, str | None]:
    if not urlsplit(url).path.casefold().endswith(".zip"):
        return payload, None
    matches: list[tuple[str, bytes]] = []
    try:
        with ZipFile(BytesIO(payload)) as archive:
            for name in archive.namelist():
                if name.casefold().endswith(".xml"):
                    candidate = archive.read(name)
                    if hashlib.sha256(candidate).hexdigest() == expected_sha256:
                        matches.append((name, candidate))
    except BadZipFile as error:
        raise ValueError(f"Source did not contain a valid ZIP archive: {url}") from error
    if len(matches) != 1:
        raise ValueError(
            f"Expected one XML payload matching the registry hash; found {len(matches)} in {url}"
        )
    return matches[0][1], matches[0][0]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--versions", type=int, nargs="+", help="editions to verify; defaults to all")
    parser.add_argument("--registry", type=Path, default=REGISTRY)
    args = parser.parse_args()
    registry = cast(SourceRegistry, json.loads(args.registry.read_text(encoding="utf-8")))
    entries = {row["version"]: row for row in registry["entries"]}
    versions = args.versions or sorted(entries)
    failures = 0
    for version in versions:
        entry = entries.get(version)
        if entry is None:
            parser.error(f"Edition v{version} is not in {args.registry}")
        sources = [("primary", entry["primary_source"])] + [
            ("mirror", mirror) for mirror in entry["verified_mirrors"]
        ]
        unavailable: list[str] = []
        matched_source: tuple[str, str, bytes, str | None] | None = None
        failure: str | None = None
        for source_kind, source in sources:
            source_url = source["url"]
            try:
                downloaded, final_url = _read_https(source_url)
            except (HTTPError, URLError, OSError) as error:
                unavailable.append(f"{source_kind} {source_url}: {error}")
                continue
            try:
                edition_xml, archive_member = _edition_payload(downloaded, source_url, entry["sha256"])
            except (ValueError, BadZipFile) as error:
                failure = f"{source_kind} source payload invalid: {error}"
                break
            sha256 = hashlib.sha256(edition_xml).hexdigest()
            git_blob = _git_blob_sha1(edition_xml)
            if (
                len(edition_xml) != entry["bytes"]
                or sha256 != entry["sha256"]
                or git_blob != entry["git_blob_sha1"]
            ):
                failure = (
                    f"{source_kind} source identity mismatch: bytes={len(edition_xml)}, sha256={sha256}, "
                    f"git_blob_sha1={git_blob}"
                )
                break
            matched_source = source_kind, final_url, edition_xml, archive_member
            break
        if matched_source is None:
            failures += 1
            detail = failure or "; ".join(unavailable) or "no primary source or mirror is listed"
            print(f"FAIL v{version}: {detail}", file=sys.stderr)
            continue
        source_kind, final_url, edition_xml, archive_member = matched_source
        sha256 = hashlib.sha256(edition_xml).hexdigest()
        git_blob = _git_blob_sha1(edition_xml)
        member = f" member={archive_member}" if archive_member is not None else ""
        print(
            f"PASS v{version} ({source_kind}): bytes={len(edition_xml)} sha256={sha256} "
            f"git_blob_sha1={git_blob} source={final_url}{member}"
        )
        if source_kind == "mirror" and unavailable:
            print(f"  verified mirror used because {unavailable[0]}")
    print(f"Upstream byte checks: passed={len(versions) - failures}, failures={failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())

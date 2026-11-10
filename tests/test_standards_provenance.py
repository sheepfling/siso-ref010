"""The remote provenance verifier validates its registry before requesting sources."""

from __future__ import annotations

import sys
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import pytest

import tools.siso_ref010.check_standards_provenance as provenance
from tools.siso_ref010.check_standards_provenance import main


def test_invalid_provenance_registry_fails_before_network_access(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = tmp_path / "PROVENANCE.json"
    registry.write_text('{"entries": false}', encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["check_standards_provenance", "--registry", str(registry)])

    with pytest.raises(SystemExit, match="2"):
        main()


def test_zip_xml_member_must_fit_decompression_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    archive_bytes = BytesIO()
    with ZipFile(archive_bytes, "w") as archive:
        archive.writestr("edition.xml", b"<ebv />")
    payload = archive_bytes.getvalue()
    monkeypatch.setattr(provenance, "MAX_EDITION_XML_BYTES", 7)
    monkeypatch.setattr(provenance, "MAX_ARCHIVE_XML_BYTES", 7)

    xml, member = provenance._edition_payload(
        payload, "https://sourceforge.net/file.zip", sha256(b"<ebv />").hexdigest()
    )

    assert xml == b"<ebv />"
    assert member == "edition.xml"

    oversized = BytesIO()
    with ZipFile(oversized, "w") as archive:
        archive.writestr("edition.xml", b"<ebv /> ")
    with pytest.raises(ValueError, match="uncompressed bytes"):
        provenance._edition_payload(
            oversized.getvalue(), "https://sourceforge.net/file.zip", sha256(b"<ebv /> ").hexdigest()
        )


def test_zip_xml_members_share_an_aggregate_decompression_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    archive_bytes = BytesIO()
    with ZipFile(archive_bytes, "w") as archive:
        archive.writestr("first.xml", b"1234")
        archive.writestr("second.xml", b"5678")
    monkeypatch.setattr(provenance, "MAX_EDITION_XML_BYTES", 8)
    monkeypatch.setattr(provenance, "MAX_ARCHIVE_XML_BYTES", 7)

    with pytest.raises(ValueError, match="aggregate uncompressed bytes"):
        provenance._edition_payload(
            archive_bytes.getvalue(), "https://sourceforge.net/file.zip", sha256(b"1234").hexdigest()
        )

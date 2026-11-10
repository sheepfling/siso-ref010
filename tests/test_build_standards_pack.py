import json
import lzma
from hashlib import sha1, sha256
from pathlib import Path

import pytest

import tools.siso_ref010.build_standards_pack as pack_builder
from tools.siso_ref010.build_standards_pack import FORMAT, build, pack_is_current


def _write_current_pack(data_dir: Path, payload: bytes) -> None:
    digest = sha256(payload).hexdigest()
    blob_digest = sha1(b"blob " + str(len(payload)).encode() + b"\0" + payload).hexdigest()
    edition = {
        "version": 1,
        "date": "2026-01-01",
        "sha256": digest,
        "size": len(payload),
        "offset": 0,
        "title": "SISO-REF-010-v1",
        "source_file": "xml/v1.xml",
    }
    pack = lzma.compress(payload)
    (data_dir / "v1.xml").write_bytes(payload)
    (data_dir / "editions.xz").write_bytes(pack)
    source = {
        "provider": "SISO",
        "repository": "fixture",
        "reference": {"type": "publisher-release", "value": "v1"},
        "path": "v1.xml",
        "url": "https://example.invalid/v1.xml",
        "verification": {"sha256_match": True, "git_blob_sha1_match": True},
    }
    entry = {
        "version": 1,
        "status": "verified",
        "file": "xml/v1.xml",
        "bytes": len(payload),
        "sha256": digest,
        "git_blob_sha1": blob_digest,
        "title": "SISO-REF-010-v1",
        "edition_date": "2026-01-01",
        "release": "",
        "schema_namespace": "urn:fixture",
        "elements": 0,
        "enum_tables": 0,
        "primary_source": source,
        "verified_mirrors": [],
        "source_history": [],
        "bundle_file": "data/standards/editions.xz",
    }
    (data_dir / "PROVENANCE.json").write_text(
        json.dumps(
            {
                "verification_scope": "fixture",
                "registry_schema": 2,
                "entries": [entry],
                "source_verification": {
                    "checked_at_utc": "2026-01-01T00:00:00Z",
                    "method": "fixture",
                    "versions": [1],
                },
                "artifacts": [],
                "validation_schemas": [],
            }
        ),
        encoding="utf-8",
    )
    (data_dir / "index.json").write_text(
        json.dumps(
            {
                "format": FORMAT,
                "latest_version": 1,
                "verified_scope": "fixture",
                "raw_size": len(payload),
                "pack_size": len(pack),
                "pack_sha256": sha256(pack).hexdigest(),
                "editions": [edition],
            }
        ),
        encoding="utf-8",
    )


def test_pack_current_check_accepts_unchanged_sources(tmp_path: Path) -> None:
    _write_current_pack(tmp_path, b"<ebv title='SISO-REF-010-v1' date='2026-01-01' />")

    assert pack_is_current(tmp_path)


def test_pack_current_check_detects_source_and_pack_changes(tmp_path: Path) -> None:
    _write_current_pack(tmp_path, b"<ebv title='SISO-REF-010-v1' date='2026-01-01' />")
    (tmp_path / "v1.xml").write_bytes(b"changed")
    assert not pack_is_current(tmp_path)

    _write_current_pack(tmp_path, b"<ebv title='SISO-REF-010-v1' date='2026-01-01' />")
    (tmp_path / "editions.xz").write_bytes(b"changed")
    assert not pack_is_current(tmp_path)


def test_pack_current_check_rejects_malformed_manifests_and_indexes(tmp_path: Path) -> None:
    _write_current_pack(tmp_path, b"<ebv title='SISO-REF-010-v1' date='2026-01-01' />")
    (tmp_path / "PROVENANCE.json").write_text('{"entries": false}', encoding="utf-8")
    assert not pack_is_current(tmp_path)

    _write_current_pack(tmp_path, b"<ebv title='SISO-REF-010-v1' date='2026-01-01' />")
    (tmp_path / "index.json").write_text('{"format": "wrong"}', encoding="utf-8")
    assert not pack_is_current(tmp_path)


def test_builder_writes_a_model_validated_index(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_current_pack(tmp_path, b"<ebv title='SISO-REF-010-v1' date='2026-01-01' />")
    monkeypatch.setattr(pack_builder, "DATA", tmp_path)

    assert build(preset=0) == (1, (tmp_path / "editions.xz").stat().st_size)
    assert pack_is_current(tmp_path)

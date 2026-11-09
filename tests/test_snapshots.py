import hashlib
import json
import lzma
from io import BytesIO

import pytest

import siso_ref010.snapshots as snapshots
from siso_ref010.snapshots import SnapshotIndex, SnapshotIntegrityError


@pytest.fixture(autouse=True)
def _clear_snapshot_caches():
    snapshots._index.cache_clear()
    snapshots._verify_pack.cache_clear()
    snapshots.read_snapshot_bytes.cache_clear()
    yield
    snapshots._index.cache_clear()
    snapshots._verify_pack.cache_clear()
    snapshots.read_snapshot_bytes.cache_clear()


def _valid_index():
    return {
        "format": snapshots._FORMAT,
        "latest_version": 1,
        "verified_scope": "test fixture",
        "raw_size": 1,
        "pack_size": 1,
        "pack_sha256": "0" * 64,
        "editions": [
            {
                "version": 1,
                "date": "2026-01-01",
                "sha256": "0" * 64,
                "size": 1,
                "offset": 0,
                "title": "fixture",
                "source_file": "v1.xml",
            }
        ],
    }


def _valid_model():
    return SnapshotIndex.model_validate_json(json.dumps(_valid_index()))


class _Resource:
    def __init__(self, content=b"", *, error=None):
        self.content = content
        self.error = error

    def joinpath(self, *_parts):
        return self

    def read_bytes(self):
        if self.error is not None:
            raise self.error
        return self.content

    def open(self, _mode):
        if self.error is not None:
            raise self.error
        return BytesIO(self.content)


@pytest.mark.parametrize(
    "content",
    [
        b"not json",
        b"[]",
        json.dumps({"format": "other"}).encode(),
        json.dumps({"format": snapshots._FORMAT, "latest_version": True}).encode(),
    ],
)
def test_index_rejects_unreadable_and_malformed_data(monkeypatch, content):
    monkeypatch.setattr(snapshots, "files", lambda _package: _Resource(content))
    with pytest.raises(SnapshotIntegrityError, match="Malformed bundled edition index"):
        snapshots._index()


def test_index_io_failure_is_reported_as_integrity_error(monkeypatch):
    monkeypatch.setattr(snapshots, "files", lambda _package: _Resource(error=OSError("missing")))
    with pytest.raises(SnapshotIntegrityError, match="Cannot read the bundled edition index"):
        snapshots._index()


@pytest.mark.parametrize(
    "mutate, message",
    [
        (lambda index: index.update(pack_size=True), "pack_size"),
        (lambda index: index.update(pack_sha256="x" * 64), "pack_sha256"),
        (lambda index: index.update(editions=[]), "edition list is empty"),
        (lambda index: index["editions"][0].update(date="2026-13-01"), "date"),
        (lambda index: index["editions"][0].update(version=0), "version"),
        (lambda index: index["editions"][0].update(sha256="0" * 63), "sha256"),
        (lambda index: index["editions"][0].update(size=0), "size"),
        (lambda index: index["editions"][0].update(extra="unexpected"), "extra"),
        (lambda index: index.update(latest_version=2), "latest edition is not first"),
        (lambda index: index.update(raw_size=2), "uncompressed size"),
    ],
)
def test_index_pydantic_models_validate_fields_and_layout(monkeypatch, mutate, message):
    payload = _valid_index()
    mutate(payload)
    monkeypatch.setattr(
        snapshots,
        "files",
        lambda _package: _Resource(json.dumps(payload).encode()),
    )
    with pytest.raises(SnapshotIntegrityError, match=message):
        snapshots._index()


def test_index_rejects_duplicate_versions(monkeypatch):
    payload = _valid_index()
    payload["editions"].append(dict(payload["editions"][0], offset=1))
    payload["raw_size"] = 2
    monkeypatch.setattr(
        snapshots,
        "files",
        lambda _package: _Resource(json.dumps(payload).encode()),
    )
    with pytest.raises(SnapshotIntegrityError, match="edition versions are duplicated"):
        snapshots._index()


def test_snapshot_models_are_frozen_and_use_date_objects():
    edition = _valid_model().editions[0]
    assert edition.date.isoformat() == "2026-01-01"
    with pytest.raises(ValueError, match="frozen"):
        edition.version = 2


def test_pack_and_edition_payload_integrity_fail_closed(monkeypatch):
    index = _valid_model()
    monkeypatch.setattr(snapshots, "_index", lambda: index)
    monkeypatch.setattr(snapshots, "files", lambda _package: _Resource(b"bad"))
    snapshots._verify_pack.cache_clear()
    with pytest.raises(SnapshotIntegrityError, match="fingerprint mismatch"):
        snapshots._verify_pack()

    monkeypatch.setattr(snapshots, "_verify_pack", lambda: None)
    with pytest.raises(KeyError, match="version True is not bundled"):
        snapshots.read_snapshot_bytes(True)
    with pytest.raises(KeyError, match="v2 is not bundled"):
        snapshots.read_snapshot_bytes(2)

    monkeypatch.setattr(snapshots, "files", lambda _package: _Resource(b"not xz"))
    with pytest.raises(SnapshotIntegrityError, match="Cannot decompress"):
        snapshots.read_snapshot_bytes(1)

    payload = b"<ebv/>"
    monkeypatch.setattr(
        snapshots,
        "files",
        lambda _package: _Resource(lzma.compress(payload)),
    )
    with pytest.raises(SnapshotIntegrityError, match="checksum mismatch"):
        snapshots.read_snapshot_bytes(1)


@pytest.mark.parametrize(
    "failure", [OSError("read failed"), EOFError("short stream"), lzma.LZMAError("bad stream")]
)
def test_decompression_failures_are_reported_as_integrity_errors(monkeypatch, failure):
    monkeypatch.setattr(snapshots, "_index", _valid_model)
    monkeypatch.setattr(snapshots, "_verify_pack", lambda: None)
    monkeypatch.setattr(snapshots, "files", lambda _package: _Resource(b"pack"))

    def fail_decompression(_raw, _mode):
        raise failure

    monkeypatch.setattr(snapshots.lzma, "LZMAFile", fail_decompression)
    with pytest.raises(SnapshotIntegrityError, match="Cannot decompress SISO-REF-010 v1"):
        snapshots.read_snapshot_bytes(1)


def test_snapshot_payload_size_must_match_index(monkeypatch):
    payload = b"x"
    index = SnapshotIndex.model_validate_json(
        json.dumps(
            {
                **_valid_index(),
                "raw_size": 2,
                "editions": [
                    {
                        **_valid_index()["editions"][0],
                        "size": 2,
                        "sha256": hashlib.sha256(payload).hexdigest(),
                    }
                ],
            }
        )
    )
    monkeypatch.setattr(snapshots, "_index", lambda: index)
    monkeypatch.setattr(snapshots, "_verify_pack", lambda: None)
    monkeypatch.setattr(snapshots, "files", lambda _package: _Resource(lzma.compress(payload)))
    with pytest.raises(SnapshotIntegrityError, match="checksum mismatch"):
        snapshots.read_snapshot_bytes(1)


def test_pack_io_errors_are_reported_as_integrity_failures(monkeypatch):
    monkeypatch.setattr(snapshots, "_index", _valid_model)
    monkeypatch.setattr(snapshots, "files", lambda _package: _Resource(error=OSError("gone")))
    snapshots._verify_pack.cache_clear()
    with pytest.raises(SnapshotIntegrityError, match="Cannot read the bundled edition pack"):
        snapshots._verify_pack()

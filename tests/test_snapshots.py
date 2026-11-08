import hashlib
import json
import lzma
from io import BytesIO

import pytest

import siso_ref010.snapshots as snapshots
from siso_ref010.snapshots import SnapshotIntegrityError


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


class _Resource:
    def __init__(self, content=b"", text=None, *, error=None):
        self.content = content
        self.text = text
        self.error = error

    def joinpath(self, *_parts):
        return self

    def read_text(self, *, encoding):
        if self.error is not None:
            raise self.error
        return self.text

    def open(self, _mode):
        if self.error is not None:
            raise self.error
        return BytesIO(self.content)


@pytest.mark.parametrize(
    "payload, message",
    [
        ("not json", "Cannot read the bundled edition index"),
        ([], "Unsupported bundled edition index"),
        ({"format": "other"}, "Unsupported bundled edition index"),
        ({"format": snapshots._FORMAT, "latest_version": True}, "Malformed edition index field"),
        ({"format": snapshots._FORMAT, "latest_version": 1}, "Malformed edition index field"),
    ],
)
def test_index_rejects_unreadable_and_malformed_roots(monkeypatch, payload, message):
    text = payload if isinstance(payload, str) else json.dumps(payload)
    resource = _Resource(text=text)
    monkeypatch.setattr(snapshots, "files", lambda _package: resource)
    snapshots._index.cache_clear()
    with pytest.raises(SnapshotIntegrityError, match=message):
        snapshots._index()


def test_index_rejects_non_string_object_keys(monkeypatch):
    resource = _Resource(text="{}")
    monkeypatch.setattr(snapshots, "files", lambda _package: resource)
    monkeypatch.setattr(snapshots.json, "loads", lambda _text: {1: "invalid key"})
    with pytest.raises(SnapshotIntegrityError, match="Unsupported bundled edition index"):
        snapshots._index()


def test_index_io_failure_is_reported_as_integrity_error(monkeypatch):
    monkeypatch.setattr(snapshots, "files", lambda _package: _Resource(error=OSError("missing")))
    with pytest.raises(SnapshotIntegrityError, match="Cannot read the bundled edition index"):
        snapshots._index()


@pytest.mark.parametrize(
    "mutate, message",
    [
        (lambda index: index.update(raw_size=0), "Malformed bundled edition index metadata"),
        (lambda index: index.update(pack_sha256="0" * 63), "Malformed bundled edition index metadata"),
        (lambda index: index.update(pack_sha256="g" * 64), "Malformed bundled pack checksum"),
        (lambda index: index.update(verified_scope=1), "Malformed edition index field"),
        (lambda index: index.update(editions=[]), "Bundled edition index is empty or malformed"),
        (lambda index: index.update(editions=[1]), "Malformed edition record"),
        (lambda index: index["editions"][0].update(date=1), "Malformed edition index field"),
        (lambda index: index["editions"][0].update(size=0), "Edition versions or offsets are invalid"),
        (lambda index: index["editions"][0].update(offset=1), "Edition versions or offsets are invalid"),
        (lambda index: index["editions"][0].update(sha256="x" * 64), "Malformed edition checksum"),
        (lambda index: index["editions"][0].update(sha256="0" * 63), "Malformed edition checksum"),
        (lambda index: index.update(latest_version=2), "Latest edition is not first in the pack"),
        (lambda index: index.update(raw_size=2), "Edition offsets do not match the uncompressed size"),
    ],
)
def test_index_rejects_invalid_metadata_and_edition_offsets(monkeypatch, mutate, message):
    payload = _valid_index()
    mutate(payload)
    resource = _Resource(text=json.dumps(payload))
    monkeypatch.setattr(snapshots, "files", lambda _package: resource)
    snapshots._index.cache_clear()
    with pytest.raises(SnapshotIntegrityError, match=message):
        snapshots._index()


def test_index_rejects_duplicate_versions(monkeypatch):
    payload = _valid_index()
    second = dict(payload["editions"][0], offset=1)
    payload["editions"].append(second)
    payload["raw_size"] = 2
    resource = _Resource(text=json.dumps(payload))
    monkeypatch.setattr(snapshots, "files", lambda _package: resource)
    with pytest.raises(SnapshotIntegrityError, match="Edition versions or offsets are invalid"):
        snapshots._index()


def test_pack_and_edition_payload_integrity_fail_closed(monkeypatch):
    index = _valid_index()
    monkeypatch.setattr(snapshots, "_index", lambda: index)
    monkeypatch.setattr(snapshots, "files", lambda _package: _Resource(content=b"bad"))
    snapshots._verify_pack.cache_clear()
    with pytest.raises(SnapshotIntegrityError, match="fingerprint mismatch"):
        snapshots._verify_pack()

    monkeypatch.setattr(snapshots, "_verify_pack", lambda: None)
    with pytest.raises(KeyError, match="version True is not bundled"):
        snapshots.read_snapshot_bytes(True)
    with pytest.raises(KeyError, match="v2 is not bundled"):
        snapshots.read_snapshot_bytes(2)

    monkeypatch.setattr(snapshots, "files", lambda _package: _Resource(content=b"not xz"))
    with pytest.raises(SnapshotIntegrityError, match="Cannot decompress"):
        snapshots.read_snapshot_bytes(1)

    payload = b"<ebv/>"
    monkeypatch.setattr(snapshots, "files", lambda _package: _Resource(content=lzma.compress(payload)))
    with pytest.raises(SnapshotIntegrityError, match="checksum mismatch"):
        snapshots.read_snapshot_bytes(1)


@pytest.mark.parametrize(
    "failure", [OSError("read failed"), EOFError("short stream"), lzma.LZMAError("bad stream")]
)
def test_decompression_failures_are_reported_as_integrity_errors(monkeypatch, failure):
    monkeypatch.setattr(snapshots, "_index", lambda: _valid_index())
    monkeypatch.setattr(snapshots, "_verify_pack", lambda: None)
    monkeypatch.setattr(snapshots, "files", lambda _package: _Resource(content=b"pack"))

    def fail_decompression(_raw, _mode):
        raise failure

    monkeypatch.setattr(snapshots.lzma, "LZMAFile", fail_decompression)
    with pytest.raises(SnapshotIntegrityError, match="Cannot decompress SISO-REF-010 v1"):
        snapshots.read_snapshot_bytes(1)


def test_snapshot_payload_size_must_match_index(monkeypatch):
    index = _valid_index()
    index["editions"][0]["size"] = 2
    payload = b"x"
    index["editions"][0]["sha256"] = hashlib.sha256(payload).hexdigest()
    monkeypatch.setattr(snapshots, "_index", lambda: index)
    monkeypatch.setattr(snapshots, "_verify_pack", lambda: None)
    monkeypatch.setattr(snapshots, "files", lambda _package: _Resource(content=lzma.compress(payload)))
    with pytest.raises(SnapshotIntegrityError, match="checksum mismatch"):
        snapshots.read_snapshot_bytes(1)


def test_pack_io_errors_are_reported_as_integrity_failures(monkeypatch):
    index = _valid_index()
    index["pack_size"] = 0
    index["pack_sha256"] = hashlib.sha256(b"").hexdigest()
    monkeypatch.setattr(snapshots, "_index", lambda: index)
    monkeypatch.setattr(snapshots, "files", lambda _package: _Resource(error=OSError("gone")))
    snapshots._verify_pack.cache_clear()
    with pytest.raises(SnapshotIntegrityError, match="Cannot read the bundled edition pack"):
        snapshots._verify_pack()

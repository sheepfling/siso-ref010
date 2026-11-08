"""Read verified, compressed SISO-REF-010 edition snapshots on demand."""

from __future__ import annotations

import json
import lzma
from collections.abc import Mapping
from functools import lru_cache
from hashlib import sha256
from importlib.resources import files
from typing import Final, TypeAlias, TypedDict, cast

_DATA_DIR: Final = "data/standards"
_INDEX_FILE: Final = "index.json"
_PACK_FILE: Final = "editions.xz"
_FORMAT: Final = "dis-entity-types-snapshot-pack-1"

_JsonValue: TypeAlias = str | int | float | bool | None | list["_JsonValue"] | dict[str, "_JsonValue"]
_JsonObject: TypeAlias = dict[str, _JsonValue]


class SnapshotEdition(TypedDict):
    version: int
    date: str
    sha256: str
    size: int
    offset: int
    title: str
    source_file: str


class SnapshotIndex(TypedDict):
    format: str
    latest_version: int
    verified_scope: str
    raw_size: int
    pack_size: int
    pack_sha256: str
    editions: list[SnapshotEdition]


class SnapshotIntegrityError(ValueError):
    """A bundled edition pack or its index is missing or inconsistent."""


def _json_object(value: object, message: str) -> _JsonObject:
    if not isinstance(value, dict):
        raise SnapshotIntegrityError(message)
    candidate = cast(Mapping[object, _JsonValue], value)
    if any(not isinstance(key, str) for key in candidate):
        raise SnapshotIntegrityError(message)
    return cast(_JsonObject, value)


def _required_int(row: _JsonObject, field: str) -> int:
    value = row.get(field)
    if type(value) is not int:
        raise SnapshotIntegrityError(f"Malformed edition index field: {field}")
    return value


def _required_string(row: _JsonObject, field: str) -> str:
    value = row.get(field)
    if not isinstance(value, str):
        raise SnapshotIntegrityError(f"Malformed edition index field: {field}")
    return value


@lru_cache(maxsize=1)
def _index() -> SnapshotIndex:
    try:
        raw_value = json.loads(
            files("dis_entity_types").joinpath(_DATA_DIR, _INDEX_FILE).read_text(encoding="utf-8")
        )
    except (OSError, ValueError) as error:
        raise SnapshotIntegrityError("Cannot read the bundled edition index") from error
    value = _json_object(raw_value, "Unsupported bundled edition index")
    if value.get("format") != _FORMAT:
        raise SnapshotIntegrityError("Unsupported bundled edition index")

    latest_version = _required_int(value, "latest_version")
    raw_size = _required_int(value, "raw_size")
    pack_size = _required_int(value, "pack_size")
    pack_sha256 = _required_string(value, "pack_sha256")
    verified_scope = _required_string(value, "verified_scope")
    if raw_size <= 0 or pack_size <= 0 or len(pack_sha256) != 64:
        raise SnapshotIntegrityError("Malformed bundled edition index metadata")
    if any(char not in "0123456789abcdef" for char in pack_sha256):
        raise SnapshotIntegrityError("Malformed bundled pack checksum")

    raw_editions = value.get("editions")
    if not isinstance(raw_editions, list) or not raw_editions:
        raise SnapshotIntegrityError("Bundled edition index is empty or malformed")
    editions: list[SnapshotEdition] = []
    expected_offset = 0
    versions: set[int] = set()
    for raw_row in raw_editions:
        row = _json_object(raw_row, "Malformed edition record")
        edition: SnapshotEdition = {
            "version": _required_int(row, "version"),
            "date": _required_string(row, "date"),
            "sha256": _required_string(row, "sha256"),
            "size": _required_int(row, "size"),
            "offset": _required_int(row, "offset"),
            "title": _required_string(row, "title"),
            "source_file": _required_string(row, "source_file"),
        }
        version = edition["version"]
        size = edition["size"]
        offset = edition["offset"]
        digest = edition["sha256"]
        if version in versions or size <= 0 or offset != expected_offset:
            raise SnapshotIntegrityError("Edition versions or offsets are invalid")
        if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
            raise SnapshotIntegrityError("Malformed edition checksum")
        versions.add(version)
        expected_offset += size
        editions.append(edition)

    if editions[0]["version"] != latest_version:
        raise SnapshotIntegrityError("Latest edition is not first in the pack")
    if expected_offset != raw_size:
        raise SnapshotIntegrityError("Edition offsets do not match the uncompressed size")
    return {
        "format": _FORMAT,
        "latest_version": latest_version,
        "verified_scope": verified_scope,
        "raw_size": raw_size,
        "pack_size": pack_size,
        "pack_sha256": pack_sha256,
        "editions": editions,
    }


@lru_cache(maxsize=1)
def _verify_pack() -> None:
    index = _index()
    digest = sha256()
    size = 0
    try:
        with files("dis_entity_types").joinpath(_DATA_DIR, _PACK_FILE).open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
                size += len(block)
    except OSError as error:
        raise SnapshotIntegrityError("Cannot read the bundled edition pack") from error
    if size != index["pack_size"] or digest.hexdigest() != index["pack_sha256"]:
        raise SnapshotIntegrityError("Bundled edition pack fingerprint mismatch")


def available_snapshot_versions() -> tuple[int, ...]:
    """Return the edition versions included in the installed distribution."""
    return tuple(sorted(edition["version"] for edition in _index()["editions"]))


@lru_cache(maxsize=4)
def read_snapshot_bytes(version: int) -> bytes:
    """Decompress and verify one edition only when requested, retaining four editions."""
    if type(version) is not int:
        raise KeyError(f"SISO-REF-010 version {version!r} is not bundled")
    index = _index()
    edition = next((row for row in index["editions"] if row["version"] == version), None)
    if edition is None:
        raise KeyError(f"SISO-REF-010 v{version} is not bundled")
    _verify_pack()
    try:
        with files("dis_entity_types").joinpath(_DATA_DIR, _PACK_FILE).open("rb") as raw:
            with lzma.LZMAFile(raw, "rb") as stream:
                stream.seek(edition["offset"])
                payload = stream.read(edition["size"])
    except (OSError, EOFError, lzma.LZMAError) as error:
        raise SnapshotIntegrityError(f"Cannot decompress SISO-REF-010 v{version}") from error
    if len(payload) != edition["size"] or sha256(payload).hexdigest() != edition["sha256"]:
        raise SnapshotIntegrityError(f"SISO-REF-010 v{version} checksum mismatch")
    return payload

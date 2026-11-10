"""Read verified, compressed SISO-REF-010 edition snapshots on demand."""

from __future__ import annotations

import lzma
from datetime import date as Date
from functools import lru_cache
from hashlib import sha256
from importlib.resources import files
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

_DATA_DIR: Final = "data/standards"
_INDEX_FILE: Final = "index.json"
_PACK_FILE: Final = "editions.xz"
_FORMAT: Final = "siso-ref010-snapshot-pack-1"
_DIGEST_PATTERN: Final = r"^[0-9a-f]{64}$"


class SnapshotEdition(BaseModel):
    """Validated offset and source identity for one edition in the XZ pack."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    version: int = Field(gt=0)
    date: Date
    sha256: str = Field(pattern=_DIGEST_PATTERN)
    size: int = Field(gt=0)
    offset: int = Field(ge=0)
    title: str = Field(min_length=1)
    source_file: str = Field(min_length=1)


class SnapshotIndex(BaseModel):
    """Validated manifest for the compressed edition stream."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    format: Literal["siso-ref010-snapshot-pack-1"]
    latest_version: int = Field(gt=0)
    verified_scope: str = Field(min_length=1)
    raw_size: int = Field(gt=0)
    pack_size: int = Field(gt=0)
    pack_sha256: str = Field(pattern=_DIGEST_PATTERN)
    editions: tuple[SnapshotEdition, ...]

    @model_validator(mode="after")
    def validate_layout(self) -> SnapshotIndex:
        if not self.editions:
            raise ValueError("edition list is empty")

        versions = tuple(edition.version for edition in self.editions)
        if len(set(versions)) != len(versions):
            raise ValueError("edition versions are duplicated")
        if self.editions[0].version != self.latest_version or max(versions) != self.latest_version:
            raise ValueError("latest edition is not first in the pack")

        expected_offset = 0
        for edition in self.editions:
            if edition.offset != expected_offset:
                raise ValueError("edition offsets are not contiguous")
            expected_offset += edition.size
        if expected_offset != self.raw_size:
            raise ValueError("edition offsets do not match the uncompressed size")
        return self


class SnapshotIntegrityError(ValueError):
    """A bundled edition pack or its index is missing or inconsistent."""


def _validation_message(error: ValidationError) -> str:
    details = "; ".join(
        f"{'.'.join(str(part) for part in item['loc'])}: {item['msg']}"
        for item in error.errors(include_url=False)
    )
    return f"Malformed bundled edition index: {details}"


@lru_cache(maxsize=1)
def _index() -> SnapshotIndex:
    try:
        raw_index = files("siso_ref010").joinpath(_DATA_DIR, _INDEX_FILE).read_bytes()
    except OSError as error:
        raise SnapshotIntegrityError("Cannot read the bundled edition index") from error
    try:
        return SnapshotIndex.model_validate_json(raw_index)
    except ValidationError as error:
        raise SnapshotIntegrityError(_validation_message(error)) from error


@lru_cache(maxsize=1)
def _verify_pack() -> None:
    index = _index()
    digest = sha256()
    size = 0
    try:
        with files("siso_ref010").joinpath(_DATA_DIR, _PACK_FILE).open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
                size += len(block)
    except OSError as error:
        raise SnapshotIntegrityError("Cannot read the bundled edition pack") from error
    if size != index.pack_size or digest.hexdigest() != index.pack_sha256:
        raise SnapshotIntegrityError("Bundled edition pack fingerprint mismatch")


def available_snapshot_versions() -> tuple[int, ...]:
    """Return the edition versions included in the installed distribution."""
    return tuple(sorted(edition.version for edition in _index().editions))


def available_snapshot_editions() -> tuple[SnapshotEdition, ...]:
    """Return indexed edition metadata without opening the compressed XML pack."""
    return tuple(sorted(_index().editions, key=lambda edition: edition.version))


@lru_cache(maxsize=4)
def read_snapshot_bytes(version: int) -> bytes:
    """Decompress and verify one edition only when requested, retaining four editions."""
    if type(version) is not int:
        raise KeyError(f"SISO-REF-010 version {version!r} is not bundled")
    edition = next((row for row in _index().editions if row.version == version), None)
    if edition is None:
        raise KeyError(f"SISO-REF-010 v{version} is not bundled")
    _verify_pack()
    try:
        with files("siso_ref010").joinpath(_DATA_DIR, _PACK_FILE).open("rb") as raw:
            with lzma.LZMAFile(raw, "rb") as stream:
                stream.seek(edition.offset)
                payload = stream.read(edition.size)
    except (OSError, EOFError, lzma.LZMAError) as error:
        raise SnapshotIntegrityError(f"Cannot decompress SISO-REF-010 v{version}") from error
    if len(payload) != edition.size or sha256(payload).hexdigest() != edition.sha256:
        raise SnapshotIntegrityError(f"SISO-REF-010 v{version} checksum mismatch")
    return payload

"""Interfaces for retrieving versioned SISO-REF-010 XML bytes."""

from __future__ import annotations

from typing import Protocol

from .snapshots import available_snapshot_versions, read_snapshot_bytes


class StandardSource(Protocol):
    """A versioned source that retrieves verified standard XML bytes."""

    @property
    def versions(self) -> tuple[int, ...]:
        """Return versions that this source can provide."""
        ...

    def read_xml(self, version: int) -> bytes:
        """Retrieve one version as its original XML bytes."""
        ...


class BundledStandardSource:
    """Read editions from the package's indexed compressed XZ snapshot."""

    @property
    def versions(self) -> tuple[int, ...]:
        return available_snapshot_versions()

    def read_xml(self, version: int) -> bytes:
        return read_snapshot_bytes(version)


BUNDLED_STANDARD_SOURCE = BundledStandardSource()

"""Shared path types and normalization for file-backed APIs."""

from __future__ import annotations

from os import PathLike
from pathlib import Path
from typing import TypeAlias

PathInput: TypeAlias = str | PathLike[str]


def normalize_path(path: PathInput) -> Path:
    """Convert any supported path input to the package's internal ``Path`` form."""
    return Path(path)

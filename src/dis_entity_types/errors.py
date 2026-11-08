"""Public exception types raised by the entity type toolkit."""

from __future__ import annotations

from collections.abc import Mapping


class EntityTypeError(Exception):
    """Base class for package-defined errors; also catchable by built-in error type."""

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        context: Mapping[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code or type(self).__name__
        self.context = dict(context or {})


class EntityTypeValueError(EntityTypeError, ValueError):
    """Invalid value with a machine-readable code and contextual values."""


class EntityTypeTypeError(EntityTypeError, TypeError):
    """Unsupported Python value type with machine-readable context."""


class EntityTypeIndexError(EntityTypeError, IndexError):
    """Unavailable result index with machine-readable context."""

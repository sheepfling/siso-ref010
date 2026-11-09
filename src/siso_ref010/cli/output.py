"""Serialization and structured error output for the command line."""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping
from typing import NotRequired, TypedDict

from pydantic import BaseModel

from ..errors import SisoRef010Error
from ..inspection import EditionReport
from ..reporting import render_json_envelope

JSON_SCHEMA_VERSION = 1


class CliErrorPayload(TypedDict):
    type: str
    message: str
    code: NotRequired[str]
    context: NotRequired[Mapping[str, object]]


def write_json_result(command: str, result: BaseModel) -> None:
    """Write a result model using the versioned machine-readable envelope."""
    if isinstance(result, EditionReport):
        print(render_json_envelope(result, command=command, schema_version=JSON_SCHEMA_VERSION))
        return
    print(
        json.dumps(
            {
                "schema_version": JSON_SCHEMA_VERSION,
                "command": command,
                "result": result.model_dump(mode="json", by_alias=True),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def write_json_error(
    message: str,
    error_type: str,
    command: str | None,
    package_error: SisoRef010Error | None = None,
) -> None:
    """Write errors to stderr without contaminating a JSON result on stdout."""
    error: CliErrorPayload = {"type": error_type, "message": message}
    if package_error is not None:
        error["code"] = package_error.code
        error["context"] = package_error.context
    print(
        json.dumps(
            {
                "schema_version": JSON_SCHEMA_VERSION,
                "command": command,
                "error": error,
            },
            ensure_ascii=False,
        ),
        file=sys.stderr,
    )


def error_type(error: Exception) -> str:
    """Return a stable exception class name for the JSON error envelope."""
    if isinstance(error, TypeError):
        return "TypeError"
    if isinstance(error, ValueError):
        return "ValueError"
    if isinstance(error, IndexError):
        return "IndexError"
    return type(error).__name__

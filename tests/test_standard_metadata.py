"""Typed boundary validation for bundled edition metadata."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from tools.siso_ref010.standard_metadata import ProvenanceRegistry, StandardPackIndex

STANDARDS = Path("src/siso_ref010/data/standards")


def test_checked_in_provenance_and_pack_index_validate_as_typed_models() -> None:
    provenance = ProvenanceRegistry.model_validate_json((STANDARDS / "PROVENANCE.json").read_bytes())
    index = StandardPackIndex.model_validate_json((STANDARDS / "index.json").read_bytes())

    assert provenance.registry_schema == 2
    assert len(provenance.entries) == len(index.editions) == 18
    assert index.latest_version == 37


@pytest.mark.parametrize(
    "payload",
    [
        b'{"registry_schema": true}',
        b'{"registry_schema": 2, "unexpected": true}',
        b'{"registry_schema": 2, "entries": [{"version": "37"}]}',
    ],
)
def test_provenance_model_rejects_invalid_json_shapes(payload: bytes) -> None:
    with pytest.raises(ValidationError):
        ProvenanceRegistry.model_validate_json(payload)


def test_pack_index_rejects_wrong_schema_and_duplicate_editions() -> None:
    with pytest.raises(ValidationError):
        StandardPackIndex.model_validate_json(b'{"format": "unknown"}')

    edition = {
        "version": 1,
        "date": "2026-01-01",
        "sha256": "0" * 64,
        "size": 1,
        "offset": 0,
        "title": "Edition 1",
        "source_file": "xml/v1.xml",
    }
    payload = {
        "format": "siso-ref010-snapshot-pack-1",
        "latest_version": 1,
        "verified_scope": "fixture",
        "raw_size": 2,
        "pack_size": 1,
        "pack_sha256": "1" * 64,
        "editions": [edition, edition],
    }
    with pytest.raises(ValidationError, match="edition versions must be unique"):
        StandardPackIndex.model_validate_json(json.dumps(payload))

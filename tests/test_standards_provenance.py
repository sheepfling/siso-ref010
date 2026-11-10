"""The remote provenance verifier validates its registry before requesting sources."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from tools.siso_ref010.check_standards_provenance import main


def test_invalid_provenance_registry_fails_before_network_access(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = tmp_path / "PROVENANCE.json"
    registry.write_text('{"entries": false}', encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["check_standards_provenance", "--registry", str(registry)])

    with pytest.raises(SystemExit, match="2"):
        main()

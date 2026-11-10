"""Fail-closed behavior for the offline XSD validation command."""

from __future__ import annotations

from pathlib import Path

import pytest

from tools.siso_ref010 import check_standards_xsd


def test_missing_schema_fails_instead_of_reporting_success(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    editions, historical, current_namespace, current_sha256 = check_standards_xsd._load_registries()
    historical_version = min(historical)
    historical.pop(historical_version)
    monkeypatch.setattr(
        check_standards_xsd,
        "_load_registries",
        lambda: (editions, historical, current_namespace, current_sha256),
    )
    monkeypatch.setattr(check_standards_xsd.shutil, "which", lambda _: "/usr/bin/xmllint")

    result = check_standards_xsd.main(["--versions", str(historical_version)])

    assert result == 1
    assert "NOT RUN" in capsys.readouterr().out


def test_xml_namespace_must_match_registry(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    editions, _, _, _ = check_standards_xsd._load_registries()
    version = max(editions)
    monkeypatch.setattr(check_standards_xsd, "_namespace", lambda _: "urn:unexpected")
    monkeypatch.setattr(check_standards_xsd.shutil, "which", lambda _: "/usr/bin/xmllint")

    result = check_standards_xsd.main(["--versions", str(version)])

    assert result == 1
    assert "does not match the provenance registry namespace" in capsys.readouterr().out


def test_default_validation_requires_xml_for_every_registry_edition(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    registry_data = check_standards_xsd._load_registries()
    (tmp_path / "v37.xml").touch()
    monkeypatch.setattr(check_standards_xsd, "STANDARDS", tmp_path)
    monkeypatch.setattr(check_standards_xsd, "_load_registries", lambda: registry_data)
    monkeypatch.setattr(check_standards_xsd.shutil, "which", lambda _: "/usr/bin/xmllint")

    result = check_standards_xsd.main([])

    assert result == 2
    assert "Bundled XML and provenance editions differ" in capsys.readouterr().err

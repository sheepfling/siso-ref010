"""Regression tests for the narrow repository hygiene rules."""

from __future__ import annotations

from pathlib import Path

import pytest

import tools.repo_hygiene.check_repository_hygiene as hygiene
from tools.repo_hygiene.check_repository_hygiene import _artifact_reason, _load_baseline, _source_findings


def test_ephemeral_artifact_classification_is_narrow() -> None:
    assert _artifact_reason(".local/siso_diff.zip") is not None
    assert _artifact_reason("docs/api.md") is None
    assert _artifact_reason("src/siso_ref010/data/standards/v37.xml") is None


def test_hardcoded_consumer_default_is_reported_but_dynamic_default_is_not() -> None:
    finding = _source_findings("examples/consumer.py", "DEFAULT_VERSION = 37\n")
    assert len(finding) == 1
    assert finding[0].category == "historical_coupling"
    assert finding[0].line == 1

    dynamic = _source_findings(
        "examples/consumer.py",
        "from siso_ref010 import SisoRef010API\napi = SisoRef010API()\n",
    )
    assert dynamic == ()


def test_hardcoded_benchmark_version_default_is_reported() -> None:
    source = 'parser.add_argument("--versions", default=(37, 30, 20))\n'
    finding = _source_findings("tools/siso_ref010/benchmark_snapshot_loading.py", source)
    assert len(finding) == 1
    assert finding[0].rule_id == "repo.edition.cli_default"


def test_general_version_argument_without_static_default_is_allowed() -> None:
    source = 'parser.add_argument("--version", type=int)\n'
    assert _source_findings("tools/siso_ref010/benchmark_entity_queries.py", source) == ()


def test_installed_count_and_historical_xsd_range_are_reported() -> None:
    installed = _source_findings(
        "tools/siso_ref010/check_installed.py", "if len(versions) != 18:\n    fail()\n"
    )
    assert len(installed) == 1
    assert installed[0].rule_id == "repo.edition.fixed_count"

    xsd = _source_findings(
        "tools/siso_ref010/check_standards_xsd.py", "for version in range(20, 30):\n    check()\n"
    )
    assert len(xsd) == 1
    assert xsd[0].rule_id == "repo.xsd.fixed_coverage_range"


def test_ci_endpoint_literals_are_reported_but_registry_selection_is_allowed() -> None:
    fixed = '_python_module("tools.siso_ref010.check_standards_xsd", "--versions", "20", "37")\n'
    assert _source_findings("tools/ci.py", fixed)[0].rule_id == "repo.ci.fixed_edition_endpoints"

    dynamic = '_python_module("tools.siso_ref010.check_standards_xsd", "--versions", *endpoints)\n'
    assert _source_findings("tools/ci.py", dynamic) == ()


def test_checker_source_does_not_trigger_its_own_rules() -> None:
    hygiene_path = Path("tools/repo_hygiene/check_repository_hygiene.py")
    source = hygiene_path.read_text(encoding="utf-8")
    assert _source_findings(hygiene_path.as_posix(), source) == ()


def test_baseline_is_validated_into_typed_models(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    baseline = tmp_path / "baseline.json"
    baseline.write_text(
        '{"schema_version":1,"acknowledged":[{"rule_id":"rule", "path":"src/file.py", '
        '"evidence":"line", "reason":"reviewed"}]}',
        encoding="utf-8",
    )
    monkeypatch.setattr(hygiene, "BASELINE", baseline)

    loaded = _load_baseline()
    assert loaded.schema_version == 1
    assert len(loaded.acknowledged) == 1
    assert loaded.acknowledged[0].fingerprint.rule_id == "rule"
    assert loaded.acknowledged[0].fingerprint.path == "src/file.py"
    assert loaded.acknowledged[0].fingerprint.evidence == "line"
    assert loaded.acknowledged[0].reason == "reviewed"


@pytest.mark.parametrize(
    "payload",
    [
        '{"schema_version":2,"acknowledged":[]}',
        '{"schema_version":true,"acknowledged":[]}',
        '{"schema_version":1,"acknowledged":{}}',
        '{"schema_version":1,"acknowledged":[{"rule_id":"rule"}]}',
        '{"schema_version":1,"acknowledged":[{"rule_id":" ","path":"p","evidence":"e","reason":"r"}]}',
        '{"schema_version":1,"acknowledged":[],"unexpected":true}',
    ],
)
def test_baseline_rejects_invalid_shapes_through_model_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, payload: str
) -> None:
    baseline = tmp_path / "baseline.json"
    baseline.write_text(payload, encoding="utf-8")
    monkeypatch.setattr(hygiene, "BASELINE", baseline)

    with pytest.raises(ValueError, match="Invalid repository hygiene baseline"):
        _load_baseline()


def test_baseline_model_rejects_duplicate_fingerprints(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    record = '{"rule_id":"rule", "path":"src/file.py", "evidence":"line", "reason":"reviewed"}'
    baseline = tmp_path / "baseline.json"
    baseline.write_text(
        f'{{"schema_version":1,"acknowledged":[{record},{record}]}}',
        encoding="utf-8",
    )
    monkeypatch.setattr(hygiene, "BASELINE", baseline)

    with pytest.raises(ValueError, match="Invalid repository hygiene baseline"):
        _load_baseline()

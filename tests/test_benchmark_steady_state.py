"""Fast benchmark-contract tests; no bundled standards are parsed."""

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from tools.siso_ref010 import benchmark_steady_state as benchmark

STAGE_KEYS = {
    "calls",
    "elapsed_ms",
    "amortized_lookup_us",
    "process_current_rss_mib",
    "process_peak_rss_mib",
    "traced_retained_mib",
    "traced_stage_peak_mib",
}


def test_untraced_stage_uses_one_clock_pair_and_labels_memory(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = iter((100, 20100))
    monkeypatch.setattr(benchmark, "perf_counter_ns", lambda: next(clock))
    monkeypatch.setattr(benchmark, "current_rss_mib", lambda: 12.0)
    monkeypatch.setattr(benchmark, "peak_rss_mib", lambda: 15.0)
    measurements = benchmark.Measurements(False)
    assert measurements.run("repeated_lookup", lambda: "result", 10) == "result"
    assert measurements.stages["repeated_lookup"] == {
        "calls": 10,
        "elapsed_ms": 0.02,
        "amortized_lookup_us": 2.0,
        "process_current_rss_mib": 12.0,
        "process_peak_rss_mib": 15.0,
        "traced_retained_mib": None,
        "traced_stage_peak_mib": None,
    }


def test_traced_stage_never_reports_latency(monkeypatch: pytest.MonkeyPatch) -> None:
    def unexpected_clock() -> None:
        raise AssertionError("Timing must not use traced execution")

    monkeypatch.setattr(benchmark, "perf_counter_ns", unexpected_clock)
    monkeypatch.setattr(benchmark.tracemalloc, "reset_peak", lambda: None)
    monkeypatch.setattr(benchmark.tracemalloc, "get_traced_memory", lambda: (2**20, 3 * 2**20))
    measurements = benchmark.Measurements(True)
    measurements.run("first_lookup", lambda: None)
    row = measurements.stages["first_lookup"]
    assert set(row) == STAGE_KEYS
    assert row["elapsed_ms"] is None
    assert row["amortized_lookup_us"] is None
    assert row["traced_retained_mib"] == 1
    assert row["traced_stage_peak_mib"] == 3


def test_repeated_lookup_calls_public_operation_exact_count() -> None:
    codes = []
    assert benchmark.repeat_lookup(codes.append, benchmark.DEFAULT_CODE, 8) is None
    assert codes == [benchmark.DEFAULT_CODE] * 8


def test_summary_does_not_mix_traced_rss_or_timings() -> None:
    rows = [
        {
            "version": 20,
            "traced": trace,
            "stages": {
                "load": {
                    "calls": 1,
                    "elapsed_ms": time,
                    "process_current_rss_mib": rss,
                    "traced_retained_mib": retained,
                }
            },
        }
        for trace, time, rss, retained in [(False, 2, 10, None), (False, 4, 12, None), (True, 99, 90, 7)]
    ]
    result = benchmark.summarize(rows)["20"]["load"]
    assert result["elapsed_ms"] == {"median": 3, "min": 2, "max": 4, "samples": 2}
    assert result["process_current_rss_mib"]["median"] == 11
    assert result["traced_retained_mib"]["median"] == 7


def test_unsupported_current_rss_is_null(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(benchmark.sys, "platform", "win32")
    assert benchmark.current_rss_mib() is None
    assert benchmark.peak_rss_mib() is None


def test_linux_current_rss_uses_resident_pages(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(benchmark.sys, "platform", "linux")
    monkeypatch.setattr(Path, "read_text", lambda self: "1234 256 99")
    monkeypatch.setattr(benchmark.os, "sysconf", lambda key: 4096)
    assert benchmark.current_rss_mib() == 1


def test_sample_runs_same_script_with_target_checkout(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured: dict[str, Any] = {}

    def run(command: list[str], **kwargs: object) -> SimpleNamespace:
        captured.update(command=command, **kwargs)
        return SimpleNamespace(stdout='{"version": 20}')

    monkeypatch.setattr(benchmark.subprocess, "run", run)
    assert benchmark.sample(tmp_path, 20, benchmark.DEFAULT_CODE, 50, True, True) == {"version": 20}
    assert captured["command"][1] == str(Path(benchmark.__file__).resolve())
    assert "--warmup" in captured["command"]
    assert "--trace" in captured["command"]
    assert captured["cwd"] == tmp_path
    assert captured["env"]["PYTHONPATH"].split(benchmark.os.pathsep) == [str(tmp_path / "src"), str(tmp_path)]


def test_main_output_schema_and_default_sample_count(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = tmp_path / "src/siso_ref010/data/standards"
    folder.mkdir(parents=True)
    (folder / "index.json").write_text(json.dumps({"editions": [{"version": n} for n in range(117, 99, -1)]}))
    calls = []

    def sample(
        checkout: Path, version: int, code: str, count: int, warmup: bool, trace: bool
    ) -> dict[str, Any]:
        calls.append((checkout, version, code, count, warmup, trace))
        return {"version": version, "traced": trace, "stages": {}}

    output = tmp_path / "result.json"
    monkeypatch.setattr(benchmark, "sample", sample)
    monkeypatch.setattr(
        benchmark.sys, "argv", ["benchmark", "--checkout", str(tmp_path), "--output", str(output)]
    )
    assert benchmark.main() == 0
    result = json.loads(capsys.readouterr().out)
    assert result == json.loads(output.read_text())
    assert set(result) == {"schema_version", "benchmark_sha256", "configuration", "samples", "summary"}
    assert result["schema_version"] == 1
    assert result["configuration"] == {
        "versions": [100, 109, 117],
        "iterations": 3,
        "lookups": 10000,
        "code": benchmark.DEFAULT_CODE,
        "warmup": False,
    }
    assert len(calls) == 18
    assert all(sum(call[1] == version for call in calls) == 6 for version in (100, 109, 117))


@pytest.mark.parametrize("option", ["--iterations", "--lookups"])
def test_rejects_nonpositive_counts(monkeypatch: pytest.MonkeyPatch, option: str) -> None:
    monkeypatch.setattr(benchmark.sys, "argv", ["benchmark", option, "0"])
    with pytest.raises(SystemExit, match="2"):
        benchmark.main()


@pytest.mark.parametrize("warmup", [False, True])
def test_child_result_schema_and_stage_order(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, warmup: bool
) -> None:
    from siso_ref010.api import SisoRef010API

    calls = []

    class FakeAPI:
        def describe(self, code: str) -> SimpleNamespace:
            calls.append(code)
            return SimpleNamespace(description="Known entity")

        def warmup(self) -> SimpleNamespace:
            return SimpleNamespace(indexed_records=42)

    monkeypatch.setattr(SisoRef010API, "from_source", lambda *args: FakeAPI())
    monkeypatch.setattr(benchmark, "checkout_metadata", lambda path: {"checkout": str(path)})
    monkeypatch.setattr(benchmark, "source_provenance", lambda version: {"sha256": "abc", "size": 42})
    result = benchmark.measure_child(20, benchmark.DEFAULT_CODE, 3, warmup, False, tmp_path)
    assert set(result) == {
        "version",
        "code",
        "traced",
        "description",
        "source",
        "indexed_records",
        "pydantic",
        "metadata",
        "stages",
    }
    stages = ["after_imports", "load", "first_lookup", "repeated_lookup"]
    if warmup:
        stages.extend(["query_warmup", "repeated_lookup_after_warmup"])
    assert list(result["stages"]) == stages
    assert all(set(row) == STAGE_KEYS for row in result["stages"].values())
    assert result["description"] == "Known entity"
    assert result["indexed_records"] == (42 if warmup else None)
    assert len(calls) == (7 if warmup else 4)


@pytest.mark.parametrize("available, expected", [([8], [8]), ([9, 4], [4, 9]), ([9, 4, 7, 5], [4, 7, 9])])
def test_default_versions_selects_sorted_unique_representatives(
    tmp_path: Path, available: list[int], expected: list[int]
) -> None:
    folder = tmp_path / "src/siso_ref010/data/standards"
    folder.mkdir(parents=True)
    (folder / "index.json").write_text(json.dumps({"editions": [{"version": n} for n in available]}))
    assert benchmark.default_versions(tmp_path) == expected


def test_default_versions_rejects_empty_index(tmp_path: Path) -> None:
    folder = tmp_path / "src/siso_ref010/data/standards"
    folder.mkdir(parents=True)
    (folder / "index.json").write_text('{"editions": []}')
    with pytest.raises(ValueError, match="no bundled editions"):
        benchmark.default_versions(tmp_path)

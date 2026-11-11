"""Benchmark exact-code lookups and retained memory in isolated, fresh processes."""

from __future__ import annotations

import argparse
import ctypes
import gc
import json
import os
import platform
import subprocess
import sys
import tracemalloc
from collections.abc import Callable
from hashlib import sha256
from pathlib import Path
from statistics import median
from time import perf_counter_ns
from typing import Any, TypeVar

T = TypeVar("T")
DEFAULT_CODE = "1.2.225.7.8.7.1"
MIB = 2**20


def current_rss_mib() -> float | None:
    """Current resident bytes, never the lifetime high-water mark."""
    try:
        if sys.platform.startswith("linux"):
            resident_pages = int(Path("/proc/self/statm").read_text().split()[1])
            return resident_pages * os.sysconf("SC_PAGE_SIZE") / MIB
        if sys.platform == "darwin":

            class TaskBasicInfo(ctypes.Structure):
                _fields_ = [
                    ("virtual_size", ctypes.c_uint64),
                    ("resident_size", ctypes.c_uint64),
                    ("resident_size_max", ctypes.c_uint64),
                    ("user_time", ctypes.c_int * 2),
                    ("system_time", ctypes.c_int * 2),
                    ("policy", ctypes.c_int),
                    ("suspend_count", ctypes.c_int),
                ]

            lib = ctypes.CDLL("/usr/lib/libSystem.B.dylib")
            lib.mach_task_self.restype = ctypes.c_uint
            info = TaskBasicInfo()
            count = ctypes.c_uint(ctypes.sizeof(info) // ctypes.sizeof(ctypes.c_int))
            status = lib.task_info(lib.mach_task_self(), 20, ctypes.byref(info), ctypes.byref(count))
            return info.resident_size / MIB if status == 0 else None
    except (OSError, ValueError, IndexError, AttributeError):
        return None
    return None


def peak_rss_mib() -> float | None:
    """Lifetime high-water RSS; not memory remaining after an operation."""
    if sys.platform not in ("darwin", "linux"):
        return None
    import resource

    unit = 1 if sys.platform == "darwin" else 1024
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * unit / MIB


class Measurements:
    def __init__(self, trace: bool) -> None:
        self.trace = trace
        self.stages: dict[str, dict[str, float | int | None]] = {}

    def run(self, name: str, operation: Callable[[], T], calls: int = 1) -> T:
        """Keep only the final result; collect outside the timing window."""
        gc.collect()
        if self.trace:
            tracemalloc.reset_peak()
        started = perf_counter_ns() if not self.trace else 0
        result = operation()
        elapsed = perf_counter_ns() - started if not self.trace else None
        gc.collect()
        retained, peak = tracemalloc.get_traced_memory() if self.trace else (None, None)
        self.stages[name] = {
            "calls": calls,
            "elapsed_ms": elapsed / 1e6 if elapsed is not None else None,
            "amortized_lookup_us": elapsed / calls / 1e3
            if elapsed is not None and name.startswith("repeated_lookup")
            else None,
            "process_current_rss_mib": current_rss_mib(),
            "process_peak_rss_mib": peak_rss_mib(),
            "traced_retained_mib": retained / MIB if retained is not None else None,
            "traced_stage_peak_mib": peak / MIB if peak is not None else None,
        }
        return result


def repeat_lookup(describe: Callable[[str], Any], code: str, count: int) -> None:
    """Measure the public string-input API, discarding every result as a caller would."""
    for _ in range(count):
        describe(code)


def checkout_metadata(checkout: Path) -> dict[str, Any]:
    def git(*args: str) -> str | None:
        try:
            return subprocess.check_output(
                ["git", "-C", str(checkout), *args], text=True, stderr=subprocess.DEVNULL
            ).strip()
        except (OSError, subprocess.CalledProcessError):
            return None

    status = git("status", "--porcelain", "--untracked-files=normal")
    modules: dict[str, dict[str, str]] = {}
    for name, module in sorted(sys.modules.items()):
        if name == "siso_ref010" or name.startswith("siso_ref010."):
            filename = getattr(module, "__file__", None)
            if filename:
                path = Path(filename).resolve()
                modules[name] = {"path": str(path), "sha256": sha256(path.read_bytes()).hexdigest()}
    return {
        "checkout": str(checkout),
        "git_revision": git("rev-parse", "HEAD"),
        "git_dirty": bool(status) if status is not None else None,
        "git_status_porcelain": status,
        "runtime_modules": modules,
        "python": sys.version,
        "python_executable": sys.executable,
        "platform": platform.platform(),
    }


def source_provenance(version: int) -> dict[str, int | str]:
    """Hash exact source bytes after all measured stages and tracing have finished."""
    from siso_ref010.snapshots import read_snapshot_bytes

    payload = read_snapshot_bytes(version)
    return {"sha256": sha256(payload).hexdigest(), "size": len(payload)}


def measure_child(
    version: int, code: str, count: int, warmup: bool, trace: bool, checkout: Path
) -> dict[str, Any]:
    # Prime the measurement helper before tracing runtime imports, not before loading data.
    current_rss_mib()
    peak_rss_mib()
    measurements = Measurements(trace)
    if trace:
        tracemalloc.start()
    import pydantic

    from siso_ref010.api import SisoRef010API
    from siso_ref010.sources import BUNDLED_STANDARD_SOURCE

    measurements.run("after_imports", lambda: None)
    api = measurements.run("load", lambda: SisoRef010API.from_source(BUNDLED_STANDARD_SOURCE, version))
    description = measurements.run("first_lookup", lambda: api.describe(code).description)
    measurements.run("repeated_lookup", lambda: repeat_lookup(api.describe, code, count), count)
    indexed_records = None
    if warmup:
        indexed_records = measurements.run("query_warmup", lambda: api.warmup().indexed_records)
        measurements.run(
            "repeated_lookup_after_warmup", lambda: repeat_lookup(api.describe, code, count), count
        )
    if trace:
        tracemalloc.stop()
    return {
        "version": version,
        "code": code,
        "traced": trace,
        "description": description,
        "source": source_provenance(version),
        "indexed_records": indexed_records,
        "pydantic": pydantic.__version__,
        "metadata": checkout_metadata(checkout),
        "stages": measurements.stages,
    }


def sample(checkout: Path, version: int, code: str, count: int, warmup: bool, trace: bool) -> dict[str, Any]:
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--child",
        str(version),
        "--checkout",
        str(checkout),
        "--code",
        code,
        "--lookups",
        str(count),
    ]
    if warmup:
        command.append("--warmup")
    if trace:
        command.append("--trace")
    env = dict(os.environ, PYTHONPATH=os.pathsep.join((str(checkout / "src"), str(checkout))))
    result = subprocess.run(command, cwd=checkout, env=env, check=True, capture_output=True, text=True)
    return json.loads(result.stdout)


def summarize(samples: list[dict[str, Any]]) -> dict[str, Any]:
    """RSS summaries use untraced processes; allocation summaries use traced ones."""
    summary: dict[str, Any] = {}
    for version in sorted({sample["version"] for sample in samples}):
        group = [sample for sample in samples if sample["version"] == version]
        stages: dict[str, Any] = {}
        for stage in group[0]["stages"]:
            metrics: dict[str, Any] = {}
            for metric in group[0]["stages"][stage]:
                if metric == "calls":
                    continue
                traced = metric.startswith("traced_")
                values = [row["stages"][stage][metric] for row in group if row["traced"] == traced]
                present = [value for value in values if value is not None]
                metrics[metric] = (
                    {
                        "median": median(present),
                        "min": min(present),
                        "max": max(present),
                        "samples": len(present),
                    }
                    if present
                    else None
                )
            stages[stage] = metrics
        summary[str(version)] = stages
    return summary


def default_versions(checkout: Path) -> list[int]:
    """Select oldest, middle and newest editions from the target checkout's index."""
    index = json.loads((checkout / "src/siso_ref010/data/standards/index.json").read_text(encoding="utf-8"))
    available = sorted({int(edition["version"]) for edition in index["editions"]})
    if not available:
        raise ValueError("the selected checkout has no bundled editions")
    return list(dict.fromkeys((available[0], available[len(available) // 2], available[-1])))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkout", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--versions", nargs="+", type=int)
    parser.add_argument("--iterations", type=int, default=3)
    parser.add_argument("--lookups", type=int, default=10000)
    parser.add_argument("--code", default=DEFAULT_CODE)
    parser.add_argument("--warmup", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--child", type=int, help=argparse.SUPPRESS)
    parser.add_argument("--trace", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.iterations < 1 or args.lookups < 1:
        parser.error("--iterations and --lookups must be positive")
    checkout = args.checkout.resolve()
    if not (checkout / "src/siso_ref010").is_dir():
        parser.error("--checkout must contain src/siso_ref010")
    if args.child is not None:
        # Also enforce the target for direct --child invocations, before runtime imports.
        sys.path[:0] = [str(checkout / "src"), str(checkout)]
        print(
            json.dumps(measure_child(args.child, args.code, args.lookups, args.warmup, args.trace, checkout))
        )
        return 0
    try:
        versions = args.versions or default_versions(checkout)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.error(f"cannot select bundled editions: {exc}")
    samples = [
        sample(checkout, version, args.code, args.lookups, args.warmup, trace)
        for version in versions
        for _ in range(args.iterations)
        for trace in (False, True)
    ]
    result = {
        "schema_version": 1,
        "benchmark_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
        "configuration": {
            "versions": versions,
            "iterations": args.iterations,
            "lookups": args.lookups,
            "code": args.code,
            "warmup": args.warmup,
        },
        "samples": samples,
        "summary": summarize(samples),
    }
    output = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.write_text(output, encoding="utf-8")
    print(output, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

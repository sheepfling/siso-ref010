"""Measure cold snapshot, API construction, and process startup by edition."""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
from statistics import median
from time import perf_counter


def _measure_child(operation: str, version: int) -> None:
    started = perf_counter()
    if operation == "snapshot":
        from siso_ref010.snapshots import read_snapshot_bytes

        payload_size = len(read_snapshot_bytes(version))
        first_result = None
    elif operation in {"api", "startup"}:
        from siso_ref010 import SisoRef010API

        api = SisoRef010API.bundled(version)
        first_result = api.info().data_version if operation == "startup" else None
        payload_size = None
    else:
        raise ValueError(f"unknown benchmark operation: {operation}")
    elapsed_ms = (perf_counter() - started) * 1000
    print(
        json.dumps(
            {
                "operation": operation,
                "version": version,
                "elapsed_ms": elapsed_ms,
                "payload_size": payload_size,
                "first_result": first_result,
            }
        )
    )


def _sample(operation: str, version: int) -> float:
    started = perf_counter()
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "tools.siso_ref010.benchmark_snapshot_loading",
            "--child",
            operation,
            "--version",
            str(version),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    sample = json.loads(result.stdout)
    if operation == "startup":
        if not sample["first_result"]:
            raise AssertionError("startup sample did not produce an API result")
        return (perf_counter() - started) * 1000
    return float(sample["elapsed_ms"])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--versions", type=int, nargs="+", help="Editions to measure (default: latest, middle, earliest)"
    )
    parser.add_argument("--iterations", type=int, default=3, help="Fresh-process samples per operation")
    parser.add_argument("--child", choices=("snapshot", "api", "startup"), help=argparse.SUPPRESS)
    parser.add_argument("--version", type=int, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.child:
        if args.version is None:
            parser.error("--version is required for a child sample")
        _measure_child(args.child, args.version)
        return 0
    if args.iterations < 1:
        parser.error("--iterations must be positive")

    from siso_ref010 import SisoRef010API

    available = SisoRef010API.bundled_versions().versions
    if not available:
        parser.error("no bundled editions are available")
    if args.versions is None:
        selected_versions = tuple(
            dict.fromkeys((available[-1], available[len(available) // 2], available[0]))
        )
    else:
        selected_versions = args.versions
    print(f"Python {platform.python_version()} · {platform.platform()}")
    print(
        "Each sample uses a fresh process. Snapshot/API timings exclude interpreter startup; "
        "startup timing includes process launch through the first info() result."
    )
    for version in selected_versions:
        if version not in available:
            parser.error(f"v{version} is not bundled; available editions are {available}")
        snapshot_times = [_sample("snapshot", version) for _ in range(args.iterations)]
        api_times = [_sample("api", version) for _ in range(args.iterations)]
        startup_times = [_sample("startup", version) for _ in range(args.iterations)]
        print(
            f"v{version}: snapshot retrieval median {median(snapshot_times):.2f} ms "
            f"(range {min(snapshot_times):.2f}–{max(snapshot_times):.2f}); "
            f"API construction median {median(api_times):.2f} ms "
            f"(range {min(api_times):.2f}–{max(api_times):.2f}); "
            f"process startup to first result median {median(startup_times):.2f} ms "
            f"(range {min(startup_times):.2f}–{max(startup_times):.2f})"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

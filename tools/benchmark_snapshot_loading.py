"""Measure cold snapshot retrieval and full bundled API construction by edition."""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
from statistics import median
from time import perf_counter

from siso_ref010 import EntityTypeAPI
from siso_ref010.snapshots import read_snapshot_bytes


def _measure_child(operation: str, version: int) -> None:
    started = perf_counter()
    if operation == "snapshot":
        payload_size = len(read_snapshot_bytes(version))
    else:
        EntityTypeAPI.bundled(version)
        payload_size = None
    elapsed_ms = (perf_counter() - started) * 1000
    print(
        json.dumps(
            {
                "operation": operation,
                "version": version,
                "elapsed_ms": elapsed_ms,
                "payload_size": payload_size,
            }
        )
    )


def _sample(operation: str, version: int) -> float:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "tools.benchmark_snapshot_loading",
            "--child",
            operation,
            "--version",
            str(version),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return float(json.loads(result.stdout)["elapsed_ms"])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--versions", type=int, nargs="+", default=(37, 30, 20))
    parser.add_argument("--iterations", type=int, default=3, help="Fresh-process samples per operation")
    parser.add_argument("--child", choices=("snapshot", "api"), help=argparse.SUPPRESS)
    parser.add_argument("--version", type=int, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.child:
        if args.version is None:
            parser.error("--version is required for a child sample")
        _measure_child(args.child, args.version)
        return 0
    if args.iterations < 1:
        parser.error("--iterations must be positive")

    available = EntityTypeAPI.bundled_versions().versions
    print(f"Python {platform.python_version()} · {platform.platform()}")
    print("Each sample uses a fresh process; timings exclude interpreter startup.")
    for version in args.versions:
        if version not in available:
            parser.error(f"v{version} is not bundled; available editions are {available}")
        snapshot_times = [_sample("snapshot", version) for _ in range(args.iterations)]
        api_times = [_sample("api", version) for _ in range(args.iterations)]
        print(
            f"v{version}: snapshot retrieval median {median(snapshot_times):.2f} ms "
            f"(range {min(snapshot_times):.2f}–{max(snapshot_times):.2f}); "
            f"API construction median {median(api_times):.2f} ms "
            f"(range {min(api_times):.2f}–{max(api_times):.2f})"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

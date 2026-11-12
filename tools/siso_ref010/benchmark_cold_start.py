"""Measure fresh-process loading stages, with separate timing and allocation passes."""

from __future__ import annotations

import argparse
import gc
import json
import platform
import subprocess
import sys
import tracemalloc
import xml.etree.ElementTree as ET
from collections.abc import Generator
from contextlib import contextmanager
from hashlib import sha256
from pathlib import Path
from statistics import median
from time import perf_counter
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from siso_ref010.models.standard import EntityTypeStandard


class Measurements:
    """Timings exclude the explicit collections used to measure retained allocations."""

    def __init__(self, trace: bool) -> None:
        self.trace = trace
        self.stages: dict[str, dict[str, float | None]] = {}
        if trace:
            tracemalloc.start()

    @contextmanager
    def stage(self, name: str) -> Generator[None]:
        gc.collect()
        if self.trace:
            tracemalloc.reset_peak()
        started = perf_counter()
        yield
        elapsed = (perf_counter() - started) * 1000
        gc.collect()
        row: dict[str, float | None] = {"elapsed_ms": elapsed, "process_peak_rss_mib": _peak_rss()}
        if self.trace:
            retained, peak = tracemalloc.get_traced_memory()
            row.update(retained_mib=retained / 2**20, peak_mib=peak / 2**20)
        self.stages[name] = row


def _peak_rss() -> float | None:
    if sys.platform == "win32":
        return None
    import resource

    unit = 1 if sys.platform == "darwin" else 1024
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * unit / 2**20


def _tree_model(root: ET.Element, digest: str, *, share: bool) -> EntityTypeStandard:
    """Reference tree projection for measurements only; inputs are verified bundled XML."""
    from siso_ref010.models.standard import ChangeRequest, EntityTypeStandard
    from siso_ref010.parsing.xml import _children, _ModelBuilder  # pyright: ignore[reportPrivateUsage]

    class UnsharedBuilder(_ModelBuilder):
        def _change_request(self, minimum: str | None, maximum: str | None) -> ChangeRequest:
            return ChangeRequest.model_validate({"minimum": minimum, "maximum": maximum})

    builder = _ModelBuilder() if share else UnsharedBuilder()
    tables = _children(root, "cet")
    table = next((row for row in tables if row.get("name") == "Entity Types"), None)
    if table is None:
        table = next((row for row in tables if row.get("name") == "Comprehensive Entity Types"), None)
    if table is None:
        table = next((row for row in tables if _children(row, "entity")), None)
    return EntityTypeStandard.model_validate(
        {
            "source": builder.source_info(root),
            "date": root.get("date") or None,
            "namespace": root.tag[1:].split("}", 1)[0] if root.tag.startswith("{") else None,
            "revisions": tuple(
                builder.source_info(row)
                for group in _children(root, "revisions")
                for row in _children(group, "revision")
            ),
            "copyright_text": "\n".join(
                "".join(node.itertext()).strip() for node in _children(root, "copyright")
            ),
            "enumerations": tuple(builder.enumeration(row) for row in _children(root, "enum")),
            "entity_table": builder.source_info(table) if table is not None else None,
            "entity_types": (
                tuple(builder.entity_branch(branch) for branch in _children(table, "entity"))
                if table is not None
                else ()
            ),
            "xml_parse_succeeded": True,
            "source_sha256": digest,
        }
    )


def measure_child(version: int, strategy: str, trace: bool) -> dict[str, Any]:
    """Run exactly one edition/strategy in a fresh interpreter."""
    measurements = Measurements(trace)
    with measurements.stage("imports"):
        import pydantic

        from siso_ref010.api import SisoRef010API
        from siso_ref010.catalog import ReferenceCatalog
        from siso_ref010.parsing.xml import EntityTypeXmlParser
        from siso_ref010.projection import build_catalog_data
        from siso_ref010.snapshots import read_snapshot_bytes

    with measurements.stage("decompression_and_verification"):
        payload = read_snapshot_bytes(version)
    if strategy == "stream":
        with measurements.stage("xml_and_source_models"):
            standard = EntityTypeXmlParser.from_bytes(payload)
    else:
        with measurements.stage("xml_parsing"):
            xml_string = payload.decode("utf-8-sig")
            root = ET.fromstring(xml_string)
        with measurements.stage("source_model_projection"):
            standard = _tree_model(root, sha256(payload).hexdigest(), share=strategy == "tree-shared")
        with measurements.stage("release_xml_tree"):
            del root, xml_string
    with measurements.stage("catalog_projection"):
        catalog = ReferenceCatalog._from_data(build_catalog_data(standard))  # pyright: ignore[reportPrivateUsage]
        api = SisoRef010API(catalog)
    with measurements.stage("first_lookup"):
        description = api.describe("1.2.225.7.8.7.1").description
    with measurements.stage("query_warmup"):
        warmup = api.warmup()
    if trace:
        tracemalloc.stop()
    return {
        "version": version,
        "strategy": strategy,
        "traced": trace,
        "pydantic": pydantic.__version__,
        "source_sha256": sha256(payload).hexdigest(),
        "model_sha256": sha256(standard.model_dump_json().encode()).hexdigest(),
        "first_description": description,
        "indexed_records": warmup.indexed_records,
        "stages": measurements.stages,
    }


def sample(version: int, strategy: str, trace: bool) -> dict[str, Any]:
    command = [sys.executable, "-m", __spec__.name if __spec__ else __name__, "--child", str(version)]
    command.extend(("--strategy", strategy))
    if trace:
        command.append("--trace")
    started = perf_counter()
    child = subprocess.run(command, check=True, capture_output=True, text=True)
    result: dict[str, Any] = json.loads(child.stdout)
    result["process_elapsed_ms"] = (perf_counter() - started) * 1000
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--versions", nargs="+", type=int)
    parser.add_argument("--iterations", type=int, default=3)
    parser.add_argument(
        "--strategies", nargs="+", choices=("stream", "tree", "tree-shared"), default=["stream"]
    )
    parser.add_argument("--output", type=Path, help="Write machine-readable raw samples")
    parser.add_argument("--child", type=int, help=argparse.SUPPRESS)
    parser.add_argument(
        "--strategy", choices=("stream", "tree", "tree-shared"), default="stream", help=argparse.SUPPRESS
    )
    parser.add_argument("--trace", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.child is not None:
        print(json.dumps(measure_child(args.child, args.strategy, args.trace)))
        return 0
    if args.iterations < 1:
        parser.error("--iterations must be positive")
    from siso_ref010.snapshots import available_snapshot_versions

    available = available_snapshot_versions()
    versions = args.versions or tuple(
        dict.fromkeys((available[0], available[len(available) // 2], available[-1]))
    )
    if any(version not in available for version in versions):
        parser.error(f"versions must be bundled: {available}")
    samples: list[dict[str, Any]] = []
    print("Fresh processes; separate untraced timing and tracemalloc allocation passes.", flush=True)
    for version in versions:
        for strategy in args.strategies:
            timed = [sample(version, strategy, False) for _ in range(args.iterations)]
            traced = [sample(version, strategy, True) for _ in range(args.iterations)]
            samples.extend((*timed, *traced))
            for stage in timed[0]["stages"]:
                times = [row["stages"][stage]["elapsed_ms"] for row in timed]
                retained = [row["stages"][stage]["retained_mib"] for row in traced]
                peaks = [row["stages"][stage]["peak_mib"] for row in traced]
                print(
                    f"v{version} {strategy} {stage}: {median(times):.2f} ms "
                    f"({min(times):.2f}–{max(times):.2f}); "
                    f"retained {median(retained):.2f} MiB; peak {median(peaks):.2f} MiB",
                    flush=True,
                )
    if args.output:
        args.output.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "python": sys.version,
                    "platform": platform.platform(),
                    "samples": samples,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

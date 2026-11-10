"""Exercise a built wheel or source distribution in a fresh offline environment.

Run from the repository root after building and downloading dependencies:
    python -m tools.siso_ref010.check_installed dist --kind wheel --wheelhouse .wheelhouse
    python -m tools.siso_ref010.check_installed dist --kind sdist --wheelhouse .wheelhouse
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import tarfile
import tempfile
import venv
from pathlib import Path, PurePosixPath
from zipfile import ZipFile


def _check_distribution_files(members: tuple[str, ...], *, source_distribution: bool) -> None:
    required_suffixes = (
        "siso_ref010/py.typed",
        "data/SISO-REF-010.xsd",
        "data/standards/editions.xz",
        "data/standards/index.json",
        "data/standards/PROVENANCE.json",
        "data/standards/SHA256SUMS.txt",
    )
    for suffix in required_suffixes:
        assert any(name.endswith(suffix) for name in members), f"Distribution is missing {suffix}"
    root_names = {PurePosixPath(name).name for name in members}
    assert "LICENSE" in root_names, "MIT code license missing from distribution"
    assert "SISO-DATA-NOTICE.txt" in root_names, "SISO data notice missing from distribution"
    raw_xml = tuple(
        name
        for name in members
        if "/data/standards/" in f"/{name}" and re.fullmatch(r"v\d+\.xml", PurePosixPath(name).name)
    )
    assert not raw_xml, f"Uncompressed edition XML leaked into distribution: {raw_xml}"
    if source_distribution:
        excluded_developer_files = (
            "tools/siso_ref010/build_diff_reports.py",
            "tools/siso_ref010/package_diff_reports.py",
            "tools/repo_hygiene/check_markdown.py",
            "tools/repo_hygiene/check_repository_hygiene.py",
            "tools/repo_hygiene/repository-hygiene-baseline.json",
            "tests/test_repository_hygiene.py",
        )
        included = tuple(
            name for name in members if any(name.endswith(path) for path in excluded_developer_files)
        )
        assert not included, f"Repository-only developer files leaked into source distribution: {included}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("distribution", type=Path, help="Built distribution file or its output directory")
    parser.add_argument("--kind", choices=("wheel", "sdist"), help="Select an artifact from a directory")
    parser.add_argument("--wheelhouse", type=Path, required=True)
    args = parser.parse_args()
    distribution = args.distribution.resolve()
    wheelhouse = args.wheelhouse.resolve()
    if distribution.is_dir():
        if args.kind is None:
            parser.error("--kind is required when distribution is a directory")
        pattern = "siso_ref010-*.whl" if args.kind == "wheel" else "siso_ref010-*.tar.gz"
        candidates = tuple(distribution.glob(pattern))
        if len(candidates) != 1:
            parser.error(f"Expected one {args.kind} matching {pattern}, found {len(candidates)}")
        distribution = candidates[0].resolve()
    elif not distribution.is_file():
        parser.error(f"Distribution not found: {distribution}")
    if not wheelhouse.is_dir():
        parser.error(f"Wheelhouse not found: {wheelhouse}")

    if distribution.name.endswith(".tar.gz"):
        if args.kind not in (None, "sdist"):
            parser.error("--kind wheel does not match a source distribution file")
        with tarfile.open(distribution, "r:gz") as archive:
            members = tuple(member.name for member in archive.getmembers() if member.isfile())
        _check_distribution_files(members, source_distribution=True)
    elif distribution.suffix == ".whl":
        if args.kind not in (None, "wheel"):
            parser.error("--kind sdist does not match a source distribution file")
        with ZipFile(distribution) as archive:
            _check_distribution_files(tuple(archive.namelist()), source_distribution=False)
    else:
        parser.error("Distribution must be a .whl or .tar.gz file")

    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    environment.pop("PYTHONHOME", None)
    with tempfile.TemporaryDirectory(prefix="siso-ref010-consumer-") as directory:
        root = Path(directory)
        venv.EnvBuilder(with_pip=True).create(root / "venv")
        binary = root / "venv" / ("Scripts" if os.name == "nt" else "bin")
        environment["PATH"] = str(binary)
        python = binary / ("python.exe" if os.name == "nt" else "python")
        console = binary / ("siso-ref010.exe" if os.name == "nt" else "siso-ref010")

        def run(*command: str, code: int = 0) -> subprocess.CompletedProcess[str]:
            result = subprocess.run(command, cwd=root, env=environment, text=True, capture_output=True)
            if result.returncode != code:
                raise AssertionError(f"Unexpected exit {result.returncode}: {result.stdout}\n{result.stderr}")
            return result

        run(
            str(python),
            "-I",
            "-m",
            "pip",
            "install",
            "--no-index",
            "--find-links",
            str(wheelhouse),
            str(distribution),
        )
        consumer_script = Path(__file__).with_name("installed_consumer_smoke.py")
        consumer = run(str(python), "-I", str(consumer_script))
        smoke = json.loads(consumer.stdout)
        versions = tuple(smoke["versions"])
        default_version = smoke["default_version"]
        assert versions and default_version == max(versions)

        cli_versions = json.loads(run(str(console), "versions", "--json").stdout)["result"]
        assert tuple(cli_versions["versions"]) == versions
        assert cli_versions["default_version"] == default_version
        cli_info = json.loads(run(str(console), "info", "--json").stdout)["result"]
        assert cli_info["data_version"] == smoke["data_version"]
        cli_describe = json.loads(run(str(console), "describe", smoke["entity"], "--json").stdout)["result"]
        assert cli_describe == smoke["description"]
        cli_tables = json.loads(run(str(console), "inspect", "tables", "--json").stdout)["result"]
        assert cli_tables["total"] > 0

        from_version, to_version = versions[0], versions[-1]
        compare = json.loads(
            run(str(console), "compare", str(from_version), str(to_version), "--json").stdout
        )["result"]
        assert compare["report_type"] == "summary"
        cli_report = json.loads(run(str(console), "inspect", "report", "--json").stdout)["result"]
        assert cli_report == smoke["report"]
        cli_markdown = run(str(console), "inspect", "report", "--format", "markdown")
        assert cli_markdown.stdout == smoke["report_markdown"]

        diagnostics = json.loads(
            run(str(console), "inspect", "diagnostics", "--details", "--limit", "1", "--json").stdout
        )["result"]
        assert diagnostics["returned"] <= 1
        assert diagnostics["total"] >= diagnostics["returned"]

        exported_xml = root / f"edition-v{from_version}.xml"
        run(str(console), "dump", str(from_version), "--output", str(exported_xml))
        assert (
            hashlib.sha256(exported_xml.read_bytes()).hexdigest() == smoke["source_sha256"][str(from_version)]
        )

        module_versions = json.loads(
            run(str(python), "-I", "-m", "siso_ref010", "versions", "--json").stdout
        )["result"]
        assert module_versions == cli_versions
        failure = run(str(console), "describe", "bad", "--json", code=2)
        assert failure.stdout == ""
        assert json.loads(failure.stderr)["error"]["type"] == "ValueError"
        help_result = run(str(console), "--help")
        assert "Python API" in help_result.stdout and "--json" in help_result.stdout

        print(
            "Installed consumer checks passed offline: dynamic editions, index-only discovery, "
            "API/CLI parity, source hashes, and error handling."
        )


if __name__ == "__main__":
    main()

"""Run the full local gate or the narrower profiles used by hosted CI."""

from __future__ import annotations

import argparse
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from tempfile import TemporaryDirectory

from packaging.version import Version

WHEELHOUSE_REQUIREMENTS = (
    "pydantic>=2.7,<3",
    "setuptools>=77",
    "setuptools-scm>=10,<11",
)


def _python_module(module: str, *arguments: str) -> tuple[str, ...]:
    return (sys.executable, "-m", module, *arguments)


def _run(command: Sequence[str]) -> int:
    print(f"$ {' '.join(command)}", flush=True)
    try:
        return subprocess.run(command, check=False).returncode
    except OSError as error:
        print(f"Could not start {' '.join(command)}: {error}", file=sys.stderr)
        return 1


def _run_commands(commands: Sequence[Sequence[str]]) -> int:
    for command in commands:
        result = _run(command)
        if result:
            return result
    return 0


def _index_check() -> tuple[str, ...]:
    return ("git", "diff", "--exit-code", "--", "src/siso_ref010/data/standards/index.json")


def _edition_endpoints() -> tuple[int, ...]:
    from siso_ref010 import SisoRef010API

    versions = SisoRef010API.bundled_versions().versions
    if not versions:
        raise ValueError("No bundled editions are available for endpoint checks")
    return tuple(dict.fromkeys((versions[0], versions[-1])))


def _quality_commands(*, full: bool) -> tuple[tuple[str, ...], ...]:
    if full:
        data_checks = (
            _python_module("tools.siso_ref010.check_bundled_standards"),
            _python_module("tools.siso_ref010.check_standards_xsd"),
        )
    else:
        endpoints = tuple(str(version) for version in _edition_endpoints())
        data_checks = (
            _python_module("tools.siso_ref010.check_bundled_edges"),
            _python_module("tools.siso_ref010.check_standards_xsd", "--versions", *endpoints),
        )
    commands = (
        _index_check(),
        _python_module("tools.repo_hygiene.check_repository_hygiene"),
        *data_checks,
        _python_module("pre_commit", "run", "--all-files"),
        _python_module("ruff", "check", "."),
        _python_module("ruff", "check", "tests", "--select", "ANN"),
        _python_module("ruff", "format", "--check", "."),
        _python_module("pyright"),
        _python_module("pyright", "--project", "pyright-tests.json"),
    )
    if full:
        return (
            *commands,
            _python_module(
                "pytest",
                "-q",
                "--cov=siso_ref010",
                "--cov-report=term-missing",
                "--cov-fail-under=98",
            ),
        )
    return commands


def _test_commands(*, full: bool) -> tuple[tuple[str, ...], ...]:
    if full:
        return ()
    return (
        _index_check(),
        _python_module("tools.siso_ref010.check_bundled_edges"),
        _python_module("pytest", "-q", "-m", "not all_editions"),
    )


def _package_checks(*, verify_wheel: bool, verify_sdist: bool, expected_version: str | None = None) -> int:
    with TemporaryDirectory(prefix="siso-ref010-ci-") as temporary_directory:
        root = Path(temporary_directory)
        distribution_directory = root / "dist"
        wheelhouse = root / "wheelhouse"
        distribution_directory.mkdir()
        wheelhouse.mkdir()

        result = _run(_python_module("build", "--outdir", str(distribution_directory)))
        if result:
            return result

        wheels = tuple(sorted(distribution_directory.glob("siso_ref010-*.whl")))
        sdists = tuple(sorted(distribution_directory.glob("siso_ref010-*.tar.gz")))
        if len(wheels) != 1 or len(sdists) != 1:
            print(
                f"Expected one wheel and one sdist; found {len(wheels)} wheels and {len(sdists)} sdists",
                file=sys.stderr,
            )
            return 1

        result = _run(_python_module("twine", "check", "--strict", str(wheels[0]), str(sdists[0])))
        if result:
            return result

        if verify_wheel or verify_sdist:
            result = _run(
                _python_module(
                    "pip",
                    "download",
                    "--only-binary=:all:",
                    "--dest",
                    str(wheelhouse),
                    *WHEELHOUSE_REQUIREMENTS,
                )
            )
            if result:
                return result

        expected_version_args = () if expected_version is None else ("--expected-version", expected_version)

        if verify_wheel:
            result = _run(
                _python_module(
                    "tools.siso_ref010.check_installed",
                    str(distribution_directory),
                    "--kind",
                    "wheel",
                    "--wheelhouse",
                    str(wheelhouse),
                    *expected_version_args,
                )
            )
            if result:
                return result
        if verify_sdist:
            result = _run(
                _python_module(
                    "tools.siso_ref010.check_installed",
                    str(distribution_directory),
                    "--kind",
                    "sdist",
                    "--wheelhouse",
                    str(wheelhouse),
                    *expected_version_args,
                )
            )
            if result:
                return result
    return 0


def _release_tag_matches_version(tags: Sequence[str], expected_version: str) -> bool:
    """Require an exact release tag at HEAD before building release artifacts."""
    Version(expected_version)
    return expected_version in tags or f"v{expected_version}" in tags


def _release_worktree_is_clean(status: str) -> bool:
    """Do not build release artifacts from uncommitted or untracked files."""
    return not status.strip()


def main(argv: Sequence[str] | None = None) -> int:
    """Run full local validation or the edge-only hosted CI profiles."""

    parser = argparse.ArgumentParser(
        description=("Run the full local gate, or the edge-only test and quality profiles used by hosted CI.")
    )
    parser.add_argument(
        "profile",
        nargs="?",
        choices=("full", "edge", "quality", "release"),
        default="full",
        help=(
            "default: full validation; CI uses edge and quality; release also checks tag and artifact version"
        ),
    )
    parser.add_argument(
        "--release-version",
        help="exact PEP 440 version to verify in artifacts (required by the release profile)",
    )
    args = parser.parse_args(argv)

    if args.profile == "full":
        result = _run_commands(_quality_commands(full=True))
        if result:
            return result
        return _package_checks(verify_wheel=True, verify_sdist=True)
    if args.profile == "edge":
        result = _run_commands(_test_commands(full=False))
        if result:
            return result
        return _package_checks(verify_wheel=False, verify_sdist=False)
    if args.profile == "quality":
        return _run_commands(_quality_commands(full=False))
    if args.profile == "release":
        if args.release_version is None:
            parser.error("the release profile requires --release-version")
        try:
            Version(args.release_version)
        except ValueError as error:
            parser.error(f"invalid --release-version: {error}")
        try:
            tags = subprocess.run(
                ("git", "tag", "--points-at", "HEAD"),
                check=False,
                capture_output=True,
                text=True,
            )
        except OSError as error:
            print(f"Could not inspect release tags: {error}", file=sys.stderr)
            return 1
        if tags.returncode:
            print("Could not inspect release tags at HEAD", file=sys.stderr)
            return tags.returncode
        if not _release_tag_matches_version(tags.stdout.splitlines(), args.release_version):
            print(
                f"HEAD must have tag {args.release_version!r} or {('v' + args.release_version)!r}",
                file=sys.stderr,
            )
            return 1
        try:
            status = subprocess.run(
                ("git", "status", "--porcelain"),
                check=False,
                capture_output=True,
                text=True,
            )
        except OSError as error:
            print(f"Could not inspect the working tree: {error}", file=sys.stderr)
            return 1
        if status.returncode:
            print("Could not inspect the working tree", file=sys.stderr)
            return status.returncode
        if not _release_worktree_is_clean(status.stdout):
            print("The release profile requires a clean working tree", file=sys.stderr)
            return 1
        result = _run_commands(_quality_commands(full=True))
        if result:
            return result
        return _package_checks(
            verify_wheel=True,
            verify_sdist=True,
            expected_version=args.release_version,
        )
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

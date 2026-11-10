"""Run Markdown lint and repository-link checks locally and in CI."""

from __future__ import annotations

import argparse
import subprocess
import sys
from collections.abc import Sequence


def commands(*, python: str = sys.executable, fix: bool = False) -> tuple[tuple[str, ...], ...]:
    """Return the ordered Markdown checks, optionally applying safe fixes first."""

    # rumdl is distributed as a native CLI; Python's rumdl.__main__ is a
    # development shim and cannot locate the installed binary.
    rumdl = ("rumdl",)
    mdrepo = (python, "-m", "mdrepo")
    if fix:
        return (
            (*rumdl, "check", "--fix", "."),
            (*mdrepo, "fix", "."),
            (*rumdl, "check", "."),
            (*mdrepo, "check", "."),
        )
    return (*rumdl, "check", "."), (*mdrepo, "check", ".")


def main(argv: Sequence[str] | None = None) -> int:
    """Run Markdown checks from the repository root, stopping at the first failure."""

    parser = argparse.ArgumentParser(
        description="Check Markdown formatting and repository-aware documentation links.",
        epilog="Checks are read-only unless --fix is specified.",
    )
    parser.add_argument("--fix", action="store_true", help="apply safe fixes, then recheck")
    args = parser.parse_args(argv)

    for command in commands(fix=args.fix):
        print(f"$ {' '.join(command)}", flush=True)
        try:
            completed = subprocess.run(command, check=False)
        except OSError as error:
            print(
                f"Could not start {' '.join(command)}; activate the development environment "
                f"and install the dev dependencies: {error}",
                file=sys.stderr,
            )
            return 1
        if completed.returncode:
            return completed.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

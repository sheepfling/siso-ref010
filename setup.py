"""Generate the compressed standards payload during source builds."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

from setuptools import setup
from setuptools.command.build_py import build_py
from setuptools.command.editable_wheel import editable_wheel
from setuptools.command.sdist import sdist

DATA = Path("src/siso_ref010/data/standards")
REPOSITORY_FILES = "https://github.com/sheepfling/siso-ref010/blob/main/"


def package_readme() -> str:
    """Keep local README links, but make inline file links usable on package indexes."""
    readme = Path("README.md").read_text(encoding="utf-8")
    return re.sub(
        r"\]\((?![a-zA-Z][a-zA-Z0-9+.-]*:|//|#)([^)\s]+)\)",
        lambda match: f"]({REPOSITORY_FILES}{match.group(1)})",
        readme,
    )


def prepare_standards_pack() -> None:
    """Pack tracked source XMLs or validate the pack already stored in an sdist."""
    if tuple(DATA.glob("v*.xml")):
        current = subprocess.run(
            [sys.executable, "-m", "tools.siso_ref010.build_standards_pack", "--check"],
            capture_output=True,
            text=True,
        )
        if current.returncode == 0:
            return
        subprocess.run([sys.executable, "-m", "tools.siso_ref010.build_standards_pack"], check=True)
        return

    try:
        index = json.loads((DATA / "index.json").read_text(encoding="utf-8"))
        pack = (DATA / "editions.xz").read_bytes()
    except (OSError, ValueError) as error:
        raise RuntimeError(
            "Source build is missing both standards XML sources and the packed bundle"
        ) from error
    if index.get("pack_size") != len(pack) or index.get("pack_sha256") != hashlib.sha256(pack).hexdigest():
        raise RuntimeError("Source distribution contains an inconsistent standards bundle")


class BuildPyWithStandards(build_py):
    def run(self) -> None:
        prepare_standards_pack()
        super().run()


class SdistWithStandards(sdist):
    def run(self) -> None:
        prepare_standards_pack()
        super().run()


class EditableWheelWithStandards(editable_wheel):
    def run(self) -> None:
        prepare_standards_pack()
        super().run()


setup(
    long_description=package_readme(),
    long_description_content_type="text/markdown",
    cmdclass={
        "build_py": BuildPyWithStandards,
        "sdist": SdistWithStandards,
        "editable_wheel": EditableWheelWithStandards,
    },
)

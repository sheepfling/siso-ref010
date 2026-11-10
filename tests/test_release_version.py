"""Release artifacts must identify one exact version."""

from __future__ import annotations

from pathlib import Path

import pytest

from tools.ci import _release_tag_matches_version, _release_worktree_is_clean
from tools.siso_ref010.check_installed import _check_distribution_version


@pytest.mark.parametrize(
    "filename",
    ["siso_ref010-0.1.0a0-py3-none-any.whl", "siso_ref010-0.1.0a0.tar.gz"],
)
def test_release_artifact_filename_matches_expected_version(filename: str, tmp_path: Path) -> None:
    distribution = tmp_path / filename

    _check_distribution_version(distribution, "0.1.0a0")


def test_release_artifact_filename_rejects_setuptools_scm_development_version(tmp_path: Path) -> None:
    distribution = tmp_path / "siso_ref010-0.1.dev1+g1234567-py3-none-any.whl"

    with pytest.raises(AssertionError, match="expected 0.1.0a0"):
        _check_distribution_version(distribution, "0.1.0a0")


@pytest.mark.parametrize("tag", ["v0.1.0a0", "0.1.0a0"])
def test_release_tag_must_name_expected_version(tag: str) -> None:
    assert _release_tag_matches_version((tag,), "0.1.0a0")


def test_release_tag_rejects_different_or_development_version() -> None:
    assert not _release_tag_matches_version(("v0.1.0a1",), "0.1.0a0")
    assert not _release_tag_matches_version(("v0.1.0a0.dev1",), "0.1.0a0")


def test_release_profile_requires_a_clean_worktree() -> None:
    assert _release_worktree_is_clean("")
    assert _release_worktree_is_clean("\n")
    assert not _release_worktree_is_clean(" M src/siso_ref010/api.py\n")
    assert not _release_worktree_is_clean("?? untracked.txt\n")


def test_source_distribution_policy_excludes_repository_development_files() -> None:
    from tools.siso_ref010.check_installed import _check_distribution_files

    base = "siso_ref010-0.1.0a0/"
    package_files = (
        "src/siso_ref010/py.typed",
        "src/siso_ref010/data/SISO-REF-010.xsd",
        "src/siso_ref010/data/standards/editions.xz",
        "src/siso_ref010/data/standards/index.json",
        "src/siso_ref010/data/standards/PROVENANCE.json",
        "src/siso_ref010/data/standards/SHA256SUMS.txt",
        "LICENSE",
        "SISO-DATA-NOTICE.txt",
    )
    _check_distribution_files(tuple(base + item for item in package_files), source_distribution=True)

    with pytest.raises(AssertionError, match="repository tools"):
        _check_distribution_files(
            (
                *tuple(base + item for item in package_files),
                base + "tools/siso_ref010/check_bundled_standards.py",
            ),
            source_distribution=True,
        )

    with pytest.raises(AssertionError, match="CI configuration"):
        _check_distribution_files(
            (
                *tuple(base + item for item in package_files),
                base + ".github/workflows/ci.yml",
            ),
            source_distribution=True,
        )

    with pytest.raises(AssertionError, match="contains tests"):
        _check_distribution_files(
            (*tuple(base + item for item in package_files), base + "tests/test_api.py"),
            source_distribution=True,
        )

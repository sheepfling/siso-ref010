"""Verify package-index links without running the setuptools build hooks."""

from __future__ import annotations

import ast
import re
from collections.abc import Callable
from pathlib import Path
from typing import cast

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _package_readme() -> str:
    # Execute the actual pure helper, not setup() or its command classes. Tests
    # should not require the build backend in the runtime test environment.
    tree = ast.parse((ROOT / "setup.py").read_text(encoding="utf-8"))
    nodes: list[ast.stmt] = [
        node
        for node in tree.body
        if (isinstance(node, ast.FunctionDef) and node.name == "package_readme")
        or (
            isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id == "REPOSITORY_FILES" for target in node.targets
            )
        )
    ]
    namespace: dict[str, object] = {"Path": Path, "re": re}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "setup.py readme helper", "exec"), namespace)
    return cast(Callable[[], str], namespace["package_readme"])()


def test_package_description_resolves_local_readme_links(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(ROOT)
    readme_path = ROOT / "README.md"
    readme = readme_path.read_text(encoding="utf-8")
    description = _package_readme()
    targets = re.findall(r"\]\(([^)]+)\)", readme)
    assert targets
    for target in targets:
        if re.match(r"[a-zA-Z][a-zA-Z0-9+.-]*:|//|#", target):
            assert f"]({target})" in description
            continue
        assert (ROOT / target.split("#", 1)[0]).is_file()
        assert f"](https://github.com/sheepfling/siso-ref010/blob/main/{target})" in description
    assert readme_path.read_text(encoding="utf-8") == readme
    assert "```python\n" in description


def test_package_description_preserves_external_and_fragment_links(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    readme = (
        "[Guide](docs/api.md#queries) [Website](https://example.com/page) "
        "[Mail](mailto:example@example.com) [Section](#quick-start) "
        "[Protocol-relative](//example.com/page)\n"
    )
    (tmp_path / "README.md").write_text(readme, encoding="utf-8")
    assert _package_readme() == readme.replace(
        "](docs/api.md#queries)",
        "](https://github.com/sheepfling/siso-ref010/blob/main/docs/api.md#queries)",
    )

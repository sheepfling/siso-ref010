"""Keep the README examples aligned with the public package entry points."""

import ast
import re
from pathlib import Path

import siso_ref010


def test_readme_python_examples_import_public_names() -> None:
    readme = (Path(__file__).resolve().parents[1] / "README.md").read_text(encoding="utf-8")
    examples = re.findall(r"```python\n(.*?)\n```", readme, flags=re.DOTALL)
    assert examples
    imported_names = []
    for example in examples:
        for node in ast.walk(ast.parse(example)):
            if isinstance(node, ast.ImportFrom) and node.module == "siso_ref010":
                imported_names.extend(alias.name for alias in node.names)

    assert imported_names
    for name in imported_names:
        assert name in siso_ref010.__all__, f"README imports non-public name: {name}"
        assert hasattr(siso_ref010, name), f"README imports missing name: {name}"

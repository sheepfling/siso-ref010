"""The shipped application is native Python and imports only the standard library."""

import ast
import sys
from pathlib import Path

import pytest

SOURCE = Path(__file__).parents[1] / "src/siso_entity_type"


@pytest.mark.parametrize("path", sorted(SOURCE.glob("*.py")), ids=lambda path: path.name)
def test_runtime_imports_only_standard_library(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [alias.name.split(".")[0] for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names = [node.module.split(".")[0]]
        else:
            continue
        assert set(names) <= sys.stdlib_module_names | {"siso_entity_type"}
        assert not set(names) & {"subprocess", "ctypes"}, (
            "Runtime must not launch or bridge a foreign runtime"
        )

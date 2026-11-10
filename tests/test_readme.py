"""Keep the README examples aligned with the public package entry points."""

import ast
import re
from pathlib import Path

import siso_ref010

PUBLIC_API = {
    "__version__",
    "BundledEdition",
    "BundledStandards",
    "CategoryCode",
    "Collection",
    "CountryCode",
    "DomainCode",
    "EntityFieldCode",
    "EntityKey",
    "EntityType",
    "EntityTypePrefix",
    "ExtraCode",
    "KindCode",
    "SisoRef010API",
    "SisoRef010Error",
    "SisoRef010IndexError",
    "SisoRef010TypeError",
    "SisoRef010ValueError",
    "SpecificCode",
    "SubcategoryCode",
    "decode_key",
    "encode_entity",
}


def _python_examples() -> tuple[str, ...]:
    readme = (Path(__file__).resolve().parents[1] / "README.md").read_text(encoding="utf-8")
    return tuple(re.findall(r"```python\n(.*?)\n```", readme, flags=re.DOTALL))


def test_top_level_exports_are_the_supported_api() -> None:
    assert set(siso_ref010.__all__) == PUBLIC_API
    assert all(hasattr(siso_ref010, name) for name in PUBLIC_API)
    assert not hasattr(siso_ref010, "ReferenceCatalog")
    assert not hasattr(siso_ref010, "EditionDiff")
    assert not hasattr(siso_ref010, "EntityTypeXmlParser")


def test_readme_python_examples_import_public_names() -> None:
    examples = _python_examples()
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


def test_readme_python_examples_execute() -> None:
    for index, example in enumerate(_python_examples(), start=1):
        namespace: dict[str, object] = {"__name__": f"readme_example_{index}"}
        code = compile(ast.parse(example), f"README.md Python example {index}", "exec")
        exec(code, namespace)

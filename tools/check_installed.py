"""Exercise the wheel as a real consumer, offline and outside the source tree.

Run after building: python tools/check_installed.py dist/dis_entity_types-0.2.0-py3-none-any.whl
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
import venv
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wheel", type=Path)
    wheel = parser.parse_args().wheel.resolve()
    if not wheel.is_file():
        parser.error(f"Wheel not found: {wheel}")
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    environment.pop("PYTHONHOME", None)
    with tempfile.TemporaryDirectory(prefix="siso-consumer-") as directory:
        root = Path(directory)
        venv.EnvBuilder(with_pip=True).create(root / "venv")
        binary = root / "venv" / ("Scripts" if os.name == "nt" else "bin")
        # Consumer execution has only the fresh Python environment on PATH.
        # In particular, no system Node/npm executable can satisfy a dependency.
        environment["PATH"] = str(binary)
        python = binary / ("python.exe" if os.name == "nt" else "python")
        console = binary / ("siso-entity-type.exe" if os.name == "nt" else "siso-entity-type")

        def run(*arguments: str, code: int = 0) -> subprocess.CompletedProcess[str]:
            result = subprocess.run(arguments, cwd=root, env=environment, text=True, capture_output=True)
            if result.returncode != code:
                raise AssertionError(f"Unexpected exit {result.returncode}: {result.stdout}\n{result.stderr}")
            return result

        run(str(python), "-I", "-m", "pip", "install", "--no-index", "--no-deps", str(wheel))
        imported = run(str(python), "-I", "-c", "import siso_entity_type; import siso_entity_type.api")
        assert imported.stdout == imported.stderr == ""
        api = run(
            str(python),
            "-I",
            "-c",
            """
import json
import sys
from importlib.resources import files
from siso_entity_type.api import EntityTypeAPI, decode_key, encode_entity
from siso_entity_type import Convert, ExtraElement, SpecificElement, SisoEnumsParser
import siso_entity_type.gui
assert "tkinter" not in sys.modules
parser = SisoEnumsParser.from_string("<ebv/>")
parser.initialize_specific(1, 2, 225, 1, 1, SpecificElement(1, "Variant", ExtraElement(2, "Equipment")), "")
assert parser.subcategory_count == 2
assert callable(Convert.to_siso_xml_types)
api = EntityTypeAPI()
item = api.describe("1.3.153.6.4.2.0")
assert item.description == "F803 Tromp"
assert api.info()["counts"]["subcategories"] == 24637
assert files("siso_entity_type").joinpath("py.typed").is_file()
assert decode_key(encode_entity(item.entity).key).entity == item.entity
print(json.dumps(item.to_dict()))
""",
        )
        console_result = run(str(console), "describe", "1.3.153.6.4.2.0", "--json")
        named_console = binary / ("dis-entity-types.exe" if os.name == "nt" else "dis-entity-types")
        named_result = run(str(named_console), "describe", "1.3.153.6.4.2.0", "--json")
        assert named_result.stdout == console_result.stdout
        assert named_result.stderr == ""
        assert console_result.stderr == ""
        assert json.loads(console_result.stdout)["result"] == json.loads(api.stdout)
        module = run(str(python), "-I", "-m", "siso_entity_type", "search", "F803", "--json")
        assert json.loads(module.stdout)["result"]["hits"][0]["description"] == "F803 Tromp"
        failure = run(str(console), "describe", "bad", "--json", code=2)
        assert failure.stdout == ""
        assert json.loads(failure.stderr)["error"]["type"] == "ValueError"
        help_result = run(str(console), "--help")
        assert "Python API" in help_result.stdout
        assert "--json" in help_result.stdout
        print(
            "Installed consumer checks passed: API, data, types, console/module CLI, JSON parity and errors."
        )


if __name__ == "__main__":
    main()

"""Exercise an installed wheel or source distribution in a fresh environment.

Run from the repository root after building and downloading dependencies:
    python -m tools.check_installed dist/siso_ref010-0.0.1-py3-none-any.whl \
        --wheelhouse .wheelhouse
    python -m tools.check_installed dist/siso_ref010-0.0.1.tar.gz \
        --wheelhouse .wheelhouse
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import tarfile
import tempfile
import venv
from pathlib import Path, PurePosixPath
from zipfile import ZipFile


def _check_standard_files(members: tuple[str, ...]) -> None:
    assert any(name.endswith("data/standards/editions.xz") for name in members)
    root_names = {PurePosixPath(name).name for name in members}
    assert "LICENSE" in root_names, "Apache-2.0 code license missing from distribution"
    assert "SISO-DATA-NOTICE.txt" in root_names, "SISO data notice missing from distribution"
    raw_xml = tuple(
        name
        for name in members
        if "/data/standards/" in f"/{name}" and re.fullmatch(r"v\d+\.xml", PurePosixPath(name).name)
    )
    assert not raw_xml, f"Uncompressed edition XML leaked into distribution: {raw_xml}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("distribution", type=Path, help="Built wheel or source distribution")
    parser.add_argument("--wheelhouse", type=Path, required=True)
    args = parser.parse_args()
    distribution = args.distribution.resolve()
    wheelhouse = args.wheelhouse.resolve()
    if not distribution.is_file():
        parser.error(f"Distribution not found: {distribution}")
    if not wheelhouse.is_dir():
        parser.error(f"Wheelhouse not found: {wheelhouse}")
    if distribution.name.endswith(".tar.gz"):
        with tarfile.open(distribution, "r:gz") as archive:
            members = tuple(member.name for member in archive.getmembers() if member.isfile())
        _check_standard_files(members)
    elif distribution.suffix == ".whl":
        with ZipFile(distribution) as archive:
            _check_standard_files(tuple(archive.namelist()))
    else:
        parser.error("Distribution must be a .whl or .tar.gz file")
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    environment.pop("PYTHONHOME", None)
    with tempfile.TemporaryDirectory(prefix="siso-ref010-consumer-") as directory:
        root = Path(directory)
        venv.EnvBuilder(with_pip=True).create(root / "venv")
        binary = root / "venv" / ("Scripts" if os.name == "nt" else "bin")
        # The consumer has only its fresh Python environment on PATH.
        environment["PATH"] = str(binary)
        python = binary / ("python.exe" if os.name == "nt" else "python")
        console = binary / ("siso-ref010.exe" if os.name == "nt" else "siso-ref010")

        def run(*arguments: str, code: int = 0) -> subprocess.CompletedProcess[str]:
            result = subprocess.run(arguments, cwd=root, env=environment, text=True, capture_output=True)
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
        imported = run(str(python), "-I", "-c", "import siso_ref010; import siso_ref010.api")
        assert imported.stdout == imported.stderr == ""
        api = run(
            str(python),
            "-I",
            "-c",
            """
import json
from importlib.resources import files
from siso_ref010.api import EntityTypeAPI, decode_key, encode_entity
from siso_ref010 import BUNDLED_STANDARD_VERSIONS, render_json, render_markdown
standards = files("siso_ref010").joinpath("data/standards")
registry = json.loads(standards.joinpath("PROVENANCE.json").read_text())
assert len(registry["entries"]) == 18
source_fields = {"provider", "repository", "reference", "path", "url", "verification"}
assert all(set(row["primary_source"]) == source_fields for row in registry["entries"])
assert all(row["bundle_file"] == "data/standards/editions.xz" for row in registry["entries"])
assert sum(len(row["verified_mirrors"]) for row in registry["entries"]) == 1
assert all(isinstance(row["source_history"], list) for row in registry["entries"])
assert len(registry["artifacts"]) == 1
assert registry["artifacts"][0]["file"] == "data/SISO-REF-010.xsd"
assert not standards.joinpath("SOURCES.json").is_file()
api = EntityTypeAPI()
item = api.describe("1.3.153.6.4.2.0")
assert item.description == "F803 Tromp"
prefix = api.resolve_entity("1.3.153.6.4.2")
assert prefix.status.value == "partial" and prefix.matched_depth == 6
assert prefix.human_outcome == "Resolved prefix"
assert prefix.not_supplied_components == ("extra",)
report = api.inspector.report()
assert report.identity.source_evidence_registry == "data/standards/PROVENANCE.json"
assert all(check.status.value == "checked" for check in report.validation.semantic_checks)
assert report.identity_diagnostics.repeated_uuid_occurrences == 22
assert report.identity_diagnostics.repeated_identity_key_occurrences == 16
assert report.identity_diagnostics.source_record_reuse_groups == 8
assert all(not hasattr(example, "python_expression") for example in report.examples)
for example in report.examples:
    if example.kind.value == "enumeration_table":
        reproduced = api.inspector.enumeration_table(int(example.query))
    elif example.kind.value == "enumeration_value":
        table_uid, value = (int(part.strip()) for part in example.query.split(",", maxsplit=1))
        reproduced = api.inspector.resolve_enumeration_value(table_uid, value)
    else:
        reproduced = api.resolve_entity(example.query)
    assert reproduced == example.result
report_json = json.loads(render_json(report))
assert report_json == report.model_dump(mode="json", by_alias=True)
report_markdown = render_markdown(report)
assert "Executable Python:" not in report_markdown
assert "```python" not in report_markdown
for boundary in (64, 127):
    resolved = api.inspector.resolve_enumeration_value(3, boundary)
    assert resolved.status.value == "range"
    assert (resolved.matches[0].value_min, resolved.matches[0].value_max) == (64, 127)
assert api.inspector.resolve_enumeration_value(3, 1_000_000).status.value == "unknown"
assert api.info().counts.subcategories == 25473
assert files("siso_ref010").joinpath("py.typed").is_file()
assert files("siso_ref010").joinpath("data/standards/editions.xz").is_file()
assert files("siso_ref010").joinpath("data/standards/index.json").is_file()
assert not files("siso_ref010").joinpath("data/standards/v37.xml").is_file()
assert files("siso_ref010").joinpath("data/SISO-REF-010.xsd").is_file()
assert EntityTypeAPI.bundled(35).info().data_version == "SISO-REF-010-v35"
assert len(BUNDLED_STANDARD_VERSIONS) == 18
assert decode_key(encode_entity(item.entity).key).entity == item.entity
print(json.dumps({
    "description": item.model_dump(mode="json", by_alias=True),
    "report": report_json,
    "markdown": report_markdown,
}))
""",
        )
        console_result = run(str(console), "describe", "1.3.153.6.4.2.0", "--json")
        assert console_result.stderr == ""
        api_result = json.loads(api.stdout)
        assert json.loads(console_result.stdout)["result"] == api_result["description"]
        report_result = run(str(console), "inspect", "report", "--json")
        report_json = json.loads(report_result.stdout)["result"]
        assert report_json == api_result["report"]
        assert report_json["identity_diagnostics"]["repeated_uuid_occurrences"] == 22
        assert report_json["identity_diagnostics"]["conflicting_source_record_groups"] == 0
        cli_markdown = run(str(console), "inspect", "report", "--format", "markdown")
        assert cli_markdown.stdout == api_result["markdown"]
        detailed_diagnostics = run(
            str(console),
            "inspect",
            "diagnostics",
            "--details",
            "--code",
            "missing_description",
            "--limit",
            "1",
            "--json",
        )
        diagnostics_json = json.loads(detailed_diagnostics.stdout)["result"]
        assert diagnostics_json["counts"]["missing_description"] == 838
        assert diagnostics_json["returned"] == 1
        entity_prefix = run(str(console), "inspect", "entity", "1.3.153.6.4.2")
        assert "Resolved prefix" in entity_prefix.stdout
        assert "Trailing Extra component: Not supplied" in entity_prefix.stdout
        assert "Unknown supplied components: None" in entity_prefix.stdout
        for boundary in (64, 127):
            ranged = run(str(console), "inspect", "value", "3", str(boundary), "--json")
            assert json.loads(ranged.stdout)["result"]["status"] == "range"
        unknown_value = run(str(console), "inspect", "value", "3", "1000000", "--json")
        assert json.loads(unknown_value.stdout)["result"]["status"] == "unknown"
        low_metadata = run(
            str(console),
            "compare",
            "35",
            "37",
            "--detail",
            "review-queue",
            "--priority",
            "low",
            "--category",
            "raw_metadata",
            "--limit",
            "0",
            "--json",
        )
        low_metadata_result = json.loads(low_metadata.stdout)["result"]
        assert low_metadata_result["total"] == 7
        assert low_metadata_result["low_priority_omitted_count"] == 7
        assert len(low_metadata_result["changes"]) == 7
        exported_xml = root / "SISO-REF-010-v35.xml"
        dump_result = run(str(console), "dump", "35", "--output", str(exported_xml))
        assert dump_result.stderr == ""
        assert "Wrote v35" in dump_result.stdout
        verified_export = run(
            str(python),
            "-I",
            "-c",
            """
import sys
from pathlib import Path
from siso_ref010 import BUNDLED_STANDARD_SOURCE
assert Path(sys.argv[1]).read_bytes() == BUNDLED_STANDARD_SOURCE.read_xml(35)
""",
            str(exported_xml),
        )
        assert verified_export.stdout == verified_export.stderr == ""
        module = run(str(python), "-I", "-m", "siso_ref010", "search", "F803", "--json")
        assert json.loads(module.stdout)["result"]["hits"][0]["description"] == "F803 Tromp"
        failure = run(str(console), "describe", "bad", "--json", code=2)
        assert failure.stdout == ""
        assert json.loads(failure.stderr)["error"]["type"] == "ValueError"
        help_result = run(str(console), "--help")
        assert "Python API" in help_result.stdout
        assert "--json" in help_result.stdout
        edition_check = run(
            str(python),
            "-I",
            "-c",
            """
from hashlib import sha256
import json
from importlib.resources import files
from siso_ref010 import BUNDLED_STANDARD_SOURCE, BUNDLED_STANDARD_VERSIONS, EntityTypeAPI
standards = files("siso_ref010").joinpath("data/standards")
registry = json.loads(standards.joinpath("PROVENANCE.json").read_text())
entries = {row["version"]: row for row in registry["entries"]}
for version in BUNDLED_STANDARD_VERSIONS:
    payload = BUNDLED_STANDARD_SOURCE.read_xml(version)
    assert sha256(payload).hexdigest() == entries[version]["sha256"]
    api = EntityTypeAPI.bundled(version)
    report = api.inspector.report()
    assert report.summary is not None
    assert report.identity.source_sha256 == entries[version]["sha256"]
    assert report.identity.provenance_status.value == "bundled_checksum_verified"
    assert all(check.status.value == "checked" for check in report.validation.semantic_checks)
    assert all(not hasattr(example, "python_expression") for example in report.examples)
    for example in report.examples:
        if example.kind.value == "enumeration_table":
            reproduced = api.inspector.enumeration_table(int(example.query))
        elif example.kind.value == "enumeration_value":
            table_uid, value = (int(part.strip()) for part in example.query.split(",", maxsplit=1))
            reproduced = api.inspector.resolve_enumeration_value(table_uid, value)
        else:
            reproduced = api.resolve_entity(example.query)
        assert reproduced == example.result
v22 = EntityTypeAPI.bundled(22).inspector.identity_diagnostics()
assert v22.duplicate_source_identifier_groups == 6
assert v22.conflicting_source_record_groups == 6
v37 = EntityTypeAPI.bundled(37).inspector
for boundary in (64, 127):
    assert v37.resolve_enumeration_value(3, boundary).status.value == "range"
assert v37.resolve_enumeration_value(3, 1_000_000).status.value == "unknown"
print(f"Installed edition inspection passed for {len(BUNDLED_STANDARD_VERSIONS)} editions")
""",
        )
        assert "Installed edition inspection passed for 18 editions" in edition_check.stdout
        for version in (22, 37):
            api_markdown = run(
                str(python),
                "-I",
                "-c",
                "import sys; from siso_ref010 import EntityTypeAPI, render_markdown; "
                "print(render_markdown(EntityTypeAPI.bundled(int(sys.argv[1])).inspector.report()), end='')",
                str(version),
            )
            cli_markdown = run(
                str(console),
                "--standard-version",
                str(version),
                "inspect",
                "report",
                "--format",
                "markdown",
            )
            assert cli_markdown.stdout == api_markdown.stdout
        api_audit_markdown = run(
            str(python),
            "-I",
            "-c",
            "from siso_ref010 import EntityTypeAPI, render_markdown; "
            "print(render_markdown(EntityTypeAPI.bundled(37).inspector.report(audit=True)), end='')",
        )
        cli_audit_markdown = run(
            str(console), "--standard-version", "37", "inspect", "report", "--audit", "--format", "markdown"
        )
        assert cli_audit_markdown.stdout == api_audit_markdown.stdout
        print(
            "Installed consumer checks passed offline: all editions, API, types, "
            "CLI/report renderer parity and errors."
        )


if __name__ == "__main__":
    main()

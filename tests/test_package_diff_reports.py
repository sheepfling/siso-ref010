import json
import pathlib
import subprocess
import sys
from zipfile import ZipFile

REPORT_NAMES = (
    "siso-ref-010-v22-to-v23-diff.json",
    "siso-ref-010-v22-to-v23-summary.txt",
    "siso-ref-010-v35-to-v37-diff-review-queue.json",
)
EVIDENCE_FILE = "siso-diff-test-evidence.json"


def test_report_bundle_is_clean_deterministic_and_self_documenting(tmp_path: pathlib.Path) -> None:
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    for name in REPORT_NAMES:
        (inputs / name).write_text("{}\n", encoding="utf-8")
    (inputs / EVIDENCE_FILE).write_text(
        json.dumps({"manifest_version": 1, "verification": []}) + "\n",
        encoding="utf-8",
    )
    (inputs / "__MACOSX").mkdir()
    (inputs / "__MACOSX" / "._junk").write_text("metadata", encoding="utf-8")

    first = tmp_path / "first.zip"
    second = tmp_path / "second.zip"
    for output in (first, second):
        subprocess.run(
            [
                sys.executable,
                "-m",
                "tools.siso_ref010.package_diff_reports",
                "--reports-dir",
                str(inputs),
                "--output",
                str(output),
            ],
            check=True,
            capture_output=True,
            text=True,
        )

    assert first.read_bytes() == second.read_bytes()
    expected = {"README.md", "SCHEMA.json", "TEST-EVIDENCE.json", *REPORT_NAMES}
    with ZipFile(first) as archive:
        assert set(archive.namelist()) == expected
        assert len(archive.namelist()) == 6
        assert archive.testzip() is None
        assert json.loads(archive.read("TEST-EVIDENCE.json")) == {
            "manifest_version": 1,
            "verification": [],
        }
        schema = json.loads(archive.read("SCHEMA.json"))
        assert "review queue" in schema["description"].lower()
        assert {
            "EditionDiff",
            "ConciseEditionDiff",
            "EditionDiffSummary",
            "ReviewQueuePage",
        } <= set(schema["$defs"])

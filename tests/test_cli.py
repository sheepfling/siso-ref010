import json
import pathlib
from io import StringIO

import pytest

from siso_ref010 import SisoRef010API
from siso_ref010.cli import main, render_diff_summary
from siso_ref010.sources import BUNDLED_STANDARD_SOURCE


def test_describe(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--standard-version", "37", "describe", "1.3.153.6.4.2.0", "--qualified"]) == 0
    assert (
        capsys.readouterr().out.strip().endswith("De Zeven Provincien Class / F803 Tromp / Unknown extra 0")
    )


def test_search(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--standard-version", "37", "search", "F803 Tromp"]) == 0
    assert "1.3.153.6.4.2.0: F803 Tromp" in capsys.readouterr().out
    assert main(["--standard-version", "37", "search", "", "--limit", "1"]) == 0
    output = capsys.readouterr()
    assert len(output.out.splitlines()) == 2
    total = output.out.splitlines()[1].split(" of ")[1].split(" matches")[0]
    assert f"Showing 1 of {total}" in output.err


def test_key(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["key", "1.2.225.7.8.7.1"]) == 0
    assert "Key: 72621510476957441" in capsys.readouterr().out
    assert main(["key", "--decode", "72621510476957441"]) == 0
    assert "Entity: 1.2.225.7.8.7.1" in capsys.readouterr().out
    assert main(["key", "--decode", "0xffffffffffffffff"]) == 0
    assert "Entity: 255.255.65535.255.255.255.255" in capsys.readouterr().out


@pytest.mark.parametrize(
    "args,length",
    [
        (["list", "countries"], 279),
        (["list", "kinds"], 11),
        (["list", "domains", "1"], 6),
        (["list", "categories", "1", "4", "153"], 2),
        (["list", "subcategories", "1", "4", "153", "5"], 2),
        (["list", "specifics", "1", "2", "106", "20", "2"], 3),
        (["list", "extras", "1", "2", "225", "7", "8", "7"], 4),
    ],
)
def test_list(capsys: pytest.CaptureFixture[str], args: list[str], length: int) -> None:
    assert main(["--standard-version", "37", *args]) == 0
    assert len(capsys.readouterr().out.splitlines()) == length


@pytest.mark.parametrize(
    "args",
    [
        ["describe", "bad"],
        ["list", "domains"],
        ["search", "text", "--limit", "-1"],
        ["parse", "missing.xml", "--output", "out"],
    ],
)
def test_errors(args: list[str], capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(args)
    assert exc.value.code == 2
    assert "error:" in capsys.readouterr().err


def test_custom_xml_source(tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]) -> None:
    source = tmp_path / "input.xml"
    source.write_text(
        '<ebv><enum uid="29" name="Country"><enumrow value="153" description="Netherlands"/></enum></ebv>',
        encoding="utf-8",
    )
    assert main(["--xml", str(source), "list", "countries"]) == 0
    assert capsys.readouterr().out.strip() == "153: Netherlands"


def test_search_labels_ambiguous_entity_descriptions(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "ambiguous-search.xml"
    source.write_text(
        '<ebv><enum uid="29" name="Country"><enumrow value="1" description="A"/></enum>'
        '<enum uid="30" name="Entity Kind"><enumrow value="1" description="Platform"/></enum>'
        '<cet><entity kind="1" domain="1" country="1">'
        '<category value="2" description="First source row"/>'
        '<category value="2" description="Second source row"/>'
        "</entity></cet></ebv>",
        encoding="utf-8",
    )

    assert main(["--xml", str(source), "search", "Second source row"]) == 0

    output = capsys.readouterr().out
    assert "1.1.1.2.0.0.0: ambiguous source descriptions" in output
    assert "First source row; Second source row" in output
    assert "1 of 1 matches" in output

    with pytest.raises(SystemExit) as error:
        main(["--xml", str(source), "describe", "1.1.1.2.0.0.0"])

    assert error.value.code == 2
    diagnostic = capsys.readouterr().err
    assert "candidate: First source row" in diagnostic
    assert "candidate: Second source row" in diagnostic


def test_info(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["info"]) == 0
    versions = SisoRef010API.bundled_versions()
    edition = next(
        item for item in SisoRef010API.bundled_editions() if item.version == versions.default_version
    )
    assert f"Data version: {edition.title}" in capsys.readouterr().out


def test_info_can_select_a_known_edition(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--standard-version", "37", "info"]) == 0
    assert "Data version: SISO-REF-010-v37" in capsys.readouterr().out


def test_versions(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["versions"]) == 0
    output = capsys.readouterr().out
    available = SisoRef010API.bundled_versions()
    assert f"default: {available.default_version}" in output
    version_lines = output.splitlines()[1:]
    assert tuple(int(line.split(maxsplit=1)[0]) for line in version_lines) == available.versions
    assert version_lines[-1] == f"{available.default_version} (default)"


def test_versions_json(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["versions", "--json"]) == 0
    result = json.loads(capsys.readouterr().out)["result"]
    available = SisoRef010API.bundled_versions()
    assert result["default_version"] == available.default_version
    assert result["versions"] == list(available.versions)


def test_help_points_to_the_public_python_api(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0
    assert "from siso_ref010 import SisoRef010API" in capsys.readouterr().out


def test_query_text_filter_coexists_with_json_output(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--standard-version", "37", "query", "--text", "F803 Tromp", "--limit", "1", "--json"]) == 0
    result = json.loads(capsys.readouterr().out)["result"]
    assert result["total"] >= 1
    assert "F803 Tromp" in result["values"][0]["description"]


def test_inspect_diagnostics_groups_by_default_and_lists_details_on_request(
    capsys: pytest.CaptureFixture[str],
) -> None:
    args = [
        "--standard-version",
        "37",
        "inspect",
        "diagnostics",
        "--code",
        "missing_description",
        "--table-uid",
        "75",
        "--severity",
        "info",
    ]
    assert main(args) == 0
    grouped = capsys.readouterr().out
    assert "818 diagnostic findings" in grouped
    assert "info missing_description: 818 · UID 75 Emitter Name" in grouped
    assert "/enumrow" not in grouped

    assert main([*args, "--details", "--limit", "1"]) == 0
    detailed = capsys.readouterr().out
    assert "info missing_description:" in detailed
    assert "[enumeration[uid=75]" in detailed
    assert "Showing 1 from offset 0" in detailed


def test_inspect_entity_accepts_a_dotted_prefix(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--standard-version", "37", "inspect", "entity", "1.3.153.6.4.2"]) == 0
    output = capsys.readouterr().out
    assert "Resolved prefix — 6 of 7 components" in output
    assert "Trailing Extra component: Not supplied" in output
    assert "Unknown supplied components: None" in output
    assert "F803 Tromp" in output


def test_inspect_entity_reports_ambiguous_and_unknown_source_paths(
    capsys: pytest.CaptureFixture[str], tmp_path: pathlib.Path
) -> None:
    source = tmp_path / "ambiguous.xml"
    source.write_text(
        '<ebv title="Fixture">'
        '<enum uid="29" name="Country"><enumrow value="1" description="Country"/></enum>'
        '<enum uid="30" name="Entity Kind"><enumrow value="1" description="Platform"/></enum>'
        '<cet><entity kind="1" domain="1" country="1">'
        '<category value="2" description="First"/>'
        '<category value="2" description="Second"/>'
        "</entity></cet></ebv>",
        encoding="utf-8",
    )
    assert main(["--xml", str(source), "inspect", "entity", "1.1.1.2.0.0.0"]) == 0
    ambiguous = capsys.readouterr().out
    assert "Ambiguous source candidates: 2" in ambiguous
    assert "candidate: 1.1.1.2: First" in ambiguous
    assert "candidate: 1.1.1.2: Second" in ambiguous

    assert main(["--xml", str(source), "inspect", "entity", "1.1.1.2.99"]) == 0
    unknown = capsys.readouterr().out
    assert "Unknown supplied components: category, subcategory" in unknown


def test_dump_writes_original_xml_bytes(
    capsysbinary: pytest.CaptureFixture[bytes], tmp_path: pathlib.Path
) -> None:
    expected = BUNDLED_STANDARD_SOURCE.read_xml(35)
    assert main(["dump", "35"]) == 0
    captured = capsysbinary.readouterr()
    assert captured.out == expected
    assert captured.err == b""

    target = tmp_path / "v35.xml"
    assert main(["dump", "35", "--output", str(target)]) == 0
    assert target.read_bytes() == expected
    assert "Wrote v35" in capsysbinary.readouterr().out.decode()

    with pytest.raises(SystemExit) as error:
        main(["dump", "35", "--output", str(target)])
    assert error.value.code == 2
    assert target.read_bytes() == expected


def test_dump_all_uses_versioned_filenames_and_prevents_partial_overwrite(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: pathlib.Path
) -> None:
    import siso_ref010.cli.app as cli

    class MemorySource:
        @property
        def versions(self) -> tuple[int, ...]:
            return (7, 8)

        def read_xml(self, version: int) -> bytes:
            return f"<ebv title='v{version}'/>".encode()

    monkeypatch.setattr(cli, "BUNDLED_STANDARD_SOURCE", MemorySource())
    output_dir = tmp_path / "standards"
    assert main(["dump", "--all", "--output-dir", str(output_dir)]) == 0
    assert (output_dir / "v7.xml").read_bytes() == b"<ebv title='v7'/>"
    assert (output_dir / "v8.xml").read_bytes() == b"<ebv title='v8'/>"
    assert "Wrote 2 editions" in capsys.readouterr().out

    output_dir = tmp_path / "existing"
    output_dir.mkdir()
    (output_dir / "v7.xml").write_bytes(b"keep")
    with pytest.raises(SystemExit) as error:
        main(["dump", "--all", "--output-dir", str(output_dir)])
    assert error.value.code == 2
    assert (output_dir / "v7.xml").read_bytes() == b"keep"
    assert not (output_dir / "v8.xml").exists()


def test_inspect_text_commands_cover_each_result_shape(capsys: pytest.CaptureFixture[str]) -> None:
    api = SisoRef010API.bundled(37)
    table = api.inspector.enumeration_table(3)
    assert table is not None
    row = api.inspector.enumeration_rows(3)[0]
    assert row.uuid is not None

    commands = (
        (["inspect", "summary"], "value/path records="),
        (["inspect", "tables", "--query", table.name], table.name),
        (["inspect", "values", "--table-uid", "3", "--limit", "1"], "table 3:"),
        (["inspect", "values", "--deprecated", "--limit", "1"], "deprecated"),
        (["inspect", "search", "F803", "--limit", "1"], "matches for 'F803'"),
        (["inspect", "value", "3", "95"], "table 3, value 95: range"),
        (["inspect", "value", "99999", "1"], "Enumeration table not found."),
        (["inspect", "resolve", table.name, "95"], f"{table.name}, value 95:"),
        (["inspect", "resolve", "No such table", "1"], "No enumeration table has that exact name."),
        (["inspect", "uuid", row.uuid], f"UUID {row.uuid}"),
        (["inspect", "entity", "1.3.153.6.4.2"], "Resolved prefix — 6 of 7 components"),
    )
    for command, expected in commands:
        assert main(["--standard-version", "37", *command]) == 0
        assert expected in capsys.readouterr().out

    annotated_table = next(item for item in api.inspector.standard.enumerations if item.annotations)
    assert main(["--standard-version", "37", "inspect", "tables", "--query", annotated_table.name]) == 0
    assert annotated_table.annotations[0].text in capsys.readouterr().out

    applicable_table = next(item for item in api.inspector.enumeration_tables() if item.applicability)
    assert main(["--standard-version", "37", "inspect", "tables", "--query", applicable_table.name]) == 0
    assert "applies=" in capsys.readouterr().out


def test_history_and_comparison_text_renderers(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    import siso_ref010.cli.app as cli

    assert main(["history", "--entity", "1.3.153.6.4.2.0", "--versions", "36", "37"]) == 0
    history_output = capsys.readouterr().out
    assert "entity history:" in history_output
    assert "v37:" in history_output

    assert main(["history", "--enum-uid", "3", "--value", "95", "--versions", "36", "37"]) == 0
    assert "enumeration history:" in capsys.readouterr().out

    diff = SisoRef010API.compare_editions(35, 37, limit=None)
    small_diff = diff.model_copy(update={"changes": diff.changes[:8], "truncated": True})
    monkeypatch.setattr(cli, "_compare_result", lambda args: diff)

    assert main(["compare", "35", "37", "--detail", "summary"]) == 0
    summary = capsys.readouterr().out
    assert "SISO-REF-010 · Edition comparison" in summary
    assert "v35 -> v37:" in summary

    assert main(["compare", "35", "37", "--json"]) == 0
    default_json = json.loads(capsys.readouterr().out)
    assert default_json["result"]["report_type"] == "summary"

    monkeypatch.setattr(cli, "_compare_result", lambda args: small_diff)

    assert main(["compare", "35", "37", "--detail", "audit"]) == 0
    audit = capsys.readouterr().out
    assert "changes (" in audit

    assert main(["compare", "35", "37", "--detail", "concise"]) == 0
    concise = capsys.readouterr().out
    assert "added:" in concise or "high:" in concise or "medium:" in concise

    monkeypatch.setattr(cli, "_compare_result", lambda args: diff)
    assert main(["compare", "35", "37", "--detail", "review-queue", "--limit", "3"]) == 0
    assert "Review queue v35 -> v37:" in capsys.readouterr().out

    assert (
        main(
            [
                "compare",
                "35",
                "37",
                "--detail",
                "review-queue",
                "--limit",
                "0",
                "--priority",
                "low",
                "--category",
                "raw_metadata",
            ]
        )
        == 0
    )
    assert "Review queue v35 -> v37:" in capsys.readouterr().out


def test_query_warmup_json_outputs_and_machine_errors(capsys: pytest.CaptureFixture[str]) -> None:
    assert (
        main(["--standard-version", "37", "--warmup", "query", "--text", "F803 Tromp", "--limit", "1"]) == 0
    )
    warmed_output = capsys.readouterr()
    assert "F803 Tromp" in warmed_output.out
    assert "Warmed" in warmed_output.err

    assert (
        main(
            [
                "--standard-version",
                "37",
                "--warmup",
                "query",
                "--text",
                "F803 Tromp",
                "--limit",
                "1",
                "--json",
            ]
        )
        == 0
    )
    warmed = json.loads(capsys.readouterr().out)
    assert warmed["result"]["total"] == 1

    assert (
        main(
            [
                "--standard-version",
                "37",
                "query",
                "--text",
                "F803 Tromp",
                "--limit",
                "1",
                "--offset",
                "0",
                "--json",
            ]
        )
        == 0
    )
    result = json.loads(capsys.readouterr().out)["result"]
    assert result["values"][0]["description"] == "F803 Tromp"

    assert main(["info", "--json"]) == 0
    versions = SisoRef010API.bundled_versions()
    edition = next(
        item for item in SisoRef010API.bundled_editions() if item.version == versions.default_version
    )
    assert json.loads(capsys.readouterr().out)["result"]["data_version"] == (edition.title)
    assert main(["--standard-version", "37", "list", "countries", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["result"]["choices"]

    with pytest.raises(SystemExit) as error:
        main(["--json", "query", "--offset", "-1"])
    assert error.value.code == 2
    payload = json.loads(capsys.readouterr().err)
    assert payload["error"]["type"] == "ValueError"


def test_inspect_and_dump_runtime_validation_errors(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    invalid_commands = (
        ["inspect", "diagnostics", "--offset", "1"],
        ["inspect", "diagnostics", "--limit", "-1"],
        ["inspect", "values", "--table-uid", "-1"],
        ["inspect", "values", "--limit", "-1"],
        ["inspect", "search", "text", "--offset", "-1"],
        ["inspect", "value", "-1", "1"],
        ["inspect", "value", "3", "-1"],
    )
    for command in invalid_commands:
        with pytest.raises(SystemExit) as error:
            main(command)
        assert error.value.code == 2
        assert "error:" in capsys.readouterr().err

    with pytest.raises(SystemExit) as error:
        main(["dump"])
    assert error.value.code == 2
    assert "dump requires an edition number" in capsys.readouterr().err

    with pytest.raises(SystemExit) as error:
        main(["dump", "35", "--output-dir", str(tmp_path)])
    assert error.value.code == 2
    assert "--output-dir can only be used" in capsys.readouterr().err

    with pytest.raises(SystemExit) as error:
        main(["dump", "--all", "35", "--output-dir", str(tmp_path)])
    assert error.value.code == 2
    assert "dump --all requires --output-dir" in capsys.readouterr().err

    import siso_ref010.cli.app as cli

    monkeypatch.setattr(cli.sys, "stdout", StringIO())
    with pytest.raises(SystemExit) as error:
        main(["dump", "35"])
    assert error.value.code == 2
    assert "stdout does not support binary output" in capsys.readouterr().err


def test_cli_rejects_incompatible_commands_and_filters_as_structured_errors(
    capsys: pytest.CaptureFixture[str],
) -> None:
    invalid = (
        (["--warmup", "versions"], "--warmup applies only"),
        (["history", "--entity", "1.1.1", "--value", "1"], "history --value requires --enum-uid"),
        (["compare", "35", "37", "--entity-prefix", "1.2"], "3 through 7"),
        (["compare", "35", "37", "--entity-prefix", "1.no.3"], "dotted decimal fields"),
        (["compare", "35", "37", "--entity-prefix", "1.2.3.-1"], "nonnegative dotted fields"),
        (["--standard-version", "37", "compare", "35", "37"], "uses the bundled version source"),
        (["--standard-version", "37", "dump", "35"], "dump reads bundled editions"),
        (["--xml", "unused.xml", "history", "--entity", "1.1.1"], "history uses the bundled version source"),
    )
    for args, message in invalid:
        with pytest.raises(SystemExit) as error:
            main(args)
        assert error.value.code == 2
        assert message in capsys.readouterr().err

    with pytest.raises(SystemExit) as error:
        main(["--json", "dump", "35"])
    assert error.value.code == 2
    assert json.loads(capsys.readouterr().err)["error"]["type"] == "ValueError"


def test_cli_summary_and_concise_output_explain_removed_and_recoded_values(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    import siso_ref010.cli.app as cli

    class MemorySource:
        def __init__(self, versions: dict[int, str]) -> None:
            self.data = versions

        @property
        def versions(self) -> tuple[int, ...]:
            return tuple(self.data)

        def read_xml(self, version: int) -> bytes:
            return self.data[version].encode()

    before = (
        '<ebv><enum uid="7" name="Example" size="8">'
        '<enumrow value="1" description="Stable identity" uuid="stable"/>'
        '<enumrow value="2" description="Removed value" uuid="removed"/>'
        "</enum></ebv>"
    )
    after = (
        '<ebv><enum uid="7" name="Example" size="16">'
        '<enumrow value="3" description="Stable identity" uuid="stable"/>'
        "</enum></ebv>"
    )
    diff = SisoRef010API.compare_editions(
        1,
        2,
        source=MemorySource({1: before, 2: after}),
        scope="enumerations",
        limit=None,
    )
    assert diff.counts.removed == 1
    assert diff.counts.recoded == 1
    monkeypatch.setattr(cli, "_compare_result", lambda _args: diff)

    assert main(["compare", "1", "2", "--detail", "summary"]) == 0
    summary = capsys.readouterr().out
    assert "Removed: 1" in summary and "recoded: 1" in summary
    assert render_diff_summary(diff) == summary

    assert main(["compare", "1", "2", "--detail", "concise", "--limit", "0"]) == 0
    concise = capsys.readouterr().out
    assert "removed: enumeration_value" in concise
    assert "Stable identity [value: 1 -> 3]" in concise

    assert main(["compare", "1", "2", "--detail", "audit", "--limit", "0"]) == 0
    audit = capsys.readouterr().out
    assert "table 7" in audit
    assert "table 7:1" in audit

    promoted_changes = tuple(
        change.model_copy(update={"review_priority": "high"}) if change.action == "recoded" else change
        for change in diff.changes
    )
    promoted = diff.model_copy(update={"changes": promoted_changes})
    promoted_summary = render_diff_summary(promoted)
    assert "Stable identity: value" in promoted_summary

    assert main(["compare", "1", "2", "--detail", "concise", "--material-only", "--limit", "1"]) == 0
    assert "v1 -> v2" in capsys.readouterr().out
    assert main(["compare", "1", "2", "--detail", "summary", "--material-only"]) == 0
    assert "total changes" in capsys.readouterr().out

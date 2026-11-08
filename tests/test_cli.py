import json

import pytest

from dis_entity_types.cli import main
from dis_entity_types.sources import BUNDLED_STANDARD_SOURCE


def test_describe(capsys):
    assert main(["describe", "1.3.153.6.4.2.0", "--qualified"]) == 0
    assert (
        capsys.readouterr().out.strip().endswith("De Zeven Provincien Class / F803 Tromp / Unknown extra 0")
    )


def test_search(capsys):
    assert main(["search", "F803 Tromp"]) == 0
    assert "1.3.153.6.4.2.0: F803 Tromp" in capsys.readouterr().out
    assert main(["search", "", "--limit", "1"]) == 0
    output = capsys.readouterr()
    assert len(output.out.splitlines()) == 2
    total = output.out.splitlines()[1].split(" of ")[1].split(" matches")[0]
    assert f"Showing 1 of {total}" in output.err


def test_key(capsys):
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
def test_list(capsys, args, length):
    assert main(args) == 0
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
def test_errors(args, capsys):
    with pytest.raises(SystemExit) as exc:
        main(args)
    assert exc.value.code == 2
    assert "error:" in capsys.readouterr().err


def test_custom_xml_source(tmp_path, capsys):
    source = tmp_path / "input.xml"
    source.write_text(
        '<ebv><enum uid="29" name="Country"><enumrow value="153" description="Netherlands"/></enum></ebv>'
    )
    assert main(["--xml", str(source), "list", "countries"]) == 0
    assert capsys.readouterr().out.strip() == "153: Netherlands"


def test_info(capsys):
    assert main(["info"]) == 0
    assert "Data version: SISO-REF-010-v37" in capsys.readouterr().out


def test_versions(capsys):
    assert main(["versions"]) == 0
    output = capsys.readouterr().out
    assert "default: 37" in output
    assert "20" in output and "36" in output and "37 (default)" in output


def test_versions_json(capsys):
    assert main(["versions", "--json"]) == 0
    result = json.loads(capsys.readouterr().out)["result"]
    assert result["default_version"] == 37
    assert result["versions"] == list(range(20, 38))


def test_query_text_filter_coexists_with_json_output(capsys):
    assert main(["query", "--text", "F803 Tromp", "--limit", "1", "--json"]) == 0
    result = json.loads(capsys.readouterr().out)["result"]
    assert result["total"] >= 1
    assert "F803 Tromp" in result["values"][0]["description"]


def test_inspect_diagnostics_groups_by_default_and_lists_details_on_request(capsys):
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


def test_inspect_entity_accepts_a_dotted_prefix(capsys):
    assert main(["--standard-version", "37", "inspect", "entity", "1.3.153.6.4.2"]) == 0
    output = capsys.readouterr().out
    assert "Resolved prefix — 6 of 7 components" in output
    assert "Trailing Extra component: Not supplied" in output
    assert "Unknown supplied components: None" in output
    assert "F803 Tromp" in output


def test_dump_writes_original_xml_bytes(capsysbinary, tmp_path):
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


def test_dump_all_uses_versioned_filenames_and_prevents_partial_overwrite(monkeypatch, capsys, tmp_path):
    import dis_entity_types.cli as cli

    class MemorySource:
        @property
        def versions(self):
            return (7, 8)

        def read_xml(self, version):
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

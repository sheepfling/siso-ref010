import json

import pytest

from siso_entity_type.cli import main


def test_describe(capsys):
    assert main(["describe", "1.3.153.6.4.2.0", "--qualified"]) == 0
    assert capsys.readouterr().out.strip().endswith("De Zeven Provincien Class / F803 Tromp")


def test_search(capsys):
    assert main(["search", "F803 Tromp"]) == 0
    assert json.loads(capsys.readouterr().out) == {"1.3.153.6.4.2.0": "F803 Tromp"}
    assert main(["search", "", "--limit", "1"]) == 0
    output = capsys.readouterr()
    assert len(json.loads(output.out)) == 1
    assert "Showing 1 of 24637" in output.err


def test_key(capsys):
    assert main(["key", "1.2.225.7.8.7.1"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result == {
        "key": "72621510476957441",
        "unsigned_key": "72621510476957441",
        "wire_hex": "010200e107080701",
    }
    assert main(["key", "--decode", result["key"]]) == 0
    assert capsys.readouterr().out.strip() == "1.2.225.7.8.7.1"
    assert main(["key", "--decode", "0xffffffffffffffff"]) == 0
    assert capsys.readouterr().out.strip() == "255.255.65535.255.255.255.255"


@pytest.mark.parametrize(
    "args,length",
    [
        (["list", "countries"], 279),
        (["list", "kinds"], 10),
        (["list", "domains", "1"], 6),
        (["list", "categories", "1", "4", "153"], 2),
        (["list", "subcategories", "1", "4", "153", "5"], 2),
        (["list", "specifics", "1", "2", "106", "20", "2"], 4),
        (["list", "extras", "1", "2", "225", "7", "8", "7"], 5),
    ],
)
def test_list(capsys, args, length):
    assert main(args) == 0
    assert len(json.loads(capsys.readouterr().out)) == length


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


def test_parse_custom_data(tmp_path, capsys):
    source = tmp_path / "input.xml"
    source.write_text('<ebv><enum uid="29"><enumrow value="153" description="Netherlands"/></enum></ebv>')
    output = tmp_path / "out"
    assert main(["parse", str(source), "--output", str(output)]) == 0
    assert str(output / "siso-enums.json") in capsys.readouterr().out
    assert main(["--data", str(output / "siso-enums.json"), "list", "countries"]) == 0
    assert json.loads(capsys.readouterr().out) == {"153": "Netherlands"}


def test_info(capsys):
    assert main(["info"]) == 0
    assert (
        json.loads(capsys.readouterr().out)["upstream_commit"] == "bb195c647b6f9c4b7bea4e5a10e6c560a0b0bceb"
    )


def test_picker(monkeypatch, capsys):
    values = iter(["oops", "65535", "153", "1", "3", "6", "4", "2", "0"])
    monkeypatch.setattr("builtins.input", lambda _: next(values))
    assert main(["pick"]) == 0
    assert "1.3.153.6.4.2.0\nGuided Missile Frigate" in capsys.readouterr().out


def test_picker_cancel(monkeypatch, capsys):
    def stop(_):
        raise EOFError

    monkeypatch.setattr("builtins.input", stop)
    assert main(["pick"]) == 130
    assert "Cancelled." in capsys.readouterr().err

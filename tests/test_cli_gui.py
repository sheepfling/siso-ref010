import json

import pytest

from siso_entity_type import gui
from siso_entity_type.cli import main


def test_gui_cli_launches_with_api(monkeypatch):
    calls = []
    monkeypatch.setattr(gui, "launch", calls.append)
    assert main(["gui"]) == 0
    assert len(calls) == 1
    assert calls[0].info()["data_source"] == "bundled"


def test_gui_cli_custom_catalog(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(gui, "launch", calls.append)
    source = tmp_path / "data.json"
    source.write_text(json.dumps(dict.fromkeys(("countries", "domains", "categories", "subcategories"), {})))
    assert main(["--data", str(source), "gui"]) == 0
    assert calls[0].info()["counts"]["countries"] == 0


def test_gui_cli_reports_missing_display(monkeypatch, capsys):
    def fail(_api):
        raise RuntimeError("Display unavailable")

    monkeypatch.setattr(gui, "launch", fail)
    with pytest.raises(SystemExit) as exc:
        main(["gui"])
    assert exc.value.code == 2
    assert "Display unavailable" in capsys.readouterr().err


def test_gui_cli_rejects_json_without_launch(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(gui, "launch", calls.append)
    with pytest.raises(SystemExit) as exc:
        main(["gui", "--json"])
    assert exc.value.code == 2
    assert not calls
    assert json.loads(capsys.readouterr().err)["error"]["type"] == "ValueError"

"""Launch error tests always run; real Tk view tests require Tk and a display."""

import builtins
import os
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from siso_entity_type import EntityTypeAPI, gui
from siso_entity_type.picker import Field


def test_gui_import_does_not_import_tk():
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import siso_entity_type.gui; assert 'tkinter' not in sys.modules",
        ],
        env={**os.environ, "PYTHONPATH": os.pathsep.join(sys.path)},
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr


def test_launch_explains_missing_tk(monkeypatch, capsys):
    original = builtins.__import__

    def without_tk(name, *args, **kwargs):
        if name == "tkinter":
            raise ImportError("No tkinter")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", without_tk)
    assert gui.main() == 2
    assert "requires Tkinter" in capsys.readouterr().err


def test_launch_explains_missing_display(monkeypatch, capsys):
    class TclError(Exception):
        pass

    def fail():
        raise TclError("no display")

    monkeypatch.setitem(sys.modules, "tkinter", SimpleNamespace(Tk=fail, TclError=TclError))
    assert gui.main() == 2
    assert "graphical desktop session" in capsys.readouterr().err


def test_launch_cleanup_after_normal_window_close(monkeypatch):
    class TclError(Exception):
        pass

    root = Mock()
    root.destroy.side_effect = TclError("already destroyed")
    monkeypatch.setitem(sys.modules, "tkinter", SimpleNamespace(Tk=lambda: root, TclError=TclError))
    window = Mock()
    monkeypatch.setattr(gui, "PickerWindow", window)
    assert gui.main() == 0
    window.assert_called_once_with(root, None)
    root.mainloop.assert_called_once()
    root.destroy.assert_called_once()


@pytest.fixture
def window():
    required = os.environ.get("SISO_REQUIRE_GUI_TESTS") == "1"
    if required:
        import tkinter as tk
    else:
        tk = pytest.importorskip("tkinter")
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        if required:
            pytest.fail(f"Required Tk display unavailable: {exc}")
        pytest.skip(f"Tk display unavailable: {exc}")
    root.withdraw()
    view = gui.PickerWindow(root, EntityTypeAPI())
    yield view
    view.close()


def test_real_tk_load_invalid_repeat_filter_and_reset(window):
    window.id_text.set("1.3.153.6.4.2.0")
    window.load_id()
    window.load_id()
    assert window.output.get() == "1.3.153.6.4.2.0"
    assert window.fields[Field.COUNTRY].get().startswith("153 — ")
    window.id_text.set("not an ID")
    window.load_id()
    assert window.output.get() == "1.3.153.6.4.2.0"
    assert "Builder unchanged" in window.status.get()
    window.fields[Field.COUNTRY].set("nether")
    window.filter_field(Field.COUNTRY)
    assert all("nether" in item.lower() for item in window.fields[Field.COUNTRY]["values"])
    window.fields[Field.COUNTRY].set("225")
    window.select_field(Field.COUNTRY)
    assert window.output.get() == "1.3.225.0.0.0.0"
    window.fields[Field.KIND].set("256")
    window.select_field(Field.KIND)
    assert window.output.get() == "1.3.225.0.0.0.0"
    window.reset()
    window.reset()
    assert window.output.get() == "0.0.0.0.0.0.0"
    assert not window.table.get_children()


def test_real_tk_search_selection_copy_and_close(window):
    window.query.set("f803")
    window.search()
    assert window.count.get() == "1 results"
    window.table.selection_set("0")
    window.select_result()
    assert window.output.get() == "1.3.153.6.4.2.0"
    window.copy_id()
    assert window.root.clipboard_get() == "1.3.153.6.4.2.0"
    window.clear_field(Field.CATEGORY)
    assert window.output.get() == "1.3.153.0.0.0.0"
    window.query.set("tank")
    window.query.set("f803")
    window.search()
    assert window.count.get() == "1 results"
    window.query.set("")
    assert not window.table.get_children()  # stale rows disappear before debounce
    window.close()
    window.close()
    assert window._pending_search is None
    assert window._pending_rows is None


def test_real_tk_new_query_cancels_chunked_results(window):
    window.query.set("   ")
    window.search()
    # A broad real substring can have >200 results, inserted in cancellable batches.
    window.query.set("tank")
    window.search()
    assert window._pending_rows is not None
    window.reset()
    window.root.update()
    assert not window.table.get_children()
    assert window._pending_rows is None

# Native Python entity-type picker

The graphical picker is a newly authored Python/Tkinter implementation of the
upstream picker's workflow, alongside the existing API and CLI. It does not use a
browser, JavaScript, Node, a web server, or third-party Python runtime packages.
Upstream behavior was consulted; this is not a clean-room implementation. Existing
attribution and the separate SISO data notices apply.

## Launch

```sh
dis-entity-types gui
# Or:
dis-entity-types-gui
python -m siso_entity_type.gui
```

Tkinter is a standard-library interface to the OS Tcl/Tk installation. Some Python
builds omit it. On Linux, install the distribution's Tk support for the Python
interpreter used to run the package (often `python3-tk`). On other platforms, use a
Python distribution with Tk support. A graphical desktop/display is required.
Missing Tk or a missing display produces an actionable error and exit status 2;
importing the package, API, picker state, or GUI module does not import Tk.

An application can supply the same catalog API used elsewhere:

```python
from siso_entity_type import EntityTypeAPI
from siso_entity_type.gui import launch

launch(EntityTypeAPI.from_json("my-catalog.json"))
```

The GUI must run on the application's main thread. `launch()` owns its Tk root and
main loop; callers embedding a view in an existing Tk application can construct
`PickerWindow(root, api)` instead and manage their own main loop.

## Workflow

- **Load ID:** enter exactly seven unsigned decimal fields in wire order:
  `kind.domain.country.category.subcategory.specific.extra`. Click Load ID or press
  Enter. All fields are validated before any builder state changes. Invalid input
  leaves the current output intact and explains the error in the status line.
- **Build:** choose country, kind, domain, category, subcategory, specific, and
  extra. Each dropdown shows numeric codes and descriptions. Type a description
  fragment to narrow its dropdown, then select a result; or enter an unsigned
  numeric code and press Enter. Escape restores the committed values.
- **Cascade:** changing country retains kind and domain but clears category and
  everything below it. Changing kind clears domain and all categories; changing
  any other field clears all its descendants. Reselecting the same value is a
  no-op. Each Clear button explicitly clears that field and its descendants,
  including when that field already contains zero.
- **Unknown codes:** in-range values without catalog entries are retained and
  labeled as unknown. Country permits 0–65535; other fields permit 0–255. Unknown
  catalog data is not confused with invalid DIS wire values.
- **Search:** type at least three characters for case-insensitive description
  substring matching. Searches are debounced, or run immediately with Enter/the
  Search button. The exact match count is shown, and every result is available
  in the scrollable list. Select a result to populate all builder fields.
- **Copy ID:** copies the committed output, with a success or failure status.
  On systems whose clipboard owner is the application (commonly X11), keep the
  picker open until pasting. The read-only output can also be selected manually.
- **Reset all:** clears the entry, all seven fields, pending searches and results.
  Closing the window cancels pending callbacks. Search results are inserted in
  small batches, so a broad result set does not monopolize the UI event loop.

## Testing and limitations

`tests/test_picker.py` exercises the headless state model. `tests/test_gui.py`
checks lazy Tk imports and launch failures without a display, and includes real
Tk widget tests that run when Tk and a graphical display are available. On a
headless host they are explicitly skipped; these skips are not visual QA. The CI
quality job uses a virtual display and `SISO_REQUIRE_GUI_TESTS=1` to require them.

```sh
pytest tests/test_picker.py tests/test_gui.py
```

The view uses native themed widgets and a resizable two-column results list.
Manual desktop verification should include loading invalid/repeated IDs, changing
parents, unknown codes, search result selection, reset during search, keyboard
navigation, copying into another application, resizing, and window close during
pending work. Native widgets may differ across operating systems.

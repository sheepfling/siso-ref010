# Modified work (2026): Python adaptation of TNO-MST/siso-entity-type picker behavior.
# Original copyright 2025 TNO; Apache-2.0. See LICENSE and NOTICE.
"""Optional standard-library Tk desktop picker; no Tk import until launch."""

from __future__ import annotations

import sys
from functools import partial
from typing import TYPE_CHECKING, Protocol, cast

from .api import EntityTypeAPI
from .picker import Field, PickerState

if TYPE_CHECKING:
    import tkinter as tk


class _ScrollCommands(Protocol):
    """Typed view of Tk's variadic scroll commands (incomplete upstream stubs)."""

    def xview(self, *args: str) -> tuple[float, float] | None: ...

    def yview(self, *args: str) -> tuple[float, float] | None: ...


class PickerWindow:
    """Native picker view. Call ``close`` to cancel pending UI work and destroy it."""

    def __init__(self, root: tk.Tk, api: EntityTypeAPI | None = None) -> None:
        import tkinter as tk
        from tkinter import ttk

        self.root = root
        self.state = PickerState(api)
        self._pending_search: str | None = None
        self._pending_rows: str | None = None
        self._closed = False
        self.root.title("DIS Entity Types")
        self.root.geometry("1000x760")
        self.root.minsize(720, 650)
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        frame = ttk.Frame(root, padding=16)
        frame.grid(sticky="nsew")
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(4, weight=1)
        ttk.Label(frame, text="DIS Entity Types", font=("TkDefaultFont", 18, "bold")).grid(sticky="w")

        entry = ttk.LabelFrame(frame, text="Enter entity-type ID", padding=8)
        entry.grid(row=1, sticky="ew", pady=8)
        entry.columnconfigure(0, weight=1)
        self.id_text = tk.StringVar(root)
        self.id_entry = ttk.Entry(entry, textvariable=self.id_text)
        self.id_entry.grid(sticky="ew")
        self.id_entry.bind("<Return>", lambda event: self.load_id())
        ttk.Button(entry, text="Load ID", command=self.load_id).grid(row=0, column=1, padx=6)
        ttk.Button(entry, text="Reset all", command=self.reset).grid(row=0, column=2)
        ttk.Label(entry, text="kind.domain.country.category.subcategory.specific.extra").grid(
            row=1, columnspan=3, sticky="w"
        )

        builder = ttk.LabelFrame(frame, text="Build • select a label or enter a numeric code", padding=8)
        builder.grid(row=2, sticky="ew")
        builder.columnconfigure(1, weight=1)
        self.fields: dict[Field, ttk.Combobox] = {}
        for row, field in enumerate(Field):
            ttk.Label(builder, text=field.value.capitalize()).grid(row=row, sticky="w", padx=(0, 10))
            box = ttk.Combobox(builder, height=12)
            box.grid(row=row, column=1, sticky="ew", pady=2)
            box.bind("<<ComboboxSelected>>", partial(self.select_field, field))
            box.bind("<Return>", partial(self.select_field, field))
            box.bind("<Escape>", lambda event: self.refresh())
            box.bind("<KeyRelease>", partial(self.filter_field, field))
            self.fields[field] = box
            ttk.Button(builder, text="Clear", command=partial(self.clear_field, field)).grid(
                row=row, column=2, padx=(6, 0)
            )
        self.output = tk.StringVar(root)
        ttk.Entry(builder, textvariable=self.output, state="readonly").grid(
            row=7, column=1, sticky="ew", pady=(8, 0)
        )
        ttk.Label(builder, text="Output").grid(row=7, column=0, sticky="w")
        ttk.Button(builder, text="Copy ID", command=self.copy_id).grid(row=7, column=2, padx=(6, 0))

        search = ttk.LabelFrame(frame, text="Search descriptions", padding=8)
        search.grid(row=3, sticky="ew", pady=8)
        search.columnconfigure(0, weight=1)
        self.query = tk.StringVar(root)
        search_entry = ttk.Entry(search, textvariable=self.query)
        search_entry.grid(sticky="ew")
        search_entry.bind("<Return>", lambda event: self.search())
        self.query.trace_add("write", self._schedule_search)
        ttk.Button(search, text="Search", command=self.search).grid(row=0, column=1, padx=6)
        ttk.Button(search, text="Clear", command=lambda: self.query.set("")).grid(row=0, column=2)
        self.count = tk.StringVar(root, "Type at least 3 characters")
        ttk.Label(search, textvariable=self.count).grid(row=1, columnspan=3, sticky="w")
        results = ttk.Frame(frame)
        results.grid(row=4, sticky="nsew")
        results.columnconfigure(0, weight=1)
        results.rowconfigure(0, weight=1)
        self.table = ttk.Treeview(
            results, columns=("entity", "description"), show="headings", selectmode="browse"
        )
        self.table.heading("entity", text="Entity type")
        self.table.heading("description", text="Description (select to load)")
        self.table.column("entity", width=210, stretch=False)
        self.table.column("description", width=450)
        self.table.grid(sticky="nsew")
        scroll = cast(_ScrollCommands, self.table)
        scrollbar = ttk.Scrollbar(
            results,
            orient="vertical",
            command=scroll.yview,
        )
        scrollbar.grid(row=0, column=1, sticky="ns")
        horizontal = ttk.Scrollbar(
            results,
            orient="horizontal",
            command=scroll.xview,
        )
        horizontal.grid(row=1, column=0, sticky="ew")
        self.table.configure(yscrollcommand=scrollbar.set, xscrollcommand=horizontal.set)
        self.table.bind("<<TreeviewSelect>>", lambda event: self.select_result())
        self.status = tk.StringVar(root, "Ready. Reprinted with permission from SISO Inc.")
        ttk.Label(frame, textvariable=self.status, wraplength=680).grid(row=5, sticky="ew", pady=(8, 0))
        self.refresh()
        self.id_entry.focus_set()

    def refresh(self) -> None:
        for field, box in self.fields.items():
            choices = self.state.choices(field)
            labels = [f"{choice.value} — {choice.description}" for choice in choices]
            box.configure(values=labels)
            selected = getattr(self.state.entity, field.value)
            box.set(
                next(label for choice, label in zip(choices, labels, strict=True) if choice.value == selected)
            )
        self.output.set(str(self.state.entity))

    def filter_field(self, field: Field, _event: tk.Event[tk.Misc] | None = None) -> None:
        """Narrow the dropdown by numeric code or description as the user types."""
        if _event is not None and _event.keysym in {"Return", "Escape", "Up", "Down", "Left", "Right", "Tab"}:
            return
        box = self.fields[field]
        query = box.get().casefold()
        labels = [f"{choice.value} — {choice.description}" for choice in self.state.choices(field)]
        box.configure(values=[label for label in labels if query in label.casefold()])

    def load_id(self) -> None:
        try:
            self.state.load(self.id_text.get())
        except ValueError as exc:
            self.status.set(f"Invalid ID: {exc}. Builder unchanged.")
            return
        self.refresh()
        self.status.set(f"Loaded {self.state.entity}")

    def select_field(self, field: Field, _event: tk.Event[tk.Misc] | None = None) -> None:
        text = self.fields[field].get().split(" — ", 1)[0].strip()
        try:
            if text and (not text.isascii() or not text.isdecimal()):
                raise ValueError("Enter an unsigned decimal code or select a listed label")
            self.state.select(field, int(text) if text else None)
        except ValueError as exc:
            self.status.set(f"Invalid {field.value}: {exc}. Builder unchanged.")
            self.refresh()
            return
        self.refresh()
        self.status.set(f"Updated {field.value}: {self.state.entity}")

    def clear_field(self, field: Field) -> None:
        self.state.select(field, None)
        self.refresh()
        self.status.set(f"Cleared {field.value}")

    def _cancel_search(self) -> None:
        for name in ("_pending_search", "_pending_rows"):
            pending = getattr(self, name)
            if pending is not None:
                self.root.after_cancel(pending)
                setattr(self, name, None)

    def _schedule_search(self, *_args: str) -> None:
        self._cancel_search()
        # Clear stale rows immediately so a click cannot select an older query.
        self.table.delete(*self.table.get_children())
        self.count.set("Searching…" if len(self.query.get()) >= 3 else "Type at least 3 characters")
        self._pending_search = self.root.after(300, self.search)

    def search(self) -> None:
        self._cancel_search()
        self.table.delete(*self.table.get_children())
        results = self.state.search(self.query.get())
        self.count.set(
            f"{results.total:,} results" if len(results.query) >= 3 else "Type at least 3 characters"
        )
        self._insert_rows(0)

    def _insert_rows(self, start: int) -> None:
        self._pending_rows = None
        hits = self.state.results.hits
        stop = min(start + 200, len(hits))
        for index in range(start, stop):
            hit = hits[index]
            self.table.insert("", "end", iid=str(index), values=(str(hit.entity), hit.description))
        if stop < len(hits):
            self._pending_rows = self.root.after(1, lambda: self._insert_rows(stop))

    def select_result(self) -> None:
        selection = self.table.selection()
        if not selection:
            return
        self.state.select_result(int(selection[0]))
        self.id_text.set(str(self.state.entity))
        self.refresh()
        self.status.set(f"Loaded search result: {self.state.entity}")

    def copy_id(self) -> None:
        import tkinter as tk

        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(str(self.state.entity))
        except tk.TclError as exc:
            self.status.set(f"Clipboard unavailable: {exc}. Select and copy the output field manually.")
            return
        self.status.set(f"Copied {self.state.entity} to clipboard")

    def reset(self) -> None:
        self.query.set("")
        self._cancel_search()
        self.state.reset()
        self.id_text.set("")
        self.table.delete(*self.table.get_children())
        self.count.set("Type at least 3 characters")
        self.refresh()
        self.status.set("All fields and search results cleared")

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._cancel_search()
        self.root.destroy()


def launch(api: EntityTypeAPI | None = None) -> None:
    """Run the desktop picker; raise RuntimeError if Tk or a display is unavailable."""
    try:
        import tkinter as tk
    except ImportError as exc:
        raise RuntimeError(
            "The picker requires Tkinter. Install your Python/OS Tk support (e.g. python3-tk)."
        ) from exc
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        raise RuntimeError(
            f"Cannot open the picker display. Run in a graphical desktop session: {exc}"
        ) from exc
    try:
        PickerWindow(root, api)
        root.mainloop()
    finally:
        # mainloop can return after quit(), or after destroy() from close().
        try:
            root.destroy()
        except tk.TclError:
            pass


def main() -> int:
    """Console entry point for the optional desktop picker."""
    try:
        launch()
    except RuntimeError as exc:
        print(f"dis-entity-types GUI: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

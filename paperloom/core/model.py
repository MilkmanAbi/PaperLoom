"""
The design-time model, deliberately decoupled from live Qt widgets.

A DesignWidget is a plain, serializable record of "what the user placed and how
they configured it" - component id, object name, geometry, property values. The
live QWidget on the canvas is a *rendering* of this record, not the record
itself. This separation is what lets the same model feed the canvas, the object
tree, every codegen backend, and the .page.json on disk without any of them
depending on Qt being live (tests included).

A DesignPage is one skeleton (spec §7.1): a titled collection of DesignWidgets.
A Project is a collection of pages plus target-language metadata (§2.2a).
"""
from __future__ import annotations
import itertools
from dataclasses import dataclass, field, asdict


_id_counters: dict[str, itertools.count] = {}


def unique_object_name(component_id: str) -> str:
    """button -> button, button_2, button_3 ... unique per component id per run."""
    counter = _id_counters.setdefault(component_id, itertools.count(1))
    n = next(counter)
    return component_id if n == 1 else f"{component_id}_{n}"


@dataclass
class DesignWidget:
    component_id: str                       # which library component this is
    object_name: str                        # unique instance name, used in codegen
    x: int = 0
    y: int = 0
    width: int = 120
    height: int = 32
    properties: dict = field(default_factory=dict)   # {prop_name: value}
    # Overrides for real Qt properties the component didn't declare (the "expert
    # peels back to Qt" layer). Applied to the live widget and emitted into
    # generated code as setProperty() calls, so editing them is not decorative.
    qt_props: dict = field(default_factory=dict)     # {qt_property_name: value}
    # Layout membership: if set, this widget belongs to a named layout group
    # rather than using absolute geometry. layout_id references a LayoutGroup
    # on the page; layout_row/col are position within that group. When
    # layout_id is None (default), codegen emits setGeometry as before.
    layout_id: str | None = None
    layout_row: int = 0
    layout_col: int = 0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "DesignWidget":
        # tolerate older page files that predate a field
        known = {f for f in ("component_id", "object_name", "x", "y",
                             "width", "height", "properties", "qt_props",
                             "layout_id", "layout_row", "layout_col")}
        return cls(**{k: v for k, v in data.items() if k in known})


@dataclass
class LayoutGroup:
    """A named layout container. Widgets reference this via layout_id.
    kind is one of: vbox, hbox, grid, form."""
    id: str
    kind: str = "vbox"           # vbox | hbox | grid | form
    parent: str | None = None    # object_name of the parent widget, or None for the central layout
    spacing: int = 6
    margins: tuple = (9, 9, 9, 9)  # left, top, right, bottom


@dataclass
class SignalConnection:
    """A signal/slot connection between two widgets (or widget+window)."""
    sender: str              # object_name
    signal: str              # e.g. "clicked()"
    receiver: str            # object_name or "MainWindow"
    slot: str                # e.g. "close()"


@dataclass
class DesignPage:
    name: str                               # e.g. "MainWindow"
    title: str = "My App"
    width: int = 900
    height: int = 600
    widgets: list[DesignWidget] = field(default_factory=list)
    layouts: list[LayoutGroup] = field(default_factory=list)
    connections: list[SignalConnection] = field(default_factory=list)
    tab_order: list[str] = field(default_factory=list)  # ordered object_names

    def add(self, widget: DesignWidget) -> DesignWidget:
        self.widgets.append(widget)
        return widget

    def remove(self, widget: DesignWidget) -> None:
        if widget in self.widgets:
            self.widgets.remove(widget)

    def to_dict(self) -> dict:
        d = {
            "name": self.name, "title": self.title,
            "width": self.width, "height": self.height,
            "widgets": [w.to_dict() for w in self.widgets],
        }
        if self.layouts:
            d["layouts"] = [asdict(lg) for lg in self.layouts]
        if self.connections:
            d["connections"] = [asdict(c) for c in self.connections]
        if self.tab_order:
            d["tab_order"] = self.tab_order
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "DesignPage":
        page = cls(name=data["name"], title=data.get("title", "My App"),
                   width=data.get("width", 900), height=data.get("height", 600))
        page.widgets = [DesignWidget.from_dict(w) for w in data.get("widgets", [])]
        page.layouts = [LayoutGroup(**lg) for lg in data.get("layouts", [])]
        page.connections = [SignalConnection(**c) for c in data.get("connections", [])]
        page.tab_order = data.get("tab_order", [])
        return page


@dataclass
class Project:
    name: str = "untitled"
    target: str = "pyside6"                  # "pyside6" | "cpp" (spec §2.2a)
    accent: str = "#6B7CFF"
    pages: list[DesignPage] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "name": self.name, "target": self.target, "accent": self.accent,
            "pages": [p.name for p in self.pages],
        }

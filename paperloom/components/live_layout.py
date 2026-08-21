"""
Builds real, live QLayout objects for a page's LayoutGroups (core/model.py) -
the imperative sibling to what codegen/pyside_backend.py's layout-emission
loop already does. That loop (lines ~155-186 of pyside_backend.py) *emits
Python source text* creating QVBoxLayout/QHBoxLayout/QGridLayout/QFormLayout,
setting spacing/margins, and addWidget()/addRow()-ing members in
layout_row/layout_col order. This module walks the exact same source of
truth (page.layouts + DesignWidget.layout_id/layout_row/layout_col) the same
way, but constructs real Qt objects instead of text - so Quick Preview
(ui/quick_preview.py) can be layout-aware: once a widget is added to a real
QLayout, Qt takes over its geometry, so resizing the preview window actually
reflows layout-managed content the way the final generated app would.

Deliberately NOT used by DesignCanvas - the canvas stays absolute-position-
only by design (it's the direct-manipulation drag/resize surface; dragging a
handle only makes sense against a fixed geometry). This makes three render
modes of one shared model: canvas (absolute, editable), Quick Preview
(absolute + real layouts, interactive), codegen (absolute + real layouts,
emitted as text) - the fidelity invariant holds at the level of "how a
widget looks and behaves" (one factory, one set of templates), while each
mode composes that output differently for its own purpose.
"""
from __future__ import annotations
from PySide6.QtWidgets import QVBoxLayout, QHBoxLayout, QGridLayout, QFormLayout, QWidget

from ..core.model import DesignPage

_LAYOUT_CLASSES = {
    "vbox": QVBoxLayout, "hbox": QHBoxLayout,
    "grid": QGridLayout, "form": QFormLayout,
}


def apply_layouts(page: DesignPage, live_by_name: dict[str, QWidget], root: QWidget) -> None:
    """Attach real QLayouts to already-instantiated live widgets.

    `live_by_name`: {object_name: QWidget} for every widget already built on
    this page (via components.factory.instantiate, absolute geometry already
    set). `root`: the container a LayoutGroup with no `parent` attaches to.

    Widgets with no layout_id are left exactly as instantiate() placed them
    (absolute x/y/width/height) - only layout-managed widgets change here,
    matching codegen's own "only emitted when present, zero change otherwise"
    behaviour.
    """
    if not page.layouts:
        return
    for group in page.layouts:
        layout_cls = _LAYOUT_CLASSES.get(group.kind, QVBoxLayout)
        parent_widget = live_by_name.get(group.parent) if group.parent else root
        if parent_widget is None:
            continue   # the declared parent widget wasn't instantiated - skip defensively
        layout = layout_cls(parent_widget)
        layout.setSpacing(int(group.spacing))
        left, top, right, bottom = group.margins
        layout.setContentsMargins(int(left), int(top), int(right), int(bottom))

        members = sorted(
            (dw for dw in page.widgets if dw.layout_id == group.id),
            key=lambda w: (w.layout_row, w.layout_col))
        for dw in members:
            widget = live_by_name.get(dw.object_name)
            if widget is None:
                continue
            if group.kind == "grid":
                layout.addWidget(widget, dw.layout_row, dw.layout_col)
            elif group.kind == "form":
                layout.addRow(widget)
            else:
                layout.addWidget(widget)

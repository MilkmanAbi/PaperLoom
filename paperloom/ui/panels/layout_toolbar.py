"""
Layout toolbar (LONG-MARCH-BACKLOG.md 2j-1, the biggest documented gap: the
model - LayoutGroup, DesignWidget.layout_id/row/col - and both codegen
backends already fully support layouts; there was just no editor UI). Pick a
target layout from the dropdown (existing groups on the current page, or
"New Vertical/Horizontal/Grid/Form"), Assign puts the canvas-selected widget
into it, Remove clears it back to absolute positioning. Spacing/margins edit
whichever group is currently targeted in the dropdown.

Single-selection-driven for now: real "select several widgets, wrap them in
a layout" (Qt Designer's Lay Out Horizontally/Vertically/Grid toolbar
buttons) needs canvas multi-selection, which doesn't exist yet
(main_window.dispatch's "selection.all" is still a stub). This toolbar is
forward-compatible with that - assigning one widget at a time to a named
group already produces exactly the LayoutGroup/layout_id data a future
"wrap selection" action would also produce, just one widget at a time.

Model mutations here are direct, not undo-stack Commands - matching how
every other model edit in the app already works (canvas.apply_property,
set_geometry_of_selected, delete_selected, etc. are all direct too; only
widget placement is undo-tracked today). Layouts stay consistent with that,
rather than being the one feature with different undo behaviour from
everything else.
"""
from __future__ import annotations
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QWidget, QLabel, QComboBox, QSpinBox, QToolBar

from ... import theme
from .. import icons

_KIND_LABELS = {"vbox": "Vertical", "hbox": "Horizontal", "grid": "Grid", "form": "Form"}
_NEW_KINDS = [
    ("new:vbox", "New Vertical Layout"), ("new:hbox", "New Horizontal Layout"),
    ("new:grid", "New Grid Layout"), ("new:form", "New Form Layout"),
]


class LayoutToolbar(QWidget):
    """Not shown itself - populate_toolbar() copies its controls into a real
    QToolBar (same convention as panels/tools_toolbar.py's ToolsToolbar), so
    the toolbar gets Qt's native movable/floatable/dockable behaviour."""

    assignRequested = Signal(str, int, int)   # target key, row, col (row/col ignored unless grid)
    removeRequested = Signal()
    spacingChanged = Signal(int)
    marginsChanged = Signal(int, int, int, int)
    targetChanged = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._toolbar = None
        self._grid_group_ids = set()

    def populate_toolbar(self, toolbar: QToolBar):
        toolbar.addWidget(QLabel("  Layout  "))
        self.target_combo = QComboBox()
        self.target_combo.setMinimumWidth(170)
        self.target_combo.currentIndexChanged.connect(self._on_target_changed)
        toolbar.addWidget(self.target_combo)

        self.assign_action = QAction(
            icons.icon("link", theme.INK_ON_DARK_MUTED, 16), "Assign selected", toolbar)
        self.assign_action.setToolTip("Put the selected widget into this layout")
        self.assign_action.triggered.connect(self._emit_assign)
        toolbar.addAction(self.assign_action)

        self.remove_action = QAction(
            icons.icon("x", theme.INK_ON_DARK_MUTED, 16), "Remove from layout", toolbar)
        self.remove_action.setToolTip("Take the selected widget back out of its layout")
        self.remove_action.triggered.connect(self.removeRequested.emit)
        toolbar.addAction(self.remove_action)

        toolbar.addSeparator()

        self.row_label = QLabel(" Row ")
        toolbar.addWidget(self.row_label)
        self.row_spin = QSpinBox()
        self.row_spin.setRange(0, 99)
        self.row_spin.setFixedWidth(46)
        toolbar.addWidget(self.row_spin)
        self.col_label = QLabel(" Col ")
        toolbar.addWidget(self.col_label)
        self.col_spin = QSpinBox()
        self.col_spin.setRange(0, 99)
        self.col_spin.setFixedWidth(46)
        toolbar.addWidget(self.col_spin)

        toolbar.addSeparator()
        toolbar.addWidget(QLabel(" Spacing "))
        self.spacing_spin = QSpinBox()
        self.spacing_spin.setRange(0, 64)
        self.spacing_spin.setFixedWidth(46)
        self.spacing_spin.valueChanged.connect(self.spacingChanged.emit)
        toolbar.addWidget(self.spacing_spin)

        toolbar.addWidget(QLabel(" Margins "))
        self.margin_spins = []
        for label in ("L", "T", "R", "B"):
            toolbar.addWidget(QLabel(label))
            sb = QSpinBox()
            sb.setRange(0, 64)
            sb.setFixedWidth(38)
            sb.valueChanged.connect(self._emit_margins)
            self.margin_spins.append(sb)
            toolbar.addWidget(sb)

        self._toolbar = toolbar
        self._set_grid_fields_visible(False)
        self.set_enabled_for_selection(False)
        return toolbar

    # --- outgoing --------------------------------------------------------
    def _emit_assign(self):
        key = self.target_combo.currentData()
        if key:
            self.assignRequested.emit(key, self.row_spin.value(), self.col_spin.value())

    def _emit_margins(self):
        vals = [sb.value() for sb in self.margin_spins]
        self.marginsChanged.emit(*vals)

    def _on_target_changed(self, _index):
        key = self.target_combo.currentData()
        is_grid = key == "new:grid" or key in self._grid_group_ids
        self._set_grid_fields_visible(is_grid)
        self.targetChanged.emit(key or "")

    def _set_grid_fields_visible(self, visible):
        for w in (self.row_label, self.row_spin, self.col_label, self.col_spin):
            w.setVisible(visible)

    # --- incoming (main_window keeps this in sync) ------------------------
    def set_enabled_for_selection(self, has_selection):
        self.assign_action.setEnabled(has_selection)
        self.remove_action.setEnabled(has_selection)

    def refresh_targets(self, page, current_group_id=None):
        """Rebuild the dropdown from this page's LayoutGroups + the 4 'New
        ...' entries. Call whenever the active page or its layouts change."""
        self.target_combo.blockSignals(True)
        self.target_combo.clear()
        self._grid_group_ids = set()
        for group in page.layouts:
            label = f"{_KIND_LABELS.get(group.kind, group.kind)} · {group.id}"
            if group.parent:
                label += f"  (in {group.parent})"
            self.target_combo.addItem(label, group.id)
            if group.kind == "grid":
                self._grid_group_ids.add(group.id)
        if page.layouts:
            self.target_combo.insertSeparator(self.target_combo.count())
        for key, label in _NEW_KINDS:
            self.target_combo.addItem(label, key)
        if current_group_id is not None:
            idx = self.target_combo.findData(current_group_id)
            if idx >= 0:
                self.target_combo.setCurrentIndex(idx)
        self.target_combo.blockSignals(False)
        self._on_target_changed(self.target_combo.currentIndex())

    def set_spacing_margins(self, spacing, margins):
        self.spacing_spin.blockSignals(True)
        self.spacing_spin.setValue(int(spacing))
        self.spacing_spin.blockSignals(False)
        for sb, v in zip(self.margin_spins, margins):
            sb.blockSignals(True)
            sb.setValue(int(v))
            sb.blockSignals(False)

    def restyle_toolbar(self):
        if self._toolbar is None:
            return
        self.assign_action.setIcon(icons.icon("link", theme.INK_ON_DARK_MUTED, 16))
        self.remove_action.setIcon(icons.icon("x", theme.INK_ON_DARK_MUTED, 16))

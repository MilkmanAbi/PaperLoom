"""
The full, live Qt property table (spec §22) - the Qt Designer property editor,
the real replacement for the old QMessageBox text dump. Reads every editable
property off the live widget via core.introspect, renders a typed editor per
property, and emits an edit when the user changes one. Filterable by name.

Edits are applied to the live widget and persisted to the model's qt_props by
the window, then emitted into generated code - so this is genuinely editable,
not a read-only dump.
"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QFormLayout, QLabel, QLineEdit, QSpinBox,
    QDoubleSpinBox, QCheckBox, QComboBox
)

from ... import theme
from ...core import introspect


class QtPropertyTable(QWidget):
    propertyEdited = Signal(str, object)      # qt property name, new value

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows = []          # (name, label_widget, editor_widget)
        self._filter = ""
        self._building = False

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self._form_host = QWidget()
        self._form = QFormLayout(self._form_host)
        self._form.setContentsMargins(0, 0, 0, 0)
        self._form.setSpacing(5)
        self._form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        self._form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        lay.addWidget(self._form_host)
        self._empty = QLabel("No live widget.")
        self._empty.setObjectName("qtEmpty")
        lay.addWidget(self._empty)
        self.restyle()

    def set_widget(self, live_widget):
        self._clear()
        if live_widget is None:
            self._empty.setVisible(True)
            return
        self._empty.setVisible(False)
        self._building = True
        for prop in introspect.editable_properties(live_widget):
            editor = self._editor_for(prop)
            if editor is None:
                continue
            label = QLabel(prop.name)
            label.setToolTip(f"{prop.name} ({prop.type_name})")
            self._form.addRow(label, editor)
            self._rows.append((prop.name.lower(), label, editor))
        self._building = False
        self.apply_filter(self._filter)

    def apply_filter(self, text):
        self._filter = (text or "").strip().lower()
        for name, label, editor in self._rows:
            show = self._filter in name
            label.setVisible(show)
            editor.setVisible(show)

    def _clear(self):
        while self._form.count():
            item = self._form.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        self._rows = []

    def _editor_for(self, prop):
        kind = prop.kind
        if kind == "bool":
            w = QCheckBox()
            w.setChecked(bool(prop.value))
            w.toggled.connect(lambda v, n=prop.name: self._emit(n, v))
            return w
        if kind == "int":
            w = QSpinBox(); w.setRange(-2_000_000, 2_000_000)
            try:
                w.setValue(int(prop.value))
            except (TypeError, ValueError):
                w.setValue(0)
            w.valueChanged.connect(lambda v, n=prop.name: self._emit(n, v))
            return w
        if kind == "number":
            w = QDoubleSpinBox(); w.setRange(-1e6, 1e6); w.setDecimals(3)
            try:
                w.setValue(float(prop.value))
            except (TypeError, ValueError):
                w.setValue(0.0)
            w.valueChanged.connect(lambda v, n=prop.name: self._emit(n, v))
            return w
        if kind == "enum":
            w = QComboBox()
            w.addItems(list(prop.enum_values))
            cur = str(prop.value).split(".")[-1]
            i = w.findText(cur)
            if i >= 0:
                w.setCurrentIndex(i)
            w.currentTextChanged.connect(lambda v, n=prop.name: self._emit(n, v))
            return w
        # string / color / other -> a line edit
        w = QLineEdit(str(prop.value) if prop.value is not None else "")
        w.editingFinished.connect(lambda e=w, n=prop.name: self._emit(n, e.text()))
        return w

    def _emit(self, name, value):
        if not self._building:
            self.propertyEdited.emit(name, value)

    def restyle(self):
        self.setStyleSheet(f"""
            QLabel {{ color: {theme.INK_ON_DARK_MUTED}; font-size: 11px; }}
            QLabel#qtEmpty {{ color: {theme.INK_ON_DARK_FAINT}; font-size: 11px; padding: 6px 2px; }}
            QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
                background: {theme.ACTIVITY_BAR}; border: 1px solid {theme.BORDER_DARK};
                border-radius: {theme.RADIUS_SM}px; padding: 2px 6px;
                color: {theme.INK_ON_DARK}; font-size: 11px; }}
            QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
                border: 1px solid {theme.ACCENT}; }}
            QComboBox QAbstractItemView {{ background: {theme.SIDE_PANEL};
                color: {theme.INK_ON_DARK}; selection-background-color: {theme.ACCENT_DIM};
                border: 1px solid {theme.BORDER_DARK}; }}
            QCheckBox {{ color: {theme.INK_ON_DARK}; }}
        """)

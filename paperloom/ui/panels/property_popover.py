"""
Contextual quick-property popover (spec §1.2 / §3.3). Renders one editor per
entry in the selected component's `quick_properties` list (§4.3) - so it's driven
by the component schema, not hardcoded per widget type. Editing a field routes
through canvas.apply_property, which updates the model and the live widget
together.
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QFormLayout, QLineEdit

from ... import theme


class PropertyPopover(QFrame):
    def __init__(self, canvas):
        super().__init__(canvas, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint)
        self.canvas = canvas
        self.restyle()
        self._layout = QFormLayout(self)
        self._layout.setContentsMargins(8, 8, 8, 8)
        self._layout.setSpacing(4)
        self._editors = {}       # prop_name -> QLineEdit
        self._model = None
        self.hide()

    def restyle(self):
        """Chrome tokens, not canvas tokens - the popover is part of PaperLoom's
        UI, so it must follow the editor theme (this was showing light-on-dark)."""
        self.setStyleSheet(
            f"QFrame {{ background: {theme.SIDE_PANEL}; border: 1px solid {theme.BORDER_DARK};"
            f" border-radius: {theme.RADIUS_SM}px; }}"
            f"QLabel {{ color: {theme.INK_ON_DARK_MUTED}; font-size: 11px; }}"
            f"QLineEdit {{ background: {theme.ACTIVITY_BAR}; color: {theme.INK_ON_DARK};"
            f" border: 1px solid {theme.BORDER_DARK};"
            f" border-radius: {theme.RADIUS_SM}px; padding: 4px 8px; }}"
            f"QLineEdit:focus {{ border: 1px solid {theme.ACCENT}; }}"
        )

    def _rebuild_for(self, component):
        # clear old rows
        while self._layout.rowCount():
            self._layout.removeRow(0)
        self._editors.clear()
        for prop_name in component.quick_properties:
            spec = component.property(prop_name)
            label = spec.name.replace("_", " ").capitalize() if spec else prop_name
            editor = QLineEdit()
            editor.textChanged.connect(lambda text, p=prop_name: self._on_changed(p, text))
            self._layout.addRow(label, editor)
            self._editors[prop_name] = editor

    def show_for(self, model, live_widget):
        if model is None:
            self.hide()
            return
        component = self.canvas.registry.get(model.component_id)
        if component is None or not component.quick_properties:
            self.hide()
            return
        if self._model is None or self._model.component_id != model.component_id \
                or set(self._editors) != set(component.quick_properties):
            self._rebuild_for(component)
        self._model = model
        for prop_name, editor in self._editors.items():
            editor.blockSignals(True)
            editor.setText(str(model.properties.get(prop_name, "")))
            editor.blockSignals(False)
        anchor = live_widget.mapTo(self.canvas, live_widget.rect().bottomLeft())
        global_pos = self.canvas.mapToGlobal(anchor)
        self.adjustSize()
        self.move(global_pos.x(), global_pos.y() + 6)
        self.show()
        self.raise_()

    def hide_popover(self):
        self._model = None
        self.hide()

    def _on_changed(self, prop_name, text):
        if self._model is not None:
            self.canvas.apply_property(prop_name, text)

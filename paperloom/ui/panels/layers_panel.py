"""
Layers panel (spec §3.4: the opt-in object/hierarchy tree). Lists every widget
on the current page as a flat row; selecting a row selects that widget on the
canvas, and vice-versa. Kept flat for now (freeform canvas has no nesting yet);
becomes a real tree when container widgets land.
"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem
)

from ... import theme


class LayersPanel(QWidget):
    widgetSelected = Signal(object)   # emits the DesignWidget, or None

    def __init__(self, parent=None):
        super().__init__(parent)
        self.page = None
        self.setObjectName("LayersPanel")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.restyle()

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        hdr = QLabel("LAYERS")
        hdr.setObjectName("hdr")
        lay.addWidget(hdr)

        self.list = QListWidget()
        self.list.currentRowChanged.connect(self._on_row_changed)
        lay.addWidget(self.list, 1)

        self._empty = QLabel("No widgets on this page yet.")
        self._empty.setObjectName("empty")
        lay.addWidget(self._empty)

        self._widgets = []

    def set_page(self, page):
        self.page = page
        self.refresh()

    def refresh(self):
        self.list.blockSignals(True)
        self.list.clear()
        self._widgets = list(self.page.widgets) if self.page else []
        for dw in self._widgets:
            self.list.addItem(QListWidgetItem("  " + dw.object_name))
        self.list.blockSignals(False)
        has = bool(self._widgets)
        self.list.setVisible(has)
        self._empty.setVisible(not has)

    def select_widget(self, dw):
        """Reflect a canvas-side selection in the list without re-emitting."""
        self.list.blockSignals(True)
        if dw is None:
            self.list.clearSelection()
        else:
            for i, w in enumerate(self._widgets):
                if w is dw:
                    self.list.setCurrentRow(i)
                    break
        self.list.blockSignals(False)

    def _on_row_changed(self, row):
        if 0 <= row < len(self._widgets):
            self.widgetSelected.emit(self._widgets[row])

    def restyle(self):
        self.setStyleSheet(f"""
            #LayersPanel {{ background: {theme.SIDE_PANEL};
                            border-right: 1px solid {theme.BORDER_DARK}; }}
            QLabel#hdr {{ color: {theme.INK_ON_DARK_MUTED}; font-size: 11px;
                          font-weight: 600; letter-spacing: 0.5px; padding: 10px 12px; }}
            QListWidget {{ background: transparent; border: none; outline: none; }}
            QListWidget::item {{ height: {theme.ROW_HEIGHT}px; color: {theme.INK_ON_DARK};
                                 padding-left: 12px; border: none; }}
            QListWidget::item:hover {{ background: {theme.ACTIVITY_BAR}; }}
            QListWidget::item:selected {{ background: {theme.ACCENT_DIM};
                                          border-left: 2px solid {theme.ACCENT}; }}
            QLabel#empty {{ color: {theme.INK_ON_DARK_FAINT}; font-size: 11px; padding: 16px 12px; }}
        """)

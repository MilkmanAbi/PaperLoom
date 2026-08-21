"""
A collapsible section (Qt Designer's grouped property sheet, PaperDesign's tree
pattern): a 30px header row with a chevron that rotates on expand, and a body
that shows/hides. Used to build the grouped property editor so the panel reads
as clear collapse/expand groups instead of one flat stack of rows.
"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QToolButton

from ... import theme
from .. import icons


class CollapsibleSection(QWidget):
    toggled = Signal(bool)

    def __init__(self, title, expanded=True, parent=None):
        super().__init__(parent)
        self._title = title
        self._expanded = expanded

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._head = QToolButton()
        self._head.setObjectName("secHead")
        self._head.setCheckable(True)
        self._head.setChecked(expanded)
        self._head.setCursor(Qt.CursorShape.PointingHandCursor)
        self._head.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self._head.setText(title.upper())
        self._head.clicked.connect(self._on_click)
        outer.addWidget(self._head)

        self._body = QWidget()
        self._body_lay = QVBoxLayout(self._body)
        self._body_lay.setContentsMargins(12, 4, 12, 10)
        self._body_lay.setSpacing(6)
        outer.addWidget(self._body)

        self._restyle_head()
        self._body.setVisible(expanded)

    def body(self):
        return self._body_lay

    def add(self, widget):
        self._body_lay.addWidget(widget)

    def set_expanded(self, on):
        self._expanded = on
        self._head.setChecked(on)
        self._body.setVisible(on)
        self._restyle_head()

    def is_expanded(self):
        return self._expanded

    def _on_click(self):
        self.set_expanded(self._head.isChecked())
        self.toggled.emit(self._expanded)

    def _restyle_head(self):
        glyph = "chevron-down" if self._expanded else "chevron-right"
        self._head.setIcon(icons.icon(glyph, theme.INK_ON_DARK_MUTED, 14))
        self._head.setStyleSheet(f"""
            QToolButton#secHead {{ background: {theme.ACTIVITY_BAR};
                color: {theme.INK_ON_DARK_MUTED}; border: none;
                border-top: 1px solid {theme.BORDER_DARK};
                padding: 7px 10px; font-size: 10px; font-weight: 700;
                letter-spacing: 0.6px; text-align: left; }}
            QToolButton#secHead:hover {{ color: {theme.INK_ON_DARK}; }}
        """)

    def restyle(self):
        self._restyle_head()

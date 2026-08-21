"""
Pages panel (spec §7.1: the multi-page / multi-skeleton model). Lists the
project's pages (each a skeleton), lets you add a new one, and switching the
active page swaps what the canvas edits. A whole new screen is a new page here;
element edits stay within the current page.
"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QPushButton, QInputDialog
)

from ... import theme
from .. import icons


class _PanelHeader(QWidget):
    addRequested = Signal()

    def __init__(self, title):
        super().__init__()
        self.setFixedHeight(34)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 0, 6, 0)
        label = QLabel(title.upper())
        label.setStyleSheet(
            f"color: {theme.INK_ON_DARK_MUTED}; font-size: 11px; font-weight: 600;"
            " letter-spacing: 0.5px;")
        lay.addWidget(label)
        lay.addStretch(1)
        add = QPushButton()
        add.setIcon(icons.icon("plus", theme.INK_ON_DARK_MUTED, 16))
        add.setFixedSize(24, 24)
        add.setCursor(Qt.CursorShape.PointingHandCursor)
        add.setToolTip("New page")
        add.setStyleSheet(
            f"QPushButton {{ background: transparent; border: none; border-radius: {theme.RADIUS_SM}px; }}"
            f"QPushButton:hover {{ background: {theme.ACTIVITY_BAR}; }}")
        add.clicked.connect(self.addRequested.emit)
        lay.addWidget(add)


class PagesPanel(QWidget):
    pageSelected = Signal(int)      # index into project.pages
    pageAddRequested = Signal(str)  # new page name

    def __init__(self, project, parent=None):
        super().__init__(parent)
        self.project = project
        self.setObjectName("PagesPanel")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.restyle()

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        header = _PanelHeader("Pages")
        header.addRequested.connect(self._prompt_add)
        lay.addWidget(header)

        self.list = QListWidget()
        self.list.currentRowChanged.connect(self._on_row_changed)
        lay.addWidget(self.list, 1)

        self.refresh()

    def refresh(self):
        self.list.blockSignals(True)
        self.list.clear()
        for page in self.project.pages:
            item = QListWidgetItem("  " + page.name)
            self.list.addItem(item)
        if self.project.pages:
            self.list.setCurrentRow(0)
        self.list.blockSignals(False)

    def _on_row_changed(self, row):
        if row >= 0:
            self.pageSelected.emit(row)

    def _prompt_add(self):
        name, ok = QInputDialog.getText(self, "New page", "Page name:")
        if ok and name.strip():
            self.pageAddRequested.emit(name.strip())

    def restyle(self):
        self.setStyleSheet(f"""
            #PagesPanel {{ background: {theme.SIDE_PANEL};
                           border-right: 1px solid {theme.BORDER_DARK}; }}
            QListWidget {{ background: transparent; border: none; outline: none; }}
            QListWidget::item {{ height: {theme.ROW_HEIGHT}px; color: {theme.INK_ON_DARK};
                                 padding-left: 12px; border: none; }}
            QListWidget::item:hover {{ background: {theme.ACTIVITY_BAR}; }}
            QListWidget::item:selected {{ background: {theme.ACCENT_DIM};
                                          border-left: 2px solid {theme.ACCENT}; }}
        """)

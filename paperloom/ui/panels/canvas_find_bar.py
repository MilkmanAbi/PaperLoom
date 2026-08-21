"""
Canvas find bar (spec §2b, Long March). A small floating bar over the canvas
that finds widgets by object name or their text-like properties - "universal
Ctrl-F", the canvas half of it (the terminal has its own find-in-output bar;
see ui/panels/terminal.py). Ctrl-F routes to whichever surface has focus.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLineEdit, QLabel, QToolButton, QFrame

from ... import theme


class CanvasFindBar(QFrame):
    queryChanged = Signal(str)
    stepRequested = Signal(int)     # +1 next, -1 previous
    closed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("canvasFindBar")
        self.setFrameShape(QFrame.Shape.NoFrame)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 6, 8, 6)
        lay.setSpacing(4)

        self.box = QLineEdit()
        self.box.setObjectName("canvasFindBox")
        self.box.setPlaceholderText("Find widget by name or text…")
        self.box.setMinimumWidth(220)
        self.box.textChanged.connect(self.queryChanged.emit)
        self.box.returnPressed.connect(lambda: self.stepRequested.emit(1))
        self.box.installEventFilter(self)
        lay.addWidget(self.box)

        self.status = QLabel("")
        self.status.setObjectName("canvasFindStatus")
        lay.addWidget(self.status)

        prev_btn = QToolButton(); prev_btn.setObjectName("canvasFindBtn")
        prev_btn.setText("↑"); prev_btn.setToolTip("Previous match (Shift+Enter)")
        prev_btn.clicked.connect(lambda: self.stepRequested.emit(-1))
        lay.addWidget(prev_btn)

        next_btn = QToolButton(); next_btn.setObjectName("canvasFindBtn")
        next_btn.setText("↓"); next_btn.setToolTip("Next match (Enter)")
        next_btn.clicked.connect(lambda: self.stepRequested.emit(1))
        lay.addWidget(next_btn)

        close_btn = QToolButton(); close_btn.setObjectName("canvasFindBtn")
        close_btn.setText("✕"); close_btn.setToolTip("Close (Esc)")
        close_btn.clicked.connect(self.close_bar)
        lay.addWidget(close_btn)

        self.restyle()
        self.hide()

    def open(self):
        self.show()
        self.raise_()
        self.reposition()
        self.box.setFocus()
        self.box.selectAll()

    def close_bar(self):
        self.hide()
        self.closed.emit()

    def set_status(self, index: int, total: int):
        self.status.setText(f"{index}/{total}" if total else "0/0")

    def reposition(self):
        if not self.parentWidget():
            return
        parent_w = self.parentWidget().width()
        self.adjustSize()
        x = max(8, parent_w - self.width() - 16)
        self.move(x, 8)

    def eventFilter(self, obj, event):
        if obj is self.box and event.type() == event.Type.KeyPress:
            if event.key() == Qt.Key.Key_Escape:
                self.close_bar()
                return True
            if (event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
                    and event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
                self.stepRequested.emit(-1)
                return True
        return super().eventFilter(obj, event)

    def restyle(self):
        self.setStyleSheet(f"""
            #canvasFindBar {{ background: {theme.SIDE_PANEL};
                border: 1px solid {theme.ACCENT}; border-radius: 8px; }}
            QLineEdit#canvasFindBox {{ background: {theme.ACTIVITY_BAR};
                color: {theme.INK_ON_DARK}; border: 1px solid {theme.BORDER_DARK};
                border-radius: {theme.RADIUS_SM}px; padding: 4px 8px; font-size: 12px; }}
            QLineEdit#canvasFindBox:focus {{ border-color: {theme.ACCENT}; }}
            QLabel#canvasFindStatus {{ color: {theme.INK_ON_DARK_FAINT}; font-size: 11px; }}
            QToolButton#canvasFindBtn {{ background: transparent; color: {theme.INK_ON_DARK_MUTED};
                border: 1px solid {theme.BORDER_DARK}; border-radius: {theme.RADIUS_SM}px;
                padding: 2px 8px; font-size: 11px; }}
            QToolButton#canvasFindBtn:hover {{ color: {theme.INK_ON_DARK}; border-color: {theme.ACCENT}; }}
        """)

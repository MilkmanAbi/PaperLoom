"""
Floating / pinnable quick-tools toolbar (spec §12.6, AutoCAD-style). Alignment,
distribution, snap toggle and z-order in one compact strip that can float over
the canvas or pin into the layout. Emits command ids shared with the menu bar.
"""
from PySide6.QtCore import Qt, Signal, QPoint
from PySide6.QtWidgets import QWidget, QHBoxLayout, QPushButton, QFrame, QLabel

from ... import theme
from .. import icons


class ToolsToolbar(QWidget):
    command = Signal(str)
    pinToggled = Signal(bool)

    TOOLS = [
        ("align.left", "align-left", "Align left"),
        ("align.center", "align-center-h", "Align center"),
        ("align.right", "align-right", "Align right"),
        None,
        ("align.top", "align-top", "Align top"),
        ("align.middle", "align-center-v", "Align middle"),
        ("align.bottom", "align-bottom", "Align bottom"),
        None,
        ("selection.front", "bring-front", "Bring to front"),
        ("selection.back", "send-back", "Send to back"),
        None,
        ("view.toggle_snap", "magnet", "Toggle snap"),
        ("view.toggle_grid", "grid", "Toggle grid"),
        None,
        ("edit.duplicate", "copy", "Duplicate"),
        ("edit.delete", "trash", "Delete"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ToolsToolbar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._pinned = True
        self._drag_from = None

        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 4, 6, 4)
        lay.setSpacing(2)

        self._grip = QLabel("⠿")
        self._grip.setObjectName("grip")
        self._grip.setCursor(Qt.CursorShape.SizeAllCursor)
        lay.addWidget(self._grip)

        for entry in self.TOOLS:
            if entry is None:
                sep = QFrame(); sep.setFrameShape(QFrame.Shape.VLine)
                sep.setFixedHeight(16); sep.setStyleSheet(f"color: {theme.BORDER_DARK};")
                lay.addWidget(sep)
                continue
            cmd, icon_name, tip = entry
            b = QPushButton()
            b.setIcon(icons.icon(icon_name, theme.INK_ON_DARK_MUTED, 15))
            b.setToolTip(tip)
            b.setFixedSize(26, 26)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _=False, c=cmd: self.command.emit(c))
            lay.addWidget(b)

        lay.addStretch(1)
        self._pin = QPushButton("Pin")
        self._pin.setCheckable(True); self._pin.setChecked(True)
        self._pin.setObjectName("pin")
        self._pin.setCursor(Qt.CursorShape.PointingHandCursor)
        self._pin.clicked.connect(self._toggle_pin)
        lay.addWidget(self._pin)

        self.restyle()

    def populate_toolbar(self, toolbar):
        """Add the tools to a real QToolBar as actions, so QToolBar's own drag
        handle, float and dock behaviour all work."""
        from PySide6.QtGui import QAction
        for entry in self.TOOLS:
            if entry is None:
                toolbar.addSeparator()
                continue
            cmd, icon_name, tip = entry
            action = QAction(icons.icon(icon_name, theme.INK_ON_DARK_MUTED, 16),
                             tip, toolbar)
            action.setToolTip(tip)
            action.triggered.connect(lambda _=False, c=cmd: self.command.emit(c))
            toolbar.addAction(action)
        self._toolbar = toolbar
        return toolbar

    def restyle_toolbar(self):
        if getattr(self, "_toolbar", None) is None:
            return
        actions = [a for a in self._toolbar.actions() if not a.isSeparator()]
        entries = [e for e in self.TOOLS if e is not None]
        for action, (cmd, icon_name, tip) in zip(actions, entries):
            action.setIcon(icons.icon(icon_name, theme.INK_ON_DARK_MUTED, 16))

    def _toggle_pin(self):
        self._pinned = self._pin.isChecked()
        self.pinToggled.emit(self._pinned)

    # dragging when floating
    def mousePressEvent(self, e):
        if not self._pinned and e.button() == Qt.MouseButton.LeftButton:
            self._drag_from = e.position().toPoint()

    def mouseMoveEvent(self, e):
        if self._drag_from is not None and not self._pinned:
            self.move(self.pos() + e.position().toPoint() - self._drag_from)

    def mouseReleaseEvent(self, e):
        self._drag_from = None

    def restyle(self):
        self.setStyleSheet(f"""
            #ToolsToolbar {{ background: {theme.ACTIVITY_BAR};
                border: 1px solid {theme.BORDER_DARK};
                border-radius: {theme.RADIUS_MD}px; }}
            QLabel#grip {{ color: {theme.INK_ON_DARK_FAINT}; padding: 0 4px; font-size: 13px; }}
            QPushButton {{ background: transparent; border: none;
                           border-radius: {theme.RADIUS_SM}px; }}
            QPushButton:hover {{ background: {theme.SIDE_PANEL}; }}
            QPushButton#pin {{ color: {theme.INK_ON_DARK_MUTED}; font-size: 10px;
                               padding: 0 8px; }}
            QPushButton#pin:checked {{ color: {theme.ACCENT}; }}
        """)

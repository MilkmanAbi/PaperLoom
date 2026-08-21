"""Thin status strip along the very bottom (VS Code status bar). A calm chrome
strip - muted ink on the chrome surface - rather than a loud full-accent band."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel
from ... import theme


class StatusBar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("StatusBar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedHeight(24)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 0, 12, 0)
        lay.setSpacing(16)
        self._left = QLabel("Ready"); self._left.setObjectName("statusLeft")
        self._appmode = QLabel("App: light")
        self._snap = QLabel("Snap off")
        self._zoom = QLabel("100%")
        self._target = QLabel("PySide6")
        self._count = QLabel("0 widgets")
        lay.addWidget(self._left)
        lay.addStretch(1)
        lay.addWidget(self._appmode)
        lay.addWidget(self._snap)
        lay.addWidget(self._zoom)
        lay.addWidget(self._count)
        lay.addWidget(self._target)
        self.restyle()

    def set_status(self, text):
        self._left.setText(text)

    def set_target(self, target):
        self._target.setText("PySide6" if target == "pyside6" else "C++")

    def set_count(self, n):
        self._count.setText(f"{n} widget{'s' if n != 1 else ''}")

    def set_app_mode(self, mode):
        self._appmode.setText(f"App: {mode}")

    def set_zoom(self, percent):
        self._zoom.setText(f"{percent}%")

    def set_snap(self, enabled, size):
        self._snap.setText(f"Snap {size}px" if enabled else "Snap off")

    def restyle(self):
        self.setStyleSheet(f"""
            #StatusBar {{ background: {theme.ACTIVITY_BAR};
                          border-top: 1px solid {theme.BORDER_DARK}; }}
            QLabel {{ color: {theme.INK_ON_DARK_MUTED}; font-size: 11px; }}
            QLabel#statusLeft {{ color: {theme.INK_ON_DARK}; }}
        """)


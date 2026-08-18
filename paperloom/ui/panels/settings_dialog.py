"""
Settings (the activity-bar gear). Deliberately small: a home for real
preferences to accrue in, not a wall of toggles. There is exactly one gear now -
the Properties pane used to also carry a gear glyph, which read as a second
settings button.
"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton, QWidget,
    QFrame
)

from ... import theme


class SettingsDialog(QDialog):
    libraryModeChanged = Signal(str)     # "popup" | "pane"
    editorModeToggled = Signal()

    def __init__(self, parent=None, library_mode="popup", editor_dark=True):
        super().__init__(parent)
        self.setObjectName("SettingsDialog")
        self.setWindowTitle("Settings")
        self.resize(440, 240)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        header = QLabel("Settings")
        header.setObjectName("hdr")
        outer.addWidget(header)

        body = QWidget()
        form = QVBoxLayout(body)
        form.setContentsMargins(20, 16, 20, 16)
        form.setSpacing(14)

        form.addWidget(self._row(
            "Component library", "How the library opens when you pick Components.",
            self._library_selector(library_mode)))

        line = QFrame(); line.setObjectName("sep"); line.setFixedHeight(1)
        form.addWidget(line)

        editor_btn = QPushButton(
            "Switch to light theme" if editor_dark else "Switch to dark theme")
        editor_btn.setObjectName("ghost")
        editor_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        editor_btn.clicked.connect(lambda: (self.editorModeToggled.emit(), self.accept()))
        form.addWidget(self._row(
            "PaperLoom theme", "Light or dark chrome for the editor itself.",
            editor_btn))

        form.addStretch(1)
        outer.addWidget(body, 1)

        footer = QWidget(); footer.setObjectName("ftr")
        fl = QHBoxLayout(footer); fl.setContentsMargins(20, 10, 20, 12)
        fl.addStretch(1)
        done = QPushButton("Done"); done.setObjectName("primary")
        done.setCursor(Qt.CursorShape.PointingHandCursor)
        done.clicked.connect(self.accept)
        fl.addWidget(done)
        outer.addWidget(footer)

        self._restyle()

    def _row(self, title, subtitle, control):
        row = QWidget()
        rl = QHBoxLayout(row); rl.setContentsMargins(0, 0, 0, 0); rl.setSpacing(12)
        text = QWidget(); tl = QVBoxLayout(text)
        tl.setContentsMargins(0, 0, 0, 0); tl.setSpacing(2)
        t = QLabel(title); t.setObjectName("rowTitle")
        s = QLabel(subtitle); s.setObjectName("rowSub"); s.setWordWrap(True)
        tl.addWidget(t); tl.addWidget(s)
        rl.addWidget(text, 1)
        rl.addWidget(control, 0, Qt.AlignmentFlag.AlignTop)
        return row

    def _library_selector(self, mode):
        combo = QComboBox()
        combo.addItem("Popup window", "popup")
        combo.addItem("Docked pane", "pane")
        combo.setCurrentIndex(1 if mode == "pane" else 0)
        combo.currentIndexChanged.connect(
            lambda _: self.libraryModeChanged.emit(combo.currentData()))
        combo.setFixedWidth(150)
        return combo

    def _restyle(self):
        self.setStyleSheet(f"""
            #SettingsDialog {{ background: {theme.SIDE_PANEL}; }}
            QLabel#hdr {{ background: {theme.ACTIVITY_BAR}; color: {theme.INK_ON_DARK};
                font-size: 14px; font-weight: 700; padding: 12px 20px;
                border-bottom: 1px solid {theme.BORDER_DARK}; }}
            QLabel#rowTitle {{ color: {theme.INK_ON_DARK}; font-size: 13px; font-weight: 600; }}
            QLabel#rowSub {{ color: {theme.INK_ON_DARK_MUTED}; font-size: 11px; }}
            QFrame#sep {{ background: {theme.BORDER_DARK}; border: none; }}
            #ftr {{ background: {theme.ACTIVITY_BAR}; border-top: 1px solid {theme.BORDER_DARK}; }}
            QComboBox {{ background: {theme.ACTIVITY_BAR}; border: 1px solid {theme.BORDER_DARK};
                border-radius: {theme.RADIUS_SM}px; padding: 5px 10px;
                color: {theme.INK_ON_DARK}; font-size: 12px; }}
            QComboBox QAbstractItemView {{ background: {theme.SIDE_PANEL};
                color: {theme.INK_ON_DARK}; selection-background-color: {theme.ACCENT_DIM};
                border: 1px solid {theme.BORDER_DARK}; }}
            QPushButton#ghost {{ background: transparent; color: {theme.INK_ON_DARK};
                border: 1px solid {theme.BORDER_DARK}; border-radius: {theme.RADIUS_SM}px;
                padding: 6px 14px; font-size: 12px; }}
            QPushButton#ghost:hover {{ border-color: {theme.ACCENT}; }}
            QPushButton#primary {{ background: {theme.ACCENT}; color: {theme.INK_ON_ACCENT};
                border: none; border-radius: {theme.RADIUS_SM}px; padding: 6px 20px;
                font-size: 12px; font-weight: 600; }}
            QPushButton#primary:hover {{ background: {theme.ACCENT_HOVER}; }}
        """)

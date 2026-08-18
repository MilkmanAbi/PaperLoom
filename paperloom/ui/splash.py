"""
Splash / project-start screen (spec §12.10). Opens before the editor:

    Start fresh   ->  pick a language (Python / C++) once, up front
    Open project  ->  load an existing project folder
    Recent        ->  jump straight back into a recent project

The target language is a project property chosen here, not a live toggle in the
top bar - "you aren't switching it mid-design." The look follows PaperDesign:
warm paper surface, one muted accent, generous but not wasteful spacing (the
Melon Synth start screen is the reference).
"""
from __future__ import annotations
import json
import os

from PySide6.QtCore import Qt, QSize
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QWidget,
    QStackedLayout, QFileDialog, QListWidget, QListWidgetItem, QFrame
)

from . import icons

# a fixed warm palette so the splash reads the same regardless of editor theme
_BG = "#F4F1EA"
_SURFACE = "#FFFFFF"
_INK = "#2B2822"
_INK_MUTED = "#6B6255"
_INK_FAINT = "#A79E8C"
_BORDER = "#D8D0C0"
_ACCENT = "#5B6BE8"

_CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".paperloom")
_RECENT_FILE = os.path.join(_CONFIG_DIR, "recent.json")


def load_recent() -> list[str]:
    try:
        with open(_RECENT_FILE, encoding="utf-8") as f:
            items = json.load(f)
        return [p for p in items if isinstance(p, str) and os.path.isdir(p)]
    except (OSError, ValueError):
        return []


def add_recent(path: str) -> None:
    if not path:
        return
    items = [path] + [p for p in load_recent() if p != path]
    items = items[:8]
    try:
        os.makedirs(_CONFIG_DIR, exist_ok=True)
        with open(_RECENT_FILE, "w", encoding="utf-8") as f:
            json.dump(items, f, indent=2)
    except OSError:
        pass


class _BigCard(QPushButton):
    def __init__(self, icon_name, title, subtitle):
        super().__init__()
        self.setObjectName("bigCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(120)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 18, 18, 18)
        lay.setSpacing(8)
        icon = QLabel()
        icon.setPixmap(icons.pixmap(icon_name, _ACCENT, 30))
        icon.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        t = QLabel(title); t.setObjectName("cardTitle")
        t.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        s = QLabel(subtitle); s.setObjectName("cardSub")
        s.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        s.setWordWrap(True)
        lay.addStretch(1); lay.addWidget(icon); lay.addWidget(t); lay.addWidget(s); lay.addStretch(1)


class SplashScreen(QDialog):
    """Blocking start screen. After exec(), read `.action` ('new'|'open'|None),
    `.target` ('pyside6'|'cpp') and `.directory`."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("PaperLoom")
        self.resize(720, 560)
        self.action = None
        self.target = "pyside6"
        self.directory = None

        self._stack = QStackedLayout(self)
        self._stack.addWidget(self._home_view())
        self._stack.addWidget(self._language_view())
        self.setStyleSheet(self._qss())

    # --- home ----------------------------------------------------------------
    def _home_view(self):
        page = QWidget(); page.setObjectName("page")
        outer = QVBoxLayout(page)
        outer.setContentsMargins(60, 48, 60, 36)
        outer.setSpacing(0)

        brand = QLabel("PaperLoom"); brand.setObjectName("brand")
        brand.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        tag = QLabel("A visual GUI builder for Qt"); tag.setObjectName("tag")
        tag.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        outer.addWidget(brand)
        outer.addWidget(tag)
        outer.addSpacing(28)

        cards = QHBoxLayout(); cards.setSpacing(16)
        fresh = _BigCard("plus-circle", "Start fresh", "New project - pick Python or C++")
        fresh.clicked.connect(lambda: self._stack.setCurrentIndex(1))
        openc = _BigCard("folder-open", "Open project", "Load an existing project folder")
        openc.clicked.connect(self._open)
        cards.addWidget(fresh); cards.addWidget(openc)
        outer.addLayout(cards)
        outer.addSpacing(24)

        rlabel = QLabel("RECENT"); rlabel.setObjectName("sectionLabel")
        outer.addWidget(rlabel)
        self._recent = QListWidget(); self._recent.setObjectName("recent")
        self._recent.itemActivated.connect(self._open_recent)
        recents = load_recent()
        if recents:
            for path in recents:
                it = QListWidgetItem(f"{os.path.basename(path)}      {path}")
                it.setData(Qt.ItemDataRole.UserRole, path)
                self._recent.addItem(it)
        else:
            placeholder = QListWidgetItem("No recent projects")
            placeholder.setFlags(Qt.ItemFlag.NoItemFlags)
            self._recent.addItem(placeholder)
        outer.addWidget(self._recent, 1)

        foot = QHBoxLayout()
        version = QLabel("PaperLoom - front-end to Qt, not a framework")
        version.setObjectName("foot")
        foot.addWidget(version); foot.addStretch(1)
        quit_btn = QPushButton("Quit"); quit_btn.setObjectName("ghost")
        quit_btn.clicked.connect(self.reject)
        foot.addWidget(quit_btn)
        outer.addLayout(foot)
        return page

    # --- language pick -------------------------------------------------------
    def _language_view(self):
        page = QWidget(); page.setObjectName("page")
        outer = QVBoxLayout(page)
        outer.setContentsMargins(60, 60, 60, 40)
        outer.setSpacing(0)

        title = QLabel("Choose a language"); title.setObjectName("brand")
        title.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        sub = QLabel("The generated app targets this - pick once, up front.")
        sub.setObjectName("tag"); sub.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        outer.addWidget(title); outer.addWidget(sub)
        outer.addSpacing(32)

        cards = QHBoxLayout(); cards.setSpacing(16)
        py = _BigCard("code", "Python", "PySide6 - run instantly, no build step")
        py.clicked.connect(lambda: self._new("pyside6"))
        cpp = _BigCard("code", "C++", "Qt Widgets - build with CMake")
        cpp.clicked.connect(lambda: self._new("cpp"))
        cards.addWidget(py); cards.addWidget(cpp)
        outer.addLayout(cards)
        outer.addStretch(1)

        back = QPushButton("Back"); back.setObjectName("ghost")
        back.clicked.connect(lambda: self._stack.setCurrentIndex(0))
        row = QHBoxLayout(); row.addWidget(back); row.addStretch(1)
        outer.addLayout(row)
        return page

    # --- results -------------------------------------------------------------
    def _new(self, target):
        self.action = "new"
        self.target = target
        self.accept()

    def _open(self):
        directory = QFileDialog.getExistingDirectory(self, "Open project folder")
        if directory:
            self.action = "open"
            self.directory = directory
            self.accept()

    def _open_recent(self, item):
        path = item.data(Qt.ItemDataRole.UserRole)
        if path:
            self.action = "open"
            self.directory = path
            self.accept()

    def _qss(self):
        return f"""
            QDialog {{ background: {_BG}; }}
            QWidget#page {{ background: {_BG}; }}
            QLabel#brand {{ color: {_ACCENT}; font-size: 34px; font-weight: 800; }}
            QLabel#tag {{ color: {_INK_MUTED}; font-size: 13px; }}
            QLabel#sectionLabel {{ color: {_INK_FAINT}; font-size: 10px; font-weight: 700;
                letter-spacing: 1px; padding: 4px 2px; }}
            QLabel#foot {{ color: {_INK_FAINT}; font-size: 11px; }}
            QPushButton#bigCard {{ background: {_SURFACE}; border: 1px solid {_BORDER};
                border-radius: 14px; text-align: center; }}
            QPushButton#bigCard:hover {{ border: 1px solid {_ACCENT}; }}
            QLabel#cardTitle {{ color: {_INK}; font-size: 16px; font-weight: 700; }}
            QLabel#cardSub {{ color: {_INK_MUTED}; font-size: 12px; }}
            QListWidget#recent {{ background: {_SURFACE}; border: 1px solid {_BORDER};
                border-radius: 10px; color: {_INK}; font-size: 12px; padding: 4px; outline: none; }}
            QListWidget#recent::item {{ padding: 8px 10px; border-radius: 6px; }}
            QListWidget#recent::item:hover {{ background: {_BG}; }}
            QListWidget#recent::item:selected {{ background: #E3E5FB; color: {_INK}; }}
            QPushButton#ghost {{ background: transparent; color: {_INK_MUTED};
                border: 1px solid {_BORDER}; border-radius: 8px; padding: 7px 18px; font-size: 12px; }}
            QPushButton#ghost:hover {{ border-color: {_ACCENT}; color: {_ACCENT}; }}
        """

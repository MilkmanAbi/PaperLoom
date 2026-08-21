"""
Splash / project-start screen (spec §12.10). Opens before the editor:

    New Python project  ->  start fresh, PySide6 target
    New C++ project     ->  start fresh, Qt Widgets/CMake target
    Open folder         ->  load an existing project folder
    Recent               ->  jump straight back into a recent project

The target language is a project property chosen here, not a live toggle in
the top bar - "you aren't switching it mid-design."

Layout follows the VS Code / Visual Studio "Get started" page: a narrow left
rail of vertical action rows (icon + title + one-line subtitle - not big
boxy cards) plus a footer, and a wider right column that's just the Recent
list, given the room to actually show full paths. One screen, no "pick a
language" sub-page in between - New Python/New C++ are each their own row,
same as VS Code lists "New File..." and "New Window" as separate rows rather
than nesting them behind a "New" menu.
"""
from __future__ import annotations
import json
import os

from PySide6.QtCore import Qt, QSize
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QWidget,
    QFileDialog, QListWidget, QListWidgetItem, QFrame
)

from . import icons
from . import branding

# a fixed dark palette, VS Code Get-Started-page inspired, so the splash
# reads the same regardless of editor theme
_BG = "#1B1B1F"
_PANEL = "#212226"
_SURFACE = "#26272C"
_INK = "#F1F0EE"
_INK_MUTED = "#A6A6AC"
_INK_FAINT = "#77777D"
_BORDER = "#34343A"
_ACCENT = "#7C8CF8"

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


class _ActionRow(QPushButton):
    """One VS-Code-Get-Started-style action row: icon, bold title, muted
    one-line subtitle below it - a text link with an icon, not a card."""

    def __init__(self, icon_name, title, subtitle):
        super().__init__()
        self.setObjectName("actionRow")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(52)
        row = QHBoxLayout(self)
        row.setContentsMargins(10, 6, 10, 6)
        row.setSpacing(12)
        icon = QLabel()
        icon.setPixmap(icons.pixmap(icon_name, _ACCENT, 20))
        icon.setFixedWidth(24)
        row.addWidget(icon)
        text = QVBoxLayout()
        text.setSpacing(1)
        t = QLabel(title); t.setObjectName("rowTitle")
        s = QLabel(subtitle); s.setObjectName("rowSub")
        s.setWordWrap(True)
        text.addWidget(t); text.addWidget(s)
        row.addLayout(text, 1)


class SplashScreen(QDialog):
    """Blocking start screen. After exec(), read `.action` ('new'|'open'|None),
    `.target` ('pyside6'|'cpp') and `.directory`."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("PaperLoom")
        self.setWindowIcon(branding.app_icon())
        self.resize(860, 560)
        self.action = None
        self.target = "pyside6"
        self.directory = None

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._start_column(), 0)
        root.addWidget(self._recent_column(), 1)
        self.setStyleSheet(self._qss())

    # --- left: brand + start actions ------------------------------------
    def _start_column(self):
        col = QFrame(); col.setObjectName("startCol")
        col.setFixedWidth(320)
        outer = QVBoxLayout(col)
        outer.setContentsMargins(28, 32, 20, 24)
        outer.setSpacing(0)

        head = QHBoxLayout(); head.setSpacing(10)
        logo_pm = branding.logo_pixmap(32)
        if not logo_pm.isNull():
            logo = QLabel(); logo.setPixmap(logo_pm)
            head.addWidget(logo)
        brand = QLabel("PaperLoom"); brand.setObjectName("brand")
        head.addWidget(brand)
        head.addStretch(1)
        outer.addLayout(head)
        tag = QLabel("A visual GUI builder for Qt"); tag.setObjectName("tag")
        outer.addWidget(tag)
        outer.addSpacing(28)

        section = QLabel("START"); section.setObjectName("sectionLabel")
        outer.addWidget(section)
        outer.addSpacing(4)

        py = _ActionRow("code", "New Python project", "PySide6 - run instantly, no build step")
        py.clicked.connect(lambda: self._new("pyside6"))
        cpp = _ActionRow("blocks", "New C++ project", "Qt Widgets - configured, built and run with CMake")
        cpp.clicked.connect(lambda: self._new("cpp"))
        openc = _ActionRow("folder-open", "Open folder...", "Load an existing project folder")
        openc.clicked.connect(self._open)
        outer.addWidget(py); outer.addWidget(cpp); outer.addWidget(openc)

        outer.addStretch(1)

        foot = QLabel("PaperLoom - front-end to Qt, not a framework")
        foot.setObjectName("foot")
        foot.setWordWrap(True)
        outer.addWidget(foot)
        outer.addSpacing(10)
        quit_btn = QPushButton("Quit"); quit_btn.setObjectName("ghost")
        quit_btn.clicked.connect(self.reject)
        outer.addWidget(quit_btn, 0, Qt.AlignmentFlag.AlignLeft)
        return col

    # --- right: recent list ----------------------------------------------
    def _recent_column(self):
        col = QFrame(); col.setObjectName("recentCol")
        outer = QVBoxLayout(col)
        outer.setContentsMargins(28, 32, 28, 24)
        outer.setSpacing(0)

        section = QLabel("RECENT"); section.setObjectName("sectionLabel")
        outer.addWidget(section)
        outer.addSpacing(8)

        self._recent = QListWidget(); self._recent.setObjectName("recent")
        self._recent.setIconSize(QSize(18, 18))
        self._recent.itemActivated.connect(self._open_recent)
        recents = load_recent()
        if recents:
            for path in recents:
                parent_dir = os.path.dirname(path)
                label = f"{os.path.basename(path)}\n{parent_dir}"
                it = QListWidgetItem(icons.icon("folder-open", _INK_FAINT), label)
                it.setData(Qt.ItemDataRole.UserRole, path)
                it.setToolTip(path)
                self._recent.addItem(it)
        else:
            placeholder = QListWidgetItem("No recent projects yet - start fresh or open a folder")
            placeholder.setFlags(Qt.ItemFlag.NoItemFlags)
            self._recent.addItem(placeholder)
        outer.addWidget(self._recent, 1)
        return col

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
            QFrame#startCol {{ background: {_PANEL}; border-right: 1px solid {_BORDER}; }}
            QFrame#recentCol {{ background: {_BG}; }}
            QLabel#brand {{ color: {_INK}; font-size: 20px; font-weight: 800; }}
            QLabel#tag {{ color: {_INK_MUTED}; font-size: 12px; }}
            QLabel#sectionLabel {{ color: {_INK_FAINT}; font-size: 10px; font-weight: 700;
                letter-spacing: 1px; }}
            QLabel#foot {{ color: {_INK_FAINT}; font-size: 10px; }}
            QPushButton#actionRow {{ background: transparent; border: none;
                border-radius: 8px; text-align: left; }}
            QPushButton#actionRow:hover {{ background: {_SURFACE}; }}
            QLabel#rowTitle {{ color: {_ACCENT}; font-size: 13px; font-weight: 600; }}
            QLabel#rowSub {{ color: {_INK_MUTED}; font-size: 11px; }}
            QListWidget#recent {{ background: transparent; border: none;
                color: {_INK}; font-size: 13px; outline: none; }}
            QListWidget#recent::item {{ padding: 9px 10px; border-radius: 6px; }}
            QListWidget#recent::item:hover {{ background: {_SURFACE}; }}
            QListWidget#recent::item:selected {{ background: #33355B; color: {_INK}; }}
            QPushButton#ghost {{ background: transparent; color: {_INK_MUTED};
                border: 1px solid {_BORDER}; border-radius: 8px; padding: 6px 16px; font-size: 12px; }}
            QPushButton#ghost:hover {{ border-color: {_ACCENT}; color: {_ACCENT}; }}
        """

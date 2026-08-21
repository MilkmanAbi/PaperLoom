"""
Settings (the activity-bar gear). Grew from a single small popup (component
library mode + PaperLoom theme) into a proper multi-section dialog per
Abinaash's session 15 follow-up request: "I wanna make a proper settings
menu - global accelerator and shortcuts menu, a cmd/powershell toggle, then
customisation and theming in personalisation, etc etc, so on, a proper
settings menu with multiple sections - fine control, a 'Data and Privacy'
section... create an Error management system."

Six sections, left-nav + right-content (the standard settings-app shape:
VS Code, most browsers, most OSes all use this same pattern for the same
reason - flat lists of unrelated toggles don't scale, but neither does a
maze of nested menus):

  Personalization - component library mode, PaperLoom light/dark theme
  Shortcuts       - read-only reference for every global keybind
                     (core/shortcuts.py is the single source of truth -
                     rebinding is real scope, flagged as a fast-follow, not
                     squeezed in here)
  Terminal        - which shell the integrated terminal starts (Windows:
                     auto-detect / PowerShell / Command Prompt)
  Data & Privacy  - the "Collect error data and crash reports" toggle;
                     backs core/error_manager.py
  Licenses        - the GPLv3 text (source-material/attribution use) and
                     PaperLoom's own crude/draft App License, both readable
                     in place
  About           - app identity, version, and a tiny LilyKnight corner
                     (Abinaash: "add him in really tiny into there, he cute")
"""
from PySide6.QtCore import Qt, Signal, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton, QWidget,
    QFrame, QListWidget, QListWidgetItem, QStackedWidget, QCheckBox,
    QPlainTextEdit, QScrollArea, QSizePolicy
)

from ... import theme
from .. import icons
from .. import branding
from ...core import shortcuts as shortcuts_mod
from ...core import licenses as licenses_mod
from ...core import error_manager


_SECTIONS = [
    # (id, label, icon)
    ("personalization", "Personalization", "palette"),
    ("shortcuts", "Shortcuts", "keyboard"),
    ("terminal", "Terminal", "terminal"),
    ("privacy", "Data & Privacy", "shield-check"),
    ("licenses", "Licenses", "scroll-text"),
    ("about", "About", "info"),
]


class SettingsDialog(QDialog):
    libraryModeChanged = Signal(str)         # "popup" | "pane"
    editorModeToggled = Signal()
    terminalShellChanged = Signal(str)       # "auto" | "powershell" | "cmd"
    collectErrorReportsChanged = Signal(bool)

    def __init__(self, parent=None, library_mode="popup", editor_dark=True,
                 terminal_shell="auto", collect_error_reports=False):
        super().__init__(parent)
        self.setObjectName("SettingsDialog")
        self.setWindowTitle("Settings")
        self.setWindowIcon(branding.app_icon())
        self.resize(720, 480)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        header = QLabel("Settings")
        header.setObjectName("hdr")
        outer.addWidget(header)

        body = QWidget()
        body_l = QHBoxLayout(body)
        body_l.setContentsMargins(0, 0, 0, 0)
        body_l.setSpacing(0)

        self._nav = QListWidget()
        self._nav.setObjectName("nav")
        self._nav.setFixedWidth(180)
        self._nav.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        for _id, label, icon_name in _SECTIONS:
            item = QListWidgetItem(icons.icon(icon_name, theme.INK_ON_DARK_MUTED, 16), label)
            item.setSizeHint(item.sizeHint().expandedTo(item.sizeHint()))
            self._nav.addItem(item)
        self._nav.setIconSize(self._nav.iconSize())
        self._nav.currentRowChanged.connect(self._on_nav_changed)
        body_l.addWidget(self._nav)

        self._stack = QStackedWidget()
        self._stack.setStyleSheet(f"background: {theme.SIDE_PANEL};")
        self._stack.addWidget(self._personalization_page(library_mode, editor_dark))
        self._stack.addWidget(self._shortcuts_page())
        self._stack.addWidget(self._terminal_page(terminal_shell))
        self._stack.addWidget(self._privacy_page(collect_error_reports))
        self._stack.addWidget(self._licenses_page())
        self._stack.addWidget(self._about_page())
        body_l.addWidget(self._stack, 1)

        outer.addWidget(body, 1)

        footer = QWidget(); footer.setObjectName("ftr")
        fl = QHBoxLayout(footer); fl.setContentsMargins(20, 10, 20, 12)
        fl.addStretch(1)
        done = QPushButton("Done"); done.setObjectName("primary")
        done.setCursor(Qt.CursorShape.PointingHandCursor)
        done.clicked.connect(self.accept)
        fl.addWidget(done)
        outer.addWidget(footer)

        self._nav.setCurrentRow(0)
        self._restyle()

    def _on_nav_changed(self, row):
        if row >= 0:
            self._stack.setCurrentIndex(row)

    # --- shared page chrome ------------------------------------------------
    def _page(self, title):
        """A scrollable content page with the standard 20/16 padding and a
        section title - every section body lives inside one of these."""
        page = QWidget()
        page.setStyleSheet(f"background: {theme.SIDE_PANEL};")
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        t = QLabel(title); t.setObjectName("pageTitle")
        outer.addWidget(t)

        scroll = QScrollArea()
        scroll.setObjectName("pageScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        # QAbstractScrollArea's internal viewport paints its own (light,
        # default-palette) background underneath whatever's inside it,
        # which otherwise hides #SettingsDialog's dark background and
        # leaves light-on-dark ink unreadable - style the scroll area, its
        # viewport, AND the inner content widget explicitly rather than
        # relying on the object-name QSS to cascade through all three.
        bg = f"background: {theme.SIDE_PANEL}; border: none;"
        scroll.setStyleSheet(bg)
        scroll.viewport().setStyleSheet(bg)
        inner = QWidget()
        inner.setStyleSheet(bg)
        form = QVBoxLayout(inner)
        form.setContentsMargins(20, 14, 20, 16)
        form.setSpacing(14)
        scroll.setWidget(inner)
        outer.addWidget(scroll, 1)
        return page, form

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

    def _sep(self):
        line = QFrame(); line.setObjectName("sep"); line.setFixedHeight(1)
        return line

    # --- Personalization -----------------------------------------------------
    def _personalization_page(self, library_mode, editor_dark):
        page, form = self._page("Personalization")

        form.addWidget(self._row(
            "Component library", "How the library opens when you pick Components.",
            self._library_selector(library_mode)))
        form.addWidget(self._sep())

        editor_btn = QPushButton(
            "Switch to light theme" if editor_dark else "Switch to dark theme")
        editor_btn.setObjectName("ghost")
        editor_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        editor_btn.clicked.connect(self.editorModeToggled.emit)
        form.addWidget(self._row(
            "PaperLoom theme", "Light or dark chrome for the editor itself.",
            editor_btn))

        form.addStretch(1)
        return page

    def _library_selector(self, mode):
        combo = QComboBox()
        combo.addItem("Popup window", "popup")
        combo.addItem("Docked pane", "pane")
        combo.setCurrentIndex(1 if mode == "pane" else 0)
        combo.currentIndexChanged.connect(
            lambda _: self.libraryModeChanged.emit(combo.currentData()))
        combo.setFixedWidth(150)
        return combo

    # --- Shortcuts -----------------------------------------------------------
    def _shortcuts_page(self):
        page, form = self._page("Shortcuts")

        note = QLabel(
            "Every global keyboard shortcut PaperLoom binds, for reference. "
            "Rebinding your own keys isn't here yet - flagged for later, not "
            "forgotten.")
        note.setObjectName("rowSub")
        note.setWordWrap(True)
        form.addWidget(note)

        for cat, entries in shortcuts_mod.grouped():
            cat_label = QLabel(cat.upper()); cat_label.setObjectName("sectionLabel")
            form.addWidget(cat_label)
            for keys, label in entries:
                row = QWidget()
                rl = QHBoxLayout(row); rl.setContentsMargins(0, 2, 0, 2)
                name = QLabel(label); name.setObjectName("rowTitle")
                keycap = QLabel(keys); keycap.setObjectName("keycap")
                keycap.setAlignment(Qt.AlignmentFlag.AlignRight)
                rl.addWidget(name, 1)
                rl.addWidget(keycap, 0)
                form.addWidget(row)

        form.addStretch(1)
        return page

    # --- Terminal --------------------------------------------------------------
    def _terminal_page(self, terminal_shell):
        page, form = self._page("Terminal")

        combo = QComboBox()
        combo.addItem("Auto-detect (prefers PowerShell)", "auto")
        combo.addItem("PowerShell", "powershell")
        combo.addItem("Command Prompt (cmd.exe)", "cmd")
        idx = {"auto": 0, "powershell": 1, "cmd": 2}.get(terminal_shell, 0)
        combo.setCurrentIndex(idx)
        combo.currentIndexChanged.connect(
            lambda _: self.terminalShellChanged.emit(combo.currentData()))
        combo.setFixedWidth(220)
        form.addWidget(self._row(
            "Default shell",
            "Which shell a new integrated terminal starts (Windows only - "
            "other platforms always use your $SHELL). Takes effect on the "
            "next terminal you open.",
            combo))

        form.addStretch(1)
        return page

    # --- Data & Privacy --------------------------------------------------------
    def _privacy_page(self, collect_error_reports):
        page, form = self._page("Data & Privacy")

        intro = QLabel(
            "PaperLoom does not collect or send anything today. This is the "
            "one setting that changes that, and only if you turn it on.")
        intro.setObjectName("rowSub")
        intro.setWordWrap(True)
        form.addWidget(intro)
        form.addWidget(self._sep())

        check = QCheckBox("Collect error data and crash reports")
        check.setObjectName("privacyCheck")
        check.setChecked(bool(collect_error_reports))
        check.toggled.connect(self.collectErrorReportsChanged.emit)
        form.addWidget(check)

        explain = QLabel(
            "When this is on, PaperLoom writes a report (what went wrong, a "
            "traceback, basic platform/version info) to a file on your own "
            "machine whenever it hits an error. Nothing is uploaded or sent "
            "anywhere - there's no server on the other end of this yet. "
            "This is the first small piece of a much bigger error/crash "
            "logging and debug tool planned for later.")
        explain.setObjectName("rowSub")
        explain.setWordWrap(True)
        form.addWidget(explain)

        reports = error_manager.list_reports()
        status = QLabel(
            f"{len(reports)} local report{'s' if len(reports) != 1 else ''} saved so far."
            if reports else "No local reports saved yet.")
        status.setObjectName("rowSub")
        form.addWidget(status)

        open_folder = QPushButton("Open reports folder")
        open_folder.setObjectName("ghost")
        open_folder.setCursor(Qt.CursorShape.PointingHandCursor)
        open_folder.clicked.connect(lambda: QDesktopServices.openUrl(
            QUrl.fromLocalFile(error_manager.REPORTS_DIR)))
        open_folder.setEnabled(bool(reports))
        form.addWidget(open_folder, 0, Qt.AlignmentFlag.AlignLeft)

        form.addStretch(1)
        return page

    # --- Licenses --------------------------------------------------------------
    def _licenses_page(self):
        page = QWidget()
        page.setStyleSheet(f"background: {theme.SIDE_PANEL};")
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        t = QLabel("Licenses"); t.setObjectName("pageTitle")
        outer.addWidget(t)

        split = QWidget()
        split.setStyleSheet(f"background: {theme.SIDE_PANEL};")
        sl = QHBoxLayout(split); sl.setContentsMargins(20, 14, 20, 16); sl.setSpacing(14)

        picker = QListWidget()
        picker.setObjectName("licensePicker")
        picker.setFixedWidth(200)
        picker.addItem("GNU GPL v3.0 (source material)")
        picker.addItem("PaperLoom App License (draft)")
        sl.addWidget(picker)

        viewer = QPlainTextEdit()
        viewer.setObjectName("licenseViewer")
        viewer.setReadOnly(True)
        viewer.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        sl.addWidget(viewer, 1)

        texts = [
            licenses_mod.read(licenses_mod.GPL_PATH),
            licenses_mod.read(licenses_mod.APP_LICENSE_PATH),
        ]
        picker.currentRowChanged.connect(
            lambda row: viewer.setPlainText(texts[row] if 0 <= row < len(texts) else ""))
        picker.setCurrentRow(0)

        outer.addWidget(split, 1)
        return page

    # --- About -------------------------------------------------------------------
    def _about_page(self):
        page, form = self._page("About")

        logo_row = QHBoxLayout()
        logo = QLabel(); logo.setPixmap(branding.logo_pixmap(72))
        logo_row.addWidget(logo)
        text = QVBoxLayout(); text.setSpacing(2)
        name = QLabel("PaperLoom"); name.setObjectName("aboutTitle")
        tagline = QLabel("A visual UI/UX builder for Qt - the power of Qt "
                          "Designer, without the learning cliff.")
        tagline.setObjectName("rowSub"); tagline.setWordWrap(True)
        version = QLabel(f"Version {error_manager.APP_VERSION}")
        version.setObjectName("rowSub")
        text.addWidget(name); text.addWidget(tagline); text.addWidget(version)
        logo_row.addLayout(text, 1)
        form.addLayout(logo_row)
        form.addWidget(self._sep())

        credit = QLabel("Created by Abi (MilkmanAbi). "
                         "Free and open-source under the GNU GPL v3.0 - see "
                         "Licenses.")
        credit.setObjectName("rowSub"); credit.setWordWrap(True)
        form.addWidget(credit)

        form.addStretch(1)

        # LilyKnight - "add him in really tiny into there, he cute." A quiet
        # corner easter egg, not a hero image: small, bottom-right, with a
        # tooltip for anyone who notices him.
        mascot_row = QHBoxLayout()
        mascot_row.addStretch(1)
        mascot = QLabel()
        mascot.setPixmap(branding.mascot_pixmap(26))
        mascot.setToolTip("LilyKnight - PaperLoom's mascot")
        mascot_row.addWidget(mascot)
        form.addLayout(mascot_row)
        return page

    def _restyle(self):
        self.setStyleSheet(f"""
            #SettingsDialog {{ background: {theme.SIDE_PANEL}; }}
            QLabel#hdr {{ background: {theme.ACTIVITY_BAR}; color: {theme.INK_ON_DARK};
                font-size: 14px; font-weight: 700; padding: 12px 20px;
                border-bottom: 1px solid {theme.BORDER_DARK}; }}
            QLabel#pageTitle {{ color: {theme.INK_ON_DARK}; font-size: 13px; font-weight: 700;
                padding: 14px 20px 0 20px; }}
            QLabel#sectionLabel {{ color: {theme.INK_ON_DARK_FAINT}; font-size: 10px;
                font-weight: 700; letter-spacing: 1px; padding-top: 6px; }}
            QLabel#rowTitle {{ color: {theme.INK_ON_DARK}; font-size: 13px; font-weight: 600; }}
            QLabel#rowSub {{ color: {theme.INK_ON_DARK_MUTED}; font-size: 11px; }}
            QLabel#keycap {{ color: {theme.INK_ON_DARK_MUTED}; font-size: 11px;
                background: {theme.ACTIVITY_BAR}; border: 1px solid {theme.BORDER_DARK};
                border-radius: {theme.RADIUS_SM}px; padding: 1px 8px; }}
            QLabel#aboutTitle {{ color: {theme.INK_ON_DARK}; font-size: 16px; font-weight: 700; }}
            QFrame#sep {{ background: {theme.BORDER_DARK}; border: none; }}
            #ftr {{ background: {theme.ACTIVITY_BAR}; border-top: 1px solid {theme.BORDER_DARK}; }}
            QListWidget#nav {{ background: {theme.ACTIVITY_BAR};
                border: none; border-right: 1px solid {theme.BORDER_DARK};
                padding: 8px; outline: none; }}
            QListWidget#nav::item {{ color: {theme.INK_ON_DARK_MUTED}; border-radius: {theme.RADIUS_SM}px;
                padding: 7px 10px; margin: 1px 0; }}
            QListWidget#nav::item:selected {{ background: {theme.ACCENT_DIM}; color: {theme.INK_ON_DARK}; }}
            QListWidget#nav::item:hover:!selected {{ background: {theme.SIDE_PANEL}; }}
            QListWidget#licensePicker {{ background: {theme.ACTIVITY_BAR};
                border: 1px solid {theme.BORDER_DARK}; border-radius: {theme.RADIUS_SM}px;
                color: {theme.INK_ON_DARK_MUTED}; outline: none; }}
            QListWidget#licensePicker::item {{ padding: 8px 10px; }}
            QListWidget#licensePicker::item:selected {{ background: {theme.ACCENT_DIM}; color: {theme.INK_ON_DARK}; }}
            QPlainTextEdit#licenseViewer {{ background: {theme.ACTIVITY_BAR};
                color: {theme.INK_ON_DARK_MUTED}; border: 1px solid {theme.BORDER_DARK};
                border-radius: {theme.RADIUS_SM}px; font-family: "Cascadia Mono", Consolas, monospace;
                font-size: 11px; padding: 8px; }}
            QScrollArea#pageScroll {{ background: transparent; border: none; }}
            QCheckBox#privacyCheck {{ color: {theme.INK_ON_DARK}; font-size: 13px; font-weight: 600; }}
            QCheckBox#privacyCheck::indicator {{ width: 16px; height: 16px; }}
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
            QPushButton#ghost:disabled {{ color: {theme.INK_ON_DARK_FAINT}; }}
            QPushButton#primary {{ background: {theme.ACCENT}; color: {theme.INK_ON_ACCENT};
                border: none; border-radius: {theme.RADIUS_SM}px; padding: 6px 20px;
                font-size: 12px; font-weight: 600; }}
            QPushButton#primary:hover {{ background: {theme.ACCENT_HOVER}; }}
        """)

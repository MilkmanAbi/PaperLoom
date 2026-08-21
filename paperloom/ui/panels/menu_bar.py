"""
Menu bar (spec §12.7) - flat, macOS/VS Code style:

    PaperLoom | File | Edit | Selection | View | Go | Run | Terminal   [ search ]

Every menu is a flat QMenu opened on click (not hover-drift), styled from the
active theme. Actions are emitted as a single `command` signal carrying a
command id, so the main window wires one slot instead of thirty, and the same
ids can be driven by the command palette.
"""
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QPushButton, QLabel, QMenu, QLineEdit
)

from ... import theme
from .. import icons


class _SearchLauncher(QLineEdit):
    """The top search field is really a launcher for the command palette - the
    two used to be separate, which is why search felt dumb. Focusing or typing
    hands straight over to the palette (which does live filtering)."""
    activated = Signal(str)

    def focusInEvent(self, event):
        super().focusInEvent(event)
        self.activated.emit(self.text())
        self.clearFocus()


# menu structure: (title, [(label, command_id, shortcut) | None for separator])
def menu_spec():
    return [
        ("PaperLoom", [
            ("About PaperLoom", "app.about", ""),
            None,
            ("Preferences...", "app.preferences", "Ctrl+,"),
            None,
            ("Quit", "app.quit", "Ctrl+Q"),
        ]),
        ("File", [
            ("New Page", "file.new_page", "Ctrl+N"),
            ("Open Project...", "file.open", "Ctrl+O"),
            None,
            ("Save", "file.save", "Ctrl+S"),
            ("Save As...", "file.save_as", "Ctrl+Shift+S"),
            None,
            ("Generate Code...", "file.generate", "Ctrl+G"),
            None,
            ("Import Qt Designer .ui...", "file.import_ui", ""),
            ("Export page as .ui...", "file.export_ui", ""),
            ("Import Stylesheet...", "file.import_stylesheet", ""),
            None,
            ("Export Project Archive...", "file.export_project", ""),
            ("Export Theme...", "file.export_theme", ""),
        ]),
        ("Edit", [
            ("Undo", "edit.undo", "Ctrl+Z"),
            ("Redo", "edit.redo", "Ctrl+Y"),
            None,
            ("Duplicate", "edit.duplicate", "Ctrl+D"),
            ("Delete", "edit.delete", "Del"),
        ]),
        ("Selection", [
            ("Select All", "selection.all", "Ctrl+A"),
            ("Deselect", "selection.none", "Esc"),
            None,
            ("Bring to Front", "selection.front", "Ctrl+]"),
            ("Send to Back", "selection.back", "Ctrl+["),
            None,
            ("Align Left", "align.left", ""),
            ("Align Center", "align.center", ""),
            ("Align Right", "align.right", ""),
            ("Align Top", "align.top", ""),
            ("Align Middle", "align.middle", ""),
            ("Align Bottom", "align.bottom", ""),
        ]),
        ("View", [
            ("Zoom In", "view.zoom_in", "Ctrl+="),
            ("Zoom Out", "view.zoom_out", "Ctrl+-"),
            ("Reset Zoom", "view.zoom_reset", "Ctrl+0"),
            None,
            ("Toggle PaperLoom Light/Dark", "view.toggle_editor_mode", "Ctrl+Shift+D"),
            ("Toggle App Light/Dark", "view.toggle_app_mode", "Ctrl+Alt+D"),
            None,
            ("Toggle Grid", "view.toggle_grid", "Ctrl+'"),
            ("Toggle Alignment Guides", "view.toggle_guides", ""),
            ("Toggle Snap", "view.toggle_snap", "Ctrl+;"),
            ("Snap Settings...", "view.snap_settings", ""),
            None,
            ("Toggle Side Panel", "view.toggle_side", "Ctrl+B"),
            ("Toggle Bottom Panel", "view.toggle_bottom", "Ctrl+J"),
            ("Toggle Tools Toolbar", "view.toggle_tools", ""),
            ("Toggle Layout Toolbar", "view.toggle_layout_toolbar", ""),
            None,
            ("Library as Docked Pane", "view.toggle_library_mode", ""),
            None,
            ("Theme", "view.theme_menu", ""),          # replaced by a submenu
            ("Import Theme...", "view.import_theme", ""),
        ]),
        ("Go", [
            ("Go to Page...", "go.page", "Ctrl+P"),
            ("Go to Component...", "go.component", "Ctrl+Shift+O"),
            None,
            ("Command Palette...", "go.commands", "Ctrl+Shift+P"),
        ]),
        ("Run", [
            ("Run Preview", "run.preview", "F5"),
            ("Stop", "run.stop", "Shift+F5"),
            None,
            ("Quick Preview...", "run.quick_preview", "Ctrl+Shift+R"),
            ("Code Editor...", "run.code_editor", "Ctrl+Shift+E"),
            None,
            ("Generate Code", "run.generate", ""),
        ]),
        ("Terminal", [
            ("New Terminal", "terminal.new", "Ctrl+`"),
            ("Clear Terminal", "terminal.clear", ""),
            None,
            ("Show Output", "terminal.output", ""),
            ("Show Problems", "terminal.problems", ""),
            ("Show Debug", "terminal.debug", ""),
        ]),
    ]


class MenuBar(QWidget):
    command = Signal(str)          # command id
    themeChosen = Signal(str)      # theme name
    searchSubmitted = Signal(str)

    def __init__(self, theme_manager, parent=None):
        super().__init__(parent)
        self.theme_manager = theme_manager
        self.setObjectName("MenuBar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedHeight(32)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 0, 8, 0)
        lay.setSpacing(0)

        # the two stretches below only balance the space AFTER the menu
        # buttons, so the search bar centred within them still sits left of
        # the window's true centre (the buttons eat space on the left with
        # nothing to match on the right). Mirror the button group's width as
        # an invisible spacer on the right so centring is against the whole
        # window, the way VS Code's actually looks.
        menu_group = QWidget()
        menu_lay = QHBoxLayout(menu_group)
        menu_lay.setContentsMargins(0, 0, 0, 0)
        menu_lay.setSpacing(0)
        for title, items in menu_spec():
            menu_lay.addWidget(self._make_menu_button(title, items))
        lay.addWidget(menu_group)

        lay.addStretch(1)

        self.search = _SearchLauncher()
        self.search.setPlaceholderText("Search or run a command...   Ctrl+Shift+P")
        self.search.setFixedWidth(340)
        self.search.setObjectName("globalSearch")
        self.search.activated.connect(self.searchSubmitted.emit)
        lay.addWidget(self.search)
        lay.addStretch(1)

        self._menu_group = menu_group
        self._right_spacer = QWidget()
        self._right_spacer.setFixedWidth(menu_group.sizeHint().width())
        lay.addWidget(self._right_spacer)

        self.restyle()

    def showEvent(self, event):
        super().showEvent(event)
        # sizeHint() measured in __init__ predates the stylesheet actually
        # being applied (button padding isn't baked in yet), which under-
        # measures the menu-button group and throws off centring. The real
        # rendered width is only correct once the widget is actually shown.
        real_width = self._menu_group.width()
        if real_width and self._right_spacer.width() != real_width:
            self._right_spacer.setFixedWidth(real_width)

    def _make_menu_button(self, title, items):
        btn = QPushButton(title)
        btn.setObjectName("brand" if title == "PaperLoom" else "menu")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        menu = QMenu(btn)
        for entry in items:
            if entry is None:
                menu.addSeparator()
                continue
            label, cmd, shortcut = entry
            if cmd == "view.theme_menu":
                self._theme_submenu(menu)
                continue
            act = QAction(label, menu)
            if shortcut:
                act.setShortcut(QKeySequence(shortcut))
            if cmd == "view.toggle_library_mode":
                act.setCheckable(True)
                self._library_pane_action = act
            act.triggered.connect(lambda _=False, c=cmd: self.command.emit(c))
            menu.addAction(act)
        btn.setMenu(menu)
        return btn

    def set_library_pane_checked(self, checked):
        if hasattr(self, "_library_pane_action"):
            self._library_pane_action.setChecked(checked)

    def _theme_submenu(self, parent_menu):
        sub = parent_menu.addMenu("Theme")
        self._theme_menu = sub
        self._rebuild_theme_menu()

    def _rebuild_theme_menu(self):
        if not hasattr(self, "_theme_menu"):
            return
        self._theme_menu.clear()
        for name in self.theme_manager.names():
            act = QAction(name, self._theme_menu)
            act.setCheckable(True)
            act.setChecked(name == self.theme_manager.active.name)
            act.triggered.connect(lambda _=False, n=name: self.themeChosen.emit(n))
            self._theme_menu.addAction(act)

    def refresh_themes(self):
        self._rebuild_theme_menu()

    def restyle(self):
        self.setStyleSheet(f"""
            #MenuBar {{ background: {theme.ACTIVITY_BAR};
                        border-bottom: 1px solid {theme.BORDER_DARK}; }}
            QPushButton#menu, QPushButton#brand {{
                background: transparent; border: none; padding: 5px 10px;
                color: {theme.INK_ON_DARK}; font-size: 12px; }}
            QPushButton#brand {{ font-weight: 700; }}
            QPushButton#menu:hover, QPushButton#brand:hover {{
                background: {theme.SIDE_PANEL}; border-radius: {theme.RADIUS_SM}px; }}
            QPushButton#menu::menu-indicator, QPushButton#brand::menu-indicator {{
                image: none; width: 0; }}
            QLineEdit#globalSearch {{
                background: {theme.SIDE_PANEL}; border: 1px solid {theme.BORDER_DARK};
                border-radius: {theme.RADIUS_SM}px; padding: 3px 10px;
                color: {theme.INK_ON_DARK}; font-size: 11px; }}
            QLineEdit#globalSearch:focus {{ border: 1px solid {theme.ACCENT}; }}
        """)

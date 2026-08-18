"""
Top bar (VS Code-style command strip). App identity, a compact menu, visible
undo/redo, target-language + zoom selectors, and Generate/Run as the loud
primary actions. Replaces the native OS menu bar entirely, so nothing inherits
OS colours that clash with the theme (the source of the earlier invisible text).
"""
from PySide6.QtCore import Signal, Qt, QSize
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QPushButton, QLabel, QComboBox, QFrame, QMenu
)

from ... import theme
from .. import icons


class _IconButton(QPushButton):
    def __init__(self, icon_name, tooltip, size=28):
        super().__init__()
        self._icon_name = icon_name
        self.setToolTip(tooltip)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(size, size)
        self.setIconSize(QSize(18, 18))
        self.setObjectName("iconbtn")
        self._set(theme.INK_ON_DARK_MUTED)

    def _set(self, color):
        self.setIcon(icons.icon(self._icon_name, color, 18))

    def setEnabled(self, enabled):
        super().setEnabled(enabled)
        self._set(theme.INK_ON_DARK_MUTED if enabled else theme.INK_ON_DARK_FAINT)


class TopBar(QWidget):
    undoRequested = Signal()
    redoRequested = Signal()
    generateRequested = Signal()
    runRequested = Signal()
    saveRequested = Signal()
    zoomChanged = Signal(int)
    toggleBottomRequested = Signal()
    editorModeToggled = Signal()
    appModeToggled = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("TopBar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedHeight(theme.BAR_HEIGHT + 6)
        self.setStyleSheet(self._qss())

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 4, 10, 4)
        layout.setSpacing(6)

        # (the brand lives in the menu bar; a second "PaperLoom" here was redundant)
        self.undo_btn = _IconButton("undo", "Undo")
        self.undo_btn.clicked.connect(self.undoRequested.emit)
        self.redo_btn = _IconButton("redo", "Redo")
        self.redo_btn.clicked.connect(self.redoRequested.emit)
        layout.addWidget(self.undo_btn)
        layout.addWidget(self.redo_btn)

        layout.addStretch(1)

        self.zoom = QComboBox()
        for z in (50, 75, 100, 125, 150):
            self.zoom.addItem(f"{z}%", z)
        self.zoom.setCurrentIndex(2)
        self.zoom.currentIndexChanged.connect(
            lambda _: self.zoomChanged.emit(self.zoom.currentData()))
        layout.addWidget(self.zoom)

        # designed-app light/dark - the app being built gets this for free
        app_label = QLabel("App")
        app_label.setObjectName("dim")
        layout.addWidget(app_label)
        self.app_mode_btn = _IconButton("sun", "Toggle the designed app's light/dark mode")
        self.app_mode_btn.clicked.connect(self.appModeToggled.emit)
        layout.addWidget(self.app_mode_btn)

        # PaperLoom's own light/dark
        self.editor_mode_btn = _IconButton("moon", "Toggle PaperLoom's light/dark theme")
        self.editor_mode_btn.clicked.connect(self.editorModeToggled.emit)
        layout.addWidget(self.editor_mode_btn)

        self.panel_btn = _IconButton("panel-bottom", "Toggle panel")
        self.panel_btn.clicked.connect(self.toggleBottomRequested.emit)
        layout.addWidget(self.panel_btn)

        layout.addWidget(self._divider())

        self.generate_btn = QPushButton("Generate")
        self.generate_btn.setObjectName("tool")
        self.generate_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.generate_btn.clicked.connect(self.generateRequested.emit)
        layout.addWidget(self.generate_btn)

        self.run_btn = QPushButton("  Run")
        self.run_btn.setObjectName("primary")
        self.run_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.run_btn.setIcon(icons.icon("play", theme.INK_ON_ACCENT, 14))
        self.run_btn.clicked.connect(self.runRequested.emit)
        layout.addWidget(self.run_btn)

        self.set_undo_state(False, False)

    def _menu_button(self):
        btn = QPushButton("Menu")
        btn.setObjectName("tool")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        menu = QMenu(btn)
        menu.setStyleSheet(f"""
            QMenu {{ background: {theme.SIDE_PANEL}; color: {theme.INK_ON_DARK};
                     border: 1px solid {theme.BORDER_DARK}; }}
            QMenu::item {{ padding: 6px 24px 6px 12px; }}
            QMenu::item:selected {{ background: {theme.ACCENT_DIM}; }}
        """)
        act_save = menu.addAction("Save\tCtrl+S")
        act_save.triggered.connect(lambda: self.saveRequested.emit())
        act_gen = menu.addAction("Generate code\tCtrl+G")
        act_gen.triggered.connect(lambda: self.generateRequested.emit())
        menu.addSeparator()
        act_undo = menu.addAction("Undo\tCtrl+Z")
        act_undo.triggered.connect(lambda: self.undoRequested.emit())
        act_redo = menu.addAction("Redo\tCtrl+Y")
        act_redo.triggered.connect(lambda: self.redoRequested.emit())
        btn.setMenu(menu)
        return btn

    def _divider(self):
        line = QFrame()
        line.setFrameShape(QFrame.Shape.VLine)
        line.setFixedHeight(18)
        line.setStyleSheet(f"color: {theme.BORDER_DARK};")
        return line

    def set_undo_state(self, can_undo, can_redo, undo_label="", redo_label=""):
        self.undo_btn.setEnabled(can_undo)
        self.redo_btn.setEnabled(can_redo)
        self.undo_btn.setToolTip(f"Undo {undo_label}".strip())
        self.redo_btn.setToolTip(f"Redo {redo_label}".strip())

    def restyle(self):
        self.setStyleSheet(self._qss())
        for btn in self.findChildren(_IconButton):
            btn._set(theme.INK_ON_DARK_MUTED if btn.isEnabled() else theme.INK_ON_DARK_FAINT)

    def set_mode_icons(self, editor_is_dark, app_mode):
        # each button shows the mode it will switch TO
        self.editor_mode_btn._icon_name = "sun" if editor_is_dark else "moon"
        self.editor_mode_btn.setToolTip(
            "Switch PaperLoom to light" if editor_is_dark else "Switch PaperLoom to dark")
        self.editor_mode_btn._set(theme.INK_ON_DARK_MUTED)
        self.app_mode_btn._icon_name = "moon" if app_mode == "light" else "sun"
        self.app_mode_btn.setToolTip(
            "Switch the app preview to dark" if app_mode == "light"
            else "Switch the app preview to light")
        self.app_mode_btn._set(theme.ACCENT)

    def _qss(self):
        return f"""
        #TopBar {{ background: {theme.ACTIVITY_BAR};
                   border-bottom: 1px solid {theme.BORDER_DARK}; }}
        #brand {{ color: {theme.INK_ON_DARK}; font-size: 13px; font-weight: 700; }}
        QLabel#dim {{ color: {theme.INK_ON_DARK_MUTED}; font-size: 11px; }}
        QPushButton#tool {{ background: transparent; border: 1px solid transparent;
            border-radius: {theme.RADIUS_SM}px; padding: 5px 10px;
            color: {theme.INK_ON_DARK}; font-size: 12px; }}
        QPushButton#tool:hover {{ background: {theme.SIDE_PANEL}; }}
        QPushButton#tool::menu-indicator {{ image: none; width: 0; }}
        QPushButton#iconbtn {{ background: transparent; border: none;
            border-radius: {theme.RADIUS_SM}px; }}
        QPushButton#iconbtn:hover {{ background: {theme.SIDE_PANEL}; }}
        QPushButton#primary {{ background: {theme.ACCENT}; border: none;
            border-radius: {theme.RADIUS_SM}px; padding: 5px 14px 5px 10px;
            color: {theme.INK_ON_ACCENT}; font-size: 12px; font-weight: 600; }}
        QPushButton#primary:hover {{ background: {theme.ACCENT_HOVER}; }}
        QComboBox {{ background: {theme.SIDE_PANEL}; border: 1px solid {theme.BORDER_DARK};
            border-radius: {theme.RADIUS_SM}px; padding: 3px 8px;
            color: {theme.INK_ON_DARK}; font-size: 11px; }}
        QComboBox QAbstractItemView {{ background: {theme.SIDE_PANEL};
            color: {theme.INK_ON_DARK}; selection-background-color: {theme.ACCENT_DIM};
            border: 1px solid {theme.BORDER_DARK}; }}
        """

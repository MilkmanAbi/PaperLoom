"""
Activity bar (VS Code-style): a thin icon rail on the far left. Each button
selects which side panel is shown; clicking the active one toggles the panel
closed. Settings pins to the bottom. Emits the selected view id.
"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QToolButton

from .. import theme
from . import icons


class _ActivityButton(QToolButton):
    def __init__(self, view_id, icon_name, tooltip):
        super().__init__()
        self.view_id = view_id
        self.icon_name = icon_name
        self.setToolTip(tooltip)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(theme.ACTIVITY_BAR_WIDTH, theme.ACTIVITY_BAR_WIDTH)
        self.setIconSize(self.sizeHint() * 0)  # icon set explicitly below
        from PySide6.QtCore import QSize
        self.setIconSize(QSize(22, 22))
        self._refresh_icon(False)

    def _refresh_icon(self, active):
        color = theme.INK_ON_DARK if active else theme.INK_ON_DARK_MUTED
        self.setIcon(icons.icon(self.icon_name, color, 22))


class ActivityBar(QWidget):
    viewSelected = Signal(str)      # view id, or "" when toggled closed
    settingsRequested = Signal()

    # each pane gets a glyph that actually says what it is - a library looks like
    # a library, properties like sliders, assets like an image. No two the same,
    # and the single settings gear lives at the bottom (there used to be two).
    PANES = [
        ("library", "library", "Components"),
        ("pages", "files", "Pages"),
        ("layers", "layers", "Layers"),
        ("properties", "sliders", "Properties"),
        ("assets", "image", "Assets"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ActivityBar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedWidth(theme.ACTIVITY_BAR_WIDTH)
        self.setStyleSheet(self._qss())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 8)
        layout.setSpacing(2)

        self._buttons = {}
        for view_id, icon_name, tip in self.PANES:
            btn = _ActivityButton(view_id, icon_name, tip)
            btn.clicked.connect(lambda _=False, v=view_id: self._on_click(v))
            layout.addWidget(btn, 0, Qt.AlignmentFlag.AlignHCenter)
            self._buttons[view_id] = btn

        layout.addStretch(1)

        self.settings_btn = _ActivityButton("settings", "settings", "Settings")
        self.settings_btn.setCheckable(False)
        self.settings_btn.clicked.connect(lambda: self.settingsRequested.emit())
        layout.addWidget(self.settings_btn, 0, Qt.AlignmentFlag.AlignHCenter)

        # nothing is forced open on boot - the canvas starts clear and the user
        # opens what they want. (Selecting a view here used to emit before the
        # window had wired the signal, which is why Components looked "stuck".)
        self._active = None

    def _qss(self):
        return f"""
            #ActivityBar {{ background: {theme.ACTIVITY_BAR};
                            border-right: 1px solid {theme.BORDER_DARK}; }}
            QToolButton {{ background: transparent; border: none;
                           border-left: 2px solid transparent; }}
            QToolButton:hover {{ background: {theme.SIDE_PANEL}; }}
            QToolButton:checked {{ border-left: 2px solid {theme.ACCENT};
                                   background: {theme.SIDE_PANEL}; }}
        """

    def set_active_view(self, view_id):
        """Reflect externally-driven state (e.g. popup library closed) without
        re-emitting viewSelected."""
        for vid, btn in self._buttons.items():
            active = vid == view_id
            btn.setChecked(active)
            btn._refresh_icon(active)
        self._active = view_id

    def restyle(self):
        self.setStyleSheet(self._qss())
        for vid, btn in self._buttons.items():
            btn._refresh_icon(vid == self._active)
        self.settings_btn._refresh_icon(False)

    def _on_click(self, view_id):
        if self._active == view_id:
            # toggle closed
            self._buttons[view_id].setChecked(False)
            self._buttons[view_id]._refresh_icon(False)
            self._active = None
            self.viewSelected.emit("")
        else:
            self.select(view_id)

    def select(self, view_id):
        for vid, btn in self._buttons.items():
            active = vid == view_id
            btn.setChecked(active)
            btn._refresh_icon(active)
        self._active = view_id
        self.viewSelected.emit(view_id)

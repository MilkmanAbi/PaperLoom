"""
Side-panel host (VS Code's collapsible side bar). Holds the library, pages, and
layers panels in a stack and shows whichever the activity bar selected. Can be
collapsed entirely (width 0) - the canvas takes the space, matching the "panels
are opt-in, nothing is forced open" principle.
"""
from PySide6.QtWidgets import QWidget, QStackedLayout

from .. import theme


class SidePanelHost(QWidget):
    def __init__(self, panels: dict, parent=None):
        """panels: {view_id: QWidget}"""
        super().__init__(parent)
        self.setObjectName("SidePanelHost")
        self.setFixedWidth(theme.SIDE_PANEL_WIDTH)
        self._stack = QStackedLayout(self)
        self._stack.setContentsMargins(0, 0, 0, 0)
        self._ids = []
        for view_id, panel in panels.items():
            self._stack.addWidget(panel)
            self._ids.append(view_id)
        self._collapsed = False

    def show_view(self, view_id):
        if view_id == "" or view_id == "settings":
            self.collapse()
            return
        if view_id in self._ids:
            self._stack.setCurrentIndex(self._ids.index(view_id))
            self.expand()

    def collapse(self):
        self._collapsed = True
        self.setFixedWidth(0)

    def expand(self):
        self._collapsed = False
        self.setFixedWidth(theme.SIDE_PANEL_WIDTH)

    @property
    def collapsed(self):
        return self._collapsed

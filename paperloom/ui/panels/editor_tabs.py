"""
Editor tab strip (VS Code-style): the pages currently OPEN for editing, distinct
from the Pages side panel (spec §7.1's "all skeletons in the project" list -
this is that panel's file-explorer counterpart to VS Code's editor tabs, not a
replacement for it). A real QTabBar, so drag-to-reorder and the close button
come from Qt for free - PaperLoom only decides how flat it looks (an accent
underline on the active tab, no boxed borders, matching the QPushButton#tab
convention the library panel's source tabs already use).

Embedded directly into TopBar (see top_bar.py's set_tab_bar()), beside undo/
redo behind a divider, rather than living on its own row below the whole bar -
so it's transparent/borderless here (the top bar already paints the row's
background and bottom border) and sized to sit comfortably inside that row's
own height, not a full separate strip.

Always visible once a page is open - including the very first page of a
brand-new project, and including the moment you're back down to one tab after
closing others. An earlier revision hid the strip below 2 open tabs; that
read as "closing a tab closed everything" (the whole strip vanished the
instant you got down to one) and left a fresh project looking tab-less, so
it's gone - one tab shown is still a real, visible tab, exactly the VS Code
behavior this widget is modeled on.
"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QTabBar

from ... import theme


class EditorTabBar(QTabBar):
    # index of the right-clicked tab (-1 if the click landed on empty tab-bar
    # space past the last tab), global position to exec() a menu at
    tabContextMenuRequested = Signal(int, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("EditorTabBar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setMovable(True)        # drag to reorder; tabMoved() keeps the model in sync
        self.setTabsClosable(True)   # native close glyph - correctly tracks the tab
        self.setExpanding(False)     # through drags, unlike a hand-rolled index-captured button
        self.setUsesScrollButtons(True)
        self.setElideMode(Qt.TextElideMode.ElideRight)
        self.setFixedHeight(theme.BAR_HEIGHT - 6)
        self.restyle()
        self.setVisible(False)   # nothing open yet; refresh() below shows it

    def refresh(self, pages, active_index):
        """Full rebuild from the open-pages list (mirrors PagesPanel.refresh's
        own clear-and-rebuild convention). Signals are blocked during the
        rebuild so this never re-triggers page activation as a side effect -
        callers that want the page actually switched call that explicitly."""
        self.blockSignals(True)
        while self.count():
            self.removeTab(0)
        for page in pages:
            idx = self.addTab(page.title or page.name)
            self.setTabToolTip(idx, page.name)
        if pages:
            self.setCurrentIndex(max(0, min(active_index, len(pages) - 1)))
        self.blockSignals(False)
        # visible as long as there's anything open at all - even just one tab
        # (see the module docstring: hiding below 2 tabs is what made closing
        # a tab look like it closed every tab)
        self.setVisible(bool(pages))

    def contextMenuEvent(self, event):
        index = self.tabAt(event.pos())
        if index < 0:
            return   # empty tab-bar space past the last tab - nothing to act on
        self.tabContextMenuRequested.emit(index, event.globalPos())

    def restyle(self):
        self.setStyleSheet(f"""
            QTabBar#EditorTabBar {{ background: transparent; border: none; }}
            QTabBar::tab {{ background: transparent; color: {theme.INK_ON_DARK_MUTED};
                border: none; border-bottom: 2px solid transparent;
                border-radius: {theme.RADIUS_SM}px;
                padding: 3px 6px 3px 10px; margin: 0; font-size: 12px; }}
            QTabBar::tab:hover {{ color: {theme.INK_ON_DARK}; background: {theme.SIDE_PANEL}; }}
            QTabBar::tab:selected {{ color: {theme.INK_ON_DARK};
                border-bottom: 2px solid {theme.ACCENT}; background: {theme.SIDE_PANEL}; }}
            QTabBar::close-button {{ subcontrol-position: right; }}
            QTabBar::close-button:hover {{ background: {theme.ACTIVITY_BAR}; border-radius: 3px; }}
            QTabBar QToolButton {{ background: transparent; border: none; }}
            QTabBar::scroller {{ width: 20px; }}
        """)

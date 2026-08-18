"""
Library panel (VS Code side-panel + EasyEDA library, combined). Source tabs
(PaperDesign / Default / User) let the user pick where components come from -
built for a future where users contribute designs. Search filters within the
active source; results render as cards with a live preview (spec §4.3) plus the
name, so you see what you're getting before you drop it.

Placing: double-click a card, or click its Place button, to drop onto the canvas.
"""
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QLabel, QScrollArea,
    QPushButton, QButtonGroup, QFrame
)

from ... import theme
from .. import icons, preview


# labels for the source tabs; only sources actually present are shown
_SOURCE_LABELS = {"default": "Default", "user": "User"}
# PaperDesign was a theme, not a component source (spec §26)
_SOURCE_ORDER = ["default", "user"]


class _PanelHeader(QWidget):
    def __init__(self, title):
        super().__init__()
        self.setFixedHeight(34)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 0, 8, 0)
        label = QLabel(title.upper())
        label.setStyleSheet(
            f"color: {theme.INK_ON_DARK_MUTED}; font-size: 11px; font-weight: 600;"
            " letter-spacing: 0.5px;")
        lay.addWidget(label)
        lay.addStretch(1)


class _ComponentCard(QFrame):
    placeRequested = Signal(str)

    def __init__(self, component):
        super().__init__()
        self.component = component
        self.setObjectName("card")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.restyle()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(4)

        thumb = QLabel()
        pix = preview.preview(component, width=232, height=52)
        thumb.setPixmap(pix)
        thumb.setFixedHeight(52)
        thumb.setStyleSheet(
            f"border-radius: {theme.RADIUS_SM}px; border: 1px solid {theme.BORDER_DARK};")
        thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(thumb)

        row = QHBoxLayout()
        row.setContentsMargins(2, 0, 2, 0)
        name = QLabel(component.name)
        name.setObjectName("name")
        row.addWidget(name)
        row.addStretch(1)
        lay.addLayout(row)

    def restyle(self):
        self.setStyleSheet(f"""
            #card {{ background: transparent; border: 1px solid transparent;
                     border-radius: {theme.RADIUS_MD}px; }}
            #card:hover {{ background: {theme.ACCENT_DIM};
                           border: 1px solid {theme.ACCENT}; }}
            QLabel#name {{ color: {theme.INK_ON_DARK}; font-size: 12px; font-weight: 500; }}
            QLabel#desc {{ color: {theme.INK_ON_DARK_MUTED}; font-size: 10px; }}
        """)

    def mouseDoubleClickEvent(self, event):
        self.placeRequested.emit(self.component.id)


class LibraryPanel(QWidget):
    componentChosen = Signal(str)

    def __init__(self, registry, parent=None):
        super().__init__(parent)
        self.registry = registry
        self.setObjectName("LibraryPanel")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            #LibraryPanel {{ background: {theme.SIDE_PANEL};
                             border-right: 1px solid {theme.BORDER_DARK}; }}
            QLineEdit {{ background: {theme.ACTIVITY_BAR}; color: {theme.INK_ON_DARK};
                         border: 1px solid {theme.BORDER_DARK}; border-radius: {theme.RADIUS_SM}px;
                         padding: 6px 8px; font-size: 12px; }}
            QLineEdit:focus {{ border: 1px solid {theme.ACCENT}; }}
            QPushButton#tab {{ background: transparent; color: {theme.INK_ON_DARK_MUTED};
                               border: none; border-bottom: 2px solid transparent;
                               padding: 6px 10px; font-size: 11px; font-weight: 600; }}
            QPushButton#tab:hover {{ color: {theme.INK_ON_DARK}; }}
            QPushButton#tab:checked {{ color: {theme.INK_ON_DARK};
                                       border-bottom: 2px solid {theme.ACCENT}; }}
            QScrollArea {{ background: transparent; border: none; }}
            QWidget#scrollBody {{ background: transparent; }}
            QLabel#empty {{ color: {theme.INK_ON_DARK_FAINT}; font-size: 11px; }}
        """)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        outer.addWidget(_PanelHeader("Components"))

        # --- source tabs ---
        tab_row = QHBoxLayout()
        tab_row.setContentsMargins(8, 0, 8, 0)
        tab_row.setSpacing(0)
        self._tab_group = QButtonGroup(self)
        self._tab_group.setExclusive(True)
        present = [s for s in _SOURCE_ORDER if s in self.registry.sources()]
        # always show all three tabs so the "future contribution" model reads,
        # even when a source currently has no components
        for source in _SOURCE_ORDER:
            btn = QPushButton(_SOURCE_LABELS[source])
            btn.setObjectName("tab")
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _=False, s=source: self._set_source(s))
            self._tab_group.addButton(btn)
            tab_row.addWidget(btn)
            if source == (present[0] if present else "default"):
                btn.setChecked(True)
                self._source = source
        tab_row.addStretch(1)
        tab_wrap = QWidget()
        tab_wrap.setLayout(tab_row)
        outer.addWidget(tab_wrap)

        # --- search ---
        search_wrap = QWidget()
        sl = QVBoxLayout(search_wrap)
        sl.setContentsMargins(8, 8, 8, 8)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search components...")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._refresh)
        sl.addWidget(self.search)
        outer.addWidget(search_wrap)

        # --- scrollable card list ---
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._body = QWidget()
        self._body.setObjectName("scrollBody")
        self._body_layout = QVBoxLayout(self._body)
        self._body_layout.setContentsMargins(8, 0, 8, 8)
        self._body_layout.setSpacing(4)
        self._body_layout.addStretch(1)
        self.scroll.setWidget(self._body)
        outer.addWidget(self.scroll, 1)

        self._refresh()

    def _set_source(self, source):
        self._source = source
        self._refresh()

    def _clear_cards(self):
        while self._body_layout.count() > 1:   # keep the trailing stretch
            item = self._body_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

    def _refresh(self):
        self._clear_cards()
        query = self.search.text()
        results = [c for c in self.registry.by_source(self._source) if c.matches(query)]
        results.sort(key=lambda c: (c.category, c.name))

        if not results:
            empty = QLabel("No components in this source yet." if not query
                           else "No matches.")
            empty.setObjectName("empty")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setContentsMargins(0, 24, 0, 0)
            self._body_layout.insertWidget(0, empty)
            return

        current_cat = None
        insert_at = 0
        for c in results:
            if c.category != current_cat:
                current_cat = c.category
                header = QLabel(c.category.capitalize())
                header.setStyleSheet(
                    f"color: {theme.INK_ON_DARK_FAINT}; font-size: 10px;"
                    " font-weight: 600; padding: 6px 2px 2px 2px;")
                self._body_layout.insertWidget(insert_at, header)
                insert_at += 1
            card = _ComponentCard(c)
            card.placeRequested.connect(self.componentChosen.emit)
            self._body_layout.insertWidget(insert_at, card)
            insert_at += 1

    def restyle(self):
        self.setStyleSheet(f"""
            #LibraryPanel {{ background: {theme.SIDE_PANEL};
                             border-right: 1px solid {theme.BORDER_DARK}; }}
            QLineEdit {{ background: {theme.ACTIVITY_BAR}; color: {theme.INK_ON_DARK};
                         border: 1px solid {theme.BORDER_DARK}; border-radius: {theme.RADIUS_SM}px;
                         padding: 6px 8px; font-size: 12px; }}
            QLineEdit:focus {{ border: 1px solid {theme.ACCENT}; }}
            QPushButton#tab {{ background: transparent; color: {theme.INK_ON_DARK_MUTED};
                               border: none; border-bottom: 2px solid transparent;
                               padding: 6px 10px; font-size: 11px; font-weight: 600; }}
            QPushButton#tab:hover {{ color: {theme.INK_ON_DARK}; }}
            QPushButton#tab:checked {{ color: {theme.INK_ON_DARK};
                                       border-bottom: 2px solid {theme.ACCENT}; }}
            QScrollArea {{ background: transparent; border: none; }}
            QWidget#scrollBody {{ background: transparent; }}
            QLabel#empty {{ color: {theme.INK_ON_DARK_FAINT}; font-size: 11px; }}
        """)
        for i in range(self._body_layout.count()):
            w = self._body_layout.itemAt(i).widget()
            if hasattr(w, "restyle"):
                w.restyle()

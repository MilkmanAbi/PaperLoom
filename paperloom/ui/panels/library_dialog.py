"""
Popup component library (spec §12.2) - the EasyEDA "Library" dialog equivalent.
A proper modal browse-and-discover surface: source tabs, type/category filters,
a searchable result table, a large live preview, and a details pane showing the
component's properties and signals. Place drops it on the canvas.

The side panel stays for quick access; this is where you go to actually look.
"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QListWidget, QListWidgetItem, QWidget, QButtonGroup, QFrame, QTextBrowser,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView
)

from ... import theme
from .. import preview

# PaperDesign was a theme, not a component source (spec §26)
_SOURCE_ORDER = ["default", "user"]
_SOURCE_LABELS = {"default": "Default", "user": "User"}


class LibraryDialog(QDialog):
    componentChosen = Signal(str)

    def __init__(self, registry, parent=None):
        super().__init__(parent)
        self.registry = registry
        self.setWindowTitle("Component Library")
        self.resize(940, 600)
        self.setObjectName("LibraryDialog")
        self._source = "default"
        self._current = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # --- header: title + search ---
        header = QWidget(); header.setObjectName("dlgHeader")
        hl = QHBoxLayout(header); hl.setContentsMargins(16, 12, 16, 12); hl.setSpacing(12)
        title = QLabel("Library"); title.setObjectName("dlgTitle")
        hl.addWidget(title)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search by name, tag or description...")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._refresh)
        hl.addWidget(self.search, 1)
        outer.addWidget(header)

        # --- filter row: source tabs + category ---
        filters = QWidget(); filters.setObjectName("dlgFilters")
        fl = QHBoxLayout(filters); fl.setContentsMargins(16, 0, 16, 0); fl.setSpacing(0)
        fl.addWidget(self._label("Source"))
        self._tabs = {}
        for src in _SOURCE_ORDER:
            b = QPushButton(_SOURCE_LABELS[src]); b.setObjectName("srcTab")
            b.setCheckable(True); b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setChecked(src == self._source)
            b.clicked.connect(lambda _=False, s=src: self._set_source(s))
            fl.addWidget(b); self._tabs[src] = b
        fl.addSpacing(24)
        fl.addWidget(self._label("Category"))
        self._cat_buttons = {}
        self._category = ""
        for cat in ["All"] + self.registry.categories():
            key = "" if cat == "All" else cat
            b = QPushButton(cat.capitalize()); b.setObjectName("catTab")
            b.setCheckable(True); b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setChecked(key == "")
            b.clicked.connect(lambda _=False, k=key: self._set_category(k))
            fl.addWidget(b); self._cat_buttons[key] = b
        fl.addStretch(1)
        outer.addWidget(filters)

        # --- body: table | preview+details ---
        body = QWidget()
        bl = QHBoxLayout(body); bl.setContentsMargins(16, 12, 16, 12); bl.setSpacing(16)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Component", "Category", "Qt class"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.itemSelectionChanged.connect(self._on_selected)
        self.table.itemDoubleClicked.connect(lambda _i: self._place())
        bl.addWidget(self.table, 3)

        right = QWidget()
        rl = QVBoxLayout(right); rl.setContentsMargins(0, 0, 0, 0); rl.setSpacing(10)
        self.preview_label = QLabel("Select a component")
        self.preview_label.setObjectName("previewBox")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMinimumHeight(120)
        rl.addWidget(self.preview_label)
        self.details = QTextBrowser()
        self.details.setObjectName("details")
        rl.addWidget(self.details, 1)
        bl.addWidget(right, 2)
        outer.addWidget(body, 1)

        # --- footer ---
        footer = QWidget(); footer.setObjectName("dlgFooter")
        ftl = QHBoxLayout(footer); ftl.setContentsMargins(16, 10, 16, 12); ftl.setSpacing(8)
        self._breadcrumb = QLabel("")
        self._breadcrumb.setObjectName("crumb")
        ftl.addWidget(self._breadcrumb)
        ftl.addStretch(1)
        close = QPushButton("Close"); close.setObjectName("ghost")
        close.clicked.connect(self.reject)
        self.place_btn = QPushButton("Place"); self.place_btn.setObjectName("primary")
        self.place_btn.setEnabled(False)
        self.place_btn.clicked.connect(self._place)
        ftl.addWidget(close); ftl.addWidget(self.place_btn)
        outer.addWidget(footer)

        self.restyle()
        self._refresh()

    def _label(self, text):
        l = QLabel(text); l.setObjectName("filterLabel")
        return l

    def _set_source(self, src):
        self._source = src
        for s, b in self._tabs.items():
            b.setChecked(s == src)
        self._refresh()

    def _set_category(self, key):
        self._category = key
        for k, b in self._cat_buttons.items():
            b.setChecked(k == key)
        self._refresh()

    def _results(self):
        out = [c for c in self.registry.by_source(self._source)
               if c.matches(self.search.text())]
        if self._category:
            out = [c for c in out if c.category == self._category]
        return sorted(out, key=lambda c: c.name)

    def _refresh(self):
        results = self._results()
        self.table.setRowCount(len(results))
        for row, c in enumerate(results):
            name = QTableWidgetItem(c.name)
            name.setData(Qt.ItemDataRole.UserRole, c.id)
            self.table.setItem(row, 0, name)
            self.table.setItem(row, 1, QTableWidgetItem(c.category.capitalize()))
            self.table.setItem(row, 2, QTableWidgetItem(c.widget_class))
        self._current = None
        self.place_btn.setEnabled(False)
        self.details.setHtml("")
        self.preview_label.setPixmap(_blank())
        self.preview_label.setText("" if results else "No components match.")
        self._breadcrumb.setText(
            f"{_SOURCE_LABELS[self._source]} · {len(results)} component(s)")

    def _on_selected(self):
        items = self.table.selectedItems()
        if not items:
            return
        cid = self.table.item(items[0].row(), 0).data(Qt.ItemDataRole.UserRole)
        component = self.registry.get(cid)
        if component is None:
            return
        self._current = component
        self.place_btn.setEnabled(True)
        self.preview_label.setPixmap(preview.preview(component, width=300, height=110))
        self.details.setHtml(self._details_html(component))
        self._breadcrumb.setText(
            f"{_SOURCE_LABELS[self._source]} · {component.category.capitalize()} · {component.name}")

    def _details_html(self, c):
        props = "".join(
            f"<tr><td>{p.name}</td><td><i>{p.type}</i></td>"
            f"<td>{p.default}</td></tr>" for p in c.properties)
        sigs = "".join(f"<li>{s.name}</li>" for s in c.signals) or "<li>none</li>"
        ink, muted, accent = theme.INK_ON_DARK, theme.INK_ON_DARK_MUTED, theme.ACCENT
        return f"""
        <div style="color:{ink}; font-size:12px;">
          <p style="color:{muted};">{c.description}</p>
          <p><b style="color:{accent};">Qt class</b> &nbsp; {c.widget_class}</p>
          <p><b style="color:{accent};">Properties</b></p>
          <table width="100%" cellspacing="0" cellpadding="3"
                 style="color:{ink}; font-size:11px;">{props}</table>
          <p><b style="color:{accent};">Signals</b></p>
          <ul style="color:{ink}; font-size:11px;">{sigs}</ul>
          <p style="color:{muted}; font-size:10px;">tags: {", ".join(c.tags)}</p>
        </div>"""

    def _place(self):
        if self._current is not None:
            self.componentChosen.emit(self._current.id)

    def restyle(self):
        self.setStyleSheet(f"""
            #LibraryDialog {{ background: {theme.SIDE_PANEL}; }}
            #dlgHeader {{ background: {theme.ACTIVITY_BAR};
                          border-bottom: 1px solid {theme.BORDER_DARK}; }}
            #dlgTitle {{ color: {theme.INK_ON_DARK}; font-size: 15px; font-weight: 700; }}
            #dlgFilters {{ background: {theme.ACTIVITY_BAR};
                           border-bottom: 1px solid {theme.BORDER_DARK}; padding: 6px 0; }}
            QLabel#filterLabel {{ color: {theme.INK_ON_DARK_FAINT}; font-size: 10px;
                                  font-weight: 700; padding-right: 8px; }}
            QPushButton#srcTab, QPushButton#catTab {{
                background: transparent; color: {theme.INK_ON_DARK_MUTED}; border: none;
                border-bottom: 2px solid transparent; padding: 6px 12px; font-size: 11px; }}
            QPushButton#srcTab:checked, QPushButton#catTab:checked {{
                color: {theme.INK_ON_DARK}; border-bottom: 2px solid {theme.ACCENT}; }}
            QPushButton#srcTab:hover, QPushButton#catTab:hover {{ color: {theme.INK_ON_DARK}; }}
            QLineEdit {{ background: {theme.SIDE_PANEL}; border: 1px solid {theme.BORDER_DARK};
                border-radius: {theme.RADIUS_SM}px; padding: 5px 10px;
                color: {theme.INK_ON_DARK}; font-size: 12px; }}
            QLineEdit:focus {{ border: 1px solid {theme.ACCENT}; }}
            QTableWidget {{ background: {theme.ACTIVITY_BAR}; border: 1px solid {theme.BORDER_DARK};
                border-radius: {theme.RADIUS_SM}px; color: {theme.INK_ON_DARK};
                gridline-color: {theme.BORDER_DARK}; font-size: 12px; }}
            QTableWidget::item {{ padding: 6px; }}
            QTableWidget::item:selected {{ background: {theme.ACCENT_DIM};
                                           color: {theme.INK_ON_DARK}; }}
            QHeaderView::section {{ background: {theme.SIDE_PANEL}; color: {theme.INK_ON_DARK_MUTED};
                border: none; border-bottom: 1px solid {theme.BORDER_DARK};
                padding: 6px; font-size: 11px; font-weight: 600; }}
            QLabel#previewBox {{ background: {theme.SURFACE_CANVAS};
                border: 1px solid {theme.BORDER_DARK}; border-radius: {theme.RADIUS_MD}px;
                color: {theme.INK_SECONDARY}; }}
            QTextBrowser#details {{ background: {theme.ACTIVITY_BAR};
                border: 1px solid {theme.BORDER_DARK}; border-radius: {theme.RADIUS_MD}px;
                padding: 8px; }}
            #dlgFooter {{ background: {theme.ACTIVITY_BAR};
                          border-top: 1px solid {theme.BORDER_DARK}; }}
            QLabel#crumb {{ color: {theme.INK_ON_DARK_FAINT}; font-size: 11px; }}
            QPushButton#primary {{ background: {theme.ACCENT}; color: {theme.INK_ON_ACCENT};
                border: none; border-radius: {theme.RADIUS_SM}px; padding: 6px 20px;
                font-size: 12px; font-weight: 600; }}
            QPushButton#primary:disabled {{ background: {theme.BORDER_DARK};
                                            color: {theme.INK_ON_DARK_FAINT}; }}
            QPushButton#ghost {{ background: transparent; color: {theme.INK_ON_DARK};
                border: 1px solid {theme.BORDER_DARK}; border-radius: {theme.RADIUS_SM}px;
                padding: 6px 16px; font-size: 12px; }}
            QPushButton#ghost:hover {{ border: 1px solid {theme.ACCENT}; }}
        """)


def _blank():
    from PySide6.QtGui import QPixmap
    pm = QPixmap(1, 1)
    pm.fill(Qt.GlobalColor.transparent)
    return pm

"""
Command palette (spec §12.7, Go > Command Palette / Ctrl+Shift+P). VS Code-style
fuzzy-ish filter over every menu command, plus pages and components, so the
global search bar and the palette share one index.
"""
from PySide6.QtCore import Qt, QEvent, Signal
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLineEdit, QListWidget, QListWidgetItem,
    QWidget, QLabel
)

from ... import theme
from .menu_bar import menu_spec


def command_index():
    """[(display, command_id, shortcut)] for every menu command. Shortcut is
    kept separate from the label (not baked into one string) so the palette
    can render it as right-aligned key chips, VS Code-style."""
    out = []
    for title, items in menu_spec():
        for entry in items:
            if entry is None:
                continue
            label, cmd, shortcut = entry
            if cmd == "view.theme_menu":
                continue
            display = f"{title}: {label}"
            out.append((display, cmd, shortcut or ""))
    return out


class CommandPalette(QDialog):
    commandChosen = Signal(str)
    pageChosen = Signal(int)
    componentChosen = Signal(str)

    def __init__(self, registry, project, parent=None):
        super().__init__(parent)
        self.registry = registry
        self.project = project
        self._context_provider = None
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setObjectName("Palette")
        self.resize(620, 400)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(1, 1, 1, 1)
        lay.setSpacing(0)

        self.input = QLineEdit()
        self.input.setPlaceholderText("Type a command, page or component...")
        self.input.textChanged.connect(self._refresh)
        self.input.returnPressed.connect(self._activate_current)
        lay.addWidget(self.input)

        self.list = QListWidget()
        self.list.itemActivated.connect(lambda _i: self._activate_current())
        self.list.itemClicked.connect(lambda _i: self._activate_current())
        # hover should move the keyboard-current row too, or pressing Enter
        # after moving the mouse activates a different item than the one
        # visually highlighted - a real VS Code palette keeps mouse/keyboard
        # selection in sync at all times.
        self.list.setMouseTracking(True)
        self.list.itemEntered.connect(self.list.setCurrentItem)
        lay.addWidget(self.list, 1)

        self.restyle()
        self._refresh()

    def open_with(self, prefix=""):
        self.input.setText(prefix)
        self._refresh()
        self.input.setFocus()
        self.show()
        self.raise_()

    def set_context_provider(self, fn):
        """fn() -> list[(display, command_id)] of actions relevant right now
        (what's selected, the current page). Makes the palette app-aware."""
        self._context_provider = fn

    def _refresh(self):
        q = self.input.text().strip().lower()
        self.list.clear()

        def add(display, kind, payload, shortcut=""):
            it = QListWidgetItem()
            it.setData(Qt.ItemDataRole.UserRole, (kind, payload))
            row = self._row_widget(display, shortcut)
            it.setSizeHint(row.sizeHint())
            self.list.addItem(it)
            self.list.setItemWidget(it, row)

        # context actions first - the thing you most likely want right now
        if self._context_provider is not None:
            for display, cmd in self._context_provider():
                if not q or q in display.lower():
                    add(display, "command", cmd)

        for display, cmd, shortcut in command_index():
            if not q or q in display.lower():
                add(display, "command", cmd, shortcut)
        for i, page in enumerate(self.project.pages):
            label = f"Go to page: {page.name}"
            if not q or q in label.lower():
                add(label, "page", i)
        for c in self.registry.all():
            label = f"Place component: {c.name}"
            if not q or q in label.lower() or q in " ".join(c.tags):
                add(label, "component", c.id)

        if self.list.count():
            self.list.setCurrentRow(0)

    def _row_widget(self, display, shortcut=""):
        """A label on the left, the shortcut as separate right-aligned key
        chips on the right (e.g. Ctrl / Shift / P as three small boxes) -
        matching VS Code's palette instead of one long plain-text string."""
        row = QWidget()
        row.setObjectName("paletteRow")
        lay = QHBoxLayout(row)
        lay.setContentsMargins(14, 5, 12, 5)
        lay.setSpacing(6)
        label = QLabel(display)
        label.setObjectName("paletteRowLabel")
        lay.addWidget(label, 1)
        if shortcut:
            for i, key in enumerate(shortcut.split("+")):
                if i:
                    plus = QLabel("+")
                    plus.setObjectName("paletteRowPlus")
                    lay.addWidget(plus)
                chip = QLabel(key.strip())
                chip.setObjectName("paletteRowChip")
                lay.addWidget(chip)
        return row

    def _activate_current(self):
        item = self.list.currentItem()
        if item is None:
            return
        kind, payload = item.data(Qt.ItemDataRole.UserRole)
        self.hide()
        if kind == "command":
            self.commandChosen.emit(payload)
        elif kind == "page":
            self.pageChosen.emit(payload)
        else:
            self.componentChosen.emit(payload)

    def event(self, e):
        # Being a non-modal Dialog rather than a Qt.WindowType.Popup, nothing
        # closes this when the user clicks elsewhere - it just sits there.
        # WindowDeactivate fires on any top-level window the instant a click
        # (or focus change) lands somewhere else, which is exactly VS Code's
        # own "click away to dismiss" palette behaviour.
        if e.type() == QEvent.Type.WindowDeactivate and self.isVisible():
            self.hide()
        return super().event(e)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.hide()
            return
        if event.key() in (Qt.Key.Key_Down, Qt.Key.Key_Up):
            count = self.list.count()
            if count == 0:
                return
            row = self.list.currentRow()
            row += 1 if event.key() == Qt.Key.Key_Down else -1
            # wrap around at the ends, like VS Code's palette - down from the
            # last item goes to the first, up from the first goes to the last
            row %= count
            self.list.setCurrentRow(row)
            return
        super().keyPressEvent(event)

    def restyle(self):
        self.setStyleSheet(f"""
            #Palette {{ background: {theme.SIDE_PANEL};
                        border: 1px solid {theme.ACCENT}; }}
            QLineEdit {{ background: {theme.ACTIVITY_BAR}; color: {theme.INK_ON_DARK};
                border: none; border-bottom: 1px solid {theme.BORDER_DARK};
                padding: 12px 14px; font-size: 14px; }}
            QListWidget {{ background: {theme.SIDE_PANEL}; border: none; outline: none;
                color: {theme.INK_ON_DARK}; font-size: 12px; }}
            QListWidget::item {{ padding: 0px; }}
            QListWidget::item:selected {{ background: {theme.ACCENT_DIM}; }}
            QListWidget::item:hover {{ background: {theme.ACTIVITY_BAR}; }}
            #paletteRow {{ background: transparent; }}
            QLabel#paletteRowLabel {{ color: {theme.INK_ON_DARK}; font-size: 12px;
                background: transparent; }}
            QLabel#paletteRowPlus {{ color: {theme.INK_ON_DARK_FAINT}; font-size: 10px;
                background: transparent; }}
            QLabel#paletteRowChip {{ color: {theme.INK_ON_DARK_MUTED}; font-size: 10px;
                background: {theme.ACTIVITY_BAR}; border: 1px solid {theme.BORDER_DARK};
                border-radius: 4px; padding: 1px 6px; }}
        """)

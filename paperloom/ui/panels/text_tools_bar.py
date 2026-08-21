"""
Text formatting toolbar - a fast lane to the Markdown syntax people reach for
constantly (bold, italic, a heading, a bullet), without opening the full
Markdown Studio dialog. Same footprint/pattern as QuickEditBar
(context_menus.py): a frameless Qt.WindowType.Tool window that floats next to
the current selection and appears/disappears as selection changes.

Shown alongside - not instead of - the existing QuickEditBar, whenever the
canvas-selected widget has a property worth formatting: a markdown-typed
property (Markdown Studio's own domain), or a plain string `text`/`title`
property (checked the same way main_window._edit_markdown_for_dw already
finds a markdown property - see main_window._text_property_for_dw).

Each button calls back into main_window with a format "kind" id
(bold/italic/strike/heading/bullet/link); main_window resolves which property
on the selected DesignWidget to touch, runs the matching pure transform from
core/text_format.py, and applies it via canvas.apply_property - the same
mutation path the Properties panel and Markdown Studio already use, so this
is a faster way to reach an existing path, not a new one.
"""
from __future__ import annotations
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QPushButton, QLabel

from ... import theme
from .. import icons

_BUTTONS = [
    ("bold", "bold", "Bold"),
    ("italic", "italic", "Italic"),
    ("strike", "strikethrough", "Strikethrough"),
    ("heading", "heading", "Heading"),
    ("bullet", "list", "Bullet list"),
    ("link", "link", "Link"),
]


class TextToolsBar(QFrame):
    """A compact floating bar of Markdown formatting actions. Appears next to
    the selection, same anchoring convention as QuickEditBar.show_for()."""

    formatRequested = Signal(str)   # one of _BUTTONS' kind ids

    def __init__(self, parent=None):
        super().__init__(parent, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint)
        self.setObjectName("TextTools")

        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 5, 6, 5)
        lay.setSpacing(2)

        lay.addWidget(self._label("Text"))
        self._buttons = []
        for kind, icon_name, tip in _BUTTONS:
            b = QPushButton()
            b.setIcon(icons.icon(icon_name, theme.INK_ON_DARK_MUTED, 15))
            b.setToolTip(tip)
            b.setFixedSize(26, 26)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _=False, k=kind: self.formatRequested.emit(k))
            lay.addWidget(b)
            self._buttons.append((b, icon_name))

        self.restyle()
        self.hide()

    def _label(self, text):
        label = QLabel(text)
        label.setObjectName("dim")
        return label

    def show_for(self, live_widget, canvas):
        """Anchor above the selected widget, same placement math QuickEditBar
        uses - the two bars stack sensibly since main_window shows both."""
        anchor = live_widget.mapTo(canvas, live_widget.rect().topLeft())
        pos = canvas.mapToGlobal(anchor)
        self.adjustSize()
        self.move(pos.x(), max(0, pos.y() - self.height() - 8))
        self.show()
        self.raise_()

    def restyle(self):
        self.setStyleSheet(f"""
            #TextTools {{ background: {theme.SIDE_PANEL};
                border: 1px solid {theme.ACCENT}; border-radius: {theme.RADIUS_MD}px; }}
            QLabel#dim {{ color: {theme.INK_ON_DARK_MUTED}; font-size: 11px;
                padding-right: 2px; }}
            QPushButton {{ background: transparent; border: none; border-radius: 4px; }}
            QPushButton:hover {{ background: {theme.ACCENT_DIM}; }}
        """)
        for b, icon_name in self._buttons:
            b.setIcon(icons.icon(icon_name, theme.INK_ON_DARK_MUTED, 15))

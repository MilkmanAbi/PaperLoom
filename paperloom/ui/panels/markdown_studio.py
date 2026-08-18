"""
Markdown Studio (spec §46) - the "write Markdown, cleanly see it" window.

Left: a Markdown source editor. Right: a live preview that renders exactly what
the widget will show (same `richtext.to_html`, so math and colours match). A top
toolbar turns selections into headings, bold/italic, lists, quotes, code, links.
A floating toolbar rises over the selection with quick text tools - colour, font,
size - so formatting is where your eyes already are.

Colour/font/size are written as inline `<span style="...">`, which Qt's Markdown
passes straight through, so they render in the preview, on the canvas and in the
generated app alike.
"""
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QTextCursor, QFont
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPlainTextEdit, QTextBrowser, QPushButton,
    QLabel, QWidget, QToolButton, QFontComboBox, QComboBox, QMenu, QFrame
)

from ... import theme
from .. import icons
from .color_picker import ColorPickerDialog
from ...core import richtext


class _SelectionToolbar(QFrame):
    """Floats over the source editor when text is selected (the tools appear
    where you're looking). Quick text tools: bold, italic, colour, size."""

    def __init__(self, editor, studio):
        super().__init__(editor)
        self.editor = editor
        self.studio = studio
        self.setObjectName("selBar")
        self.setWindowFlags(Qt.WindowType.ToolTip)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(4, 3, 4, 3)
        lay.setSpacing(2)
        for label, tip, slot in [
            ("B", "Bold", studio.bold),
            ("i", "Italic", studio.italic),
            ("A", "Colour", studio.color),
            ("A+", "Size", studio.size_menu),
        ]:
            b = QToolButton()
            b.setText(label)
            b.setToolTip(tip)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(slot)
            lay.addWidget(b)
        self.hide()

    def reposition(self):
        cur = self.editor.textCursor()
        if not cur.hasSelection():
            self.hide()
            return
        rect = self.editor.cursorRect(cur)
        self.adjustSize()
        x = min(max(rect.left(), 4),
                self.editor.width() - self.width() - 4)
        y = rect.top() - self.height() - 4
        if y < 2:
            y = rect.bottom() + 4
        self.move(x, y)
        self.show()
        self.raise_()


class MarkdownStudio(QDialog):
    def __init__(self, content="", parent=None):
        super().__init__(parent)
        self.setObjectName("MarkdownStudio")
        self.setWindowTitle("Markdown Studio")
        self.resize(920, 640)
        self.result_markdown = content

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self._build_toolbar())

        split = QWidget()
        sl = QHBoxLayout(split)
        sl.setContentsMargins(12, 10, 12, 10)
        sl.setSpacing(10)

        left = QWidget()
        ll = QVBoxLayout(left); ll.setContentsMargins(0, 0, 0, 0); ll.setSpacing(4)
        ll.addWidget(self._caption("MARKDOWN"))
        self.editor = QPlainTextEdit()
        self.editor.setObjectName("mdSource")
        self.editor.setPlainText(content)
        self.editor.textChanged.connect(self._queue_render)
        self.editor.selectionChanged.connect(self._on_selection)
        self.editor.cursorPositionChanged.connect(self._on_selection)
        ll.addWidget(self.editor, 1)

        right = QWidget()
        rl = QVBoxLayout(right); rl.setContentsMargins(0, 0, 0, 0); rl.setSpacing(4)
        rl.addWidget(self._caption("PREVIEW"))
        self.preview = QTextBrowser()
        self.preview.setObjectName("mdPreview")
        self.preview.setOpenExternalLinks(True)
        rl.addWidget(self.preview, 1)

        sl.addWidget(left, 1)
        sl.addWidget(right, 1)
        outer.addWidget(split, 1)

        footer = QWidget(); footer.setObjectName("mdFooter")
        fl = QHBoxLayout(footer); fl.setContentsMargins(12, 8, 12, 10)
        self._hint = QLabel("Markdown + $LaTeX$ - headings, **bold**, lists, links, math")
        self._hint.setObjectName("mdHint")
        fl.addWidget(self._hint); fl.addStretch(1)
        cancel = QPushButton("Cancel"); cancel.setObjectName("mdGhost")
        cancel.clicked.connect(self.reject)
        save = QPushButton("Done"); save.setObjectName("mdPrimary")
        save.clicked.connect(self._accept)
        fl.addWidget(cancel); fl.addWidget(save)
        outer.addWidget(footer)

        self._sel_bar = _SelectionToolbar(self.editor, self)
        self._timer = QTimer(self); self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._render)
        self._restyle()
        self._render()

    # --- toolbar --------------------------------------------------------------
    def _build_toolbar(self):
        bar = QWidget(); bar.setObjectName("mdToolbar")
        lay = QHBoxLayout(bar); lay.setContentsMargins(10, 6, 10, 6); lay.setSpacing(4)

        def tb(text, tip, slot):
            b = QToolButton(); b.setText(text); b.setToolTip(tip)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(slot); lay.addWidget(b); return b

        tb("H1", "Heading 1", lambda: self.heading(1))
        tb("H2", "Heading 2", lambda: self.heading(2))
        tb("H3", "Heading 3", lambda: self.heading(3))
        lay.addWidget(self._sep())
        tb("B", "Bold", self.bold)
        tb("i", "Italic", self.italic)
        tb("S", "Strikethrough", self.strike)
        tb("</>", "Inline code", self.code)
        lay.addWidget(self._sep())
        tb("• List", "Bullet list", self.bullet)
        tb("1. List", "Numbered list", self.numbered)
        tb("❝", "Quote", self.quote)
        tb("Link", "Link", self.link)
        tb("Math", "Inline math", self.math)
        lay.addWidget(self._sep())

        self._font = QFontComboBox()
        self._font.setMaximumWidth(150)
        self._font.activated.connect(lambda _=0: self.set_font(self._font.currentFont().family()))
        lay.addWidget(self._font)
        self._size = QComboBox()
        self._size.addItems(["12", "14", "16", "18", "24", "32"])
        self._size.setMaximumWidth(60)
        self._size.activated.connect(lambda _=0: self.set_size(int(self._size.currentText())))
        lay.addWidget(self._size)
        tb("A", "Text colour", self.color)
        lay.addStretch(1)
        return bar

    def _sep(self):
        s = QFrame(); s.setObjectName("mdSep"); s.setFixedWidth(1); return s

    def _caption(self, text):
        c = QLabel(text); c.setObjectName("mdCaption"); return c

    # --- formatting actions ---------------------------------------------------
    def _wrap(self, prefix, suffix=None, placeholder="text"):
        suffix = prefix if suffix is None else suffix
        cur = self.editor.textCursor()
        sel = cur.selectedText() or placeholder
        cur.insertText(f"{prefix}{sel}{suffix}")
        self.editor.setFocus()

    def _line_prefix(self, prefix):
        cur = self.editor.textCursor()
        cur.beginEditBlock()
        start = cur.selectionStart(); end = cur.selectionEnd()
        cur.setPosition(start); cur.movePosition(QTextCursor.MoveOperation.StartOfBlock)
        while True:
            cur.insertText(prefix)
            if not cur.movePosition(QTextCursor.MoveOperation.NextBlock):
                break
            if cur.position() > end + len(prefix):
                break
        cur.endEditBlock()
        self.editor.setFocus()

    def heading(self, level):
        self._line_prefix("#" * level + " ")

    def bold(self):
        self._wrap("**")

    def italic(self):
        self._wrap("*")

    def strike(self):
        self._wrap("~~")

    def code(self):
        self._wrap("`")

    def bullet(self):
        self._line_prefix("- ")

    def numbered(self):
        self._line_prefix("1. ")

    def quote(self):
        self._line_prefix("> ")

    def link(self):
        cur = self.editor.textCursor()
        sel = cur.selectedText() or "text"
        cur.insertText(f"[{sel}](https://)")
        self.editor.setFocus()

    def math(self):
        self._wrap("$", "$", "x^2")

    def color(self):
        picked = ColorPickerDialog.get_color("#e11d48", self)
        if picked is not None:
            self._span(f"color:{picked.name()}")

    def set_font(self, family):
        self._span(f"font-family:'{family}'")

    def set_size(self, px):
        self._span(f"font-size:{px}px")

    def size_menu(self):
        menu = QMenu(self)
        for px in (12, 14, 16, 18, 24, 32):
            menu.addAction(f"{px}px", lambda p=px: self.set_size(p))
        menu.exec(self._sel_bar.mapToGlobal(self._sel_bar.rect().bottomLeft()))

    def _span(self, style):
        cur = self.editor.textCursor()
        sel = cur.selectedText() or "text"
        cur.insertText(f'<span style="{style}">{sel}</span>')
        self.editor.setFocus()

    # --- preview + selection --------------------------------------------------
    def _queue_render(self):
        self._timer.start(220)

    def _render(self):
        html = richtext.to_html(self.editor.toPlainText())
        self.preview.setHtml(html)

    def _on_selection(self):
        self._sel_bar.reposition()

    def _accept(self):
        self.result_markdown = self.editor.toPlainText()
        self.accept()

    @staticmethod
    def edit(content, parent=None):
        dlg = MarkdownStudio(content, parent)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            return dlg.result_markdown
        return None

    def _restyle(self):
        self.setStyleSheet(f"""
            #MarkdownStudio {{ background: {theme.SIDE_PANEL}; }}
            #mdToolbar {{ background: {theme.ACTIVITY_BAR};
                border-bottom: 1px solid {theme.BORDER_DARK}; }}
            #mdFooter {{ background: {theme.ACTIVITY_BAR};
                border-top: 1px solid {theme.BORDER_DARK}; }}
            QLabel#mdCaption {{ color: {theme.INK_ON_DARK_MUTED}; font-size: 10px;
                font-weight: 700; letter-spacing: 0.6px; }}
            QLabel#mdHint {{ color: {theme.INK_ON_DARK_FAINT}; font-size: 11px; }}
            QToolButton {{ background: transparent; color: {theme.INK_ON_DARK};
                border: 1px solid transparent; border-radius: {theme.RADIUS_SM}px;
                padding: 4px 7px; font-size: 12px; }}
            QToolButton:hover {{ background: {theme.SIDE_PANEL};
                border-color: {theme.BORDER_DARK}; }}
            QFrame#mdSep {{ background: {theme.BORDER_DARK}; }}
            QPlainTextEdit#mdSource {{ background: {theme.ACTIVITY_BAR};
                color: {theme.INK_ON_DARK}; border: 1px solid {theme.BORDER_DARK};
                border-radius: {theme.RADIUS_SM}px; padding: 8px;
                font-family: {theme.MONO_STACK if hasattr(theme,'MONO_STACK') else 'monospace'};
                font-size: 13px; selection-background-color: {theme.ACCENT}; }}
            QTextBrowser#mdPreview {{ background: #FFFFFF; color: #1a1a1a;
                border: 1px solid {theme.BORDER_DARK}; border-radius: {theme.RADIUS_SM}px;
                padding: 8px; }}
            QFontComboBox, QComboBox {{ background: {theme.SIDE_PANEL};
                color: {theme.INK_ON_DARK}; border: 1px solid {theme.BORDER_DARK};
                border-radius: {theme.RADIUS_SM}px; padding: 3px 6px; font-size: 11px; }}
            QComboBox QAbstractItemView, QFontComboBox QAbstractItemView {{
                background: {theme.SIDE_PANEL}; color: {theme.INK_ON_DARK};
                selection-background-color: {theme.ACCENT_DIM if hasattr(theme,'ACCENT_DIM') else theme.ACCENT}; }}
            #selBar {{ background: {theme.ACTIVITY_BAR};
                border: 1px solid {theme.ACCENT}; border-radius: 6px; }}
            #selBar QToolButton {{ color: {theme.INK_ON_DARK}; font-size: 12px;
                padding: 3px 7px; }}
            QPushButton#mdGhost {{ background: transparent; color: {theme.INK_ON_DARK};
                border: 1px solid {theme.BORDER_DARK}; border-radius: {theme.RADIUS_SM}px;
                padding: 6px 16px; font-size: 12px; }}
            QPushButton#mdGhost:hover {{ border-color: {theme.ACCENT}; }}
            QPushButton#mdPrimary {{ background: {theme.ACCENT};
                color: {theme.INK_ON_ACCENT}; border: none;
                border-radius: {theme.RADIUS_SM}px; padding: 6px 20px;
                font-size: 12px; font-weight: 600; }}
            QPushButton#mdPrimary:hover {{ background: {theme.ACCENT_HOVER}; }}
        """)
        b = self.editor.font(); b.setBold(True)

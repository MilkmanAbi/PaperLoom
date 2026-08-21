"""
Code Editor - a popup window to hand-edit a page's *logic* file directly
inside PaperLoom, for "absolute control" without leaving the app.

Codegen already splits its output in two (codegen/base.py): the generated UI
file is always overwritten (`_write_generated` - PaperLoom-owned, never
meant to be hand-edited, your changes would just vanish on the next Generate/
Run) and the logic file is written ONCE and never touched again after that
(`_write_logic_once` - yours forever). That split already exists purely so
hand-written logic survives regeneration; this editor is just a fast way to
reach the file that guarantee already protects, instead of alt-tabbing to an
external editor.

Scoped to the CURRENT page's logic file only (not a full project file
browser - see main_window._on_code_editor for the open/switch/dirty-guard
logic) and to PySide6 projects (the logic file is real Python; C++ projects
emit a header+source+CMakeLists quartet that's a different shape of problem,
deferred). Real syntax highlighting (PythonHighlighter, a single-pass regex
tokenizer - good enough for a quick-access editor, not a claim of full
Python-grammar correctness: it doesn't track multi-line strings or exclude
"#" inside a string from being read as a comment start) and a line-number
gutter (Qt's own well-known QPlainTextEdit + LineNumberArea pattern) so it
reads as a real code editor, not a plain text box.
"""
from __future__ import annotations
import os
import re

from PySide6.QtCore import Qt, QRect, QSize, Signal
from PySide6.QtGui import QColor, QFont, QKeySequence, QPainter, QSyntaxHighlighter, QTextCharFormat
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QPlainTextEdit, QMessageBox
)

from .. import theme
from . import icons
from . import branding

MONO_STACK = ('"Cascadia Mono", "Cascadia Code", Consolas, "DejaVu Sans Mono", '
              'Menlo, monospace')

_KEYWORDS = (
    "False", "None", "True", "and", "as", "assert", "async", "await",
    "break", "class", "continue", "def", "del", "elif", "else", "except",
    "finally", "for", "from", "global", "if", "import", "in", "is",
    "lambda", "nonlocal", "not", "or", "pass", "raise", "return", "self",
    "try", "while", "with", "yield",
)


class PythonHighlighter(QSyntaxHighlighter):
    """A compact single-pass tokenizer, not a full Python grammar - good
    enough to make hand-written logic legible at a glance."""

    def __init__(self, document):
        super().__init__(document)
        self._rules = []

        kw_fmt = QTextCharFormat()
        kw_fmt.setForeground(QColor("#C678DD"))
        kw_fmt.setFontWeight(QFont.Weight.Bold)
        for kw in _KEYWORDS:
            self._rules.append((re.compile(rf"\b{kw}\b"), kw_fmt, 0))

        func_fmt = QTextCharFormat()
        func_fmt.setForeground(QColor("#61AFEF"))
        self._rules.append((re.compile(r"\bdef\s+(\w+)"), func_fmt, 1))
        self._rules.append((re.compile(r"\bclass\s+(\w+)"), func_fmt, 1))

        str_fmt = QTextCharFormat()
        str_fmt.setForeground(QColor("#98C379"))
        self._rules.append((re.compile(r"'[^'\\]*(?:\\.[^'\\]*)*'"), str_fmt, 0))
        self._rules.append((re.compile(r'"[^"\\]*(?:\\.[^"\\]*)*"'), str_fmt, 0))

        num_fmt = QTextCharFormat()
        num_fmt.setForeground(QColor("#D19A66"))
        self._rules.append((re.compile(r"\b[0-9]+\.?[0-9]*\b"), num_fmt, 0))

        self._comment_fmt = QTextCharFormat()
        self._comment_fmt.setForeground(QColor("#5C6370"))
        self._comment_fmt.setFontItalic(True)
        self._comment_re = re.compile(r"#[^\n]*")

    def highlightBlock(self, text):
        for pattern, fmt, group in self._rules:
            for m in pattern.finditer(text):
                self.setFormat(m.start(group), m.end(group) - m.start(group), fmt)
        # applied last so a "#" inside an already-matched string still loses
        # to the comment colour if it happens to look like one - an accepted
        # limitation of a single-pass tokenizer, noted above
        m = self._comment_re.search(text)
        if m:
            self.setFormat(m.start(), m.end() - m.start(), self._comment_fmt)


class _LineNumberArea(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor

    def sizeHint(self):
        return QSize(self.editor.line_number_area_width(), 0)

    def paintEvent(self, event):
        self.editor.line_number_area_paint_event(event)


class _CodeTextEdit(QPlainTextEdit):
    """QPlainTextEdit + a line-number gutter - Qt's own canonical pattern
    (the "Code Editor Example"), adapted to PaperLoom's theme tokens."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.setTabStopDistance(4 * self.fontMetrics().horizontalAdvance(" "))
        self._gutter = _LineNumberArea(self)
        self.blockCountChanged.connect(self._update_gutter_width)
        self.updateRequest.connect(self._update_gutter)
        self._update_gutter_width(0)

    def line_number_area_width(self):
        digits = max(2, len(str(max(1, self.blockCount()))))
        return 12 + self.fontMetrics().horizontalAdvance("9") * digits

    def _update_gutter_width(self, _count):
        self.setViewportMargins(self.line_number_area_width(), 0, 0, 0)

    def _update_gutter(self, rect, dy):
        if dy:
            self._gutter.scroll(0, dy)
        else:
            self._gutter.update(0, rect.y(), self._gutter.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self._update_gutter_width(0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        cr = self.contentsRect()
        self._gutter.setGeometry(QRect(cr.left(), cr.top(), self.line_number_area_width(), cr.height()))

    def line_number_area_paint_event(self, event):
        painter = QPainter(self._gutter)
        painter.fillRect(event.rect(), QColor(theme.ACTIVITY_BAR))
        block = self.firstVisibleBlock()
        block_number = block.blockNumber()
        top = int(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + int(self.blockBoundingRect(block).height())
        muted = QColor(theme.INK_ON_DARK_FAINT)
        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                painter.setPen(muted)
                painter.drawText(0, top, self._gutter.width() - 6, self.fontMetrics().height(),
                                 Qt.AlignmentFlag.AlignRight, str(block_number + 1))
            block = block.next()
            top = bottom
            bottom = top + int(self.blockBoundingRect(block).height())
            block_number += 1


class CodeEditorWindow(QWidget):
    """A floating popup (same Qt.WindowType.Tool footprint every other
    PaperLoom floater uses) editing one page's logic file at a time. Reused
    across opens like QuickPreviewWindow - main_window owns a single
    instance and calls open_path() again to point it at a different file."""

    saved = Signal(str)   # path just written

    def __init__(self, parent=None):
        super().__init__(parent, Qt.WindowType.Tool)
        self.setObjectName("CodeEditor")
        self.setWindowIcon(branding.app_icon())
        self.resize(760, 620)
        self._path = None
        self._dirty = False
        self._loading = False

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        header = QWidget()
        header.setObjectName("ceHeader")
        hl = QHBoxLayout(header)
        hl.setContentsMargins(12, 8, 10, 8)
        hl.setSpacing(8)
        self._icon_label = QLabel()
        self._icon_label.setPixmap(icons.icon("code", theme.INK_ON_DARK_MUTED, 16).pixmap(16, 16))
        hl.addWidget(self._icon_label)
        self.title_label = QLabel("Logic Editor")
        self.title_label.setObjectName("ceTitle")
        hl.addWidget(self.title_label, 1)
        self.hint_label = QLabel("never overwritten by Generate/Run")
        self.hint_label.setObjectName("ceHint")
        hl.addWidget(self.hint_label)
        self.save_btn = QPushButton("Save")
        self.save_btn.setObjectName("ceSave")
        self.save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.save_btn.clicked.connect(self.save)
        hl.addWidget(self.save_btn)
        lay.addWidget(header)

        self.editor = _CodeTextEdit()
        self.editor.setFont(QFont(MONO_STACK.split(",")[0].strip(' "'), 11))
        self.editor.setStyleSheet(f"""
            QPlainTextEdit {{ background: {theme.ACTIVITY_BAR}; color: {theme.INK_ON_DARK};
                border: none; font-family: {MONO_STACK}; font-size: 12px; padding: 6px; }}
        """)
        self.highlighter = PythonHighlighter(self.editor.document())
        self.editor.textChanged.connect(self._on_text_changed)
        lay.addWidget(self.editor, 1)

        self.restyle()
        self._update_save_state()
        self.hide()

    # --- state -------------------------------------------------------------
    @property
    def current_path(self):
        return self._path

    def is_dirty(self):
        return self._dirty

    def open_path(self, path, page_label):
        """Load `path` (creating nothing - the caller is responsible for
        having generated it first, so it always exists by the time we get
        here) into the editor and show the window."""
        self._loading = True
        text = ""
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                text = f.read()
        self.editor.setPlainText(text)
        self._loading = False
        self._path = path
        self._dirty = False
        self.title_label.setText(f"Logic — {page_label}")
        self.title_label.setToolTip(path)
        self._update_save_state()
        self.show()
        self.raise_()
        self.activateWindow()

    def _on_text_changed(self):
        if self._loading:
            return
        self._dirty = True
        self._update_save_state()

    def _update_save_state(self):
        self.save_btn.setEnabled(self._dirty)
        self.save_btn.setText("Save •" if self._dirty else "Save")

    def save(self):
        if self._path is None or not self._dirty:
            return
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        with open(self._path, "w", encoding="utf-8") as f:
            f.write(self.editor.toPlainText())
        self._dirty = False
        self._update_save_state()
        self.saved.emit(self._path)

    # --- lifecycle -----------------------------------------------------------
    def keyPressEvent(self, event):
        if event.matches(QKeySequence.StandardKey.Save):
            self.save()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event):
        if self._dirty:
            resp = QMessageBox.question(
                self, "Unsaved changes", "Save changes before closing?",
                QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard
                | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Save)
            if resp == QMessageBox.StandardButton.Cancel:
                event.ignore()
                return
            if resp == QMessageBox.StandardButton.Save:
                self.save()
        super().closeEvent(event)

    def restyle(self):
        self._icon_label.setPixmap(icons.icon("code", theme.INK_ON_DARK_MUTED, 16).pixmap(16, 16))
        self.setStyleSheet(f"""
            #CodeEditor {{ background: {theme.SIDE_PANEL}; border: 1px solid {theme.ACCENT}; }}
            #ceHeader {{ background: {theme.ACTIVITY_BAR}; border-bottom: 1px solid {theme.BORDER_DARK}; }}
            QLabel#ceTitle {{ color: {theme.INK_ON_DARK}; font-size: 12px; font-weight: 600; }}
            QLabel#ceHint {{ color: {theme.INK_ON_DARK_FAINT}; font-size: 10px; }}
            QPushButton#ceSave {{ background: {theme.ACCENT}; color: {theme.INK_ON_ACCENT};
                border: none; border-radius: {theme.RADIUS_SM}px; padding: 4px 12px; font-size: 11px; }}
            QPushButton#ceSave:disabled {{ background: {theme.BORDER_DARK}; color: {theme.INK_ON_DARK_FAINT}; }}
        """)
        self.editor.setStyleSheet(f"""
            QPlainTextEdit {{ background: {theme.ACTIVITY_BAR}; color: {theme.INK_ON_DARK};
                border: none; font-family: {MONO_STACK}; font-size: 12px; padding: 6px; }}
        """)

"""
Integrated terminal (spec §27). VS Code-style: a real shell, typed into
*inline* at the prompt rather than through a separate input box, with ANSI
colour, carriage-return handling, and full Unicode support.

Text handling, deliberately:
  - decoding is incremental UTF-8, so a multi-byte character split across two
    reads (very common with emoji) is never mangled into replacement chars
  - a bare carriage return rewrites the current line instead of adding one,
    which is what progress bars and spinners actually do
  - ANSI SGR sequences become real colours; cursor/erase sequences are consumed
    rather than printed as garbage
  - the font stack prefers fonts with emoji and CJK coverage
"""
from __future__ import annotations
import codecs
import os
import re
import sys

from PySide6.QtCore import Qt, QProcess, Signal
from PySide6.QtGui import QTextCursor, QTextCharFormat, QColor, QFont, QKeyEvent, QTextDocument
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPlainTextEdit, QToolButton, QLineEdit, QLabel
)

from ... import theme
from ...core import app_settings

_ANSI_SGR = re.compile(r"\x1b\[([0-9;]*)m")
_ANSI_OTHER = re.compile(r"\x1b\[[0-9;?]*[A-Za-ln-z]|\x1b\][^\x07]*\x07|\x1b[()][A-Za-z0-9]")

_ANSI_COLORS = [
    "#3B4048", "#E06C75", "#98C379", "#E5C07B",
    "#61AFEF", "#C678DD", "#56B6C2", "#ABB2BF",
    "#5C6370", "#E06C75", "#98C379", "#E5C07B",
    "#61AFEF", "#C678DD", "#56B6C2", "#FFFFFF",
]

MONO_STACK = ('"Cascadia Mono", "Cascadia Code", Consolas, "DejaVu Sans Mono", '
              '"Noto Sans Mono CJK SC", Menlo, "Noto Color Emoji", '
              '"Segoe UI Emoji", monospace')


# PowerShell has no real console handle when QProcess pipes its stdio (no
# ConPTY here) - so the built-in Clear-Host (what `clear`/`cls` are aliased
# to) crashes with "Exception setting CursorPosition: The handle is invalid"
# the moment it tries to touch $Host.UI.RawUI. We override Clear-Host at
# startup with one that never touches RawUI: it just writes a private-use-
# Unicode-wrapped marker that _on_output() below recognizes and reacts to by
# clearing the view itself (exactly what the toolbar's own Clear button
# does) - so `clear` in-shell behaves the same as clicking Clear, instead of
# crashing. -NoProfile skips the user's personal $PROFILE (Windows commonly
# leaves broken/environment-specific Import-Module lines in there, e.g. a
# WinGet module that only works outside a piped shell) so the embedded
# terminal starts clean; -NoExit keeps the session interactive afterward.
_CLEAR_MARKER = "PAPERLOOM-CLEAR"
_PS_CLEAR_HOST_OVERRIDE = (
    "function Clear-Host { Write-Host -NoNewline "
    "([char]0xE000+'PAPERLOOM-CLEAR'+[char]0xE000) }"
)


def default_shell():
    if sys.platform.startswith("win"):
        import shutil
        # Settings > Terminal lets a person pin this instead of auto-
        # detecting - "cmd" forces cmd.exe even when PowerShell is present,
        # "powershell" forces PowerShell (erroring loudly is unnecessary -
        # if it's genuinely missing we just fall through to auto/cmd below).
        choice = app_settings.get("terminal_shell", "auto")
        if choice == "cmd":
            return os.environ.get("COMSPEC", "cmd.exe"), []
        if choice == "powershell":
            for candidate in ("pwsh.exe", "pwsh", "powershell.exe", "powershell"):
                path = shutil.which(candidate)
                if path:
                    return path, ["-NoLogo", "-NoProfile", "-NoExit", "-Command",
                                  _PS_CLEAR_HOST_OVERRIDE]
        # cmd.exe is painful (no real scripting, weird quoting, dated) - prefer
        # PowerShell. pwsh (PowerShell 7+, cross-platform installer) first,
        # then the Windows-builtin powershell.exe, and only fall back to
        # cmd.exe if genuinely neither is present (very old/stripped Windows).
        for candidate in ("pwsh.exe", "pwsh", "powershell.exe", "powershell"):
            path = shutil.which(candidate)
            if path:
                return path, ["-NoLogo", "-NoProfile", "-NoExit", "-Command",
                              _PS_CLEAR_HOST_OVERRIDE]
        return os.environ.get("COMSPEC", "cmd.exe"), []
    return os.environ.get("SHELL", "/bin/bash"), ["-i"]


# cmd.exe only treats a line as submitted when it ends in CRLF; writing a bare
# "\n" is exactly why the terminal looked "fake" on Windows - the prompt showed
# but nothing you typed ever ran. POSIX shells take "\n". This is the default;
# a per-terminal EOL toggle (Auto/CRLF/LF) can override it for edge cases like
# a remote shell over a proxy that doesn't match the local platform.
SUBMIT_EOL = "\r\n" if sys.platform.startswith("win") else "\n"
_EOL_MODES = {"auto": SUBMIT_EOL, "crlf": "\r\n", "lf": "\n"}
_EOL_CYCLE = ["auto", "crlf", "lf"]


class TerminalView(QPlainTextEdit):
    """A console you type into directly. Everything before the prompt is
    read-only; keystrokes after it edit the pending command line."""

    commandEntered = Signal(str)
    interruptRequested = Signal()
    findRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setUndoRedoEnabled(False)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.document().setMaximumBlockCount(5000)
        self._input_start = 0
        self._history: list[str] = []
        self._history_at = 0

    def mark_input_start(self):
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.setTextCursor(cursor)
        self._input_start = cursor.position()

    def _in_editable_zone(self):
        return self.textCursor().position() >= self._input_start

    def current_input(self):
        return self.toPlainText()[self._input_start:]

    def _replace_input(self, text):
        cursor = self.textCursor()
        cursor.setPosition(self._input_start)
        cursor.movePosition(QTextCursor.MoveOperation.End,
                            QTextCursor.MoveMode.KeepAnchor)
        cursor.insertText(text)
        self.setTextCursor(cursor)

    def keyPressEvent(self, event: QKeyEvent):
        key = event.key()
        ctrl = event.modifiers() & Qt.KeyboardModifier.ControlModifier

        if ctrl and key == Qt.Key.Key_C:
            if self.textCursor().hasSelection():
                super().keyPressEvent(event)
            else:
                self.interruptRequested.emit()
            return
        if ctrl and key == Qt.Key.Key_F:
            self.findRequested.emit()
            return
        if ctrl and key in (Qt.Key.Key_V, Qt.Key.Key_A):
            super().keyPressEvent(event)
            return

        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            command = self.current_input()
            cursor = self.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            cursor.insertText("\n")
            self.setTextCursor(cursor)
            if command.strip():
                self._history.append(command)
            self._history_at = len(self._history)
            self.commandEntered.emit(command)
            return

        if key == Qt.Key.Key_Up:
            if self._history:
                self._history_at = max(0, self._history_at - 1)
                self._replace_input(self._history[self._history_at])
            return
        if key == Qt.Key.Key_Down:
            if self._history:
                self._history_at = min(len(self._history), self._history_at + 1)
                self._replace_input(self._history[self._history_at]
                                    if self._history_at < len(self._history) else "")
            return

        if key in (Qt.Key.Key_Backspace, Qt.Key.Key_Left):
            if self.textCursor().position() <= self._input_start:
                return
        if key == Qt.Key.Key_Home:
            cursor = self.textCursor()
            cursor.setPosition(self._input_start)
            self.setTextCursor(cursor)
            return

        if not self._in_editable_zone() and event.text():
            cursor = self.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            self.setTextCursor(cursor)
        super().keyPressEvent(event)


class TerminalWidget(QWidget):
    """The panel: a real shell process plus the inline console view."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Terminal")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._proc = None
        self._decoder = codecs.getincrementaldecoder("utf-8")("replace")
        self._pending_format = QTextCharFormat()
        self._eol_mode = "auto"     # auto | crlf | lf - see _EOL_MODES
        self._filter_text = ""
        self._find_matches = []
        self._find_index = -1

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        lay.addWidget(self._build_toolbar())

        self.view = TerminalView()
        self.view.commandEntered.connect(self._on_command)
        self.view.interruptRequested.connect(self.interrupt)
        self.view.findRequested.connect(self.open_find)
        lay.addWidget(self.view, 1)

        self._find_bar = self._build_find_bar()
        lay.addWidget(self._find_bar)
        self._find_bar.hide()
        self._find_box.installEventFilter(self)

        self.restyle()

    # --- toolbar: clear / CR-LF / filter --------------------------------------
    def _build_toolbar(self):
        bar = QWidget()
        bar.setObjectName("termToolbar")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(6, 4, 6, 4)
        lay.setSpacing(4)

        self._clear_btn = QToolButton()
        self._clear_btn.setObjectName("termToolBtn")
        self._clear_btn.setText("Clear")
        self._clear_btn.setToolTip("Clear the terminal output")
        self._clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._clear_btn.clicked.connect(self.clear)
        lay.addWidget(self._clear_btn)

        self._eol_btn = QToolButton()
        self._eol_btn.setObjectName("termToolBtn")
        self._eol_btn.setToolTip(
            "Line ending used when you press Enter.\n"
            "Auto follows the platform (CRLF on Windows, LF elsewhere).")
        self._eol_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._eol_btn.clicked.connect(self._cycle_eol_mode)
        self._update_eol_label()
        lay.addWidget(self._eol_btn)

        lay.addStretch(1)

        self._filter_box = QLineEdit()
        self._filter_box.setObjectName("termFilter")
        self._filter_box.setPlaceholderText("Filter output…")
        self._filter_box.setClearButtonEnabled(True)
        self._filter_box.setMaximumWidth(220)
        self._filter_box.textChanged.connect(self._apply_filter)
        lay.addWidget(self._filter_box)
        return bar

    def _cycle_eol_mode(self):
        i = _EOL_CYCLE.index(self._eol_mode)
        self._eol_mode = _EOL_CYCLE[(i + 1) % len(_EOL_CYCLE)]
        self._update_eol_label()

    def _update_eol_label(self):
        label = {"auto": "EOL: Auto", "crlf": "EOL: CRLF", "lf": "EOL: LF"}[self._eol_mode]
        self._eol_btn.setText(label)

    def _current_submit_eol(self) -> str:
        return _EOL_MODES[self._eol_mode]

    def _apply_filter(self, text: str):
        """Live-filter visible output lines by substring (case-insensitive).
        Filtering hides/shows whole blocks rather than mutating the document,
        so the underlying scrollback is never lost - clearing the filter
        restores everything exactly as it was."""
        self._filter_text = text
        needle = text.strip().lower()
        doc = self.view.document()
        block = doc.begin()
        while block.isValid():
            visible = (not needle) or (needle in block.text().lower())
            if block.isVisible() != visible:
                block.setVisible(visible)
            block = block.next()
        doc.markContentsDirty(0, doc.characterCount())
        self.view.viewport().update()

    # --- find (Ctrl-F) ---------------------------------------------------------
    def _build_find_bar(self):
        bar = QWidget()
        bar.setObjectName("termFindBar")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(6, 4, 6, 4)
        lay.setSpacing(4)

        self._find_box = QLineEdit()
        self._find_box.setObjectName("termFilter")
        self._find_box.setPlaceholderText("Find in output…")
        self._find_box.returnPressed.connect(lambda: self._find_step(1))
        self._find_box.textChanged.connect(lambda _t: self._find_step(0))
        lay.addWidget(self._find_box, 1)

        self._find_status = QLabel("")
        self._find_status.setObjectName("termFindStatus")
        lay.addWidget(self._find_status)

        prev_btn = QToolButton(); prev_btn.setObjectName("termToolBtn")
        prev_btn.setText("↑"); prev_btn.setToolTip("Previous match (Shift+Enter)")
        prev_btn.clicked.connect(lambda: self._find_step(-1))
        lay.addWidget(prev_btn)

        next_btn = QToolButton(); next_btn.setObjectName("termToolBtn")
        next_btn.setText("↓"); next_btn.setToolTip("Next match (Enter)")
        next_btn.clicked.connect(lambda: self._find_step(1))
        lay.addWidget(next_btn)

        close_btn = QToolButton(); close_btn.setObjectName("termToolBtn")
        close_btn.setText("✕"); close_btn.setToolTip("Close (Esc)")
        close_btn.clicked.connect(self.close_find)
        lay.addWidget(close_btn)
        return bar

    def open_find(self):
        self._find_bar.show()
        self._find_box.setFocus()
        self._find_box.selectAll()
        if self._find_box.text():
            self._find_step(0)

    def close_find(self):
        self._find_bar.hide()
        self.view.setFocus()

    def _find_step(self, direction: int):
        """direction: 0 = re-search from the current text (typing), 1/-1 = move
        to the next/previous match."""
        needle = self._find_box.text()
        if not needle:
            self._find_status.setText("")
            self._find_matches = []
            self._find_index = -1
            return
        doc = self.view.document()
        matches = []
        cursor = QTextCursor(doc)
        flags = QTextDocument.FindFlag(0)
        while True:
            cursor = doc.find(needle, cursor, flags)
            if cursor.isNull():
                break
            matches.append(QTextCursor(cursor))
        self._find_matches = matches
        if not matches:
            self._find_status.setText("0/0")
            self._find_index = -1
            return
        if direction == 0:
            self._find_index = 0
        else:
            self._find_index = (self._find_index + direction) % len(matches)
        self._find_status.setText(f"{self._find_index + 1}/{len(matches)}")
        self.view.setTextCursor(matches[self._find_index])
        self.view.ensureCursorVisible()

    def eventFilter(self, obj, event):
        if obj is self._find_box and event.type() == event.Type.KeyPress:
            if event.key() == Qt.Key.Key_Escape:
                self.close_find()
                return True
            if (event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
                    and event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
                self._find_step(-1)
                return True
        return super().eventFilter(obj, event)

    def showEvent(self, event):
        # start the shell the moment the terminal becomes visible, so it shows a
        # live prompt instead of an empty box waiting for a first keystroke
        super().showEvent(event)
        self.ensure_started()

    # --- process --------------------------------------------------------------
    def ensure_started(self, cwd=None):
        if self._proc is not None and self._proc.state() != QProcess.ProcessState.NotRunning:
            return
        shell, args = default_shell()
        self._proc = QProcess(self)
        self._proc.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        env = self._proc.processEnvironment()
        env.insert("PYTHONIOENCODING", "utf-8")
        env.insert("PYTHONUTF8", "1")
        env.insert("TERM", "xterm-256color")
        self._proc.setProcessEnvironment(env)
        if cwd and os.path.isdir(cwd):
            self._proc.setWorkingDirectory(cwd)
        self._proc.readyReadStandardOutput.connect(self._on_output)
        self._proc.finished.connect(self._on_finished)
        self._proc.start(shell, args)
        self.append(f"[terminal] {shell} started")

    def _on_finished(self, code, _status=None):
        self.append(f"[process exited with code {code}]")

    def _on_output(self):
        raw = bytes(self._proc.readAllStandardOutput())
        text = self._decoder.decode(raw)
        # our own Clear-Host override (see default_shell()) writes this
        # instead of touching the console cursor - react to it the same way
        # the toolbar's Clear button does, and drop it from the stream.
        if _CLEAR_MARKER in text:
            text = text.replace(_CLEAR_MARKER, "")
            self.clear()
        if text:
            self.write_ansi(text)
            self.view.mark_input_start()

    def _on_command(self, command):
        self.ensure_started()
        if self._proc is not None:
            self._proc.write((command + self._current_submit_eol()).encode("utf-8"))
        self.view.mark_input_start()

    def run_command(self, cmd, cwd=None):
        self.ensure_started(cwd)
        self.append(f"› {cmd}")
        if self._proc is not None:
            self._proc.write((cmd + self._current_submit_eol()).encode("utf-8"))

    def interrupt(self):
        if self._proc is not None and self._proc.state() != QProcess.ProcessState.NotRunning:
            self.append("^C")
            self._proc.write(b"\x03")

    def closeEvent(self, event):
        self.stop()
        super().closeEvent(event)

    def __del__(self):
        try:
            self.stop()
        except Exception:
            pass

    def stop(self):
        if self._proc is not None and self._proc.state() != QProcess.ProcessState.NotRunning:
            self._proc.kill()
            self._proc.waitForFinished(1000)
        self._proc = None

    # --- text rendering -------------------------------------------------------
    def write_ansi(self, text: str):
        try:
            cursor = self.view.textCursor()
        except RuntimeError:
            return
        cursor.movePosition(QTextCursor.MoveOperation.End)

        # CRLF is an ordinary Windows newline, not a carriage return - collapse it
        # first so only a *lone* \r (progress bars, spinners) rewrites the line.
        # Without this every line of cmd.exe/PowerShell output was inserted and
        # then immediately erased by the \r half of its \r\n, so command replies
        # came back invisible on Windows.
        text = text.replace("\r\n", "\n")

        lines = text.split("\n")
        for index, line in enumerate(lines):
            if index:
                cursor.insertText("\n")
            # a bare \r rewrites the line (progress bars, spinners)
            parts = line.split("\r")
            for part_index, piece in enumerate(parts):
                if part_index:
                    cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock,
                                        QTextCursor.MoveMode.KeepAnchor)
                    cursor.removeSelectedText()
                self._insert_with_ansi(cursor, piece)

        self.view.setTextCursor(cursor)
        self.view.ensureCursorVisible()

    def _insert_with_ansi(self, cursor, text):
        pos = 0
        for match in _ANSI_SGR.finditer(text):
            before = text[pos:match.start()]
            if before:
                cursor.insertText(_ANSI_OTHER.sub("", before), self._pending_format)
            self._pending_format = self._format_for(match.group(1))
            pos = match.end()
        rest = text[pos:]
        if rest:
            cursor.insertText(_ANSI_OTHER.sub("", rest), self._pending_format)

    def _format_for(self, params: str) -> QTextCharFormat:
        fmt = QTextCharFormat(self._pending_format)
        codes = [int(c) for c in params.split(";") if c.isdigit()] or [0]
        for code in codes:
            if code == 0:
                fmt = QTextCharFormat()
                fmt.setForeground(QColor(theme.INK_ON_DARK))
            elif code == 1:
                fmt.setFontWeight(QFont.Weight.Bold)
            elif code == 3:
                fmt.setFontItalic(True)
            elif code == 4:
                fmt.setFontUnderline(True)
            elif 30 <= code <= 37:
                fmt.setForeground(QColor(_ANSI_COLORS[code - 30]))
            elif 90 <= code <= 97:
                fmt.setForeground(QColor(_ANSI_COLORS[code - 90 + 8]))
            elif 40 <= code <= 47:
                fmt.setBackground(QColor(_ANSI_COLORS[code - 40]))
        return fmt

    def append(self, text):
        # the shell can outlive the widget at shutdown and emit finished() after
        # the view is gone; writing then raises from deep inside Qt
        try:
            self.view.appendPlainText(text)
            self.view.mark_input_start()
        except RuntimeError:
            pass

    def clear(self):
        self.view.clear()
        self.view.mark_input_start()
        if self._filter_box.text():
            self._filter_box.clear()   # clear() itself triggers _apply_filter

    def restyle(self):
        self.setStyleSheet(f"""
            #Terminal {{ background: {theme.ACTIVITY_BAR}; }}
            QPlainTextEdit {{ background: {theme.ACTIVITY_BAR}; border: none;
                color: {theme.INK_ON_DARK}; font-family: {MONO_STACK};
                font-size: 12px; padding: 8px;
                selection-background-color: {theme.ACCENT};
                selection-color: {theme.INK_ON_ACCENT}; }}
            #termToolbar {{ background: {theme.SIDE_PANEL};
                border-bottom: 1px solid {theme.BORDER_DARK}; }}
            #termFindBar {{ background: {theme.SIDE_PANEL};
                border-top: 1px solid {theme.BORDER_DARK}; }}
            QToolButton#termToolBtn {{ background: transparent; color: {theme.INK_ON_DARK_MUTED};
                border: 1px solid {theme.BORDER_DARK}; border-radius: {theme.RADIUS_SM}px;
                padding: 2px 8px; font-size: 11px; }}
            QToolButton#termToolBtn:hover {{ color: {theme.INK_ON_DARK}; border-color: {theme.ACCENT}; }}
            QLineEdit#termFilter {{ background: {theme.ACTIVITY_BAR}; color: {theme.INK_ON_DARK};
                border: 1px solid {theme.BORDER_DARK}; border-radius: {theme.RADIUS_SM}px;
                padding: 3px 6px; font-size: 11px; }}
            QLineEdit#termFilter:focus {{ border-color: {theme.ACCENT}; }}
            QLabel#termFindStatus {{ color: {theme.INK_ON_DARK_FAINT}; font-size: 11px; }}
        """)
        # setStyleSheet alone doesn't recolour a QPlainTextEdit that's already
        # visible with content, so plain text stays the old theme's colour when
        # you flip light/dark with the terminal open. Push the palette and force
        # a viewport repaint so it tracks the theme like every other panel.
        from PySide6.QtGui import QPalette, QColor
        pal = self.view.palette()
        pal.setColor(QPalette.ColorRole.Base, QColor(theme.ACTIVITY_BAR))
        pal.setColor(QPalette.ColorRole.Text, QColor(theme.INK_ON_DARK))
        self.view.setPalette(pal)
        self._pending_format = QTextCharFormat()
        self.view.viewport().update()

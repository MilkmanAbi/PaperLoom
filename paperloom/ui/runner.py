"""
Runs a generated app as a child process and relays everything back to the UI
(spec §11.3): live stdout/stderr into the Output tab, and parsed Python
tracebacks into structured Problems entries. Uses QProcess so streaming
integrates with Qt's event loop without blocking.
"""
from __future__ import annotations
import re
import os

from PySide6.QtCore import QObject, QProcess, Signal

# matches: File "path", line 42
_TRACE_RE = re.compile(r'File "([^"]+)", line (\d+)')
# matches a trailing "SomeError: message" line
_ERROR_RE = re.compile(r'^([A-Za-z_][\w.]*(?:Error|Exception|Warning)): (.+)$')


class AppRunner(QObject):
    output = Signal(str)              # a line of stdout/stderr
    problem = Signal(str, str, int)   # message, file, line
    finished = Signal(int)            # exit code

    def __init__(self, parent=None):
        super().__init__(parent)
        self._proc = None
        self._buffer = ""
        self._last_trace = ("", 0)    # most recent File/line seen in a traceback

    def run(self, script_path: str, python_exe: str):
        self.stop()
        self._buffer = ""
        self._last_trace = ("", 0)
        self._proc = QProcess(self)
        self._proc.setWorkingDirectory(os.path.dirname(script_path))
        self._proc.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self._proc.readyReadStandardOutput.connect(self._on_output)
        self._proc.finished.connect(lambda code, _s: self.finished.emit(code))
        self._proc.start(python_exe, [script_path])

    def stop(self):
        if self._proc is not None and self._proc.state() != QProcess.ProcessState.NotRunning:
            self._proc.kill()
            self._proc.waitForFinished(1000)
        self._proc = None

    def _on_output(self):
        data = bytes(self._proc.readAllStandardOutput()).decode("utf-8", "replace")
        self._buffer += data
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            self._handle_line(line)

    def _handle_line(self, line: str):
        self.output.emit(line)
        trace = _TRACE_RE.search(line)
        if trace:
            self._last_trace = (trace.group(1), int(trace.group(2)))
            return
        err = _ERROR_RE.match(line.strip())
        if err:
            msg = f"{err.group(1)}: {err.group(2)}"
            file, ln = self._last_trace
            self.problem.emit(msg, file, ln)

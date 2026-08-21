"""
Runs a generated app as a child process and relays everything back to the UI
(spec §11.3): live stdout/stderr into the Output tab, and parsed Python
tracebacks into structured Problems entries. Uses QProcess so streaming
integrates with Qt's event loop without blocking.
"""
from __future__ import annotations
import glob
import re
import os
import shutil
import sys

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


class CppBuildRunner(QObject):
    """Run for a C++ target: PySide6 Run just launches a script, but C++
    needs an actual compiler in the loop first. This chains three real
    QProcess stages - configure, build, then run - through the exact same
    "one click, see it running" motion PySide6 already gets, instead of
    PaperLoom dropping raw source + a CMakeLists.txt and telling the user
    to go figure out the rest themselves.

    On Windows, plain `cmake -B build` picks up whatever Visual Studio/MSVC
    toolchain is already registered with CMake - this deliberately does NOT
    hardcode a generator string, since guessing the wrong VS version/arch is
    worse than letting CMake's own defaults (which is exactly what a person
    would get running cmake by hand) decide. If CMake itself isn't on PATH,
    or the configure/build step fails, this reports that clearly and stops -
    it never silently falls back to anything else.
    """
    stageStarted = Signal(str)         # "configure" | "build" | "run"
    output = Signal(str)               # a line of stdout/stderr, any stage
    problem = Signal(str, str, int)    # message, file, line (compiler errors)
    buildFailed = Signal(str, int)     # stage, exit code
    cmakeMissing = Signal()
    finished = Signal(int)             # the RUN stage's exit code

    # MSVC's compiler emits `path(line): error C1234: message` - a distinct
    # shape from the Python traceback regexes above, so compiler errors also
    # surface as real Problems entries rather than scrolling past in Output.
    _MSVC_ERROR_RE = re.compile(r'^(.+?)\((\d+)\).*:\s*(error [A-Za-z0-9]+:.+)$')
    _GCC_ERROR_RE = re.compile(r'^(.+?):(\d+):\d+:\s*(error:.+)$')

    def __init__(self, parent=None):
        super().__init__(parent)
        self._proc = None
        self._buffer = ""
        self._src_dir = None
        self._build_dir = None
        self._exe_name = None

    def start(self, src_dir: str, exe_name: str):
        """src_dir: the folder holding CMakeLists.txt (paths['cmake']'s
        directory). exe_name: the CMake target/executable name (cpp_backend
        names it after the page's snake_case name - the same string both
        add_executable() and target_link_libraries() use)."""
        self.stop()
        cmake = shutil.which("cmake")
        if not cmake:
            self.cmakeMissing.emit()
            return
        self._src_dir = src_dir
        self._build_dir = os.path.join(src_dir, "build")
        self._exe_name = exe_name
        self._run_stage("configure", cmake, ["-S", src_dir, "-B", self._build_dir])

    def stop(self):
        if self._proc is not None and self._proc.state() != QProcess.ProcessState.NotRunning:
            self._proc.kill()
            self._proc.waitForFinished(1000)
        self._proc = None

    def _run_stage(self, stage, program, args):
        self._stage = stage
        self._buffer = ""
        self.stageStarted.emit(stage)
        self._proc = QProcess(self)
        self._proc.setWorkingDirectory(self._src_dir)
        self._proc.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self._proc.readyReadStandardOutput.connect(self._on_output)
        self._proc.finished.connect(self._on_stage_finished)
        self._proc.start(program, args)

    def _on_output(self):
        data = bytes(self._proc.readAllStandardOutput()).decode("utf-8", "replace")
        self._buffer += data
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            self._handle_line(line)

    def _handle_line(self, line: str):
        self.output.emit(line)
        if self._stage != "build":
            return
        m = self._MSVC_ERROR_RE.match(line.strip()) or self._GCC_ERROR_RE.match(line.strip())
        if m:
            file, ln, msg = m.group(1), int(m.group(2)), m.group(3)
            self.problem.emit(msg, file, ln)

    def _on_stage_finished(self, code, _status):
        stage = self._stage
        if code != 0:
            self.buildFailed.emit(stage, code)
            self._proc = None
            return
        if stage == "configure":
            cmake = shutil.which("cmake")
            self._run_stage("build", cmake, ["--build", self._build_dir])
        elif stage == "build":
            exe = self._find_executable()
            if exe is None:
                self.buildFailed.emit("build", 0)
                return
            self._run_stage("run", exe, [])
        else:  # "run" stage's own process just exited
            self.finished.emit(code)
            self._proc = None

    def _find_executable(self):
        """The build succeeded, but WHERE the binary landed depends on the
        generator CMake picked - Visual Studio's multi-config generator puts
        it under build/Debug/ or build/Release/, Ninja/Makefiles put it
        directly under build/. Searching for it beats guessing a fixed path
        for a generator PaperLoom didn't choose."""
        name = self._exe_name + (".exe" if sys.platform.startswith("win") else "")
        matches = glob.glob(os.path.join(self._build_dir, "**", name), recursive=True)
        return matches[0] if matches else None

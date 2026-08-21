"""
Bottom panel (VS Code style). Tabbed Output / Problems / Debug, collapsible.
Output streams live process text; Problems holds parsed, structured issues
(clickable later); Debug is groundwork for VS Code / debugger integration.
Starts hidden - costs nothing until opened.
"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QPlainTextEdit,
    QListWidget, QListWidgetItem
)

from ... import theme


class BottomPanel(QWidget):
    problemActivated = Signal(str, int)   # file, line - for jump-to (future)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("BottomPanel")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(self._qss())
        self.setFixedHeight(200)
        

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        tabs = QHBoxLayout()
        tabs.setContentsMargins(8, 0, 8, 0)
        tabs.setSpacing(0)
        self._tabs = {}
        for key, label in [("output", "OUTPUT"), ("problems", "PROBLEMS"),
                           ("debug", "DEBUG"), ("terminal", "TERMINAL")]:
            btn = QPushButton(label)
            btn.setObjectName("tab"); btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _=False, k=key: self._switch(k))
            tabs.addWidget(btn)
            self._tabs[key] = btn
        self._problem_count = QPushButton("0")
        self._problem_count.setObjectName("count")
        self._problem_count.setEnabled(False)
        self._problem_count.hide()
        tabs.addWidget(self._problem_count)
        tabs.addStretch(1)
        tab_wrap = QWidget(); tab_wrap.setLayout(tabs)
        outer.addWidget(tab_wrap)

        self._output = QPlainTextEdit(); self._output.setReadOnly(True)
        self._problems = QListWidget()
        self._problems.itemActivated.connect(self._on_problem_clicked)
        self._debug = QPlainTextEdit(); self._debug.setReadOnly(True)
        self._debug.setPlainText("Debug session integration coming soon.\n"
                                 "Will attach to the running generated app.")
        from .terminal import TerminalWidget
        self.terminal = TerminalWidget()
        self.terminal.hide()
        outer.addWidget(self._output, 1)
        outer.addWidget(self._problems, 1)
        outer.addWidget(self._debug, 1)
        outer.addWidget(self.terminal, 1)

        self._problem_entries = []
        self._switch("output")

    def _switch(self, which):
        for k, btn in self._tabs.items():
            btn.setChecked(k == which)
        self._output.setVisible(which == "output")
        self._problems.setVisible(which == "problems")
        self._debug.setVisible(which == "debug")
        self.terminal.setVisible(which == "terminal")
        if which == "terminal":
            self.terminal.ensure_started()
            self.terminal.view.setFocus()

    # --- output ---
    def log(self, message):
        self._output.appendPlainText(message)

    def clear_output(self):
        self._output.clear()

    # --- problems ---
    def clear_problems(self):
        self._problems.clear()
        self._problem_entries = []
        self._update_count()

    def add_problem(self, message, file="", line=0):
        item = QListWidgetItem(("● " + message) if not file else f"● {message}  —  {file}:{line}")
        item.setData(Qt.ItemDataRole.UserRole, (file, line))
        self._problems.addItem(item)
        self._problem_entries.append((message, file, line))
        self._update_count()

    def _update_count(self):
        n = len(self._problem_entries)
        self._problem_count.setText(str(n))
        self._problem_count.setVisible(n > 0)

    def _on_problem_clicked(self, item):
        file, line = item.data(Qt.ItemDataRole.UserRole)
        if file:
            self.problemActivated.emit(file, line)

    def show_problems_tab(self):
        self._switch("problems")

    def show_tab(self, which):
        self._switch(which)

    def problem_count(self):
        return len(self._problem_entries)

    def _qss(self):
        return f"""
            #BottomPanel {{ background: {theme.BOTTOM_BAR};
                            border-top: 1px solid {theme.BORDER_DARK}; }}
            QPushButton#tab {{ background: transparent; color: {theme.INK_ON_DARK_MUTED};
                border: none; border-bottom: 2px solid transparent;
                padding: 6px 12px; font-size: 11px; font-weight: 600; }}
            QPushButton#tab:hover {{ color: {theme.INK_ON_DARK}; }}
            QPushButton#tab:checked {{ color: {theme.INK_ON_DARK};
                border-bottom: 2px solid {theme.ACCENT}; }}
            QPushButton#count {{ background: {theme.ACCENT}; color: {theme.INK_ON_ACCENT};
                border: none; border-radius: 8px; padding: 0 6px; font-size: 10px; }}
            QPlainTextEdit {{ background: {theme.ACTIVITY_BAR}; border: none;
                color: {theme.INK_ON_DARK_MUTED}; font-family: 'Consolas','Menlo',monospace;
                font-size: 11px; padding: 6px; }}
            QListWidget {{ background: {theme.ACTIVITY_BAR}; border: none; outline: none;
                color: {theme.INK_ON_DARK}; font-size: 11px; }}
            QListWidget::item {{ padding: 4px 8px; border-bottom: 1px solid {theme.BORDER_DARK}; }}
            QListWidget::item:hover {{ background: {theme.SIDE_PANEL}; }}
        """

    def restyle(self):
        self.setStyleSheet(self._qss())
        self.terminal.restyle()

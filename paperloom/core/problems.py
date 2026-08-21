"""
Central problem reporting (spec §25). Everything that can go wrong - a codegen
coercion, a failed asset import, a bad stylesheet, a crashed preview, a corrupt
project file - reports here, and the Problems panel renders one consistent list
instead of each subsystem inventing its own channel.
"""
from __future__ import annotations
import weakref
import time
from dataclasses import dataclass, field

SEVERITIES = ("error", "warning", "info")


@dataclass
class Problem:
    message: str
    severity: str = "warning"
    source: str = ""          # "codegen" | "assets" | "run" | "project" | "styles"
    file: str = ""
    line: int = 0
    at: float = field(default_factory=time.time)

    def label(self):
        where = f"  —  {self.file}:{self.line}" if self.file else ""
        return f"{self.message}{where}"


class ProblemLog:
    """Append-only within a run; listeners repaint on change."""

    def __init__(self):
        self._items: list[Problem] = []
        self._listeners = []

    def on_change(self, callback):
        """Listeners are held weakly. A window that has been closed must not be
        called back into - that raised "Internal C++ object already deleted"
        when a second window changed the theme."""
        if hasattr(callback, "__self__"):
            self._listeners.append(weakref.WeakMethod(callback))
        else:
            self._listeners.append(callback)

    def off_change(self, callback):
        self._listeners = [
            listener for listener in self._listeners
            if not (listener is callback
                    or (isinstance(listener, weakref.WeakMethod)
                        and listener() == callback))]

    def _notify(self):
        alive = []
        for listener in self._listeners:
            fn = listener() if isinstance(listener, weakref.WeakMethod) else listener
            if fn is None:
                continue
            alive.append(listener)
            try:
                fn(self)
            except Exception:
                pass
        self._listeners = alive

    def add(self, message, severity="warning", source="", file="", line=0):
        problem = Problem(message=message, severity=severity,
                          source=source, file=file, line=line)
        self._items.append(problem)
        self._notify()
        return problem

    def error(self, message, **kw):
        return self.add(message, severity="error", **kw)

    def warn(self, message, **kw):
        return self.add(message, severity="warning", **kw)

    def info(self, message, **kw):
        return self.add(message, severity="info", **kw)

    def extend(self, messages, severity="warning", source=""):
        for m in messages:
            self.add(m, severity=severity, source=source)

    def clear(self, source=None):
        if source is None:
            self._items = []
        else:
            self._items = [p for p in self._items if p.source != source]
        self._notify()

    def all(self):
        return list(self._items)

    def by_severity(self, severity):
        return [p for p in self._items if p.severity == severity]

    def counts(self):
        return {s: len(self.by_severity(s)) for s in SEVERITIES}

    def __len__(self):
        return len(self._items)

"""
A minimal command stack for undo/redo (spec §1: visible undo/redo is a stated
requirement). UI-agnostic: commands are plain callables with a do/undo pair, so
the canvas records edits here and the top bar just calls undo()/redo() and reads
can_undo/can_redo to drive its buttons.

Commands are coalesced only when explicitly asked (e.g. a drag produces many
geometry updates but should undo as one step) - the canvas decides that, not
this stack.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Callable


@dataclass
class Command:
    label: str
    do: Callable[[], None]
    undo: Callable[[], None]


class UndoStack:
    def __init__(self):
        self._undo: list[Command] = []
        self._redo: list[Command] = []
        self._listeners: list[Callable[[], None]] = []

    def on_change(self, callback: Callable[[], None]) -> None:
        self._listeners.append(callback)

    def _notify(self) -> None:
        for cb in self._listeners:
            cb()

    def push(self, command: Command, run: bool = True) -> None:
        """Record a command. If run=True, execute its do() now."""
        if run:
            command.do()
        self._undo.append(command)
        self._redo.clear()
        self._notify()

    def undo(self) -> None:
        if not self._undo:
            return
        cmd = self._undo.pop()
        cmd.undo()
        self._redo.append(cmd)
        self._notify()

    def redo(self) -> None:
        if not self._redo:
            return
        cmd = self._redo.pop()
        cmd.do()
        self._undo.append(cmd)
        self._notify()

    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)

    @property
    def undo_label(self) -> str:
        return self._undo[-1].label if self._undo else ""

    @property
    def redo_label(self) -> str:
        return self._redo[-1].label if self._redo else ""

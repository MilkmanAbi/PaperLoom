"""
Stylesheet manager (spec §24). Users bring their own QSS: import a .qss file,
have it validated and layered on top of the app theme, and have it travel with
the project and into generated code.

Layering order (last wins, like CSS):
    app theme QSS  ->  imported stylesheets in order  ->  per-widget overrides
"""
from __future__ import annotations
import os
import re
from dataclasses import dataclass


@dataclass
class Stylesheet:
    name: str
    source: str
    path: str = ""
    enabled: bool = True

    def to_dict(self):
        return {"name": self.name, "path": self.path,
                "enabled": self.enabled, "source": self.source}

    @classmethod
    def from_dict(cls, d):
        return cls(name=d.get("name", "sheet"), source=d.get("source", ""),
                   path=d.get("path", ""), enabled=d.get("enabled", True))


class StylesheetError(Exception):
    pass


def validate(source: str) -> list[str]:
    """Cheap structural QSS validation. Returns a list of problems (empty = fine).
    Not a full parser - it catches the mistakes that actually break Qt silently."""
    problems = []
    depth = 0
    for lineno, line in enumerate(source.splitlines(), 1):
        stripped = line.split("/*")[0]
        depth += stripped.count("{") - stripped.count("}")
        if depth < 0:
            problems.append(f"line {lineno}: unmatched closing brace")
            depth = 0
    if depth > 0:
        problems.append(f"{depth} unclosed block(s) - missing '}}'")
    if source.count("/*") != source.count("*/"):
        problems.append("unterminated /* comment */")
    for lineno, line in enumerate(source.splitlines(), 1):
        s = line.strip()
        if not s or s.startswith(("/*", "*", "}", "{")):
            continue
        if ":" in s and not s.endswith((";", "{", "}", ",")) and "{" not in s:
            problems.append(f"line {lineno}: declaration may be missing a ';'")
    return problems


class StylesheetManager:
    def __init__(self):
        self.sheets: list[Stylesheet] = []
        self.errors: list[str] = []

    def import_file(self, path: str) -> Stylesheet:
        if not os.path.isfile(path):
            raise StylesheetError(f"No such stylesheet: {path}")
        if os.path.splitext(path)[1].lower() not in (".qss", ".css", ".txt"):
            raise StylesheetError("Stylesheets must be .qss or .css")
        try:
            with open(path, encoding="utf-8") as f:
                source = f.read()
        except OSError as exc:
            raise StylesheetError(f"Could not read stylesheet: {exc}") from exc

        problems = validate(source)
        if problems:
            self.errors.extend(f"{os.path.basename(path)}: {p}" for p in problems)

        sheet = Stylesheet(name=os.path.basename(path), source=source, path=path)
        self.sheets = [s for s in self.sheets if s.name != sheet.name]
        self.sheets.append(sheet)
        return sheet

    def add_source(self, name: str, source: str) -> Stylesheet:
        sheet = Stylesheet(name=name, source=source)
        self.sheets = [s for s in self.sheets if s.name != name]
        self.sheets.append(sheet)
        return sheet

    def remove(self, name: str):
        self.sheets = [s for s in self.sheets if s.name != name]

    def set_enabled(self, name: str, enabled: bool):
        for s in self.sheets:
            if s.name == name:
                s.enabled = enabled

    def combined(self) -> str:
        return "\n\n".join(s.source for s in self.sheets if s.enabled)

    def sources(self) -> list:
        return [s.source for s in self.sheets if s.enabled]

    def export(self, path: str) -> str:
        with open(path, "w", encoding="utf-8") as f:
            f.write(self.combined())
        return path

    def to_dict(self):
        return [s.to_dict() for s in self.sheets]

    def load_list(self, data):
        self.sheets = [Stylesheet.from_dict(d) for d in (data or [])]
        return self

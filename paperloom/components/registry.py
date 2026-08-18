"""
The component library system (spec §4). Each component lives in its own folder
under components/library/<id>/ with:

    meta.json            metadata + property schema + signals
    template.pyside.jinja  PySide6 code fragment
    template.cpp.jinja     C++ Qt code fragment (present but unused until the
                           C++ backend lands - see spec §2.2a sequencing)

The registry loads every folder at startup (adding a component = dropping in a
folder, nothing else to touch - §4.3). It also knows how to instantiate a live
QWidget for a component so the canvas can host the real thing, and how to render
that component's code fragment for a given DesignWidget so codegen stays a thin
loop over the model.
"""
from __future__ import annotations
import json
import os
from dataclasses import dataclass

from jinja2 import Template

_LIBRARY_DIR = os.path.join(os.path.dirname(__file__), "library")


@dataclass
class PropertySpec:
    name: str
    type: str
    default: object
    control: str

    @classmethod
    def from_dict(cls, d):
        return cls(d["name"], d["type"], d.get("default"), d.get("control", "text"))


@dataclass
class SignalSpec:
    name: str
    stub: str          # e.g. "on_{name}_clicked" - {name} filled with object_name
    body: str = ""     # optional: pre-filled method body (e.g. "self.toggle_theme()")


@dataclass
class Component:
    id: str
    name: str
    category: str
    tags: list
    description: str
    properties: list          # list[PropertySpec]
    quick_properties: list    # list[str] - subset of property names
    signals: list             # list[SignalSpec]
    widget_class: str         # Qt class the templates instantiate (e.g. "QPushButton")
    qt_include: str           # Qt header/import needed (usually == widget_class)
    source: str               # "default" | "paperdesign" | "user" - library source tab
    style_role: str           # app-theme role driving this component's QSS
    _pyside_template: str
    _cpp_template: str

    def default_properties(self) -> dict:
        return {p.name: p.default for p in self.properties}

    def property(self, name) -> PropertySpec | None:
        return next((p for p in self.properties if p.name == name), None)

    def matches(self, query: str) -> bool:
        q = query.lower().strip()
        if not q:
            return True
        haystack = " ".join([self.id, self.name, self.category, self.description, *self.tags]).lower()
        return q in haystack

    def render_pyside(self, ctx: dict) -> str:
        return Template(self._pyside_template).render(**ctx)

    def render_cpp(self, ctx: dict) -> str:
        return Template(self._cpp_template).render(**ctx)


class ComponentRegistry:
    def __init__(self):
        self._components: dict[str, Component] = {}

    def load(self, library_dir: str = _LIBRARY_DIR) -> "ComponentRegistry":
        if not os.path.isdir(library_dir):
            return self
        for entry in sorted(os.listdir(library_dir)):
            folder = os.path.join(library_dir, entry)
            meta_path = os.path.join(folder, "meta.json")
            if not os.path.isfile(meta_path):
                continue
            with open(meta_path, encoding="utf-8") as f:
                meta = json.load(f)
            self._components[meta["id"]] = Component(
                id=meta["id"],
                name=meta["name"],
                category=meta.get("category", "misc"),
                tags=meta.get("tags", []),
                description=meta.get("description", ""),
                properties=[PropertySpec.from_dict(p) for p in meta.get("properties", [])],
                quick_properties=meta.get("quick_properties", []),
                signals=[SignalSpec(s["name"], s.get("stub", "on_{name}_" + s["name"]),
                                    s.get("body", ""))
                         for s in meta.get("signals", [])],
                widget_class=meta.get("widget_class", "QWidget"),
                qt_include=meta.get("qt_include", meta.get("widget_class", "QWidget")),
                source=meta.get("source", "default"),
                style_role=meta.get("style_role", "label"),
                _pyside_template=self._read(folder, "template.pyside.jinja"),
                _cpp_template=self._read(folder, "template.cpp.jinja"),
            )
        return self

    @staticmethod
    def _read(folder, filename) -> str:
        path = os.path.join(folder, filename)
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as f:
                return f.read()
        return ""

    def get(self, component_id: str) -> Component | None:
        return self._components.get(component_id)

    def all(self) -> list:
        return list(self._components.values())

    def search(self, query: str) -> list:
        return [c for c in self._components.values() if c.matches(query)]

    def categories(self) -> list:
        return sorted({c.category for c in self._components.values()})

    def sources(self) -> list:
        return sorted({c.source for c in self._components.values()})

    def by_source(self, source: str) -> list:
        return [c for c in self._components.values() if c.source == source]

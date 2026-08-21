"""
Qt property introspection (spec §22) - the Qt Designer capability of editing any
property a widget actually exposes, not just the handful a component declares.

Qt's meta-object system already knows every property on a QObject, its type, and
whether it's writable. This reads that live, so the properties panel can offer an
"All properties" view for the real widget on the canvas - including properties
PaperLoom never had to hardcode.
"""
from __future__ import annotations
from dataclasses import dataclass

from PySide6.QtCore import QMetaProperty

# Qt type names -> the editor kind PaperLoom knows how to render
_TYPE_MAP = {
    "QString": "string", "int": "int", "uint": "int", "double": "number",
    "float": "number", "bool": "bool", "QColor": "color",
    "QSize": "size", "QPoint": "point", "QRect": "rect", "QFont": "font",
}

# properties that are noise in a designer, or unsafe to poke live
_HIDDEN = {
    "objectName", "windowIcon", "windowIconText", "styleSheet", "geometry",
    "pos", "size", "children", "parent", "focusProxy", "graphicsEffect",
    "windowFilePath", "accessibleName", "accessibleDescription",
    "inputMethodHints", "locale", "layoutDirection", "palette", "font",
}


@dataclass
class QtProperty:
    name: str
    type_name: str
    kind: str           # string | int | number | bool | color | enum | other
    value: object
    writable: bool
    enum_values: tuple = ()

    @property
    def editable(self):
        return self.writable and self.kind in ("string", "int", "number", "bool", "color", "enum")


def read_properties(widget, include_hidden=False) -> list[QtProperty]:
    """Every property Qt reports for this widget, most-derived class first."""
    meta = widget.metaObject()
    out: list[QtProperty] = []
    seen = set()
    for i in range(meta.propertyCount() - 1, -1, -1):
        prop: QMetaProperty = meta.property(i)
        name = prop.name()
        if name in seen:
            continue
        seen.add(name)
        if not include_hidden and name in _HIDDEN:
            continue
        type_name = prop.typeName()
        kind = _TYPE_MAP.get(type_name, "other")
        enum_values = ()
        if prop.isEnumType():
            kind = "enum"
            enumerator = prop.enumerator()
            enum_values = tuple(enumerator.key(k) for k in range(enumerator.keyCount()))
        try:
            value = prop.read(widget)
        except Exception:
            value = None
        out.append(QtProperty(name=name, type_name=type_name, kind=kind,
                              value=value, writable=prop.isWritable(),
                              enum_values=enum_values))
    out.sort(key=lambda p: p.name)
    return out


def editable_properties(widget) -> list[QtProperty]:
    return [p for p in read_properties(widget) if p.editable]


def write_property(widget, name: str, value) -> bool:
    """Set a property by name, coercing to the type Qt expects. Returns success."""
    meta = widget.metaObject()
    index = meta.indexOfProperty(name)
    if index < 0:
        return False
    prop = meta.property(index)
    if not prop.isWritable():
        return False
    type_name = prop.typeName()
    try:
        if type_name in ("int", "uint"):
            value = int(value)
        elif type_name in ("double", "float"):
            value = float(value)
        elif type_name == "bool":
            value = value if isinstance(value, bool) else \
                str(value).strip().lower() in ("true", "1", "yes", "on")
        elif type_name == "QString":
            value = str(value)
        elif prop.isEnumType() and isinstance(value, str):
            enumerator = prop.enumerator()
            resolved = enumerator.keyToValue(value)
            value = resolved[0] if isinstance(resolved, tuple) else resolved
        return prop.write(widget, value)
    except (TypeError, ValueError):
        return False


def signals_of(widget) -> list[str]:
    """Signal names this widget exposes - for the signal/slot editor."""
    meta = widget.metaObject()
    out = []
    for i in range(meta.methodCount()):
        method = meta.method(i)
        if method.methodType() == method.MethodType.Signal:
            name = bytes(method.name()).decode()
            if name not in out:
                out.append(name)
    return sorted(out)

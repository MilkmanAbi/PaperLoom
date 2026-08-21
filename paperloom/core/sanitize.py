"""
Value sanitization (spec §11.1). The single guarantee: a value leaving this
module is always safe to drop into generated code for its declared type. A
malformed value becomes the property's default rather than raw garbage - so
PaperLoom can never emit uncompilable code like `setValue(6056+)`.

Used by both the codegen context builder (hard invariant) and the property
editors (so bad input is corrected at the source). Keyed on the property `type`
declared in meta.json.
"""
from __future__ import annotations
import re

_COLOR_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")


def coerce(value, prop_type: str, default=None):
    """Return a value guaranteed valid for prop_type, or `default` (itself
    coerced) if the value can't be made valid."""
    if prop_type in ("int", "number"):
        return _as_int(value, default)
    if prop_type == "bool":
        return _as_bool(value)
    if prop_type == "color":
        return _as_color(value, default)
    # string and anything unknown: normalise to a safe string
    return _as_str(value)


def _as_int(value, default):
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        try:
            return int(str(default).strip())
        except (TypeError, ValueError):
            return 0


def _as_bool(value):
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("true", "1", "yes", "on", "checked")


def _as_color(value, default):
    v = str(value).strip()
    if _COLOR_RE.match(v):
        return v
    d = str(default).strip()
    if _COLOR_RE.match(d):
        return d
    return "#000000"


def _as_str(value):
    return str(value) if value is not None else ""


def escape_string(value: str) -> str:
    """Escape a string for safe embedding in a double-quoted code literal
    (both Python and C++ use the same basic escapes here)."""
    return (
        str(value)
        .replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
    )

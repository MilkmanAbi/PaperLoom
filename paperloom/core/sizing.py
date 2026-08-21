"""
Sensible defaults (spec §30).

Absolute positioning is seductive while building a UI and disastrous the moment
the window is a different size. This module gives every component a *default*
sizing behaviour - a size policy, a minimum size, a text-overflow strategy - so a
beginner who has never heard of QSizePolicy still gets an app that survives a
1366x768 laptop.

The governing rule, from the project's philosophy: **sane defaults, not hidden
opinions.** Every value here is a starting point the user can override per
widget, and `adaptive=False` on a widget opts out entirely and keeps the exact
geometry it was drawn with.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict

# how text that doesn't fit should behave
WRAP_MODES = {
    "wrap": "Wrap onto the next line (carriage flow)",
    "elide": "Truncate with an ellipsis",
    "clip": "Cut off at the edge",
    "none": "Let it overflow",
}

# horizontal / vertical size policy per role
# (policy names map onto QSizePolicy.Policy)
_ROLE_POLICY = {
    # buttons keep their natural height, can stretch a little horizontally
    "button_primary": ("Preferred", "Fixed"),
    "button_secondary": ("Preferred", "Fixed"),
    "button_ghost": ("Preferred", "Fixed"),
    "button_danger": ("Preferred", "Fixed"),
    "button_pill": ("Preferred", "Fixed"),
    "button_icon": ("Fixed", "Fixed"),
    "tool": ("Fixed", "Fixed"),
    # inputs want to grow with the form
    "input": ("Expanding", "Fixed"),
    "search": ("Expanding", "Fixed"),
    "select": ("Expanding", "Fixed"),
    "slider": ("Expanding", "Fixed"),
    "dial": ("Fixed", "Fixed"),
    "checkbox": ("Preferred", "Fixed"),
    "radio": ("Preferred", "Fixed"),
    "switch": ("Preferred", "Fixed"),
    # display
    "label": ("Preferred", "Fixed"),
    "title": ("Expanding", "Fixed"),
    "subtitle": ("Expanding", "Fixed"),
    "caption": ("Expanding", "Fixed"),
    "badge": ("Fixed", "Fixed"),
    "avatar": ("Fixed", "Fixed"),
    "image": ("Expanding", "Expanding"),
    "media_frame": ("Expanding", "Expanding"),
    "progress": ("Expanding", "Fixed"),
    "divider": ("Expanding", "Fixed"),
    # containers fill what they're given
    "card": ("Expanding", "Expanding"),
    "panel": ("Expanding", "Expanding"),
    "group": ("Expanding", "Expanding"),
    "tabs": ("Expanding", "Expanding"),
    "scroll": ("Expanding", "Expanding"),
    "list": ("Expanding", "Expanding"),
    "tree": ("Expanding", "Expanding"),
    "table": ("Expanding", "Expanding"),
    # chrome
    "appbar": ("Expanding", "Fixed"),
    "sidebar": ("Fixed", "Expanding"),
    "statusbar": ("Expanding", "Fixed"),
    # overlays
    "scrim": ("Expanding", "Expanding"),
    "modal": ("Preferred", "Preferred"),
    "toast": ("Preferred", "Fixed"),
    "tooltip": ("Preferred", "Fixed"),
}

# minimum sizes so nothing collapses into nothing
_ROLE_MINIMUM = {
    "button_icon": (28, 28), "avatar": (28, 28), "dial": (40, 40),
    "badge": (32, 18), "progress": (60, 6), "divider": (24, 1),
    "input": (80, 26), "search": (100, 26), "select": (80, 26),
    "card": (80, 60), "panel": (80, 60), "group": (80, 60),
    "image": (60, 40), "media_frame": (60, 40),
    "appbar": (120, 36), "sidebar": (100, 80), "statusbar": (120, 20),
}

# which roles hold text that can overflow, and what should happen
_ROLE_WRAP = {
    "label": "wrap", "title": "elide", "subtitle": "wrap", "caption": "wrap",
    "badge": "elide", "toast": "wrap", "tooltip": "wrap", "modal": "wrap",
    "button_primary": "elide", "button_secondary": "elide",
    "button_ghost": "elide", "button_danger": "elide", "button_pill": "elide",
}


@dataclass
class SizingDefaults:
    h_policy: str = "Preferred"
    v_policy: str = "Fixed"
    min_width: int = 0
    min_height: int = 0
    wrap: str = "none"
    adaptive: bool = True         # False = keep exact drawn geometry

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, d):
        return cls(**{k: v for k, v in (d or {}).items()
                      if k in cls.__dataclass_fields__})


def defaults_for(component) -> SizingDefaults:
    """The sane starting behaviour for a component, by role."""
    role = getattr(component, "style_role", "label")
    h, v = _ROLE_POLICY.get(role, ("Preferred", "Fixed"))
    min_w, min_h = _ROLE_MINIMUM.get(role, (0, 0))
    return SizingDefaults(h_policy=h, v_policy=v,
                          min_width=min_w, min_height=min_h,
                          wrap=_ROLE_WRAP.get(role, "none"))


def sizing_for_widget(dw, component) -> SizingDefaults:
    """A widget's sizing, honouring anything the user overrode in its properties."""
    base = defaults_for(component)
    stored = dw.properties.get("_sizing")
    if isinstance(stored, dict):
        merged = base.to_dict()
        merged.update(stored)
        return SizingDefaults.from_dict(merged)
    return base


# --- code generation ---------------------------------------------------------
def pyside_lines(object_name: str, sizing: SizingDefaults, component) -> list[str]:
    """Lines that apply the sizing behaviour in generated PySide6 code."""
    if not sizing.adaptive:
        return []
    lines = [
        f"self.{object_name}.setSizePolicy("
        f"QSizePolicy.Policy.{sizing.h_policy}, QSizePolicy.Policy.{sizing.v_policy})"
    ]
    if sizing.min_width or sizing.min_height:
        lines.append(
            f"self.{object_name}.setMinimumSize({sizing.min_width}, {sizing.min_height})")
    if sizing.wrap == "wrap" and component.widget_class == "QLabel":
        lines.append(f"self.{object_name}.setWordWrap(True)")
    return lines


def cpp_lines(object_name: str, sizing: SizingDefaults, component) -> list[str]:
    if not sizing.adaptive:
        return []
    lines = [
        f"{object_name}->setSizePolicy("
        f"QSizePolicy::{sizing.h_policy}, QSizePolicy::{sizing.v_policy});"
    ]
    if sizing.min_width or sizing.min_height:
        lines.append(
            f"{object_name}->setMinimumSize({sizing.min_width}, {sizing.min_height});")
    if sizing.wrap == "wrap" and component.widget_class == "QLabel":
        lines.append(f"{object_name}->setWordWrap(true);")
    return lines


def window_lines(page) -> list[str]:
    """Window-level sanity: a sensible minimum size so the design can't be
    crushed below the point where it stops making sense."""
    min_w = max(320, min(page.width, 480))
    min_h = max(240, min(page.height, 360))
    return [f"MainWindow.setMinimumSize({min_w}, {min_h})"]


def cpp_window_lines(page) -> list[str]:
    min_w = max(320, min(page.width, 480))
    min_h = max(240, min(page.height, 360))
    return [f"MainWindow->setMinimumSize({min_w}, {min_h});"]


def elide_helper_source() -> str:
    """A tiny helper emitted when any widget uses elide, so long text truncates
    with an ellipsis instead of overflowing its widget."""
    return '''

def _elide(widget, full_text):
    """Truncate `full_text` to fit `widget`, with an ellipsis. Re-run on resize."""
    from PySide6.QtGui import QFontMetrics
    from PySide6.QtCore import Qt
    metrics = QFontMetrics(widget.font())
    available = max(0, widget.width() - 16)
    widget.setText(metrics.elidedText(full_text, Qt.TextElideMode.ElideRight, available))
'''

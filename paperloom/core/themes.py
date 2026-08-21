"""
Theme system (spec §12.8). Themes are data, not code: a Theme is a token dict
that can be built in, loaded from JSON, or imported by the user via View > Theme.
The whole shell re-styles from the active theme's tokens.

A theme file is JSON:
    {
      "name": "Midnight",
      "dark_chrome": true,
      "tokens": { "ACCENT": "#6B7CFF", "ACTIVITY_BAR": "#2A2B32", ... }
    }
Any token the file omits falls back to the default theme's value, so a user can
ship a two-line theme that only changes the accent.
"""
from __future__ import annotations
import weakref
import json
import os
from dataclasses import dataclass, field

# --- the token contract ------------------------------------------------------
# every key here must exist on any resolved theme; user files may override any subset.
DEFAULT_TOKENS = {
    # surfaces - chrome
    "ACTIVITY_BAR": "#2A2B32",
    "SIDE_PANEL": "#33343B",
    "BOTTOM_BAR": "#33343B",
    "BORDER_DARK": "#22232A",
    # surfaces - canvas side
    "SURFACE_CANVAS": "#F4F1EA",
    "SURFACE_RAISED": "#FBFAF6",
    "SURFACE_SUNKEN": "#E7E2D6",
    "BORDER": "#C9C2B4",
    # ink
    "INK_ON_DARK": "#E6E4DE",
    "INK_ON_DARK_MUTED": "#9A9AA2",
    "INK_ON_DARK_FAINT": "#6E6F78",
    "INK_PRIMARY": "#2B2822",
    "INK_SECONDARY": "#6B6255",
    "INK_TERTIARY": "#A79E8C",
    # accent
    "ACCENT": "#6B7CFF",
    "ACCENT_HOVER": "#7C8BFF",
    "ACCENT_MUTED": "#E3E5FB",
    "ACCENT_DIM": "#3B3E63",
    "STATUS_BAR": "#6B7CFF",
    "INK_ON_ACCENT": "#FFFFFF",
    # semantic
    "DANGER": "#D9534F",
    "WARNING": "#E0A33E",
    "SUCCESS": "#4C9A6A",
}


@dataclass
class Theme:
    name: str = "PaperLoom Dark"
    tokens: dict = field(default_factory=lambda: dict(DEFAULT_TOKENS))
    builtin: bool = True
    is_dark: bool = True

    def get(self, key):
        return self.tokens.get(key, DEFAULT_TOKENS.get(key, "#000000"))

    def to_dict(self):
        return {"name": self.name, "tokens": self.tokens}

    @classmethod
    def from_dict(cls, data, builtin=False):
        merged = dict(DEFAULT_TOKENS)
        merged.update(data.get("tokens", {}))
        return cls(name=data.get("name", "Untitled theme"), tokens=merged,
                   builtin=builtin, is_dark=data.get("dark", True))

    @classmethod
    def load(cls, path):
        with open(path, encoding="utf-8") as f:
            return cls.from_dict(json.load(f))


# --- built-in themes ---------------------------------------------------------
def _builtin(name, overrides, is_dark=True):
    merged = dict(DEFAULT_TOKENS)
    merged.update(overrides)
    return Theme(name=name, tokens=merged, builtin=True, is_dark=is_dark)


BUILTIN_THEMES = [
    # --- dark editor chrome (default) ---
    Theme(),  # PaperLoom Dark
    # --- light editor chrome: every ink token flips so nothing is white-on-white ---
    _builtin("PaperLoom Light", {
        "ACTIVITY_BAR": "#EDEAE2", "SIDE_PANEL": "#F7F5F0", "BOTTOM_BAR": "#F7F5F0",
        "BORDER_DARK": "#D3CCBE",
        "SURFACE_CANVAS": "#FFFFFF", "SURFACE_RAISED": "#FFFFFF",
        "SURFACE_SUNKEN": "#EDEAE2", "BORDER": "#D3CCBE",
        "INK_ON_DARK": "#23201B", "INK_ON_DARK_MUTED": "#6B6255",
        "INK_ON_DARK_FAINT": "#9C9384",
        "INK_PRIMARY": "#23201B", "INK_SECONDARY": "#6B6255", "INK_TERTIARY": "#9C9384",
        "ACCENT": "#5B6BE8", "ACCENT_HOVER": "#4C5CD9",
        "ACCENT_MUTED": "#E3E5FB", "ACCENT_DIM": "#DCDFFA",
        "STATUS_BAR": "#5B6BE8",
    }, is_dark=False),
    _builtin("Midnight", {
        "ACTIVITY_BAR": "#16171C", "SIDE_PANEL": "#1E1F26", "BOTTOM_BAR": "#1E1F26",
        "BORDER_DARK": "#0F1014",
        "SURFACE_CANVAS": "#24252C", "SURFACE_RAISED": "#2C2D35",
        "SURFACE_SUNKEN": "#1A1B21", "BORDER": "#3A3B44",
        "INK_PRIMARY": "#E6E4DE", "INK_SECONDARY": "#9A9AA2", "INK_TERTIARY": "#6E6F78",
        "ACCENT": "#7C8BFF", "STATUS_BAR": "#3B3E63", "ACCENT_DIM": "#33365C",
    }),
    _builtin("Forest", {
        "ACTIVITY_BAR": "#23302A", "SIDE_PANEL": "#2C3B34", "BOTTOM_BAR": "#2C3B34",
        "BORDER_DARK": "#1A241F",
        "SURFACE_CANVAS": "#F1F4EF", "SURFACE_RAISED": "#F8FAF6",
        "ACCENT": "#5B9E77", "ACCENT_HOVER": "#6BB088", "ACCENT_MUTED": "#DCEDE3",
        "ACCENT_DIM": "#37503F", "STATUS_BAR": "#5B9E77",
    }),
]


class ThemeManager:
    """Holds the active theme and any imported ones; notifies listeners on change."""

    def __init__(self):
        self.themes = list(BUILTIN_THEMES)
        self.active = self.themes[0]
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
                continue          # owner was garbage collected; drop the listener
            alive.append(listener)
            try:
                fn(self.active)
            except RuntimeError:
                pass              # underlying C++ object went away mid-notify
        self._listeners = alive

    def names(self):
        return [t.name for t in self.themes]

    def set_active(self, name):
        for t in self.themes:
            if t.name == name:
                self.active = t
                self._notify()
                return True
        return False

    def toggle_light_dark(self):
        """Flip the editor between its light and dark counterpart."""
        want_dark = not self.active.is_dark
        pair = {"PaperLoom Dark": "PaperLoom Light", "PaperLoom Light": "PaperLoom Dark"}
        target = pair.get(self.active.name)
        if target is None:
            target = next((t.name for t in self.themes if t.is_dark == want_dark), None)
        if target:
            self.set_active(target)
        return self.active

    def import_theme(self, path):
        """Load a user theme file, add it, and make it active. Returns the Theme."""
        theme = Theme.load(path)
        # replace a same-named import rather than duplicating
        self.themes = [t for t in self.themes if t.name != theme.name or t.builtin]
        self.themes.append(theme)
        self.active = theme
        self._notify()
        return theme

    def export_active(self, path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.active.to_dict(), f, indent=2)
        return path

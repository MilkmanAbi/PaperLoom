"""
App theme (spec §14) - the theme of the *app being designed*, distinct from the
editor theme (core/themes.py) which styles PaperLoom's own chrome.

Every app PaperLoom builds gets light/dark support for free, because that is the
most basic thing any app should support. Components declare a `style_role`
("button_primary", "input", "label", ...) and this module generates one
window-level stylesheet per mode that styles every role via Qt's dynamic
property selector:

    widget.setProperty("role", "button_primary")
    QPushButton[role="button_primary"] { ... }

That means switching light/dark in the generated app is literally one line -
`MainWindow.setStyleSheet(app_theme.stylesheet(mode))` - and the canvas shows the
exact same thing by applying the same stylesheet to itself.
"""
from __future__ import annotations
from dataclasses import dataclass, field

LIGHT = {
    "bg": "#F5F3EE",
    "surface": "#FFFFFF",
    "surface_alt": "#EBE7DE",
    "fg": "#23201B",
    "fg_muted": "#6B6255",
    "fg_faint": "#9C9384",
    "border": "#D3CCBE",
    "accent": "#5B6BE8",
    "accent_hover": "#6C7BF0",
    "accent_fg": "#FFFFFF",
    "danger": "#C8453F",
    "danger_hover": "#B23A34",
    "on_danger": "#FBEEEE",
    "warning": "#B8842B",
    "success": "#3F8A5F",
}

DARK = {
    "bg": "#1E1F25",
    "surface": "#282A32",
    "surface_alt": "#32343D",
    "fg": "#ECEAE4",
    "fg_muted": "#A9A79F",
    "fg_faint": "#74727B",
    "border": "#3D3F49",
    "accent": "#7C8BFF",
    "accent_hover": "#8D9AFF",
    "accent_fg": "#15161A",
    "danger": "#E4756F",
    "danger_hover": "#EC8781",
    "on_danger": "#2A1615",
    "warning": "#D9A84E",
    "success": "#6BB98A",
}


@dataclass
class AppTheme:
    """The designed app's theme: two palettes plus the currently previewed mode."""
    mode: str = "light"                       # "light" | "dark"
    light: dict = field(default_factory=lambda: dict(LIGHT))
    dark: dict = field(default_factory=lambda: dict(DARK))
    radius: int = 6

    def tokens(self, mode=None):
        return dict(self.dark if (mode or self.mode) == "dark" else self.light)

    def toggled(self):
        return "dark" if self.mode == "light" else "light"

    def to_dict(self):
        return {"mode": self.mode, "light": self.light, "dark": self.dark, "radius": self.radius}

    @classmethod
    def from_dict(cls, d):
        return cls(mode=d.get("mode", "light"),
                   light={**LIGHT, **d.get("light", {})},
                   dark={**DARK, **d.get("dark", {})},
                   radius=d.get("radius", 6))


def stylesheet(mode="light", theme: AppTheme = None) -> str:
    """The complete window-level stylesheet for one mode. Every role a component
    can declare is styled here, so adding a component never means adding QSS."""
    t = (theme or AppTheme()).tokens(mode)
    r = (theme or AppTheme()).radius
    return f"""
/* base */
QWidget {{ background: {t['bg']}; color: {t['fg']}; font-size: 13px; }}
QMainWindow {{ background: {t['bg']}; }}
QToolTip {{ background: {t['surface_alt']}; color: {t['fg']};
            border: 1px solid {t['border']}; padding: 4px 6px; }}

/* --- buttons ---
   every interactive role carries the full state set (hover / pressed / focus /
   disabled) so a placed button always feels like a button. :pressed shifts
   padding rather than colour so the generated-app runtime QSS round-trips
   without needing a token for every state. */
QPushButton[role="button_primary"] {{
    background: {t['accent']}; color: {t['accent_fg']}; border: none;
    border-radius: {r}px; padding: 7px 18px; font-weight: 600; }}
QPushButton[role="button_primary"]:hover {{ background: {t['accent_hover']}; }}
QPushButton[role="button_primary"]:pressed {{ padding-top: 8px; padding-bottom: 6px; }}
QPushButton[role="button_primary"]:focus {{ outline: none; border: 2px solid {t['accent_hover']}; padding: 6px 17px; }}
QPushButton[role="button_primary"]:disabled {{
    background: {t['surface_alt']}; color: {t['fg_faint']}; }}

QPushButton[role="button_secondary"] {{
    background: {t['surface']}; color: {t['fg']};
    border: 1px solid {t['border']}; border-radius: {r}px;
    padding: 7px 18px; }}
QPushButton[role="button_secondary"]:hover {{ border-color: {t['accent']}; color: {t['accent']}; }}
QPushButton[role="button_secondary"]:pressed {{ background: {t['surface_alt']}; padding-top: 8px; padding-bottom: 6px; }}
QPushButton[role="button_secondary"]:focus {{ outline: none; border: 1px solid {t['accent']}; }}
QPushButton[role="button_secondary"]:disabled {{ color: {t['fg_faint']}; border-color: {t['surface_alt']}; }}

QPushButton[role="button_ghost"] {{
    background: transparent; color: {t['accent']}; border: none;
    border-radius: {r}px; padding: 7px 14px; }}
QPushButton[role="button_ghost"]:hover {{ background: {t['surface_alt']}; }}
QPushButton[role="button_ghost"]:pressed {{ background: {t['surface_alt']}; padding-top: 8px; padding-bottom: 6px; }}
QPushButton[role="button_ghost"]:focus {{ outline: none; background: {t['surface_alt']}; }}
QPushButton[role="button_ghost"]:disabled {{ color: {t['fg_faint']}; }}

QPushButton[role="button_danger"] {{
    background: {t['danger']}; color: {t['on_danger']}; border: none;
    border-radius: {r}px; padding: 7px 18px; font-weight: 600; }}
QPushButton[role="button_danger"]:hover {{ background: {t['danger_hover']}; }}
QPushButton[role="button_danger"]:pressed {{ background: {t['danger_hover']}; padding-top: 8px; padding-bottom: 6px; }}
QPushButton[role="button_danger"]:focus {{ outline: none; border: 2px solid {t['danger_hover']}; padding: 6px 17px; }}
QPushButton[role="button_danger"]:disabled {{ background: {t['surface_alt']}; color: {t['fg_faint']}; }}

QPushButton[role="button_pill"] {{
    background: {t['accent']}; color: {t['accent_fg']}; border: none;
    border-radius: 16px; padding: 7px 20px; font-weight: 600; }}
QPushButton[role="button_pill"]:hover {{ background: {t['accent_hover']}; }}
QPushButton[role="button_pill"]:pressed {{ padding-top: 8px; padding-bottom: 6px; }}
QPushButton[role="button_pill"]:focus {{ outline: none; border: 2px solid {t['accent_hover']}; padding: 6px 19px; }}
QPushButton[role="button_pill"]:disabled {{ background: {t['surface_alt']}; color: {t['fg_faint']}; }}

QPushButton[role="button_icon"] {{
    background: transparent; color: {t['fg']};
    border: 1px solid {t['border']}; border-radius: {r}px; }}
QPushButton[role="button_icon"]:hover {{ border-color: {t['accent']}; background: {t['surface_alt']}; }}
QPushButton[role="button_icon"]:pressed {{ background: {t['surface_alt']}; }}
QPushButton[role="button_icon"]:focus {{ outline: none; border-color: {t['accent']}; }}
QPushButton[role="button_icon"]:disabled {{ color: {t['fg_faint']}; border-color: {t['surface_alt']}; }}

QToolButton[role="tool"] {{
    background: transparent; color: {t['fg']}; border: none;
    border-radius: {r}px; padding: 6px; }}
QToolButton[role="tool"]:hover {{ background: {t['surface_alt']}; }}
QToolButton[role="tool"]:pressed {{ background: {t['border']}; }}
QToolButton[role="tool"]:focus {{ outline: none; background: {t['surface_alt']}; }}

/* --- inputs --- */
QLineEdit[role="input"], QPlainTextEdit[role="input"], QTextEdit[role="input"],
QSpinBox[role="input"], QDoubleSpinBox[role="input"], QDateEdit[role="input"],
QTimeEdit[role="input"], QDateTimeEdit[role="input"] {{
    background: {t['surface']}; color: {t['fg']};
    border: 1px solid {t['border']}; border-radius: {r}px; padding: 6px 10px; }}
QLineEdit[role="input"]:focus, QPlainTextEdit[role="input"]:focus,
QTextEdit[role="input"]:focus, QSpinBox[role="input"]:focus {{
    border: 1px solid {t['accent']}; }}

QLineEdit[role="search"] {{
    background: {t['surface']}; color: {t['fg']};
    border: 1px solid {t['border']}; border-radius: 16px; padding: 6px 14px; }}
QLineEdit[role="search"]:focus {{ border: 1px solid {t['accent']}; }}

QComboBox[role="select"] {{
    background: {t['surface']}; color: {t['fg']};
    border: 1px solid {t['border']}; border-radius: {r}px; padding: 6px 10px; }}
QComboBox[role="select"]:hover {{ border-color: {t['accent']}; }}
QComboBox[role="select"] QAbstractItemView {{
    background: {t['surface']}; color: {t['fg']};
    selection-background-color: {t['accent']}; selection-color: {t['accent_fg']};
    border: 1px solid {t['border']}; }}

QCheckBox[role="checkbox"], QRadioButton[role="radio"] {{
    color: {t['fg']}; spacing: 8px; background: transparent; }}
QCheckBox[role="checkbox"]::indicator, QRadioButton[role="radio"]::indicator {{
    width: 16px; height: 16px; border: 1px solid {t['border']};
    background: {t['surface']}; border-radius: 3px; }}
QRadioButton[role="radio"]::indicator {{ border-radius: 8px; }}
QCheckBox[role="checkbox"]::indicator:checked,
QRadioButton[role="radio"]::indicator:checked {{
    background: {t['accent']}; border-color: {t['accent']}; }}

QCheckBox[role="switch"] {{ color: {t['fg']}; spacing: 8px; background: transparent; }}
QCheckBox[role="switch"]::indicator {{
    width: 34px; height: 18px; border-radius: 9px;
    background: {t['surface_alt']}; border: 1px solid {t['border']}; }}
QCheckBox[role="switch"]::indicator:checked {{
    background: {t['accent']}; border-color: {t['accent']}; }}

QSlider[role="slider"]::groove:horizontal {{
    height: 4px; background: {t['surface_alt']}; border-radius: 2px; }}
QSlider[role="slider"]::handle:horizontal {{
    background: {t['accent']}; width: 16px; margin: -7px 0; border-radius: 8px; }}
QSlider[role="slider"]::sub-page:horizontal {{ background: {t['accent']}; border-radius: 2px; }}

QDial[role="dial"] {{ background: {t['surface']}; }}

/* --- display --- */
QLabel[role="label"] {{ color: {t['fg']}; background: transparent; }}
QLabel[role="title"] {{ color: {t['fg']}; background: transparent;
    font-size: 22px; font-weight: 700; }}
QLabel[role="subtitle"] {{ color: {t['fg']}; background: transparent;
    font-size: 16px; font-weight: 600; }}
QLabel[role="caption"] {{ color: {t['fg_muted']}; background: transparent; font-size: 11px; }}
QLabel[role="badge"] {{
    background: {t['accent']}; color: {t['accent_fg']}; border-radius: 9px;
    padding: 2px 10px; font-size: 11px; font-weight: 600; }}
QLabel[role="badge_muted"] {{
    background: {t['surface_alt']}; color: {t['fg_muted']}; border-radius: 9px;
    padding: 2px 10px; font-size: 11px; }}
QLabel[role="avatar"] {{
    background: {t['accent']}; color: {t['accent_fg']}; border-radius: 20px;
    font-weight: 700; }}
QLabel[role="image"] {{
    background: {t['surface_alt']}; color: {t['fg_faint']};
    border: 1px dashed {t['border']}; border-radius: {r}px; }}
QFrame[role="divider"] {{ background: {t['border']}; border: none; max-height: 1px; }}
QFrame[role="card"] {{
    background: {t['surface']}; border: 1px solid {t['border']};
    border-radius: {r}px; }}
QFrame[role="panel"] {{
    background: {t['surface_alt']}; border: none; border-radius: {r}px; }}

QProgressBar[role="progress"] {{
    background: {t['surface_alt']}; border: none; border-radius: 4px;
    text-align: center; color: {t['fg']}; font-size: 11px; height: 8px; }}
QProgressBar[role="progress"]::chunk {{ background: {t['accent']}; border-radius: 4px; }}

/* --- containers --- */
QGroupBox[role="group"] {{
    background: transparent; color: {t['fg']};
    border: 1px solid {t['border']}; border-radius: {r}px;
    margin-top: 10px; padding-top: 8px; }}
QGroupBox[role="group"]::title {{
    subcontrol-origin: margin; left: 10px; padding: 0 4px; color: {t['fg_muted']}; }}

QTabWidget[role="tabs"]::pane {{
    border: 1px solid {t['border']}; border-radius: {r}px; background: {t['surface']}; }}
QTabBar::tab {{
    background: transparent; color: {t['fg_muted']};
    padding: 7px 16px; border-bottom: 2px solid transparent; }}
QTabBar::tab:selected {{ color: {t['fg']}; border-bottom: 2px solid {t['accent']}; }}

QListWidget[role="list"], QTreeWidget[role="tree"], QTableWidget[role="table"] {{
    background: {t['surface']}; color: {t['fg']};
    border: 1px solid {t['border']}; border-radius: {r}px; outline: none; }}
QListWidget[role="list"]::item, QTreeWidget[role="tree"]::item {{ padding: 6px 8px; }}
QListWidget[role="list"]::item:selected, QTreeWidget[role="tree"]::item:selected {{
    background: {t['accent']}; color: {t['accent_fg']}; }}
QHeaderView::section {{
    background: {t['surface_alt']}; color: {t['fg_muted']};
    border: none; padding: 6px; }}

QScrollArea[role="scroll"] {{ background: transparent; border: none; }}
QScrollBar:vertical {{ background: transparent; width: 10px; }}
QScrollBar::handle:vertical {{ background: {t['border']}; border-radius: 5px; min-height: 24px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}

/* --- media --- */
QLabel[role="media_frame"], QWidget[role="media_frame"] {{
    background: {t['surface_alt']}; color: {t['fg_faint']};
    border: 1px solid {t['border']}; border-radius: {r}px; }}

/* --- overlays --- */
QWidget[role="scrim"] {{ background: rgba(0, 0, 0, 110); border: none; }}
QFrame[role="modal"] {{
    background: {t['surface']}; border: 1px solid {t['border']};
    border-radius: {r + 4}px; }}
QFrame[role="toast"] {{
    background: {t['fg']}; color: {t['bg']};
    border: none; border-radius: {r + 10}px; padding: 8px 16px; }}
QFrame[role="tooltip"] {{
    background: {t['surface_alt']}; color: {t['fg']};
    border: 1px solid {t['border']}; border-radius: {r}px; padding: 4px 8px; }}

/* --- app chrome roles --- */
QWidget[role="appbar"] {{
    background: {t['surface']}; border-bottom: 1px solid {t['border']}; }}
QWidget[role="sidebar"] {{
    background: {t['surface']}; border-right: 1px solid {t['border']}; }}
QWidget[role="statusbar"] {{
    background: {t['surface_alt']}; border-top: 1px solid {t['border']}; }}
"""


# --- the runtime module PaperLoom emits into generated projects ---------------
def runtime_module_source(theme: AppTheme) -> str:
    """The `app_theme.py` shipped with a generated PySide6 app: both palettes, the
    stylesheet builder, and a one-call light/dark toggle."""
    return f'''# -*- coding: utf-8 -*-
"""
Auto-generated by PaperLoom. Light/dark theming for this app.

    import app_theme
    MainWindow.setStyleSheet(app_theme.stylesheet("dark"))

Every widget PaperLoom placed carries a `role` property, and the stylesheet
styles roles - so switching mode restyles the whole app in one call.
"""

LIGHT = {theme.light!r}

DARK = {theme.dark!r}

RADIUS = {theme.radius}

_MODE = "system"          # shipped default: follow the OS (light / dark / system)


def resolve_mode(mode=None):
    """Turn 'system' into a concrete 'light'/'dark' by asking the OS. Falls back
    to light on Qt versions without colorScheme() (< 6.5)."""
    mode = mode or _MODE
    if mode == "system":
        try:
            from PySide6.QtWidgets import QApplication
            from PySide6.QtCore import Qt
            scheme = QApplication.styleHints().colorScheme()
            return "dark" if scheme == Qt.ColorScheme.Dark else "light"
        except Exception:
            return "light"
    return mode


def tokens(mode=None):
    return dict(DARK if resolve_mode(mode) == "dark" else LIGHT)


def current_mode():
    return _MODE


def apply(window, extra=""):
    """Apply the theme to a window and, when following the system, keep it in
    sync as the OS light/dark setting changes. `extra` is appended custom QSS."""
    window.setStyleSheet(stylesheet() + extra)
    if _MODE == "system" and not getattr(window, "_pl_theme_hooked", False):
        try:
            from PySide6.QtWidgets import QApplication
            window._pl_theme_hooked = True
            QApplication.styleHints().colorSchemeChanged.connect(
                lambda _s: window.setStyleSheet(stylesheet() + extra))
        except Exception:
            pass
    return _MODE


def set_mode(window, mode, extra=""):
    """Switch to 'light', 'dark' or 'system' and restyle."""
    global _MODE
    _MODE = mode
    return apply(window, extra)


def toggle(window, extra=""):
    """Cycle light -> dark -> system -> light and restyle. Returns the new mode."""
    global _MODE
    order = ["light", "dark", "system"]
    try:
        i = order.index(_MODE)
    except ValueError:
        i = -1
    _MODE = order[(i + 1) % 3]
    return apply(window, extra)


def stylesheet(mode=None):
    """Substitute tokens into the QSS template. Deliberately not str.format -
    QSS is full of braces, so we replace explicit $token markers instead."""
    qss = STYLESHEET_TEMPLATE
    values = dict(tokens(mode))
    values["r"] = RADIUS
    for key, value in values.items():
        qss = qss.replace("$" + key + "$", str(value))
    return qss


STYLESHEET_TEMPLATE = """{_qss_template()}"""
'''


def _qss_template() -> str:
    """The QSS with {token} placeholders, for the generated runtime module."""
    sample = AppTheme()
    qss = stylesheet("light", sample)
    # turn concrete colours back into format placeholders
    # longest values first so e.g. #FFFFFF inside another token can't half-match
    for key, value in sorted(sample.light.items(), key=lambda kv: -len(kv[1])):
        qss = qss.replace(value, "$" + key + "$")
    qss = qss.replace(f"border-radius: {sample.radius}px", "border-radius: $r$px")
    return qss

"""
PaperLoom design tokens. Colour tokens are now backed by the active Theme
(core/themes.py) so the whole shell can re-style at runtime and users can import
their own themes (spec §12.8). Spacing/motion/density stay constant.

Modules keep doing `from .. import theme` and reading `theme.ACCENT` - calling
`theme.apply(active_theme)` rebinds the module attributes in place.
"""
from .core.themes import ThemeManager, Theme, DEFAULT_TOKENS

# --- spacing (8px base unit) -------------------------------------------------
SPACE_1, SPACE_2, SPACE_3, SPACE_4, SPACE_5, SPACE_6 = 4, 8, 16, 24, 32, 48
GRID_STEP = SPACE_4
BASE_UNIT = SPACE_2

# --- radius / density --------------------------------------------------------
RADIUS_SM = 4
RADIUS_MD = 6
ROW_HEIGHT = 30
BAR_HEIGHT = 36
ACTIVITY_BAR_WIDTH = 48
SIDE_PANEL_WIDTH = 264
HANDLE_SIZE = 8

# --- motion (ms) -------------------------------------------------------------
MOTION_MICRO, MOTION_DEFAULT, MOTION_MACRO = 100, 180, 260

# --- the shared theme manager ------------------------------------------------
manager = ThemeManager()


def apply(theme_obj=None):
    """Rebind every colour token on this module from the given (or active) theme."""
    t = theme_obj or manager.active
    g = globals()
    for key in DEFAULT_TOKENS:
        g[key] = t.get(key)


# populate colour tokens at import time
apply(manager.active)
manager.on_change(apply)


def app_stylesheet():
    """Application-wide QSS. Canvas-side native widgets adopt the single accent;
    every surface gets explicit fg/bg so nothing can go invisible."""
    return f"""
    QToolTip {{
        background: {ACTIVITY_BAR}; color: {INK_ON_DARK};
        border: 1px solid {BORDER_DARK}; padding: 4px 6px;
    }}
    QSlider::groove:horizontal {{ height: 4px; background: {SURFACE_SUNKEN}; border-radius: 2px; }}
    QSlider::handle:horizontal {{ background: {ACCENT}; width: 14px; margin: -6px 0; border-radius: 7px; }}
    QSlider::sub-page:horizontal {{ background: {ACCENT}; border-radius: 2px; }}
    QProgressBar {{
        background: {SURFACE_SUNKEN}; border: none; border-radius: {RADIUS_SM}px;
        text-align: center; color: {INK_PRIMARY}; font-size: 11px;
    }}
    QProgressBar::chunk {{ background: {ACCENT}; border-radius: {RADIUS_SM}px; }}
    QScrollBar:vertical {{ background: transparent; width: 10px; margin: 0; }}
    QScrollBar::handle:vertical {{ background: {INK_ON_DARK_FAINT}; border-radius: 5px; min-height: 24px; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 0; }}
    QScrollBar::handle:horizontal {{ background: {INK_ON_DARK_FAINT}; border-radius: 5px; min-width: 24px; }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
    QMenu {{ background: {SIDE_PANEL}; color: {INK_ON_DARK};
             border: 1px solid {BORDER_DARK}; padding: 4px; }}
    QMenu::item {{ padding: 5px 28px 5px 14px; border-radius: {RADIUS_SM}px; }}
    QMenu::item:selected {{ background: {ACCENT_DIM}; }}
    QMenu::separator {{ height: 1px; background: {BORDER_DARK}; margin: 4px 8px; }}
    QDialog {{ background: {SIDE_PANEL}; color: {INK_ON_DARK}; }}
    """

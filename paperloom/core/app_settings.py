"""
PaperLoom's own settings - separate from a *project's* settings (that's
project_io.py/the .paperloom project folder); this is per-machine, per-user
preference: which shell the terminal starts, whether error/crash reports are
collected, personalization choices. Same "~/.paperloom" convention
splash.py's recent-projects list already established, one JSON file.

Deliberately tiny and dependency-free (no QSettings) so it's trivial to read/
write from a script or test without a QApplication alive - core/ modules stay
Qt-free by convention (see themes.py, model.py).
"""
from __future__ import annotations
import json
import os

_CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".paperloom")
_SETTINGS_FILE = os.path.join(_CONFIG_DIR, "settings.json")

# every key PaperLoom's Settings dialog currently reads/writes, with its
# default - the single source of truth for "what a fresh install looks
# like". Data & Privacy: collect_error_reports defaults OFF - PaperLoom
# collects nothing until a person explicitly turns this on themselves.
DEFAULTS = {
    "editor_theme": "dark",          # "dark" | "light" - PaperLoom's own chrome
    "library_mode": "popup",         # "popup" | "pane"
    "terminal_shell": "auto",        # "auto" | "powershell" | "cmd" (Windows only)
    "collect_error_reports": False,  # Data & Privacy toggle - see core/error_manager.py
}


def load() -> dict:
    """Always returns a dict with every DEFAULTS key present, even if the
    file is missing, empty, corrupt, or from an older version that didn't
    know about a newer key yet."""
    data = dict(DEFAULTS)
    try:
        with open(_SETTINGS_FILE, encoding="utf-8") as f:
            on_disk = json.load(f)
        if isinstance(on_disk, dict):
            for key in DEFAULTS:
                if key in on_disk:
                    data[key] = on_disk[key]
    except (OSError, ValueError):
        pass
    return data


def save(data: dict) -> None:
    try:
        os.makedirs(_CONFIG_DIR, exist_ok=True)
        with open(_SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except OSError:
        pass


def get(key, default=None):
    return load().get(key, DEFAULTS.get(key, default))


def set(key, value) -> None:
    """Read-modify-write a single key, preserving everything else already
    on disk (including keys a newer/older version of PaperLoom wrote that
    this process doesn't otherwise touch)."""
    data = load()
    data[key] = value
    save(data)

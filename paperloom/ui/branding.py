"""
Branding assets - referenced by PATH, not baked into code or resource-compiled,
so swapping the logo or mascot later is a one-file drop-in. Per Abinaash: "I
made a crude, ugly logo - just use it as a path in the project - Logo.png, so
I can update easily in the future, all app icons, favicons etc shld use it."

Three files live in resources/branding/:
  Logo.png       - the app's identity. Window icon, splash screen, About
                   section, and (later) any favicon/installer icon export -
                   every one of those should call app_icon()/LOGO_PATH from
                   here rather than loading its own copy.
  LilyKnight.png - the mascot. Shown small, once, as a quiet easter egg
                   (Settings > About) - not plastered everywhere.
  SplashArt.jpg  - Abinaash's own hand-taken photo (a rainbow over
                   buildings), used as the background artwork for the
                   boot-time loading screen (ui/loading_splash.py) - the
                   Krita-style "here's something nice to look at while the
                   app wakes up" screen, not the project-picker dialog
                   (ui/splash.py).

Nothing here caches a QPixmap/QIcon at import time: nobody but a real Qt
application should touch QIcon/QPixmap at module-import time anyway (needs a
QApplication alive first), and reading fresh from disk on each call means
replacing the PNG on disk takes effect the next time a window opens it, no
code change or rebuild required.
"""
import os

_DIR = os.path.dirname(os.path.abspath(__file__))
_RESOURCES = os.path.join(os.path.dirname(_DIR), "resources", "branding")

LOGO_PATH = os.path.join(_RESOURCES, "Logo.png")
MASCOT_PATH = os.path.join(_RESOURCES, "LilyKnight.png")
SPLASH_ART_PATH = os.path.join(_RESOURCES, "SplashArt.jpg")


def app_icon():
    """The one QIcon every window/dialog/taskbar entry should use."""
    from PySide6.QtGui import QIcon
    if os.path.isfile(LOGO_PATH):
        icon = QIcon(LOGO_PATH)
        if not icon.isNull():
            return icon
    return QIcon()


def logo_pixmap(size=64):
    """Logo.png scaled to a square of `size`, aspect-preserved, smoothly
    resampled - for the splash screen and the Settings About page."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QPixmap
    if os.path.isfile(LOGO_PATH):
        pm = QPixmap(LOGO_PATH)
        if not pm.isNull():
            return pm.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio,
                              Qt.TransformationMode.SmoothTransformation)
    return QPixmap()


def mascot_pixmap(size=28):
    """LilyKnight.png, tiny by design - callers should not scale this any
    larger than a couple dozen px; he's a corner easter egg, not a hero
    image."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QPixmap
    if os.path.isfile(MASCOT_PATH):
        pm = QPixmap(MASCOT_PATH)
        if not pm.isNull():
            return pm.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio,
                              Qt.TransformationMode.SmoothTransformation)
    return QPixmap()


def splash_art_pixmap():
    """SplashArt.jpg at its native resolution - the boot splash scales/crops
    it itself (it needs to know the target window size to crop correctly),
    so this hands back the raw pixmap rather than pre-scaling like the two
    helpers above."""
    from PySide6.QtGui import QPixmap
    if os.path.isfile(SPLASH_ART_PATH):
        pm = QPixmap(SPLASH_ART_PATH)
        if not pm.isNull():
            return pm
    return QPixmap()

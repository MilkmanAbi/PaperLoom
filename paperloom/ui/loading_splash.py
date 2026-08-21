"""
Boot-time loading screen (not to be confused with `ui/splash.py`'s
project-picker dialog). PaperLoom's cold start is slow enough - PySide6
itself, the component library, the editor chrome - that showing *nothing*
until the project picker appears reads as "did it hang?". Krita's splash
(artwork + logo/version tucked in a corner + a small "Loading ..." line
that updates as the app boots) is the reference: something pleasant to
look at that also tells you it's alive and roughly what it's doing.

The artwork is Abinaash's own hand-taken photo (a rainbow over buildings -
resources/branding/SplashArt.jpg via branding.splash_art_pixmap()), because
"make one with my HAND taken image" was the actual ask, not stock art.

Usage (see main.py):

    boot = LoadingSplash()
    boot.show()
    app.processEvents()
    boot.set_status("Loading component library...")
    app.processEvents()
    ... do the slow work ...
    boot.close()

This is a plain QWidget, not QSplashScreen - QSplashScreen only supports one
pixmap plus one line of overlay text, which can't reproduce the "logo block
in one corner, status text in another, both over cropped artwork" layout
Krita uses. Full control here costs nothing extra since it's still just a
handful of child widgets over a painted background.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QRect, QRectF
from PySide6.QtGui import QPainter, QColor, QLinearGradient, QPen
from PySide6.QtWidgets import QWidget, QLabel, QVBoxLayout, QHBoxLayout

from . import branding
from ..core.error_manager import APP_VERSION

_W, _H = 640, 380
_BORDER = QColor(20, 18, 15)
_INK = "#FFFFFF"
_INK_MUTED = "rgba(255, 255, 255, 190)"


class LoadingSplash(QWidget):
    """A frameless, centered, always-on-top boot screen. Not a QDialog - it
    has no event loop of its own; the caller drives `app.processEvents()`
    between `show()` and `close()` so the slow init work runs on the main
    thread while this still gets to paint and stay responsive."""

    def __init__(self):
        super().__init__(
            None,
            Qt.WindowType.SplashScreen
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setFixedSize(_W, _H)
        self._art = branding.splash_art_pixmap()
        self._build()
        self._center_on_screen()

    # --- layout ----------------------------------------------------------
    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 16, 18, 14)

        # top row: logo + brand, top-left; nothing top-right (the art
        # itself is the visual interest, unlike Krita's corner logo - ours
        # sits with the brand text instead so the photo stays uncluttered)
        top = QHBoxLayout()
        logo_pm = branding.logo_pixmap(28)
        if not logo_pm.isNull():
            logo = QLabel()
            logo.setPixmap(logo_pm)
            top.addWidget(logo)
        brand = QLabel("PaperLoom")
        brand.setStyleSheet(f"color: {_INK}; font-size: 15px; font-weight: 800; "
                             "background: transparent;")
        top.addWidget(brand)
        top.addStretch(1)
        version = QLabel(f"v{APP_VERSION}")
        version.setStyleSheet(f"color: {_INK_MUTED}; font-size: 11px; "
                               "background: transparent;")
        top.addWidget(version)
        outer.addLayout(top)
        outer.addStretch(1)

        # bottom row: dynamic status line, bottom-right - Krita's
        # "Loading Main Window..." spot
        bottom = QHBoxLayout()
        bottom.addStretch(1)
        self._status = QLabel("Starting PaperLoom...")
        self._status.setStyleSheet(
            f"color: {_INK}; font-size: 12px; font-style: italic; "
            "background: transparent;"
        )
        bottom.addWidget(self._status)
        outer.addLayout(bottom)

    def _center_on_screen(self):
        screen = self.screen()
        if screen is not None:
            geo = screen.availableGeometry()
            self.move(geo.center().x() - _W // 2, geo.center().y() - _H // 2)

    # --- public API --------------------------------------------------------
    def set_status(self, text: str):
        self._status.setText(text)

    # --- painting ------------------------------------------------------------
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        rect = self.rect()

        if not self._art.isNull():
            # cover-fit: scale up to fill, then center-crop the overflow -
            # same idea as CSS `background-size: cover`, so the photo
            # always fills the frame with no letterboxing regardless of
            # its own aspect ratio.
            scaled = self._art.scaled(
                rect.size(),
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            x = (scaled.width() - rect.width()) // 2
            y = (scaled.height() - rect.height()) // 2
            source = QRect(x, y, rect.width(), rect.height())
            p.drawPixmap(rect, scaled, source)
        else:
            p.fillRect(rect, QColor(43, 40, 34))

        # gradient scrims top and bottom so the white text stays legible
        # over whatever the photo happens to show there
        top_grad = QLinearGradient(0, 0, 0, rect.height() * 0.35)
        top_grad.setColorAt(0, QColor(0, 0, 0, 130))
        top_grad.setColorAt(1, QColor(0, 0, 0, 0))
        p.fillRect(QRectF(0, 0, rect.width(), rect.height() * 0.35), top_grad)

        bottom_grad = QLinearGradient(0, rect.height() * 0.72, 0, rect.height())
        bottom_grad.setColorAt(0, QColor(0, 0, 0, 0))
        bottom_grad.setColorAt(1, QColor(0, 0, 0, 150))
        p.fillRect(QRectF(0, rect.height() * 0.72, rect.width(), rect.height() * 0.28), bottom_grad)

        # thin frame, matching Krita's bordered-splash look
        pen = QPen(_BORDER)
        pen.setWidth(2)
        p.setPen(pen)
        p.drawRect(rect.adjusted(1, 1, -1, -1))
        p.end()

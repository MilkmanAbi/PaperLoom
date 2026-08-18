"""
Component preview renderer (spec §4.3, §14). Instantiates a component with its
default properties through the same factory the canvas uses, applies the app
theme stylesheet, and grabs it at 2x for a crisp thumbnail - so a preview is a
faithful, sharp picture of exactly what dropping the component produces.
"""
from __future__ import annotations
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap, QPainter, QColor
from PySide6.QtWidgets import QWidget

from ..core import app_theme as app_theme_mod
from ..components import factory
from ..core.model import DesignWidget

_cache: dict[str, QPixmap] = {}
_mode = "light"


def set_mode(mode):
    global _mode
    if mode != _mode:
        _mode = mode
        clear_cache()


def preview(component, width: int = 220, height: int = 56) -> QPixmap:
    key = f"{component.id}:{_mode}:{width}x{height}"
    if key in _cache:
        return _cache[key]

    theme = app_theme_mod.AppTheme(mode=_mode)
    tokens = theme.tokens()
    qss = app_theme_mod.stylesheet(_mode, theme)

    dpr = 2  # render at 2x for a crisp thumbnail
    canvas_pix = QPixmap(width * dpr, height * dpr)
    canvas_pix.setDevicePixelRatio(dpr)
    canvas_pix.fill(QColor(tokens["bg"]))

    host = QWidget()
    host.setStyleSheet(qss)
    host.resize(width, height)

    # use exactly the size the canvas would give this component, clamped to the
    # thumbnail - otherwise the preview and the placed widget disagree, which is
    # the fidelity promise broken in miniature
    from ..ui.canvas import _default_width, _default_height
    w = min(_default_width(component), width - 24)
    h = min(_default_height(component), height - 12)
    w, h = max(w, 12), max(h, 2)

    dw = DesignWidget(component_id=component.id,
                      object_name=f"preview_{component.id}",
                      x=0, y=0, width=w, height=h,
                      properties=component.default_properties())
    live = factory.instantiate(component, dw, host)
    live.setGeometry(0, 0, w, h)
    live.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    live.show()

    widget_pix = live.grab()
    widget_pix.setDevicePixelRatio(dpr)

    painter = QPainter(canvas_pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    painter.drawPixmap((width - w) // 2, (height - h) // 2, widget_pix)
    painter.end()

    host.deleteLater()
    _cache[key] = canvas_pix
    return canvas_pix


def clear_cache():
    _cache.clear()

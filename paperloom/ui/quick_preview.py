"""
Quick Preview - an in-app, instant, fully interactive preview of the current
page: a fake OS window (custom titlebar, real drag, real corner-resize)
hosting a SECOND, independent live widget tree built from the exact same
`components.factory.instantiate()` call the canvas uses, but WITHOUT the
design-mode event filter (ui/canvas.py's DesignModeFilter) - so nothing
intercepts events here. Buttons really click, sliders really drag, combo
boxes really drop. Layout-managed widgets get real QLayout objects via
components/live_layout.py, so resizing the preview window actually reflows
content the way the final generated app would - the canvas itself stays
absolute-position-only by design (see live_layout.py's docstring for why
that's not a fidelity break).

Not a new OS-level window: a frameless Qt.WindowType.Tool widget, the same
flag combination QuickEditBar/CommandPalette already use (panels/context_menus.py,
panels/command_palette.py) to float over the app without a taskbar entry - so
it visually reads as "inside PaperLoom" while being fully draggable/resizable
on its own, no fighting the real window manager for custom chrome.
"""
from __future__ import annotations
from PySide6.QtCore import Qt, QPoint, QRect, Signal
from PySide6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton, QFrame

from .. import theme
from . import icons
from ..components import factory
from ..components.live_layout import apply_layouts
from ..core import app_theme as app_theme_mod

_TITLEBAR_H = 30
_BORDER = 1
_GRIP = 14


class _TitleBar(QFrame):
    """The fake OS titlebar. Themed off the app being designed (its own
    tokens), not PaperLoom's editor chrome - it's previewing THAT app."""
    closeRequested = Signal()
    minimizeRequested = Signal()
    maximizeRequested = Signal()

    def __init__(self, host):
        super().__init__(host)
        self.host = host
        self.setObjectName("QuickPreviewTitle")
        self.setFixedHeight(_TITLEBAR_H)
        self._drag_anchor = None

        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 0, 6, 0)
        lay.setSpacing(6)

        self.title_label = QLabel("Preview")
        self.title_label.setObjectName("qpTitle")
        lay.addWidget(self.title_label)
        lay.addStretch(1)

        self.min_btn = self._dot("minus", "Hide")
        self.max_btn = self._dot("square", "Maximize / restore")
        self.close_btn = self._dot("x", "Close")
        for b in (self.min_btn, self.max_btn, self.close_btn):
            lay.addWidget(b)

        self.min_btn.clicked.connect(self.minimizeRequested.emit)
        self.max_btn.clicked.connect(self.maximizeRequested.emit)
        self.close_btn.clicked.connect(self.closeRequested.emit)

    def _dot(self, icon_name, tip):
        b = QPushButton()
        b.setObjectName(f"qp_{icon_name}")
        b.setFixedSize(20, 20)
        b.setToolTip(tip)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b._icon_name = icon_name
        return b

    def set_title(self, text):
        self.title_label.setText(text or "Preview")

    def set_tokens(self, tokens):
        ink = tokens.get("fg", "#1a1a1a")
        bg = tokens.get("surface", tokens.get("bg", "#ffffff"))
        border = tokens.get("border", "#00000022")
        for b in (self.min_btn, self.max_btn, self.close_btn):
            b.setIcon(icons.icon(b._icon_name, ink, 12))
        self.setStyleSheet(f"""
            #QuickPreviewTitle {{ background: {bg}; border-bottom: 1px solid {border}; }}
            QLabel#qpTitle {{ color: {ink}; font-size: 12px; font-weight: 600; }}
            QPushButton {{ background: transparent; border: none; border-radius: 4px; }}
            QPushButton:hover {{ background: rgba(128,128,128,0.18); }}
        """)

    # drag-to-move: moves the top-level host window directly, same manual
    # press/move/release pattern panels/tools_toolbar.py already uses for its
    # own floating drag mode
    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag_anchor = e.globalPosition().toPoint() - self.host.pos()
        e.accept()

    def mouseMoveEvent(self, e):
        if self._drag_anchor is not None:
            self.host.move(e.globalPosition().toPoint() - self._drag_anchor)
        e.accept()

    def mouseReleaseEvent(self, e):
        self._drag_anchor = None
        e.accept()

    def mouseDoubleClickEvent(self, e):
        self.maximizeRequested.emit()


class _CornerGrip(QWidget):
    """One corner resize handle. corner is one of 'tl'/'tr'/'bl'/'br'. Direct
    QRect.setX/setY/setWidth/setHeight calls give each corner the right
    "opposite corner stays anchored" behaviour for free."""

    def __init__(self, host, corner):
        super().__init__(host)
        self.host = host
        self.corner = corner
        self.setFixedSize(_GRIP, _GRIP)
        diag = Qt.CursorShape.SizeFDiagCursor if corner in ("tl", "br") \
            else Qt.CursorShape.SizeBDiagCursor
        self.setCursor(diag)
        self._drag_start = None
        self._start_geo = None

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag_start = e.globalPosition().toPoint()
            self._start_geo = self.host.geometry()
        e.accept()

    def mouseMoveEvent(self, e):
        if self._drag_start is None:
            return
        delta = e.globalPosition().toPoint() - self._drag_start
        geo = QRect(self._start_geo)
        min_w, min_h = self.host.min_total_size()
        if "r" in self.corner:
            geo.setWidth(max(min_w, self._start_geo.width() + delta.x()))
        if "l" in self.corner:
            geo.setX(min(self._start_geo.right() - min_w, self._start_geo.x() + delta.x()))
        if "b" in self.corner:
            geo.setHeight(max(min_h, self._start_geo.height() + delta.y()))
        if "t" in self.corner:
            geo.setY(min(self._start_geo.bottom() - min_h, self._start_geo.y() + delta.y()))
        self.host.setGeometry(geo)
        e.accept()

    def mouseReleaseEvent(self, e):
        self._drag_start = None
        e.accept()


class QuickPreviewWindow(QWidget):
    """The preview frame itself. One instance is reused across opens (the
    window keeps its screen position/size between reopens, like a real app
    window would)."""
    closed = Signal()

    def __init__(self, registry, asset_resolver=None, parent=None):
        super().__init__(parent, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint)
        self.setObjectName("QuickPreview")
        self.registry = registry
        self.asset_resolver = asset_resolver
        self.page = None
        self._min_w, self._min_h = 240, 160
        self._restored_geometry = None   # set while maximized, for restore
        self._positioned = False         # True once an initial geometry is set
        self._live = []                  # keeps live widgets referenced

        outer = QVBoxLayout(self)
        outer.setContentsMargins(_BORDER, _BORDER, _BORDER, _BORDER)
        outer.setSpacing(0)

        self.titlebar = _TitleBar(self)
        self.titlebar.closeRequested.connect(self.hide)
        self.titlebar.minimizeRequested.connect(self.hide)
        self.titlebar.maximizeRequested.connect(self._toggle_maximize)
        outer.addWidget(self.titlebar)

        self.content = QWidget(self)
        self.content.setObjectName("QuickPreviewContent")
        outer.addWidget(self.content, 1)

        self._grips = {c: _CornerGrip(self, c) for c in ("tl", "tr", "bl", "br")}

        self.setStyleSheet(
            f"#QuickPreview {{ border: 1px solid {theme.BORDER_DARK}; }}")

    # --- public API ------------------------------------------------------
    def show_page(self, page, app_theme_obj):
        """Show (or, if already open, follow) `page`. Position/size are only
        computed the first time this window becomes visible - reopening or
        following a tab switch keeps wherever the user left it."""
        self.page = page
        self._min_w = max(240, int(page.width * 0.5))
        self._min_h = max(160, int(page.height * 0.5))
        self._rebuild(app_theme_obj)
        if not self._positioned:
            self._place_initial(page)
            self._positioned = True
        self.show()
        self.raise_()
        self.activateWindow()

    def refresh(self, app_theme_obj=None):
        if self.page is not None:
            self._rebuild(app_theme_obj)

    def min_total_size(self):
        return self._min_w + 2 * _BORDER, self._min_h + _TITLEBAR_H + 2 * _BORDER

    # --- internals ---------------------------------------------------------
    def _place_initial(self, page):
        host = self.parentWidget()
        w = page.width
        h = page.height + _TITLEBAR_H + 2 * _BORDER
        if host is not None:
            w = min(w, max(self._min_w, host.width() - 80))
            h = min(h, max(self._min_h + _TITLEBAR_H, host.height() - 120))
            top_left = host.mapToGlobal(QPoint(0, 0))
            x = top_left.x() + (host.width() - w) // 2
            y = top_left.y() + max(20, (host.height() - h) // 2)
        else:
            x, y = 120, 100
        self.setGeometry(x, y, w, h)

    def _bounds_rect(self):
        """The area 'filling the main window' means, for maximize."""
        host = self.parentWidget()
        if host is None:
            return self.geometry()
        margin = 24
        top_left = host.mapToGlobal(QPoint(0, 0))
        return QRect(top_left.x() + margin, top_left.y() + margin,
                     max(self._min_w, host.width() - margin * 2),
                     max(self._min_h, host.height() - margin * 2))

    def _toggle_maximize(self):
        if self._restored_geometry is None:
            self._restored_geometry = self.geometry()
            self.setGeometry(self._bounds_rect())
        else:
            self.setGeometry(self._restored_geometry)
            self._restored_geometry = None

    def _rebuild(self, app_theme_obj):
        # a page with layout groups leaves self.content owning a real QLayout
        # afterwards - QWidget.setLayout() silently refuses a second one, so
        # clearing children in place isn't enough between rebuilds. Replace
        # the whole content widget (and whatever layout it owns) instead.
        old_content = self.content
        self.content = QWidget(self)
        self.content.setObjectName("QuickPreviewContent")
        self.layout().replaceWidget(old_content, self.content)
        old_content.hide()
        old_content.setParent(None)
        old_content.deleteLater()
        self._live.clear()

        if app_theme_obj is not None:
            tokens = app_theme_obj.tokens()
            qss = app_theme_mod.stylesheet(app_theme_obj.mode, app_theme_obj)
            self.content.setStyleSheet(
                f"#QuickPreviewContent {{ background: {tokens['bg']}; }}\n" + qss)
            self.titlebar.set_tokens(tokens)
        self.titlebar.set_title(self.page.title if self.page else "Preview")

        live_by_name = {}
        for dw in (self.page.widgets if self.page else []):
            component = self.registry.get(dw.component_id)
            if component is None:
                continue
            # NO DesignModeFilter installed - the entire point of Quick
            # Preview is that nothing intercepts these widgets' real events
            widget = factory.instantiate(component, dw, self.content, self.asset_resolver)
            widget.show()
            live_by_name[dw.object_name] = widget
            self._live.append(widget)

        if self.page is not None:
            apply_layouts(self.page, live_by_name, self.content)

        for grip in self._grips.values():
            grip.raise_()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        w, h = self.width(), self.height()
        self._grips["tl"].move(0, 0)
        self._grips["tr"].move(w - _GRIP, 0)
        self._grips["bl"].move(0, h - _GRIP)
        self._grips["br"].move(w - _GRIP, h - _GRIP)

    def hideEvent(self, event):
        super().hideEvent(event)
        self.closed.emit()

"""
Context menus and the quick-edit bar (spec §29).

Right-click is where a designer's hands already are, so it carries real work
here, not just Cut/Copy/Paste: per-widget actions adapt to what you clicked -
a button offers text and colour, a media widget offers "change image", a
container offers layout choices - and the canvas itself offers paste, grid and
snap toggles.

The quick-edit bar is the fast lane for the three things people change
constantly: opacity, colour and corner rounding.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal, QPoint
from PySide6.QtGui import QAction, QColor
from PySide6.QtWidgets import (
    QMenu, QWidget, QHBoxLayout, QLabel, QSlider, QPushButton, QSpinBox, QFrame
)

from ... import theme
from .color_picker import ColorPickerDialog


# --- context menus -----------------------------------------------------------
def style_menu(menu: QMenu):
    menu.setStyleSheet(f"""
        QMenu {{ background: {theme.SIDE_PANEL}; color: {theme.INK_ON_DARK};
                 border: 1px solid {theme.BORDER_DARK}; padding: 4px; }}
        QMenu::item {{ padding: 6px 26px 6px 12px; border-radius: 4px; }}
        QMenu::item:selected {{ background: {theme.ACCENT_DIM}; }}
        QMenu::item:disabled {{ color: {theme.INK_ON_DARK_FAINT}; }}
        QMenu::separator {{ height: 1px; background: {theme.BORDER_DARK};
                            margin: 4px 8px; }}
    """)
    return menu


def build_widget_menu(parent, component, dw, handlers) -> QMenu:
    """The menu for a widget on the canvas. Adapts to the component's role and
    declared properties - a media widget gets 'Change image', a button gets
    'Edit text', anything with a colour gets a picker."""
    menu = style_menu(QMenu(parent))
    role = getattr(component, "style_role", "")
    prop_names = {p.name for p in component.properties}

    header = menu.addAction(f"{component.name}  ·  {dw.object_name}")
    header.setEnabled(False)
    menu.addSeparator()

    if "text" in prop_names or "title" in prop_names:
        menu.addAction("Edit text…", handlers["edit_text"])
    if "placeholder" in prop_names:
        menu.addAction("Edit placeholder…", handlers["edit_text"])
    prop_types = {p.name: (p.type or "string") for p in component.properties}
    if any(t == "markdown" for t in prop_types.values()):
        menu.addAction("Edit content…", handlers["edit_markdown"])
    if "asset" in prop_names or role == "media_frame":
        menu.addAction("Change media…", handlers["change_media"])

    menu.addAction("Colour…", handlers["pick_color"])
    menu.addAction("Quick edit…", handlers["quick_edit"])
    menu.addSeparator()

    # arrange
    arrange = style_menu(menu.addMenu("Arrange"))
    arrange.addAction("Bring to front", handlers["bring_front"])
    arrange.addAction("Send to back", handlers["send_back"])
    arrange.addSeparator()
    for label, how in (("Align left", "left"), ("Align centre", "center"),
                       ("Align right", "right"), ("Align top", "top"),
                       ("Align middle", "middle"), ("Align bottom", "bottom")):
        arrange.addAction(label, lambda h=how: handlers["align"](h))

    # size
    size = style_menu(menu.addMenu("Size"))
    size.addAction("Fit to contents", handlers["fit_contents"])
    size.addAction("Fill width", handlers["fill_width"])
    size.addAction("Reset size", handlers["reset_size"])

    animate = style_menu(menu.addMenu("Animate"))
    for label, kind in (("Fade in", "fade_in"), ("Slide up", "slide_up"),
                        ("Pop", "pop"), ("Shake", "shake")):
        animate.addAction(label, lambda k=kind: handlers["animate"](k))

    menu.addSeparator()
    menu.addAction("Duplicate", handlers["duplicate"])
    menu.addAction("Copy", handlers["copy"])
    delete = menu.addAction("Delete", handlers["delete"])
    delete.setShortcut("Del")
    menu.addSeparator()
    menu.addAction("Properties…", handlers["properties"])
    menu.addAction("All Qt properties…", handlers["qt_properties"])
    return menu


def build_canvas_menu(parent, handlers, has_clipboard=False) -> QMenu:
    """The menu for empty canvas: paste, view toggles, page-level actions."""
    menu = style_menu(QMenu(parent))
    paste = menu.addAction("Paste", handlers["paste"])
    paste.setEnabled(has_clipboard)
    menu.addAction("Add component…", handlers["open_library"])
    menu.addSeparator()

    view = style_menu(menu.addMenu("View"))
    grid = view.addAction("Show grid", handlers["toggle_grid"])
    grid.setCheckable(True); grid.setChecked(handlers["grid_on"]())
    guides = view.addAction("Alignment guides", handlers["toggle_guides"])
    guides.setCheckable(True); guides.setChecked(handlers["guides_on"]())
    snap = view.addAction("Snap to grid", handlers["toggle_snap"])
    snap.setCheckable(True); snap.setChecked(handlers["snap_on"]())
    view.addSeparator()
    view.addAction("Snap settings…", handlers["snap_settings"])

    menu.addAction("Toggle app light/dark", handlers["toggle_app_mode"])
    menu.addSeparator()
    menu.addAction("Select all", handlers["select_all"])
    menu.addAction("Page settings…", handlers["page_settings"])
    return menu


# --- quick edit bar ----------------------------------------------------------
class QuickEditBar(QFrame):
    """A compact floating bar for the properties people change constantly:
    opacity, colour and corner rounding. Appears next to the selection."""

    opacityChanged = Signal(float)
    colorChanged = Signal(str)
    radiusChanged = Signal(int)
    closed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint)
        self.setObjectName("QuickEdit")
        self._color = "#5B6BE8"

        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 6, 8, 6)
        lay.setSpacing(10)

        lay.addWidget(self._label("Opacity"))
        self.opacity = QSlider(Qt.Orientation.Horizontal)
        self.opacity.setRange(0, 100); self.opacity.setValue(100)
        self.opacity.setFixedWidth(90)
        self.opacity.valueChanged.connect(
            lambda v: (self._pct.setText(f"{v}%"), self.opacityChanged.emit(v / 100.0)))
        lay.addWidget(self.opacity)
        self._pct = self._label("100%")
        lay.addWidget(self._pct)

        lay.addWidget(self._divider())

        lay.addWidget(self._label("Colour"))
        self.swatch = QPushButton()
        self.swatch.setFixedSize(24, 22)
        self.swatch.setCursor(Qt.CursorShape.PointingHandCursor)
        self.swatch.clicked.connect(self._pick)
        lay.addWidget(self.swatch)

        lay.addWidget(self._divider())

        lay.addWidget(self._label("Radius"))
        self.radius = QSpinBox()
        self.radius.setRange(0, 100); self.radius.setSuffix(" px")
        self.radius.setFixedWidth(70)
        self.radius.valueChanged.connect(self.radiusChanged.emit)
        lay.addWidget(self.radius)

        close = QPushButton("✕")
        close.setObjectName("close")
        close.setFixedSize(20, 20)
        close.setCursor(Qt.CursorShape.PointingHandCursor)
        close.clicked.connect(self._close)
        lay.addWidget(close)

        self.restyle()
        self.hide()

    def _label(self, text):
        label = QLabel(text); label.setObjectName("dim")
        return label

    def _divider(self):
        line = QFrame(); line.setFrameShape(QFrame.Shape.VLine)
        line.setFixedHeight(16)
        line.setStyleSheet(f"color: {theme.BORDER_DARK};")
        return line

    def show_for(self, live_widget, canvas, opacity=1.0, color="#5B6BE8", radius=6):
        self.opacity.blockSignals(True); self.opacity.setValue(int(opacity * 100))
        self.opacity.blockSignals(False)
        self._pct.setText(f"{int(opacity * 100)}%")
        self.radius.blockSignals(True); self.radius.setValue(int(radius))
        self.radius.blockSignals(False)
        self.set_color(color)
        anchor = live_widget.mapTo(canvas, live_widget.rect().topLeft())
        pos = canvas.mapToGlobal(anchor)
        self.adjustSize()
        self.move(pos.x(), max(0, pos.y() - self.height() - 8))
        self.show()
        self.raise_()

    def set_color(self, color):
        self._color = color
        self.swatch.setStyleSheet(
            f"background: {color}; border: 1px solid {theme.BORDER_DARK};"
            f" border-radius: 4px;")

    def _pick(self):
        picked = ColorPickerDialog.get_color(self._color, self)
        if picked is not None:
            self.set_color(picked.name())
            self.colorChanged.emit(picked.name())

    def _close(self):
        self.hide()
        self.closed.emit()

    def restyle(self):
        self.setStyleSheet(f"""
            #QuickEdit {{ background: {theme.SIDE_PANEL};
                border: 1px solid {theme.ACCENT}; border-radius: {theme.RADIUS_MD}px; }}
            QLabel#dim {{ color: {theme.INK_ON_DARK_MUTED}; font-size: 11px; }}
            QSpinBox {{ background: {theme.ACTIVITY_BAR}; color: {theme.INK_ON_DARK};
                border: 1px solid {theme.BORDER_DARK}; border-radius: 4px;
                padding: 2px 4px; font-size: 11px; }}
            QPushButton#close {{ background: transparent;
                color: {theme.INK_ON_DARK_MUTED}; border: none; font-size: 12px; }}
            QPushButton#close:hover {{ color: {theme.INK_ON_DARK}; }}
        """)
        self.set_color(self._color)

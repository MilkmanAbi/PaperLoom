"""
Colour picker (spec §28). A real one: hue wheel with a saturation/lightness
triangle-style square, HSL / RGB / ARGB / HEX entry, an alpha channel, curated
palettes, and a recent-colours history.

Everything stays in sync from one source of truth (`self._color`), so dragging
the wheel updates the sliders and the hex field, and typing hex moves the wheel.
"""
from __future__ import annotations
import math

from PySide6.QtCore import Qt, Signal, QPointF, QRectF
from PySide6.QtGui import (
    QColor, QPainter, QConicalGradient, QLinearGradient, QPen, QBrush, QPixmap
)
from PySide6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QLineEdit,
    QSlider, QSpinBox, QPushButton, QTabWidget, QFrame, QSizePolicy
)

from ... import theme

# a few curated palettes, plus the app theme's own colours
PALETTES = {
    "Theme": ["#5B6BE8", "#7C8BFF", "#4C9A6A", "#B8842B", "#C8453F",
              "#23201B", "#6B6255", "#D3CCBE", "#F5F3EE", "#FFFFFF"],
    "Warm": ["#FFF3E0", "#FFE0B2", "#FFCC80", "#FFB74D", "#FFA726",
             "#FB8C00", "#F57C00", "#EF6C00", "#E65100", "#BF360C"],
    "Cool": ["#E3F2FD", "#BBDEFB", "#90CAF9", "#64B5F6", "#42A5F5",
             "#2196F3", "#1E88E5", "#1976D2", "#1565C0", "#0D47A1"],
    "Greys": ["#FFFFFF", "#F5F5F5", "#E0E0E0", "#BDBDBD", "#9E9E9E",
              "#757575", "#616161", "#424242", "#212121", "#000000"],
}

_RECENT: list[str] = []


class ColorWheel(QWidget):
    """Hue ring plus a saturation/value square in the middle."""
    colorChanged = Signal(QColor)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(200, 200)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._color = QColor("#5B6BE8")
        self._dragging = None       # "ring" | "square"

    def color(self):
        return QColor(self._color)

    def set_color(self, color: QColor):
        if color.isValid():
            self._color = QColor(color)
            self.update()

    # --- geometry -------------------------------------------------------------
    def _ring_radius(self):
        return min(self.width(), self.height()) / 2 - 4

    def _ring_thickness(self):
        return max(14.0, self._ring_radius() * 0.18)

    def _square_rect(self):
        inner = self._ring_radius() - self._ring_thickness() - 6
        side = inner * math.sqrt(2)
        c = QPointF(self.width() / 2, self.height() / 2)
        return QRectF(c.x() - side / 2, c.y() - side / 2, side, side)

    # --- painting -------------------------------------------------------------
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        c = QPointF(self.width() / 2, self.height() / 2)
        radius = self._ring_radius()
        thickness = self._ring_thickness()

        # hue ring
        gradient = QConicalGradient(c, 0)
        for i in range(0, 361, 10):
            gradient.setColorAt(i / 360.0, QColor.fromHsv(i % 360, 255, 255))
        painter.setPen(QPen(QBrush(gradient), thickness))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(c, radius - thickness / 2, radius - thickness / 2)

        # hue marker
        hue = max(0, self._color.hue())
        angle = math.radians(hue)
        mr = radius - thickness / 2
        marker = QPointF(c.x() + mr * math.cos(angle), c.y() - mr * math.sin(angle))
        painter.setPen(QPen(QColor("#FFFFFF"), 2))
        painter.setBrush(QColor.fromHsv(hue, 255, 255))
        painter.drawEllipse(marker, thickness / 2 - 1, thickness / 2 - 1)

        # saturation / value square
        rect = self._square_rect()
        base = QColor.fromHsv(hue, 255, 255)
        sat = QLinearGradient(rect.topLeft(), rect.topRight())
        sat.setColorAt(0, QColor("#FFFFFF")); sat.setColorAt(1, base)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(sat); painter.drawRect(rect)
        val = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        val.setColorAt(0, QColor(0, 0, 0, 0)); val.setColorAt(1, QColor(0, 0, 0, 255))
        painter.setBrush(val); painter.drawRect(rect)

        # sv marker
        s = self._color.saturationF()
        v = self._color.valueF()
        px = rect.left() + s * rect.width()
        py = rect.top() + (1 - v) * rect.height()
        painter.setPen(QPen(QColor("#FFFFFF"), 2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QPointF(px, py), 6, 6)
        painter.setPen(QPen(QColor("#000000"), 1))
        painter.drawEllipse(QPointF(px, py), 7.5, 7.5)

    # --- interaction ----------------------------------------------------------
    def mousePressEvent(self, event):
        pos = event.position()
        c = QPointF(self.width() / 2, self.height() / 2)
        dist = math.hypot(pos.x() - c.x(), pos.y() - c.y())
        if dist > self._ring_radius() - self._ring_thickness() - 2:
            self._dragging = "ring"
        elif self._square_rect().contains(pos):
            self._dragging = "square"
        self._apply(pos)

    def mouseMoveEvent(self, event):
        if self._dragging:
            self._apply(event.position())

    def mouseReleaseEvent(self, event):
        self._dragging = None

    def _apply(self, pos: QPointF):
        c = QPointF(self.width() / 2, self.height() / 2)
        if self._dragging == "ring":
            angle = math.degrees(math.atan2(c.y() - pos.y(), pos.x() - c.x()))
            hue = int(angle % 360)
            self._color.setHsv(hue, self._color.saturation(),
                               self._color.value(), self._color.alpha())
        elif self._dragging == "square":
            rect = self._square_rect()
            s = min(max((pos.x() - rect.left()) / rect.width(), 0.0), 1.0)
            v = 1 - min(max((pos.y() - rect.top()) / rect.height(), 0.0), 1.0)
            self._color.setHsvF(max(self._color.hueF(), 0.0), s, v,
                                self._color.alphaF())
        else:
            return
        self.update()
        self.colorChanged.emit(QColor(self._color))


class ColorPickerDialog(QDialog):
    """The full picker: wheel, channel entry in several models, palettes."""
    colorPicked = Signal(QColor)

    def __init__(self, initial="#5B6BE8", allow_alpha=True, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Pick a colour")
        self.setObjectName("ColorPicker")
        self.resize(420, 560)
        self._color = QColor(initial)
        if not self._color.isValid():
            self._color = QColor("#000000")
        self._allow_alpha = allow_alpha
        self._syncing = False

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 12)
        root.setSpacing(10)

        # preview + hex
        top = QHBoxLayout(); top.setSpacing(10)
        self.preview = QFrame(); self.preview.setFixedSize(64, 48)
        self.preview.setObjectName("swatchPreview")
        top.addWidget(self.preview)
        hex_col = QVBoxLayout(); hex_col.setSpacing(2)
        hex_label = QLabel("HEX"); hex_label.setObjectName("dim")
        self.hex_edit = QLineEdit()
        self.hex_edit.setMaxLength(9)
        self.hex_edit.editingFinished.connect(self._from_hex)
        hex_col.addWidget(hex_label); hex_col.addWidget(self.hex_edit)
        top.addLayout(hex_col, 1)
        root.addLayout(top)

        self.wheel = ColorWheel()
        self.wheel.colorChanged.connect(self._from_wheel)
        root.addWidget(self.wheel, 1)

        # channel models
        self.tabs = QTabWidget()
        self.tabs.addTab(self._rgb_tab(), "RGB")
        self.tabs.addTab(self._hsl_tab(), "HSL")
        self.tabs.addTab(self._palette_tab(), "Palettes")
        root.addWidget(self.tabs)

        # alpha
        self.alpha_row = QWidget()
        arow = QHBoxLayout(self.alpha_row)
        arow.setContentsMargins(0, 0, 0, 0); arow.setSpacing(8)
        alabel = QLabel("Alpha"); alabel.setObjectName("dim")
        self.alpha = QSlider(Qt.Orientation.Horizontal)
        self.alpha.setRange(0, 255); self.alpha.setValue(self._color.alpha())
        self.alpha.valueChanged.connect(self._from_alpha)
        self.alpha_value = QLabel("255"); self.alpha_value.setObjectName("dim")
        arow.addWidget(alabel); arow.addWidget(self.alpha, 1); arow.addWidget(self.alpha_value)
        self.alpha_row.setVisible(allow_alpha)
        root.addWidget(self.alpha_row)

        # recent
        self.recent_row = QHBoxLayout(); self.recent_row.setSpacing(4)
        recent_label = QLabel("Recent"); recent_label.setObjectName("dim")
        root.addWidget(recent_label)
        recent_holder = QWidget(); recent_holder.setLayout(self.recent_row)
        root.addWidget(recent_holder)
        self._build_recent()

        # buttons
        buttons = QHBoxLayout(); buttons.addStretch(1)
        cancel = QPushButton("Cancel"); cancel.setObjectName("ghost")
        cancel.clicked.connect(self.reject)
        ok = QPushButton("Use colour"); ok.setObjectName("primary")
        ok.clicked.connect(self._accept)
        buttons.addWidget(cancel); buttons.addWidget(ok)
        root.addLayout(buttons)

        self.restyle()
        self._sync_all(from_widget=None)

    # --- tabs -----------------------------------------------------------------
    def _rgb_tab(self):
        w = QWidget(); grid = QGridLayout(w)
        grid.setContentsMargins(8, 8, 8, 8); grid.setSpacing(6)
        self.rgb_spins = {}
        for row, name in enumerate(("R", "G", "B")):
            label = QLabel(name); label.setObjectName("dim")
            slider = QSlider(Qt.Orientation.Horizontal); slider.setRange(0, 255)
            spin = QSpinBox(); spin.setRange(0, 255)
            slider.valueChanged.connect(spin.setValue)
            spin.valueChanged.connect(slider.setValue)
            spin.valueChanged.connect(self._from_rgb)
            grid.addWidget(label, row, 0)
            grid.addWidget(slider, row, 1)
            grid.addWidget(spin, row, 2)
            self.rgb_spins[name] = spin
        return w

    def _hsl_tab(self):
        w = QWidget(); grid = QGridLayout(w)
        grid.setContentsMargins(8, 8, 8, 8); grid.setSpacing(6)
        self.hsl_spins = {}
        for row, (name, top) in enumerate((("H", 359), ("S", 255), ("L", 255))):
            label = QLabel(name); label.setObjectName("dim")
            slider = QSlider(Qt.Orientation.Horizontal); slider.setRange(0, top)
            spin = QSpinBox(); spin.setRange(0, top)
            slider.valueChanged.connect(spin.setValue)
            spin.valueChanged.connect(slider.setValue)
            spin.valueChanged.connect(self._from_hsl)
            grid.addWidget(label, row, 0)
            grid.addWidget(slider, row, 1)
            grid.addWidget(spin, row, 2)
            self.hsl_spins[name] = spin
        return w

    def _palette_tab(self):
        w = QWidget(); outer = QVBoxLayout(w)
        outer.setContentsMargins(8, 8, 8, 8); outer.setSpacing(6)
        for name, colours in PALETTES.items():
            label = QLabel(name); label.setObjectName("dim")
            outer.addWidget(label)
            row = QHBoxLayout(); row.setSpacing(3)
            for hex_value in colours:
                row.addWidget(self._swatch(hex_value))
            row.addStretch(1)
            holder = QWidget(); holder.setLayout(row)
            outer.addWidget(holder)
        outer.addStretch(1)
        return w

    def _swatch(self, hex_value, size=22):
        button = QPushButton()
        button.setFixedSize(size, size)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setToolTip(hex_value)
        button.setStyleSheet(
            f"background: {hex_value}; border: 1px solid {theme.BORDER_DARK};"
            f" border-radius: 3px;")
        button.clicked.connect(lambda _=False, h=hex_value: self.set_color(QColor(h)))
        return button

    def _build_recent(self):
        while self.recent_row.count():
            item = self.recent_row.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for hex_value in _RECENT[-12:]:
            self.recent_row.addWidget(self._swatch(hex_value, 18))
        self.recent_row.addStretch(1)

    # --- syncing --------------------------------------------------------------
    def set_color(self, color: QColor):
        if color.isValid():
            alpha = self._color.alpha()
            self._color = QColor(color)
            if not self._allow_alpha:
                self._color.setAlpha(255)
            elif color.alpha() == 255:
                self._color.setAlpha(alpha)
            self._sync_all(from_widget=None)

    def color(self):
        return QColor(self._color)

    def _sync_all(self, from_widget):
        if self._syncing:
            return
        self._syncing = True
        c = self._color
        if from_widget != "wheel":
            self.wheel.set_color(c)
        if from_widget != "hex":
            self.hex_edit.setText(
                c.name(QColor.NameFormat.HexArgb) if self._allow_alpha and c.alpha() < 255
                else c.name())
        if from_widget != "rgb":
            for name, value in zip("RGB", (c.red(), c.green(), c.blue())):
                self.rgb_spins[name].setValue(value)
        if from_widget != "hsl":
            self.hsl_spins["H"].setValue(max(0, c.hslHue()))
            self.hsl_spins["S"].setValue(c.hslSaturation())
            self.hsl_spins["L"].setValue(c.lightness())
        if from_widget != "alpha":
            self.alpha.setValue(c.alpha())
        self.alpha_value.setText(str(c.alpha()))
        self.preview.setStyleSheet(
            f"#swatchPreview {{ background: {c.name()}; "
            f"border: 1px solid {theme.BORDER_DARK}; border-radius: 4px; }}")
        self._syncing = False

    def _from_wheel(self, color):
        color.setAlpha(self._color.alpha())
        self._color = color
        self._sync_all("wheel")

    def _from_hex(self):
        text = self.hex_edit.text().strip()
        if not text.startswith("#"):
            text = "#" + text
        color = QColor(text)
        if color.isValid():
            self._color = color
            self._sync_all("hex")
        else:
            self._sync_all(None)

    def _from_rgb(self):
        if self._syncing:
            return
        self._color = QColor(self.rgb_spins["R"].value(),
                             self.rgb_spins["G"].value(),
                             self.rgb_spins["B"].value(),
                             self._color.alpha())
        self._sync_all("rgb")

    def _from_hsl(self):
        if self._syncing:
            return
        color = QColor()
        color.setHsl(self.hsl_spins["H"].value(), self.hsl_spins["S"].value(),
                     self.hsl_spins["L"].value(), self._color.alpha())
        self._color = color
        self._sync_all("hsl")

    def _from_alpha(self, value):
        if self._syncing:
            return
        self._color.setAlpha(value)
        self._sync_all("alpha")

    def _accept(self):
        hex_value = self._color.name()
        if hex_value in _RECENT:
            _RECENT.remove(hex_value)
        _RECENT.append(hex_value)
        self.colorPicked.emit(QColor(self._color))
        self.accept()

    # --- convenience ----------------------------------------------------------
    @staticmethod
    def get_color(initial="#5B6BE8", parent=None, allow_alpha=True):
        dialog = ColorPickerDialog(initial, allow_alpha, parent)
        if dialog.exec():
            return dialog.color()
        return None

    def restyle(self):
        self.setStyleSheet(f"""
            #ColorPicker {{ background: {theme.SIDE_PANEL}; }}
            QLabel {{ color: {theme.INK_ON_DARK}; font-size: 12px; }}
            QLabel#dim {{ color: {theme.INK_ON_DARK_MUTED}; font-size: 11px; }}
            QLineEdit, QSpinBox {{ background: {theme.ACTIVITY_BAR};
                color: {theme.INK_ON_DARK}; border: 1px solid {theme.BORDER_DARK};
                border-radius: {theme.RADIUS_SM}px; padding: 4px 8px;
                font-family: monospace; }}
            QLineEdit:focus, QSpinBox:focus {{ border: 1px solid {theme.ACCENT}; }}
            QTabWidget::pane {{ border: 1px solid {theme.BORDER_DARK};
                border-radius: {theme.RADIUS_SM}px; background: {theme.ACTIVITY_BAR}; }}
            QTabBar::tab {{ background: transparent; color: {theme.INK_ON_DARK_MUTED};
                padding: 6px 14px; border-bottom: 2px solid transparent; }}
            QTabBar::tab:selected {{ color: {theme.INK_ON_DARK};
                border-bottom: 2px solid {theme.ACCENT}; }}
            QPushButton#primary {{ background: {theme.ACCENT}; color: {theme.INK_ON_ACCENT};
                border: none; border-radius: {theme.RADIUS_SM}px; padding: 7px 18px;
                font-weight: 600; }}
            QPushButton#ghost {{ background: transparent; color: {theme.INK_ON_DARK};
                border: 1px solid {theme.BORDER_DARK}; border-radius: {theme.RADIUS_SM}px;
                padding: 7px 14px; }}
        """)

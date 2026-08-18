"""Selection overlay: the dashed accent outline + eight resize handles drawn over
a selected canvas widget. Design-time decoration only; legitimately a transient
overlay, not a persistent panel."""
from PySide6.QtCore import Qt, QRect
from PySide6.QtGui import QPainter, QPen, QColor
from PySide6.QtWidgets import QWidget

from .. import theme


class ResizeHandle(QWidget):
    _CURSORS = {
        "nw": Qt.CursorShape.SizeFDiagCursor, "se": Qt.CursorShape.SizeFDiagCursor,
        "ne": Qt.CursorShape.SizeBDiagCursor, "sw": Qt.CursorShape.SizeBDiagCursor,
        "n": Qt.CursorShape.SizeVerCursor, "s": Qt.CursorShape.SizeVerCursor,
        "e": Qt.CursorShape.SizeHorCursor, "w": Qt.CursorShape.SizeHorCursor,
    }

    def __init__(self, overlay, role):
        super().__init__(overlay)
        self.overlay = overlay
        self.role = role
        self.setFixedSize(theme.HANDLE_SIZE, theme.HANDLE_SIZE)
        self.setCursor(self._CURSORS[role])
        self._dragging = False
        self._start_geo = None
        self._start_pos = None

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor(theme.ACCENT))
        painter.setPen(QPen(QColor("#FFFFFF"), 1))
        painter.drawRect(0, 0, self.width() - 1, self.height() - 1)

    def mousePressEvent(self, event):
        target = self.overlay.canvas.selected_qwidget
        if target is None:
            return
        self._dragging = True
        self._start_geo = QRect(target.geometry())
        self._start_pos = event.globalPosition().toPoint()

    def mouseMoveEvent(self, event):
        if not self._dragging:
            return
        target = self.overlay.canvas.selected_qwidget
        if target is None:
            return
        delta = event.globalPosition().toPoint() - self._start_pos
        geo = QRect(self._start_geo)
        if "n" in self.role:
            geo.setTop(geo.top() + delta.y())
        if "s" in self.role:
            geo.setBottom(geo.bottom() + delta.y())
        if "w" in self.role:
            geo.setLeft(geo.left() + delta.x())
        if "e" in self.role:
            geo.setRight(geo.right() + delta.x())
        if geo.width() < 24:
            geo.setWidth(24)
        if geo.height() < 20:
            geo.setHeight(20)
        canvas = self.overlay.canvas
        geo.setLeft(canvas.snap(geo.left())); geo.setTop(canvas.snap(geo.top()))
        geo.setRight(canvas.snap(geo.right())); geo.setBottom(canvas.snap(geo.bottom()))
        target.setGeometry(geo)
        self.overlay.canvas.commit_geometry(target)
        self.overlay.canvas.sync_overlay()
        self.overlay.canvas.popover_follow()

    def mouseReleaseEvent(self, event):
        self._dragging = False


class SelectionOverlay(QWidget):
    ROLES = ("nw", "n", "ne", "e", "se", "s", "sw", "w")

    def __init__(self, canvas):
        super().__init__(canvas)
        self.canvas = canvas
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.handles = {role: ResizeHandle(self, role) for role in self.ROLES}
        for h in self.handles.values():
            h.show()
        self.hide()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setPen(QPen(QColor(theme.ACCENT), 1, Qt.PenStyle.DashLine))
        painter.drawRect(0, 0, self.width() - 1, self.height() - 1)

    def follow(self, widget):
        self.setGeometry(widget.geometry())
        self._layout_handles()
        self.show()
        self.raise_()

    def _layout_handles(self):
        w, h, hs = self.width(), self.height(), theme.HANDLE_SIZE
        positions = {
            "nw": (0, 0), "n": (w // 2 - hs // 2, 0), "ne": (w - hs, 0),
            "e": (w - hs, h // 2 - hs // 2), "se": (w - hs, h - hs),
            "s": (w // 2 - hs // 2, h - hs), "sw": (0, h - hs),
            "w": (0, h // 2 - hs // 2),
        }
        for role, (x, y) in positions.items():
            self.handles[role].move(x, y)

"""
DesignCanvas hosts live QWidgets that render the DesignPage model (spec §2.1).
Each live widget is paired with its DesignWidget record; dragging or resizing a
live widget commits back onto that record, so the model stays the single source
of truth for codegen and saving.

The design-mode event filter (§2.1) intercepts mouse events on hosted widgets so
a click selects/drags instead of firing the widget's real behaviour.
"""
from PySide6.QtCore import Qt, QObject, QEvent, Signal, QPoint
from PySide6.QtGui import QPainter, QPen, QColor, QAction
from PySide6.QtWidgets import QWidget, QMenu

from .. import theme
from .selection import SelectionOverlay
from ..core.model import DesignPage, DesignWidget, unique_object_name
from ..core import app_theme as app_theme_mod
from ..components import factory


def _default_width(component):
    role = getattr(component, "style_role", "label")
    return {"dial": 56, "avatar": 44, "badge": 64, "divider": 200, "image": 160,
            "card": 220, "panel": 220, "group": 220, "tabs": 240, "list": 200,
            "tree": 200, "table": 260, "scroll": 200, "appbar": 320,
            "sidebar": 140, "statusbar": 320, "button_icon": 36,
            "title": 220, "progress": 180}.get(role, 150)


def _default_height(component):
    role = getattr(component, "style_role", "label")
    return {"dial": 56, "avatar": 44, "badge": 22, "divider": 2, "image": 100,
            "card": 120, "panel": 120, "group": 120, "tabs": 140, "list": 120,
            "tree": 120, "table": 140, "scroll": 120, "appbar": 48,
            "sidebar": 200, "statusbar": 28, "button_icon": 36,
            "title": 36, "subtitle": 28, "progress": 10, "text_area": 90}.get(role, 32)


class DesignModeFilter(QObject):
    def __init__(self, canvas):
        super().__init__(canvas)
        self.canvas = canvas
        self._drag_offset = None

    def eventFilter(self, watched, event):
        et = event.type()
        if et == QEvent.Type.MouseButtonPress:
            if event.button() == Qt.MouseButton.RightButton:
                self.canvas.select_qwidget(watched)
                self.canvas.show_context_menu(event.globalPosition().toPoint())
                return True
            self.canvas.select_qwidget(watched)
            self._drag_offset = event.position().toPoint()
            return True
        elif et == QEvent.Type.MouseMove:
            if self._drag_offset is not None and (event.buttons() & Qt.MouseButton.LeftButton):
                delta = event.position().toPoint() - self._drag_offset
                target = watched.pos() + delta
                nx, ny = self.canvas.snap(target.x()), self.canvas.snap(target.y())
                dw = self.canvas._model_by_live.get(id(watched))
                if dw is not None:
                    dw.x, dw.y = nx, ny
                    gx, gy, ax, ay = self.canvas.alignment_guides_for(dw)
                    nx, ny = ax, ay
                    self.canvas.set_guides(gx, gy)
                watched.move(nx, ny)
                self.canvas.commit_geometry(watched)
                self.canvas.sync_overlay()
                self.canvas.popover_follow()
            return True
        elif et == QEvent.Type.MouseButtonRelease:
            self._drag_offset = None
            self.canvas.clear_guides()
            return True
        return False


class DesignCanvas(QWidget):
    selectionChanged = Signal(object)   # emits the selected DesignWidget, or None
    pageChanged = Signal(object)        # emits the newly-loaded DesignPage
    modelChanged = Signal()             # emits when widgets added/removed (for layers panel)
    geometryCommitted = Signal(object)  # emits the DesignWidget after a move/resize
    # the window installs richer, component-aware menus (spec §29); these hooks
    # keep the canvas ignorant of what's in them
    widgetMenuRequested = Signal(object, object)   # DesignWidget, global QPoint
    canvasMenuRequested = Signal(object)           # global QPoint

    def __init__(self, registry, page: DesignPage = None, parent=None, undo_stack=None):
        super().__init__(parent)
        self.registry = registry
        self.asset_resolver = None      # set by the window; maps asset key -> abspath
        self.page = page or DesignPage(name="MainWindow")
        self.undo_stack = undo_stack
        self.setObjectName("DesignCanvas")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setMinimumSize(640, 480)

        self.app_theme = app_theme_mod.AppTheme()
        self.extra_stylesheets = []
        self._anim_keep = []   # keeps preview animations alive
        self._filter = DesignModeFilter(self)
        self.overlay = SelectionOverlay(self)
        self.show_grid = True
        self.show_guides = True
        self._guides = None          # (x, y) crosshair while dragging
        self.snap_enabled = False
        self.snap_size = theme.GRID_STEP
        self._cascade = 0          # offsets successive placements so they don't stack

        # live QWidget <-> DesignWidget pairing, both directions
        self._live_by_model = {}   # id(DesignWidget) -> QWidget
        self._model_by_live = {}   # id(QWidget) -> DesignWidget
        self.selected_qwidget = None
        self._popover = None

        self.apply_app_theme()
        self._render_existing_page()

    def restyle(self):
        self.apply_app_theme()
        # re-render every live widget so component QSS picks up new theme tokens
        for dw in list(self.page.widgets):
            self._rebuild_live(dw)
        self.update()

    # --- wiring ---------------------------------------------------------------
    def set_popover(self, popover):
        self._popover = popover

    @property
    def selected_model(self):
        if self.selected_qwidget is None:
            return None
        return self._model_by_live.get(id(self.selected_qwidget))

    # --- rendering the model --------------------------------------------------
    def _render_existing_page(self):
        for dw in self.page.widgets:
            self._spawn_live(dw)

    def load_page(self, page):
        """Rebind the canvas to a different page (multi-skeleton switch, spec §7)."""
        # tear down current live widgets
        for live in list(self._model_by_live.keys()):
            pass
        for dw in list(self.page.widgets):
            live = self._live_by_model.get(id(dw))
            if live is not None:
                live.deleteLater()
        self._live_by_model.clear()
        self._model_by_live.clear()
        self.select_qwidget(None)
        self.page = page
        self._cascade = 0
        self._render_existing_page()
        self.pageChanged.emit(page)

    def _richtext_fg(self) -> str:
        """The text colour rich-text math should be baked in, so it reads
        against whatever the app theme (light/dark) is currently set to -
        canvas and codegen must use the exact same colour (spec §13 fidelity;
        a mismatch here was the dark-mode math legibility bug)."""
        try:
            return self.app_theme.tokens().get("fg", "#1a1a1a")
        except Exception:
            return "#1a1a1a"

    def _spawn_live(self, dw: DesignWidget):
        component = self.registry.get(dw.component_id)
        if component is None:
            return None
        live = factory.instantiate(component, dw, self, self.asset_resolver, self._richtext_fg())
        live.installEventFilter(self._filter)
        live.show()
        self._live_by_model[id(dw)] = live
        self._model_by_live[id(live)] = dw
        return live

    def place_component(self, component_id, x=None, y=None):
        """Add a new component instance to the page and render it live. Undoable."""
        component = self.registry.get(component_id)
        if component is None:
            return None
        if x is None or y is None:
            # flow successive drops down the canvas, wrapping into a new column
            # when we run out of height - never stack on one spot
            margin, row_h, col_w = 40, 48, 220
            per_col = max(1, (self.height() - margin * 2) // row_h)
            col, row = divmod(self._cascade, per_col)
            x = margin + col * col_w
            y = margin + row * row_h
            self._cascade += 1
        dw = DesignWidget(
            component_id=component_id,
            object_name=unique_object_name(component_id),
            x=x, y=y,
            width=_default_width(component), height=_default_height(component),
            properties=component.default_properties(),
        )
        if self.undo_stack is not None:
            from ..core.undo import Command
            self.undo_stack.push(Command(
                label=f"Add {component.name}",
                do=lambda: self._add_widget(dw),
                undo=lambda: self._remove_widget(dw),
            ))
        else:
            self._add_widget(dw)
        return dw

    def _add_widget(self, dw: DesignWidget):
        if dw not in self.page.widgets:
            self.page.add(dw)
        live = self._spawn_live(dw)
        self.select_qwidget(live)
        self.modelChanged.emit()
        return live

    def _remove_widget(self, dw: DesignWidget):
        live = self._live_by_model.pop(id(dw), None)
        if live is not None:
            self._model_by_live.pop(id(live), None)
            live.deleteLater()
        self.page.remove(dw)
        if self.selected_model is dw or self.selected_qwidget is live:
            self.select_qwidget(None)
        self.modelChanged.emit()

    def select_by_model(self, dw: DesignWidget):
        """Select the live widget backing a model object (driven by the layers panel)."""
        live = self._live_by_model.get(id(dw)) if dw is not None else None
        self.select_qwidget(live)

    # --- selection ------------------------------------------------------------
    def select_qwidget(self, widget):
        self.selected_qwidget = widget
        if widget is None:
            self.overlay.hide()
        else:
            self.overlay.follow(widget)
        self.selectionChanged.emit(self.selected_model)

    def sync_overlay(self):
        if self.selected_qwidget is not None:
            self.overlay.follow(self.selected_qwidget)

    def popover_follow(self):
        if self._popover is not None and self.selected_qwidget is not None:
            self._popover.show_for(self.selected_model, self.selected_qwidget)

    # --- model sync -----------------------------------------------------------
    def commit_geometry(self, live_widget):
        dw = self._model_by_live.get(id(live_widget))
        if dw is None:
            return
        geo = live_widget.geometry()
        dw.x, dw.y, dw.width, dw.height = geo.x(), geo.y(), geo.width(), geo.height()
        self.geometryCommitted.emit(dw)

    def apply_property(self, prop_name, value):
        """Update the model, then rebuild the live widget from its template so the
        canvas exactly matches what codegen will emit (spec §11.2). Rebuilding
        (rather than a partial setter) is the only way to stay faithful for
        arbitrary property/QSS changes."""
        dw = self.selected_model
        if dw is None:
            return
        dw.properties[prop_name] = value
        self._rebuild_live(dw)
        self.sync_overlay()

    def _rebuild_live(self, dw: DesignWidget):
        """Replace the live widget for a model with a freshly-rendered one."""
        old = self._live_by_model.get(id(dw))
        was_selected = old is self.selected_qwidget
        if old is not None:
            self._model_by_live.pop(id(old), None)
            old.deleteLater()
        component = self.registry.get(dw.component_id)
        live = factory.rerender(component, dw, self, self.asset_resolver, self._richtext_fg())
        live.installEventFilter(self._filter)
        live.show()
        self._live_by_model[id(dw)] = live
        self._model_by_live[id(live)] = dw
        if was_selected:
            self.selected_qwidget = live
        return live

    def delete_selected(self):
        live = self.selected_qwidget
        if live is None:
            return
        dw = self._model_by_live.pop(id(live), None)
        if dw is not None:
            self._live_by_model.pop(id(dw), None)
            self.page.remove(dw)
        live.deleteLater()
        self.select_qwidget(None)
        self.modelChanged.emit()

    def duplicate_selected(self):
        dw = self.selected_model
        if dw is None:
            return
        clone = self.place_component(dw.component_id, dw.x + 16, dw.y + 16)
        if clone is not None:
            clone.properties = dict(dw.properties)
            clone.width, clone.height = dw.width, dw.height
            self._rebuild_live(clone)
            self.select_by_model(clone)


    # --- snapping -------------------------------------------------------------
    def snap(self, value):
        if not self.snap_enabled or self.snap_size <= 0:
            return int(value)
        return int(round(value / self.snap_size) * self.snap_size)

    def set_snap(self, enabled, size=None, grid_visible=None):
        self.snap_enabled = enabled
        if size:
            self.snap_size = max(1, int(size))
        if grid_visible is not None:
            self.show_grid = grid_visible
        self.update()

    # --- alignment ------------------------------------------------------------
    def align_selected(self, how):
        """Align the selected widget against the canvas bounds (single-selection
        alignment; multi-select alignment lands with marquee selection)."""
        dw = self.selected_model
        if dw is None:
            return
        if how == "left":
            dw.x = 0
        elif how == "right":
            dw.x = max(0, self.width() - dw.width)
        elif how == "center":
            dw.x = max(0, (self.width() - dw.width) // 2)
        elif how == "top":
            dw.y = 0
        elif how == "bottom":
            dw.y = max(0, self.height() - dw.height)
        elif how == "middle":
            dw.y = max(0, (self.height() - dw.height) // 2)
        live = self._live_by_model.get(id(dw))
        if live is not None:
            live.setGeometry(dw.x, dw.y, dw.width, dw.height)
        self.sync_overlay()
        self.popover_follow()
        self.geometryCommitted.emit(dw)

    def raise_selected(self):
        if self.selected_qwidget is not None:
            self.selected_qwidget.raise_()
            self.overlay.raise_()

    def lower_selected(self):
        if self.selected_qwidget is not None:
            self.selected_qwidget.lower()

    def set_geometry_of_selected(self, x, y, w, h):
        dw = self.selected_model
        if dw is None:
            return
        dw.x, dw.y, dw.width, dw.height = int(x), int(y), int(w), int(h)
        live = self._live_by_model.get(id(dw))
        if live is not None:
            live.setGeometry(dw.x, dw.y, dw.width, dw.height)
        self.sync_overlay()
        self.popover_follow()

    def set_style_override(self, dw, css):
        """Layer a per-widget QSS override on top of the theme (used by quick edit)."""
        live = self._live_by_model.get(id(dw))
        if live is None:
            return
        dw.properties["_style"] = css
        live.setStyleSheet(css)

    def set_radius_of_selected(self, radius):
        dw = self.selected_model
        if dw is None:
            return
        existing = dw.properties.get("_style", "")
        base = "; ".join(part for part in existing.split(";")
                         if part.strip() and "border-radius" not in part)
        css = (base + "; " if base else "") + f"border-radius: {int(radius)}px"
        self.set_style_override(dw, css)

    def set_color_of_selected(self, color):
        dw = self.selected_model
        if dw is None:
            return
        if "color" in dw.properties:
            self.apply_property("color", color)
            return
        existing = dw.properties.get("_style", "")
        base = "; ".join(part for part in existing.split(";")
                         if part.strip() and "background" not in part)
        css = (base + "; " if base else "") + f"background: {color}"
        self.set_style_override(dw, css)

    def set_opacity_of_selected(self, value):
        from PySide6.QtWidgets import QGraphicsOpacityEffect
        dw = self.selected_model
        live = self.selected_qwidget
        if dw is None or live is None:
            return
        dw.properties["opacity"] = value
        effect = QGraphicsOpacityEffect(live)
        effect.setOpacity(float(value))
        live.setGraphicsEffect(effect)

    # --- context menu ---------------------------------------------------------
    def show_context_menu(self, global_pos):
        dw = self.selected_model
        if dw is not None:
            self.widgetMenuRequested.emit(dw, global_pos)
        else:
            self.canvasMenuRequested.emit(global_pos)

    # --- painting -------------------------------------------------------------
    # --- app theme ------------------------------------------------------------
    def apply_app_theme(self, mode=None):
        """Style the canvas and every hosted widget exactly as the generated app
        will be styled - the canvas IS a preview of the real app."""
        if mode:
            self.app_theme.mode = mode
        qss = app_theme_mod.stylesheet(self.app_theme.mode, self.app_theme)
        tokens = self.app_theme.tokens()
        # user stylesheets layer on top of the theme, exactly as in generated code
        extra = "\n".join(self.extra_stylesheets or [])
        # canvas background comes from the app theme, not the editor theme
        self.setStyleSheet(
            f"#DesignCanvas {{ background: {tokens['bg']}; }}\n" + qss + "\n" + extra)
        self.update()
        self._refresh_richtext_widgets()

    def _refresh_richtext_widgets(self):
        """Math is baked into rich-text widgets as a raster image at build time,
        coloured for the app theme's ink - a plain stylesheet re-apply can't
        update an already-baked image, so rebuild any widget with a markdown
        property whenever the app theme changes."""
        if not self.page:
            return
        for dw in list(self.page.widgets):
            component = self.registry.get(dw.component_id)
            if component and any((p.type or "") == "markdown" for p in component.properties):
                self._rebuild_live(dw)

    def set_extra_stylesheets(self, sources):
        self.extra_stylesheets = list(sources or [])
        self.apply_app_theme()

    def preview_animation(self, object_name, animation):
        """Play an animation on the real canvas widget so the user sees it now."""
        from PySide6.QtCore import QPropertyAnimation, QEasingCurve, QPoint
        from PySide6.QtWidgets import QGraphicsOpacityEffect
        dw = next((w for w in self.page.widgets if w.object_name == object_name), None)
        live = self._live_by_model.get(id(dw)) if dw else None
        if live is None:
            return
        curve = getattr(QEasingCurve.Type, animation.easing, QEasingCurve.Type.OutCubic)
        geo = live.geometry()

        if animation.kind in ("fade_in", "fade_out"):
            effect = QGraphicsOpacityEffect(live)
            live.setGraphicsEffect(effect)
            anim = QPropertyAnimation(effect, b"opacity", self)
            start, end = (0.0, 1.0) if animation.kind == "fade_in" else (1.0, 0.0)
            anim.setStartValue(start); anim.setEndValue(end)
        elif animation.kind.startswith("slide"):
            from ..core.animations import _offset
            dx, dy = _offset(animation.kind, animation.distance)
            anim = QPropertyAnimation(live, b"geometry", self)
            anim.setStartValue(geo.translated(dx, dy)); anim.setEndValue(geo)
        elif animation.kind in ("pop", "pulse"):
            grow = 6 if animation.kind == "pulse" else 10
            anim = QPropertyAnimation(live, b"geometry", self)
            anim.setStartValue(geo)
            anim.setKeyValueAt(0.5, geo.adjusted(-grow, -grow, grow, grow))
            anim.setEndValue(geo)
        elif animation.kind == "shake":
            d = int(animation.distance) // 3 or 6
            pos = live.pos()
            anim = QPropertyAnimation(live, b"pos", self)
            anim.setStartValue(pos)
            anim.setKeyValueAt(0.25, pos + QPoint(d, 0))
            anim.setKeyValueAt(0.75, pos + QPoint(-d, 0))
            anim.setEndValue(pos)
        else:
            return

        anim.setDuration(int(animation.duration))
        anim.setEasingCurve(curve)
        anim.finished.connect(lambda: self.sync_overlay())
        self._anim_keep = [a for a in self._anim_keep if a.state() != a.State.Stopped]
        self._anim_keep.append(anim)
        anim.start()
        return anim

    def toggle_app_mode(self):
        self.app_theme.mode = self.app_theme.toggled()
        self.apply_app_theme()
        return self.app_theme.mode

    # --- painting -------------------------------------------------------------
    def paintEvent(self, event):
        """Grid and guides are painted on the canvas BACKGROUND, beneath every
        hosted widget - child widgets always paint after their parent, so the
        grid can never cover or glitch over the design."""
        painter = QPainter(self)
        tokens = self.app_theme.tokens()
        dark = self.app_theme.mode == "dark"
        line = QColor(255, 255, 255, 20) if dark else QColor(0, 0, 0, 20)
        major = QColor(255, 255, 255, 34) if dark else QColor(0, 0, 0, 34)

        if self.show_grid:
            step = self.snap_size if self.snap_enabled else theme.GRID_STEP
            step = max(4, int(step))
            painter.setPen(QPen(line, 1))
            x = 0
            while x < self.width():
                painter.setPen(QPen(major if (x // step) % 5 == 0 else line, 1))
                painter.drawLine(x, 0, x, self.height())
                x += step
            y = 0
            while y < self.height():
                painter.setPen(QPen(major if (y // step) % 5 == 0 else line, 1))
                painter.drawLine(0, y, self.width(), y)
                y += step

        # PowerPoint-style alignment guides while dragging
        if self.show_guides and self._guides is not None:
            gx, gy = self._guides
            accent = QColor(theme.ACCENT)
            accent.setAlpha(200)
            pen = QPen(accent, 1, Qt.PenStyle.DashLine)
            painter.setPen(pen)
            if gx is not None:
                painter.drawLine(gx, 0, gx, self.height())
            if gy is not None:
                painter.drawLine(0, gy, self.width(), gy)

    def set_guides(self, x=None, y=None):
        self._guides = None if (x is None and y is None) else (x, y)
        self.update()

    def clear_guides(self):
        self._guides = None
        self.update()

    def alignment_guides_for(self, dw):
        """Snap-lines against other widgets' edges/centres, PowerPoint-style.
        Returns (guide_x, guide_y, adjusted_x, adjusted_y)."""
        if not self.show_guides:
            return None, None, dw.x, dw.y
        tol = 6
        gx = gy = None
        ax, ay = dw.x, dw.y
        my_cx, my_cy = dw.x + dw.width // 2, dw.y + dw.height // 2
        # canvas centre lines
        targets_x = [(self.width() // 2, "centre")]
        targets_y = [(self.height() // 2, "centre")]
        for other in self.page.widgets:
            if other is dw:
                continue
            targets_x += [(other.x, "l"), (other.x + other.width, "r"),
                          (other.x + other.width // 2, "c")]
            targets_y += [(other.y, "t"), (other.y + other.height, "b"),
                          (other.y + other.height // 2, "m")]
        for tx, kind in targets_x:
            if abs(my_cx - tx) <= tol:
                gx = tx; ax = tx - dw.width // 2; break
            if abs(dw.x - tx) <= tol:
                gx = tx; ax = tx; break
        for ty, kind in targets_y:
            if abs(my_cy - ty) <= tol:
                gy = ty; ay = ty - dw.height // 2; break
            if abs(dw.y - ty) <= tol:
                gy = ty; ay = ty; break
        return gx, gy, ax, ay

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            self.select_qwidget(None)
            self.canvasMenuRequested.emit(event.globalPosition().toPoint())
            return
        self.select_qwidget(None)
        super().mousePressEvent(event)

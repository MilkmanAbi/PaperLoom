"""
Properties panel (spec §12.3), rebuilt as a Qt Designer-style grouped, collapsible,
filterable property editor - the fix for the "unstructured properties window"
complaint and the embarrassing QMessageBox Qt-property dump.

Layout, top to bottom:
    Object / Class header      what's selected and its Qt class
    Filter properties...       narrows every row across every group by name
    [ GEOMETRY ]               x / y / w / h
    [ APPEARANCE ]             opacity
    [ <COMPONENT> ]            the component's declared properties, typed
    [ ANIMATIONS ]             per-widget animations (embedded, was its own pane)
    [ QT PROPERTIES ]          the full live Qt property table, editable

Every editor is matched to its declared type, so an int property can never
receive "6056+" (spec §11.1). The panel is top-aligned and compact; the empty
state is a single top hint, not a label floating in the middle.
"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QSpinBox, QCheckBox, QPushButton, QScrollArea, QSlider, QPlainTextEdit
)

from ... import theme
from .collapsible import CollapsibleSection
from .qt_property_table import QtPropertyTable
from .color_picker import ColorPickerDialog


class AutoGrowTextEdit(QPlainTextEdit):
    """A text field that grows to fit what you type - starts at one line, wraps,
    and expands down to a few lines before it scrolls. A component's text is
    often a whole sentence; a one-line box that clips at "Hello, this app is--"
    is exactly the small thing that makes a builder feel cheap."""
    edited = Signal(str)

    MIN_LINES = 1
    MAX_LINES = 8

    def __init__(self, value="", parent=None):
        super().__init__(parent)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setTabChangesFocus(True)
        self.setPlainText(str(value or ""))
        self.textChanged.connect(self._on_change)
        self.document().documentLayout().documentSizeChanged.connect(
            lambda _=None: self._resize_to_fit())
        self._resize_to_fit()

    def _line_height(self):
        return int(self.fontMetrics().lineSpacing())

    def _resize_to_fit(self):
        doc_h = self.document().size().height()
        lines = max(self.MIN_LINES, min(self.MAX_LINES, int(doc_h) or 1))
        h = int(lines * self._line_height() + 12)
        if self.height() != h:
            self.setFixedHeight(h)

    def _on_change(self):
        self._resize_to_fit()
        self.edited.emit(self.toPlainText())

    def resizeEvent(self, event):
        # WidgetWidth wrapping only knows how many lines once we have a real
        # width, which we don't at construction - so recompute on resize too
        super().resizeEvent(event)
        self._resize_to_fit()

    def showEvent(self, event):
        super().showEvent(event)
        self._resize_to_fit()


class MarkdownField(QWidget):
    """Editor for a `markdown`-typed property: a real, directly-typable
    multi-line box (grows like any text field) for quick edits, plus a
    "Studio…" button for the full toolbar + live preview + selection tools.
    Markdown deserves an actual text box here, not a truncated one-line
    label - the Studio is for deep editing, not the only way to type."""
    editRequested = Signal()
    textEdited = Signal(str)

    def __init__(self, value=""):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        self._box = AutoGrowTextEdit(str(value or ""))
        self._box.MAX_LINES = 6
        self._box.edited.connect(self.textEdited.emit)
        lay.addWidget(self._box)
        studio_row = QHBoxLayout()
        studio_row.setContentsMargins(0, 0, 0, 0)
        studio_row.addStretch(1)
        studio = QPushButton("Studio…")
        studio.setObjectName("mdFieldEdit")
        studio.setToolTip("Open the Markdown Studio: toolbar, live preview, selection tools")
        studio.setCursor(Qt.CursorShape.PointingHandCursor)
        studio.clicked.connect(self.editRequested.emit)
        studio_row.addWidget(studio)
        lay.addLayout(studio_row)

    def set_value(self, value):
        text = str(value or "")
        if self._box.toPlainText() != text:
            self._box.setPlainText(text)


class ColorField(QWidget):
    """A swatch button + hex field; opens PaperLoom's colour picker on click."""
    changed = Signal(str)

    def __init__(self, value="#000000"):
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        self._swatch = QPushButton()
        self._swatch.setFixedSize(20, 20)
        self._swatch.setCursor(Qt.CursorShape.PointingHandCursor)
        self._swatch.clicked.connect(self._pick)
        self._hex = QLineEdit(value)
        self._hex.setMaxLength(9)
        self._hex.editingFinished.connect(self._on_hex)
        lay.addWidget(self._swatch)
        lay.addWidget(self._hex, 1)
        self.set_value(value)

    def set_value(self, value):
        self._value = str(value)
        self._hex.blockSignals(True)
        self._hex.setText(self._value)
        self._hex.blockSignals(False)
        self._swatch.setStyleSheet(
            f"background: {self._value}; border: 1px solid {theme.BORDER_DARK};"
            f" border-radius: {theme.RADIUS_SM}px;")

    def _pick(self):
        picked = ColorPickerDialog.get_color(self._value, self)
        if picked is not None:
            self.set_value(picked.name())
            self.changed.emit(self._value)

    def _on_hex(self):
        self.set_value(self._hex.text())
        self.changed.emit(self._value)


class AssetField(QWidget):
    """Editor for an `asset`-typed property: a thumbnail preview, the asset name,
    and Choose / Clear. Choosing opens the shared asset picker (import or pick an
    existing project asset). This is what lets media widgets and overlays actually
    take an uploaded image, instead of typing a key into a text box."""
    pickRequested = Signal()
    cleared = Signal()

    def __init__(self, value="", resolver=None):
        super().__init__()
        self._resolver = resolver
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        self._thumb = QLabel()
        self._thumb.setObjectName("assetThumb")
        self._thumb.setFixedSize(34, 26)
        self._thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._name = QLabel()
        self._name.setObjectName("assetName")
        choose = QPushButton("Choose…")
        choose.setObjectName("assetChoose")
        choose.setCursor(Qt.CursorShape.PointingHandCursor)
        choose.clicked.connect(self.pickRequested.emit)
        clear = QPushButton("×")
        clear.setObjectName("assetClear")
        clear.setFixedWidth(22)
        clear.setCursor(Qt.CursorShape.PointingHandCursor)
        clear.clicked.connect(self.cleared.emit)
        lay.addWidget(self._thumb)
        lay.addWidget(self._name, 1)
        lay.addWidget(choose)
        lay.addWidget(clear)
        self.set_value(value)

    def set_value(self, value):
        from PySide6.QtGui import QPixmap
        key = str(value or "")
        self._name.setText(key.rsplit("/", 1)[-1] if key else "none")
        pm = None
        if key and self._resolver is not None:
            path = self._resolver(key)
            if path:
                pm = QPixmap(path)
        if pm is not None and not pm.isNull():
            self._thumb.setPixmap(pm.scaled(
                34, 26, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation))
        else:
            self._thumb.setPixmap(QPixmap())
            self._thumb.setText("—")


class PropertiesPanel(QWidget):
    propertyChanged = Signal(str, object)         # declared name, value
    geometryChanged = Signal(int, int, int, int)
    opacityChanged = Signal(float)
    qtPropertyChanged = Signal(str, object)       # live Qt property name, value
    assetPickRequested = Signal(str)              # declared property name
    markdownEditRequested = Signal(str)           # declared property name

    def __init__(self, registry, parent=None):
        super().__init__(parent)
        self.registry = registry
        self._asset_resolver = None
        self.setObjectName("PropertiesPanel")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._model = None
        self._building = False
        self._editors = {}
        self._geo_fields = {}
        self._rows = []           # (label_lower, row_widget) for filtering
        self._animations = None
        self._qt_table = None
        self._qt_section = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # --- object / class header ---
        self._obj_head = QWidget(); self._obj_head.setObjectName("objHead")
        oh = QVBoxLayout(self._obj_head)
        oh.setContentsMargins(12, 10, 12, 8); oh.setSpacing(6)
        top = QHBoxLayout(); top.setSpacing(8)
        self._obj_name = QLabel("-"); self._obj_name.setObjectName("objName")
        self._obj_class = QLabel(""); self._obj_class.setObjectName("objClass")
        top.addWidget(self._obj_name); top.addStretch(1); top.addWidget(self._obj_class)
        oh.addLayout(top)
        self._filter = QLineEdit()
        self._filter.setPlaceholderText("Filter properties...")
        self._filter.setClearButtonEnabled(True)
        self._filter.textChanged.connect(self._apply_filter)
        oh.addWidget(self._filter)
        outer.addWidget(self._obj_head)

        # --- scrollable stack of collapsible sections ---
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._body = QWidget(); self._body.setObjectName("propBody")
        self._stack = QVBoxLayout(self._body)
        self._stack.setContentsMargins(0, 0, 0, 0)
        self._stack.setSpacing(0)
        self._stack.addStretch(1)
        self._scroll.setWidget(self._body)
        outer.addWidget(self._scroll, 1)

        # --- empty state (top-aligned, not floating in the middle) ---
        self._empty = QLabel("Select a widget on the canvas to edit its properties.")
        self._empty.setObjectName("empty")
        self._empty.setWordWrap(True)
        self._empty.setAlignment(Qt.AlignmentFlag.AlignTop)
        outer.addWidget(self._empty)

        self.restyle()
        self.set_target(None)

    # --- animations get folded in here rather than being their own pane -------
    def embed_animations(self, animations_panel):
        self._animations = animations_panel
        if hasattr(animations_panel, "_header"):
            animations_panel._header.hide()

    # --- section helpers ------------------------------------------------------
    def _new_section(self, title, expanded=True):
        sec = CollapsibleSection(title, expanded=expanded)
        self._stack.insertWidget(self._stack.count() - 1, sec)   # before stretch
        return sec

    def _add_row(self, section, label_text, editor):
        row = QWidget()
        rl = QHBoxLayout(row); rl.setContentsMargins(0, 0, 0, 0); rl.setSpacing(8)
        label = QLabel(label_text)
        label.setFixedWidth(66)
        label.setObjectName("propLabel")
        rl.addWidget(label)
        rl.addWidget(editor, 1)
        section.add(row)
        self._rows.append((label_text.lower(), row))
        return editor

    # --- (re)building for a target -------------------------------------------
    def set_target(self, model, live_widget=None):
        self._model = model
        self._clear()
        has = model is not None
        self._obj_head.setVisible(has)
        self._scroll.setVisible(has)
        self._empty.setVisible(not has)
        if not has:
            return

        component = self.registry.get(model.component_id)
        self._obj_name.setText(model.object_name)
        self._obj_class.setText(component.widget_class if component else "QWidget")
        self._building = True

        # geometry
        geo = self._new_section("Geometry")
        self._geo_fields = {}
        for key, val in (("x", model.x), ("y", model.y),
                         ("width", model.width), ("height", model.height)):
            sb = QSpinBox(); sb.setRange(-9999, 9999); sb.setValue(int(val))
            sb.valueChanged.connect(lambda _=0: self._emit_geometry())
            self._add_row(geo, key.capitalize(), sb)
            self._geo_fields[key] = sb

        # appearance / opacity
        appearance = self._new_section("Appearance")
        op_row = QWidget(); op_lay = QHBoxLayout(op_row)
        op_lay.setContentsMargins(0, 0, 0, 0); op_lay.setSpacing(8)
        oplbl = QLabel("Opacity"); oplbl.setFixedWidth(66); oplbl.setObjectName("propLabel")
        op_lay.addWidget(oplbl)
        self._opacity = QSlider(Qt.Orientation.Horizontal)
        self._opacity.setRange(0, 100)
        self._opacity.setValue(int(float(model.properties.get("opacity", 1.0)) * 100))
        self._opacity_label = QLabel(f"{self._opacity.value()}%")
        self._opacity_label.setObjectName("propLabel")
        self._opacity_label.setFixedWidth(38)
        self._opacity_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._opacity.valueChanged.connect(self._on_opacity)
        op_lay.addWidget(self._opacity, 1)
        op_lay.addWidget(self._opacity_label)
        appearance.add(op_row)
        self._rows.append(("opacity", op_row))

        # component-declared properties, typed
        if component and component.properties:
            sec = self._new_section(component.name)
            for spec in component.properties:
                value = model.properties.get(spec.name, spec.default)
                editor = self._editor_for(spec, value)
                self._add_row(sec, spec.name.replace("_", " ").capitalize(), editor)
                self._editors[spec.name] = editor

        # animations (embedded) - per-widget, collapsed by default
        if self._animations is not None:
            anim_sec = self._new_section("Animations", expanded=False)
            anim_sec.add(self._animations)
            self._animations.setVisible(True)

        # live Qt properties (the real editable table, was a QMessageBox)
        self._qt_table = QtPropertyTable()
        self._qt_table.propertyEdited.connect(self._on_qt_prop)
        self._qt_table.set_widget(live_widget)
        qt_sec = self._new_section("Qt properties", expanded=False)
        qt_sec.add(self._qt_table)
        self._qt_section = qt_sec

        self._building = False
        self._apply_filter(self._filter.text())

    def _clear(self):
        # reparent the shared animations panel out first so it survives the purge
        if self._animations is not None:
            self._animations.setParent(None)
        while self._stack.count() > 1:                 # keep the trailing stretch
            item = self._stack.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        self._editors.clear()
        self._geo_fields = {}
        self._rows = []
        self._qt_table = None
        self._qt_section = None

    def set_asset_resolver(self, fn):
        """fn(asset_key) -> absolute path, for asset-field thumbnails."""
        self._asset_resolver = fn

    def _editor_for(self, spec, value):
        ptype = (spec.type or "string").lower()
        if ptype == "markdown":
            w = MarkdownField(str(value or ""))
            w.editRequested.connect(lambda n=spec.name: self.markdownEditRequested.emit(n))
            w.textEdited.connect(lambda v, n=spec.name: self._emit(n, v))
            return w
        if ptype == "asset":
            w = AssetField(str(value or ""), self._asset_resolver)
            w.pickRequested.connect(lambda n=spec.name: self.assetPickRequested.emit(n))
            w.cleared.connect(lambda n=spec.name: self._emit(n, ""))
            return w
        if ptype in ("int", "number"):
            w = QSpinBox(); w.setRange(-99999, 99999)
            try:
                w.setValue(int(value))
            except (TypeError, ValueError):
                w.setValue(int(spec.default or 0))
            w.valueChanged.connect(lambda v, n=spec.name: self._emit(n, v))
            return w
        if ptype == "bool":
            w = QCheckBox()
            w.setChecked(str(value).lower() in ("true", "1", "yes", "on"))
            w.toggled.connect(lambda v, n=spec.name: self._emit(n, v))
            return w
        if ptype == "color":
            w = ColorField(str(value))
            w.changed.connect(lambda v, n=spec.name: self._emit(n, v))
            return w
        w = AutoGrowTextEdit(str(value))
        w.edited.connect(lambda v, n=spec.name: self._emit(n, v))
        return w

    # --- filtering ------------------------------------------------------------
    def _apply_filter(self, text):
        q = (text or "").strip().lower()
        for name, row in self._rows:
            row.setVisible(q in name)
        if self._qt_table is not None:
            self._qt_table.apply_filter(q)

    # --- emitting -------------------------------------------------------------
    def _emit(self, name, value):
        if not self._building:
            self.propertyChanged.emit(name, value)

    def _emit_geometry(self):
        if self._building:
            return
        g = self._geo_fields
        self.geometryChanged.emit(g["x"].value(), g["y"].value(),
                                  g["width"].value(), g["height"].value())

    def _on_opacity(self, v):
        self._opacity_label.setText(f"{v}%")
        if not self._building:
            self.opacityChanged.emit(v / 100.0)

    def _on_qt_prop(self, name, value):
        if not self._building:
            self.qtPropertyChanged.emit(name, value)

    def focus_qt_properties(self):
        """Open and reveal the Qt-properties section (right-click 'All Qt
        properties'), replacing the old message box."""
        if self._qt_section is not None:
            self._qt_section.set_expanded(True)
            self._scroll.ensureWidgetVisible(self._qt_section)
            self._filter.setFocus()

    def refresh_geometry(self, model):
        if self._model is not model or not self._geo_fields:
            return
        self._building = True
        for key, val in (("x", model.x), ("y", model.y),
                         ("width", model.width), ("height", model.height)):
            self._geo_fields[key].setValue(int(val))
        self._building = False

    def restyle(self):
        self.setStyleSheet(f"""
            #PropertiesPanel {{ background: {theme.SIDE_PANEL};
                                border-right: 1px solid {theme.BORDER_DARK}; }}
            #objHead {{ background: {theme.SIDE_PANEL};
                        border-bottom: 1px solid {theme.BORDER_DARK}; }}
            QLabel#objName {{ color: {theme.INK_ON_DARK}; font-size: 12px; font-weight: 700; }}
            QLabel#objClass {{ color: {theme.ACCENT}; font-size: 11px; font-weight: 600; }}
            QLabel#empty {{ color: {theme.INK_ON_DARK_FAINT}; font-size: 11px; padding: 16px 12px; }}
            QLabel#propLabel {{ color: {theme.INK_ON_DARK_MUTED}; font-size: 11px; }}
            QWidget#propBody {{ background: transparent; }}
            QScrollArea {{ background: transparent; border: none; }}
            QLineEdit {{ background: {theme.ACTIVITY_BAR}; color: {theme.INK_ON_DARK};
                border: 1px solid {theme.BORDER_DARK}; border-radius: {theme.RADIUS_SM}px;
                padding: 4px 8px; font-size: 11px; }}
            QLineEdit:focus {{ border: 1px solid {theme.ACCENT}; }}
            QPlainTextEdit {{ background: {theme.ACTIVITY_BAR}; color: {theme.INK_ON_DARK};
                border: 1px solid {theme.BORDER_DARK}; border-radius: {theme.RADIUS_SM}px;
                padding: 4px 8px; font-size: 11px; }}
            QPlainTextEdit:focus {{ border: 1px solid {theme.ACCENT}; }}
            QSpinBox {{ background: {theme.ACTIVITY_BAR}; color: {theme.INK_ON_DARK};
                border: 1px solid {theme.BORDER_DARK}; border-radius: {theme.RADIUS_SM}px;
                padding: 2px 6px; font-size: 11px; }}
            QSpinBox:focus {{ border: 1px solid {theme.ACCENT}; }}
            QSpinBox::up-button, QSpinBox::down-button {{ width: 14px; border: none;
                background: transparent; subcontrol-origin: border; }}
            QSpinBox::up-arrow {{ image: none; width: 0; height: 0;
                border-left: 3px solid transparent; border-right: 3px solid transparent;
                border-bottom: 4px solid {theme.INK_ON_DARK_MUTED}; }}
            QSpinBox::down-arrow {{ image: none; width: 0; height: 0;
                border-left: 3px solid transparent; border-right: 3px solid transparent;
                border-top: 4px solid {theme.INK_ON_DARK_MUTED}; }}
            QCheckBox {{ color: {theme.INK_ON_DARK}; }}
            QLabel#assetThumb {{ background: {theme.ACTIVITY_BAR};
                border: 1px solid {theme.BORDER_DARK}; border-radius: {theme.RADIUS_SM}px;
                color: {theme.INK_ON_DARK_FAINT}; }}
            QLabel#assetName {{ color: {theme.INK_ON_DARK}; font-size: 11px; }}
            QLabel#mdFieldPreview {{ color: {theme.INK_ON_DARK_MUTED}; font-size: 11px;
                font-style: italic; }}
            QPushButton#mdFieldEdit {{ background: {theme.ACCENT}; color: {theme.INK_ON_ACCENT};
                border: none; border-radius: {theme.RADIUS_SM}px; padding: 4px 12px;
                font-size: 11px; font-weight: 600; }}
            QPushButton#mdFieldEdit:hover {{ background: {theme.ACCENT_HOVER}; }}
            QPushButton#assetChoose {{ background: {theme.ACTIVITY_BAR}; color: {theme.INK_ON_DARK};
                border: 1px solid {theme.BORDER_DARK}; border-radius: {theme.RADIUS_SM}px;
                padding: 3px 8px; font-size: 11px; }}
            QPushButton#assetChoose:hover {{ border-color: {theme.ACCENT}; color: {theme.ACCENT}; }}
            QPushButton#assetClear {{ background: transparent; color: {theme.INK_ON_DARK_MUTED};
                border: 1px solid {theme.BORDER_DARK}; border-radius: {theme.RADIUS_SM}px;
                font-size: 13px; }}
            QPushButton#assetClear:hover {{ color: {theme.DANGER}; border-color: {theme.DANGER}; }}
            QSlider::groove:horizontal {{ height: 4px; background: {theme.ACTIVITY_BAR};
                border-radius: 2px; }}
            QSlider::handle:horizontal {{ background: {theme.ACCENT}; width: 12px;
                margin: -5px 0; border-radius: 6px; }}
            QSlider::sub-page:horizontal {{ background: {theme.ACCENT}; border-radius: 2px; }}
        """)
        for sec in self._body.findChildren(CollapsibleSection):
            sec.restyle()
        if self._qt_table is not None:
            self._qt_table.restyle()
        if self._animations is not None and hasattr(self._animations, "restyle"):
            self._animations.restyle()

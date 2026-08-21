"""
Turns a DesignWidget (model) into a live QWidget - by executing the component's
OWN PySide template, the exact code codegen emits (spec §11.2, §13).

This is the single-source-of-truth fix for WYSIWYG fidelity. There is no second
styling path: the canvas widget is literally the generated widget. A component's
appearance is defined once (in its template + meta.json); the canvas, the
library preview, and the generated app all render from that one definition, so
they cannot drift.

How it works: render the template fragment with the same sanitized context the
codegen backend builds, then exec it in a namespace where `self` is a tiny
attribute bag and `MainWindow` is the parent. The fragment does
`self.<name> = QWidget(MainWindow); self.<name>.setGeometry(...); ...` exactly as
in generated code; we pull the widget back out of the bag.
"""
from __future__ import annotations
from PySide6.QtWidgets import (
    QPushButton, QToolButton, QLineEdit, QPlainTextEdit, QTextEdit, QLabel,
    QCheckBox, QRadioButton, QComboBox, QSlider, QDial, QProgressBar, QWidget,
    QFrame, QGroupBox, QTabWidget, QScrollArea, QListWidget, QTreeWidget,
    QTableWidget, QSpinBox, QDoubleSpinBox, QDateEdit, QTimeEdit, QDateTimeEdit,
    QTextBrowser, QTreeWidgetItem,
)
from PySide6.QtCore import Qt, QDate, QTime
from PySide6.QtGui import QPixmap, QMovie

from .registry import Component
from ..core.model import DesignWidget
from ..core import sanitize

def _fit_pixmap(path, w, h, mode="contain"):
    """Scale a QPixmap according to CSS-like fit modes. Used by the image_frame
    template on the canvas (identity path via _asset) and in generated code."""
    pm = QPixmap(path) if isinstance(path, str) else path
    if pm.isNull():
        return pm
    if mode == "stretch":
        return pm.scaled(w, h, Qt.AspectRatioMode.IgnoreAspectRatio,
                         Qt.TransformationMode.SmoothTransformation)
    if mode == "cover":
        return pm.scaled(w, h, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                         Qt.TransformationMode.SmoothTransformation)
    if mode == "center":
        return pm  # original size, label alignment handles centring
    if mode == "scale-down":
        if pm.width() <= w and pm.height() <= h:
            return pm  # already fits, never upscale
        return pm.scaled(w, h, Qt.AspectRatioMode.KeepAspectRatio,
                         Qt.TransformationMode.SmoothTransformation)
    # default: contain
    return pm.scaled(w, h, Qt.AspectRatioMode.KeepAspectRatio,
                     Qt.TransformationMode.SmoothTransformation)


# the Qt classes a template might reference, provided to the exec namespace
_EXEC_GLOBALS = {
    "QPushButton": QPushButton, "QToolButton": QToolButton, "QLineEdit": QLineEdit,
    "QPlainTextEdit": QPlainTextEdit, "QTextEdit": QTextEdit, "QLabel": QLabel,
    "QCheckBox": QCheckBox, "QRadioButton": QRadioButton, "QComboBox": QComboBox,
    "QSlider": QSlider, "QDial": QDial, "QProgressBar": QProgressBar,
    "QWidget": QWidget, "QFrame": QFrame, "QGroupBox": QGroupBox,
    "QTabWidget": QTabWidget, "QScrollArea": QScrollArea, "QListWidget": QListWidget,
    "QTreeWidget": QTreeWidget, "QTableWidget": QTableWidget, "QSpinBox": QSpinBox,
    "QDoubleSpinBox": QDoubleSpinBox, "QDateEdit": QDateEdit, "QTimeEdit": QTimeEdit,
    "QDateTimeEdit": QDateTimeEdit, "QTextBrowser": QTextBrowser,
    "QTreeWidgetItem": QTreeWidgetItem, "QDate": QDate, "QTime": QTime,
    "Qt": Qt, "QPixmap": QPixmap, "QMovie": QMovie,
    # media templates wrap asset paths in _asset(); on the canvas the path is
    # already absolute, so here it's the identity. Generated code defines an
    # _asset() that resolves relative to the script, for CWD-independent loading.
    "_asset": (lambda p: p),
    "_fit_pixmap": _fit_pixmap,
}


class _AttrBag:
    """Stands in for `self` in the executed fragment: `self.<name> = w` just sets
    an attribute we can read back."""
    pass


def _context(component: Component, dw: DesignWidget, asset_resolver=None, fg: str = "#1a1a1a") -> dict:
    """Build the same sanitized, escaped context codegen uses, so the executed
    fragment is identical to what gets generated.

    `asset_resolver`, when given, maps an asset key to an absolute path on disk so
    a media widget renders its real image on the canvas (codegen resolves the same
    key to a project-relative path instead - same template, two path sources)."""
    ctx = {
        "name": dw.object_name,
        "x": int(dw.x), "y": int(dw.y),
        "width": int(dw.width), "height": int(dw.height),
    }
    specs = {p.name: p for p in component.properties}
    for prop_name, raw in dw.properties.items():
        spec = specs.get(prop_name)
        ptype = spec.type if spec else "string"
        default = spec.default if spec else None
        safe = sanitize.coerce(raw, ptype, default)
        if ptype == "string":
            safe = sanitize.escape_string(safe)
        ctx[prop_name] = safe
    # resolve an asset key to a concrete on-disk path for live rendering
    asset_key = dw.properties.get("asset")
    if asset_key and asset_resolver is not None:
        path = asset_resolver(asset_key)
        if path:
            ctx["asset_path"] = path.replace("\\", "/")
    # render any Markdown/LaTeX content to HTML (same conversion codegen uses,
    # same fg so canvas math ink matches whatever the app theme is set to -
    # a hardcoded fg here was the dark-mode math legibility bug from session 13)
    from ..core import richtext
    richtext.attach_to_context(component, dw, ctx, fg=fg)
    return ctx


def _render_widget(component: Component, dw: DesignWidget, parent, asset_resolver=None,
                    fg: str = "#1a1a1a") -> QWidget:
    fragment = component.render_pyside(_context(component, dw, asset_resolver, fg))
    bag = _AttrBag()
    namespace = dict(_EXEC_GLOBALS)
    namespace["self"] = bag
    namespace["MainWindow"] = parent
    try:
        exec(fragment, namespace)
    except Exception:
        # never let a bad fragment crash the canvas; fall back to a labelled box
        w = QLabel(f"[{component.id}]", parent)
        w.setObjectName(dw.object_name)
        w.setGeometry(dw.x, dw.y, dw.width, dw.height)
        return w
    widget = getattr(bag, dw.object_name, None)
    if widget is None:
        widget = QWidget(parent)
        widget.setObjectName(dw.object_name)
        widget.setGeometry(dw.x, dw.y, dw.width, dw.height)
    # apply any raw Qt-property overrides so the canvas matches generated code,
    # which emits the same setProperty() calls (spec §13 fidelity)
    qt_props = getattr(dw, "qt_props", None)
    if qt_props:
        from ..core import introspect
        for key, value in qt_props.items():
            introspect.write_property(widget, key, value)
    return widget


def instantiate(component: Component, design_widget: DesignWidget, parent, asset_resolver=None,
                 fg: str = "#1a1a1a"):
    return _render_widget(component, design_widget, parent, asset_resolver, fg)


def rerender(component: Component, design_widget: DesignWidget, parent, asset_resolver=None,
             fg: str = "#1a1a1a"):
    """Rebuild the live widget from scratch after a property change - the only
    honest way to guarantee the canvas matches generated output for arbitrary
    property/QSS changes (a partial setter path is exactly how drift starts)."""
    return _render_widget(component, design_widget, parent, asset_resolver, fg)

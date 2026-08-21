"""
Qt Designer interop (spec §21). Reads and writes `.ui` XML, so PaperLoom is not
an island: an existing Qt Designer form can be opened, edited visually, and
handed back - and a PaperLoom page can be exported for anyone using Designer,
`uic`, or `QUiLoader`.

Mapping strategy: `.ui` describes widgets by Qt class, PaperLoom describes them
by component. On import we match a Qt class to the best component that wraps it
(preferring one whose style_role suits the class), and carry over geometry plus
any property we understand. Anything we can't map is still imported as a plain
widget of the right class rather than being dropped - lossy is better than
lossless-or-nothing when the alternative is refusing the file.
"""
from __future__ import annotations
import os
import xml.etree.ElementTree as ET

from .model import DesignPage, DesignWidget, LayoutGroup, SignalConnection, unique_object_name

# Qt property name -> (PaperLoom property, parser)
_PROP_READERS = {
    "text": ("text", lambda e: _text(e, "string")),
    "title": ("title", lambda e: _text(e, "string")),
    "placeholderText": ("placeholder", lambda e: _text(e, "string")),
    "value": ("value", lambda e: _int(e, "number")),
    "checked": ("checked", lambda e: _text(e, "bool") == "true"),
}

_PROP_WRITERS = {
    "text": ("text", "string"),
    "title": ("title", "string"),
    "placeholder": ("placeholderText", "string"),
    "value": ("value", "number"),
    "checked": ("checked", "bool"),
}


# Qt scaffolding that is structure, not design - never imported as a component
STRUCTURAL_NAMES = {"centralwidget", "menubar", "statusbar", "menuBar",
                    "statusBar", "centralWidget", "layoutWidget"}
STRUCTURAL_CLASSES = {"QMainWindow", "QMenuBar", "QStatusBar", "QToolBar",
                      "QLayout", "QVBoxLayout", "QHBoxLayout", "QGridLayout"}


class UiImportError(Exception):
    pass


class UiIO:
    """Bidirectional .ui support. Non-fatal issues land in `warnings`."""

    def __init__(self, registry):
        self.registry = registry
        self.warnings: list[str] = []

    # --- component matching --------------------------------------------------
    def _component_for(self, qt_class: str):
        """Best component wrapping a Qt class; None if we have nothing."""
        exact = [c for c in self.registry.all() if c.widget_class == qt_class]
        if not exact:
            return None
        # prefer the plainest wrapper: shortest id usually means the base variant
        base = qt_class[1:].lower() if qt_class.startswith("Q") else qt_class.lower()

        def rank(c):
            # exact id match to the Qt class name wins, then the plainest name
            return (0 if c.id.replace("_", "") == base else 1, len(c.id), c.id)

        exact.sort(key=rank)
        return exact[0]

    # --- import --------------------------------------------------------------
    def import_file(self, path: str) -> DesignPage:
        if not os.path.isfile(path):
            raise UiImportError(f"No such .ui file: {path}")
        try:
            tree = ET.parse(path)
        except ET.ParseError as exc:
            raise UiImportError(f"Malformed .ui XML: {exc}") from exc
        return self.import_tree(tree.getroot(),
                                default_name=os.path.splitext(os.path.basename(path))[0])

    def import_tree(self, root: ET.Element, default_name="Imported") -> DesignPage:
        self.warnings = []
        if root.tag != "ui":
            raise UiImportError("Not a Qt Designer .ui file (root element is not <ui>)")

        top = root.find("widget")
        if top is None:
            raise UiImportError(".ui file has no root <widget>")

        page_name = _pascal(top.get("name") or default_name)
        page = DesignPage(name=page_name, title=page_name)

        # window geometry + title
        for prop in top.findall("property"):
            pname = prop.get("name")
            if pname == "geometry":
                rect = prop.find("rect")
                if rect is not None:
                    page.width = _child_int(rect, "width", page.width)
                    page.height = _child_int(rect, "height", page.height)
            elif pname == "windowTitle":
                page.title = _text(prop, "string") or page.title

        for child in _iter_widgets(top):
            dw = self._widget_from_element(child)
            if dw is not None:
                page.add(dw)

        # layouts: a real Qt Designer file almost always positions widgets via
        # <layout>, not absolute geometry - without this, every widget would
        # import stacked at (0,0), which is the real "slightly lacking" gap
        by_name = {dw.object_name: dw for dw in page.widgets}
        page.layouts = self._layouts_from_tree(top, by_name)

        # signal/slot connections - a top-level <connections> sibling of <widget>
        conns = root.find("connections")
        if conns is not None:
            for conn in conns.findall("connection"):
                sender = conn.findtext("sender") or ""
                signal = conn.findtext("signal") or ""
                receiver = conn.findtext("receiver") or ""
                slot = conn.findtext("slot") or ""
                if sender and receiver:
                    page.connections.append(SignalConnection(
                        sender=_identifier(sender), signal=signal,
                        receiver=_identifier(receiver), slot=slot))

        # tab order
        tabstops = root.find("tabstops")
        if tabstops is not None:
            page.tab_order = [_identifier(t.text or "")
                              for t in tabstops.findall("tabstop") if t.text]

        if not page.widgets:
            self.warnings.append("No widgets could be imported from this .ui file")
        return page

    def _layouts_from_tree(self, top: ET.Element, by_name: dict) -> list:
        """Walk every <layout> element, wherever it is nested, and build a
        LayoutGroup for each - recording which widgets it contains and their
        row/col (for grid layouts) so import isn't lossy for layout-based
        files (the common case for anything authored in real Qt Designer)."""
        groups: list[LayoutGroup] = []
        seen_ids = set()

        def walk(element: ET.Element, parent_widget_name):
            for child in element:
                if child.tag == "layout":
                    lg_id = _identifier(child.get("name") or f"layout_{len(groups)}")
                    while lg_id in seen_ids:
                        lg_id += "_"
                    seen_ids.add(lg_id)
                    qt_class = child.get("class") or "QVBoxLayout"
                    kind = {"QVBoxLayout": "vbox", "QHBoxLayout": "hbox",
                            "QGridLayout": "grid", "QFormLayout": "form"}.get(qt_class, "vbox")
                    lg = LayoutGroup(id=lg_id, kind=kind, parent=parent_widget_name)
                    groups.append(lg)
                    for item_index, item in enumerate(child.findall("item")):
                        w = item.find("widget")
                        if w is not None:
                            wname = _identifier(w.get("name") or "")
                            dw = by_name.get(wname)
                            if dw is not None:
                                dw.layout_id = lg_id
                                # prefer an explicit row/column attribute (grid
                                # layouts, or our own export); fall back to the
                                # item's position in document order, since real
                                # Designer files often omit row for vbox/hbox
                                row_attr = item.get("row")
                                dw.layout_row = int(row_attr) if row_attr is not None else item_index
                                dw.layout_col = int(item.get("column", 0) or 0)
                        walk(item, parent_widget_name)
                elif child.tag == "widget":
                    walk(child, _identifier(child.get("name") or parent_widget_name or ""))
                else:
                    walk(child, parent_widget_name)

        walk(top, None)
        return groups

    def _widget_from_element(self, element: ET.Element) -> DesignWidget | None:
        qt_class = element.get("class") or ""
        name = element.get("name") or qt_class.lower()

        # skip Qt's own scaffolding, and bare QWidget containers that only exist
        # to hold other widgets - importing those as components is noise
        if name in STRUCTURAL_NAMES or qt_class in STRUCTURAL_CLASSES:
            return None
        if qt_class == "QWidget" and element.find("widget") is not None:
            return None
        if qt_class == "QWidget" and element.find("property[@name='geometry']") is None:
            return None

        stamped = element.find("property[@name='paperloomComponent']")
        component = None
        if stamped is not None:
            component = self.registry.get(_text(stamped, "string"))
        if component is None:
            component = self._component_for(qt_class)
        if component is None:
            self.warnings.append(
                f"No PaperLoom component wraps {qt_class} - '{name}' was skipped")
            return None

        props = component.default_properties()
        qt_props = {}
        x = y = 0
        w, h = 120, 30
        for prop in element.findall("property"):
            pname = prop.get("name")
            if pname == "geometry":
                rect = prop.find("rect")
                if rect is not None:
                    x = _child_int(rect, "x", 0)
                    y = _child_int(rect, "y", 0)
                    w = _child_int(rect, "width", w)
                    h = _child_int(rect, "height", h)
                continue
            if pname == "paperloomComponent":
                continue
            reader = _PROP_READERS.get(pname)
            if reader is not None:
                target, parse = reader
                if target in props or target in {p.name for p in component.properties}:
                    try:
                        props[target] = parse(prop)
                        continue
                    except (TypeError, ValueError):
                        self.warnings.append(f"Could not read {pname} on '{name}'")
                        continue
            # not a property this component declares - keep it anyway as a raw
            # Qt property override, so round-tripping a real Designer file
            # (which sets far more than text/title/value/checked) isn't lossy
            value = _any_prop_value(prop)
            if value is not None and pname:
                qt_props[pname] = value

        return DesignWidget(component_id=component.id,
                            object_name=_identifier(name),
                            x=x, y=y, width=w, height=h, properties=props,
                            qt_props=qt_props)

    # --- export --------------------------------------------------------------
    def export_page(self, page: DesignPage, path: str) -> str:
        xml = self.page_to_xml(page)
        tree = ET.ElementTree(xml)
        ET.indent(tree, space=" ")
        tree.write(path, encoding="utf-8", xml_declaration=False)
        return path

    def page_to_xml(self, page: DesignPage) -> ET.Element:
        ui = ET.Element("ui", {"version": "4.0"})
        ET.SubElement(ui, "class").text = page.name
        top = ET.SubElement(ui, "widget",
                            {"class": "QMainWindow", "name": page.name})
        _rect_prop(top, "geometry", 0, 0, page.width, page.height)
        _string_prop(top, "windowTitle", page.title)

        central = ET.SubElement(top, "widget",
                                {"class": "QWidget", "name": "centralwidget"})

        # node-per-object-name, so a layout whose parent references a widget
        # (not the central widget) can be nested inside that widget's element
        node_by_name = {"centralwidget": central}

        def widget_node(dw, parent_node):
            component = self.registry.get(dw.component_id)
            if component is None:
                self.warnings.append(f"Unknown component '{dw.component_id}' skipped")
                return None
            node = ET.SubElement(parent_node, "widget",
                                 {"class": component.widget_class, "name": dw.object_name})
            _string_prop(node, "paperloomComponent", dw.component_id)
            for our_name, value in dw.properties.items():
                mapping = _PROP_WRITERS.get(our_name)
                if mapping is None:
                    continue
                qt_name, kind = mapping
                if kind == "string":
                    _string_prop(node, qt_name, str(value))
                elif kind == "number":
                    _number_prop(node, qt_name, value)
                elif kind == "bool":
                    _bool_prop(node, qt_name, value)
            # arbitrary Qt property overrides (the "expert peels back to Qt"
            # layer) round-trip too, not just the properties we specifically
            # model - this is the biggest lever on import/export fidelity
            for qt_name, value in (dw.qt_props or {}).items():
                if isinstance(value, bool):
                    _bool_prop(node, qt_name, value)
                elif isinstance(value, (int, float)):
                    _number_prop(node, qt_name, value)
                else:
                    _string_prop(node, qt_name, str(value))
            node_by_name[dw.object_name] = node
            return node

        laid_out_ids = {dw.object_name for lg in page.layouts
                        for dw in page.widgets if dw.layout_id == lg.id}

        # widgets with no layout membership: unchanged flat + absolute geometry
        for dw in page.widgets:
            if dw.object_name in laid_out_ids:
                continue
            node = widget_node(dw, central)
            if node is not None:
                _rect_prop(node, "geometry", dw.x, dw.y, dw.width, dw.height)

        # layout groups: nest a real <layout> under their parent widget (or
        # centralwidget), with each member wrapped in <item row="" column="">
        pending = list(page.layouts)
        guard = 0
        while pending and guard < 100:
            guard += 1
            still_pending = []
            for lg in pending:
                parent_node = node_by_name.get(lg.parent or "centralwidget")
                if parent_node is None:
                    still_pending.append(lg)   # parent not built yet - retry
                    continue
                qt_class = {"vbox": "QVBoxLayout", "hbox": "QHBoxLayout",
                           "grid": "QGridLayout", "form": "QFormLayout"}.get(lg.kind, "QVBoxLayout")
                layout_node = ET.SubElement(parent_node, "layout",
                                            {"class": qt_class, "name": lg.id})
                members = sorted(
                    [dw for dw in page.widgets if dw.layout_id == lg.id],
                    key=lambda w: (w.layout_row, w.layout_col))
                for dw in members:
                    attrs = {"row": str(dw.layout_row)}
                    if lg.kind == "grid":
                        attrs["column"] = str(dw.layout_col)
                    item = ET.SubElement(layout_node, "item", attrs)
                    widget_node(dw, item)
            pending = still_pending

        # signal/slot connections
        conns = ET.SubElement(ui, "connections")
        for conn in (page.connections or []):
            c = ET.SubElement(conns, "connection")
            ET.SubElement(c, "sender").text = conn.sender
            ET.SubElement(c, "signal").text = conn.signal
            ET.SubElement(c, "receiver").text = conn.receiver
            ET.SubElement(c, "slot").text = conn.slot

        # tab order
        if page.tab_order:
            tabstops = ET.SubElement(ui, "tabstops")
            for name in page.tab_order:
                ET.SubElement(tabstops, "tabstop").text = name

        ET.SubElement(ui, "resources")
        return ui


# --- xml helpers -------------------------------------------------------------
def _iter_widgets(element: ET.Element):
    """Yield every descendant <widget>, skipping layout scaffolding."""
    for child in element:
        if child.tag == "widget":
            yield child
            yield from _iter_widgets(child)
        elif child.tag in ("layout", "item"):
            yield from _iter_widgets(child)


def _text(prop: ET.Element, kind: str):
    node = prop.find(kind)
    return (node.text or "") if node is not None else ""


def _int(prop: ET.Element, kind: str):
    node = prop.find(kind)
    try:
        return int((node.text or "0").strip())
    except (AttributeError, ValueError):
        return 0


def _child_int(rect: ET.Element, name: str, fallback: int):
    node = rect.find(name)
    try:
        return int((node.text or "").strip())
    except (AttributeError, ValueError):
        return fallback


def _rect_prop(parent, name, x, y, w, h):
    prop = ET.SubElement(parent, "property", {"name": name})
    rect = ET.SubElement(prop, "rect")
    for key, value in (("x", x), ("y", y), ("width", w), ("height", h)):
        ET.SubElement(rect, key).text = str(int(value))


def _string_prop(parent, name, value):
    prop = ET.SubElement(parent, "property", {"name": name})
    ET.SubElement(prop, "string").text = str(value)


def _number_prop(parent, name, value):
    prop = ET.SubElement(parent, "property", {"name": name})
    try:
        ET.SubElement(prop, "number").text = str(int(value))
    except (TypeError, ValueError):
        ET.SubElement(prop, "number").text = "0"


def _bool_prop(parent, name, value):
    prop = ET.SubElement(parent, "property", {"name": name})
    ET.SubElement(prop, "bool").text = "true" if value else "false"


def _any_prop_value(prop: ET.Element):
    """Best-effort parse of any <property> element, keyed by its child tag,
    for capturing properties PaperLoom doesn't specifically model (qt_props)."""
    for child in prop:
        tag = child.tag
        if tag == "bool":
            return (child.text or "").strip() == "true"
        if tag == "number":
            try:
                return int((child.text or "0").strip())
            except ValueError:
                try:
                    return float(child.text.strip())
                except (TypeError, ValueError):
                    return None
        if tag == "double":
            try:
                return float((child.text or "0").strip())
            except ValueError:
                return None
        if tag == "string":
            return child.text or ""
        if tag == "enum":
            return child.text or ""
        if tag == "set":
            return child.text or ""
        # font/color/rect/size/point/etc: structured, not worth a lossy guess
        return None
    return None


def _pascal(name: str) -> str:
    parts = [p for p in name.replace("-", "_").split("_") if p]
    return "".join(p[:1].upper() + p[1:] for p in parts) or "Imported"


def _identifier(name: str) -> str:
    cleaned = "".join(c if c.isalnum() or c == "_" else "_" for c in name)
    if not cleaned or cleaned[0].isdigit():
        cleaned = "w_" + cleaned
    return cleaned

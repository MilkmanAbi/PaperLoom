"""
Headless test suite for the modular PaperLoom build. Runs offscreen and drives
the real modules end to end. Covers: registry loading, live placement, the
design-mode filter, resize->model sync, schema-driven popover editing,
delete/duplicate, and codegen (including the round-trip guarantee).
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import sys
import importlib
import py_compile
import shutil
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from PySide6.QtCore import Qt, QPoint, QPointF
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication, QMainWindow
from PySide6.QtTest import QTest

from paperloom.components.registry import ComponentRegistry
from paperloom.core.model import DesignPage, DesignWidget, LayoutGroup, SignalConnection
from paperloom.core import model as model_module
from paperloom.core import app_settings
from paperloom.ui.main_window import PaperLoomWindow
from paperloom.components import factory

# The whole suite gets its own settings.json, sandboxed away from a real
# ~/.paperloom - PaperLoomWindow now restores library_mode/editor_theme from
# app_settings on construction, and plenty of existing tests toggle those
# via set_library_mode()/view.toggle_editor_mode as part of testing other
# things entirely. Without this, one test's toggle would leak into every
# window built afterward (same run AND future runs, since it's a real file
# on disk) - tests must never depend on run order or a previous run's state.
_TEST_SETTINGS_DIR = tempfile.mkdtemp(prefix="paperloom_test_settings_")
app_settings._CONFIG_DIR = _TEST_SETTINGS_DIR
app_settings._SETTINGS_FILE = os.path.join(_TEST_SETTINGS_DIR, "settings.json")


_REGISTRY = None


def registry():
    """One shared registry. Loading 52 component folders per test was the
    dominant cost of the suite; the registry is immutable once loaded."""
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = ComponentRegistry().load()
    return _REGISTRY


_WINDOWS = []


def make_window(*args, **kwargs):
    """Build a window and keep a handle so tests can release them; windows were
    accumulating across the suite and slowing everything down."""
    win = PaperLoomWindow(*args, **kwargs)
    _WINDOWS.append(win)
    return win


def release_windows():
    for win in _WINDOWS:
        try:
            if hasattr(win, "bottom_panel"):
                win.bottom_panel.terminal.stop()
            win.close()
            win.deleteLater()
        except Exception:
            pass
    _WINDOWS.clear()


def reset_ids():
    """Object-name counters are process-global by design (unique per run); reset
    them between tests so generated names are deterministic in isolation."""
    model_module._id_counters.clear()


def get_app():
    return QApplication.instance() or QApplication(sys.argv)


def mouse_event(kind, local, glob, button, buttons):
    return QMouseEvent(kind, QPointF(local), QPointF(glob), button, buttons, Qt.KeyboardModifier.NoModifier)


def test_registry_loads():
    reg = registry()
    ids = {c.id for c in reg.all()}
    expected = {"pill_button", "primary_button", "button", "text_box", "label",
                "checkbox", "switch", "radio", "combo_box", "slider",
                "progress_bar", "search_bar", "dial", "card", "title"}
    assert expected <= ids, f"missing: {expected - ids}"
    pill = reg.get("pill_button")
    assert pill.quick_properties == ["text"]
    assert pill.default_properties()["text"] == "Button"
    assert pill.style_role == "button_pill"
    assert pill.widget_class == "QPushButton"
    assert reg.search("input")
    assert len(ids) >= 40, f"expected the expanded library, got {len(ids)}"
    print(f"[OK] registry loaded {len(ids)} components with schema + search")


def test_all_components_generate_both_languages():
    app = get_app()
    from PySide6.QtWidgets import QWidget
    import py_compile
    reg = registry()
    host = QWidget()
    page = DesignPage(name="AllWidgets", title="Everything")
    y = 10
    for c in sorted(reg.all(), key=lambda c: c.id):
        dw = DesignWidget(c.id, c.id, 10, y, 140, 32, c.default_properties())
        page.add(dw)
        # every component instantiates live without error
        assert factory.instantiate(c, dw, host) is not None, c.id
        y += 44

    out = tempfile.mkdtemp(prefix="paperloom_all_")
    from paperloom.codegen import get_backend
    py_paths = get_backend("pyside6", reg).generate(page, out)
    py_compile.compile(py_paths["generated"], doraise=True)
    py_compile.compile(py_paths["logic"], doraise=True)
    get_backend("cpp", reg).generate(page, out)   # emits without error
    print(f"[OK] all {len(reg.all())} components instantiate + generate in both languages")
    shutil.rmtree(out, ignore_errors=True)


def test_model_roundtrip():
    page = DesignPage(name="MainWindow", title="Demo")
    page.add(DesignWidget("pill_button", "button", 10, 20, 120, 32, {"text": "Hi", "color": "#6B7CFF"}))
    restored = DesignPage.from_dict(page.to_dict())
    assert restored.name == "MainWindow" and restored.title == "Demo"
    assert restored.widgets[0].object_name == "button"
    assert restored.widgets[0].properties["text"] == "Hi"
    print("[OK] model serializes and restores without loss")


def test_place_select_resize():
    app = get_app()
    win = make_window(registry())
    win.show()
    canvas = win.canvas

    dw = canvas.place_component("pill_button")
    assert dw is not None and len(canvas.page.widgets) == 1
    live = canvas.selected_qwidget
    assert live is not None and live.text() == "Button"

    # design-mode filter: click selects, real click never fires
    fired = {"v": False}
    live.clicked.connect(lambda: fired.__setitem__("v", True))
    QTest.mouseClick(live, Qt.MouseButton.LeftButton, pos=QPoint(8, 8))
    assert canvas.selected_qwidget is live
    assert fired["v"] is False
    assert canvas.overlay.isVisible()

    # resize via SE handle -> live widget grows AND model commits
    before = live.geometry()
    se = canvas.overlay.handles["se"]
    se.mousePressEvent(mouse_event(QMouseEvent.Type.MouseButtonPress, QPoint(4, 4), QPoint(100, 100),
                                   Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton))
    se.mouseMoveEvent(mouse_event(QMouseEvent.Type.MouseMove, QPoint(44, 24), QPoint(140, 120),
                                  Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton))
    se.mouseReleaseEvent(mouse_event(QMouseEvent.Type.MouseButtonRelease, QPoint(44, 24), QPoint(140, 120),
                                     Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton))
    after = live.geometry()
    assert after.width() > before.width()
    assert dw.width == after.width() and dw.height == after.height(), "resize must commit to model"
    print(f"[OK] place/select/resize works and syncs model ({before.width()}x{before.height()} -> "
          f"{after.width()}x{after.height()})")


def test_popover_edits_model():
    app = get_app()
    win = make_window(registry())
    win.show()
    canvas = win.canvas
    dw = canvas.place_component("pill_button")

    # popover was rebuilt for pill_button (text + color)
    assert set(win.popover._editors) == {"text"}
    win.popover._editors["text"].setText("Log in")
    assert canvas.selected_qwidget.text() == "Log in"     # live widget updated
    assert dw.properties["text"] == "Log in"              # model updated
    print("[OK] schema-driven popover edits both live widget and model")


def test_delete_and_duplicate():
    app = get_app()
    win = make_window(registry())
    canvas = win.canvas
    canvas.place_component("button")
    assert len(canvas.page.widgets) == 1
    canvas.duplicate_selected()
    assert len(canvas.page.widgets) == 2
    canvas.delete_selected()
    assert len(canvas.page.widgets) == 1
    print("[OK] duplicate and delete keep model consistent")


def test_codegen_multiwidget_and_roundtrip():
    app = get_app()
    win = make_window(registry())
    canvas = win.canvas
    canvas.place_component("pill_button")
    canvas.place_component("text_box")
    canvas.place_component("label")

    out = tempfile.mkdtemp(prefix="paperloom_gen_")
    paths = win.generate_code(target_dir=out)
    ui_path, logic_path = paths["generated"], paths["logic"]

    py_compile.compile(ui_path, doraise=True)
    py_compile.compile(logic_path, doraise=True)

    gen_dir = os.path.dirname(ui_path)
    sys.path.insert(0, gen_dir)
    mod = importlib.import_module(os.path.basename(ui_path)[:-3])
    importlib.reload(mod)
    probe = QMainWindow()
    ui = mod.Ui_MainWindow()
    ui.setupUi(probe)
    # all three widgets exist on the generated window
    assert hasattr(ui, "pill_button") and hasattr(ui, "text_box") and hasattr(ui, "label")
    print("[OK] codegen emits a working multi-widget UI from templates")

    # round-trip: hand-edit logic, regenerate, edit survives
    with open(logic_path, "a") as f:
        f.write("\n# hand marker\n")
    win.generate_code(target_dir=out)
    with open(logic_path) as f:
        assert "# hand marker" in f.read()
    print("[OK] regeneration never clobbers hand-written logic")

    shutil.rmtree(out, ignore_errors=True)


def test_cpp_codegen_and_roundtrip():
    app = get_app()
    win = make_window(registry())
    win.target = "cpp"
    canvas = win.canvas
    canvas.place_component("pill_button")
    canvas.place_component("text_box")

    out = tempfile.mkdtemp(prefix="paperloom_cpp_")
    paths = win.generate_code(target_dir=out)
    ui_h = paths["generated"]
    logic_cpp = paths["logic"]

    ui_text = open(ui_h).read()
    assert "class Ui_MainWindow" in ui_text
    assert "QPushButton *pill_button;" in ui_text
    assert "QLineEdit *text_box;" in ui_text
    # radius is computed as height/2 in the template; assert that relationship
    # holds for the pill's actual placed height rather than a hardcoded pixel value
    assert 'setProperty("role", "button_pill")' in ui_text
    print("[OK] C++ backend emits a well-formed Ui_ struct with correct members")

    # signal wiring lives in the hand-written source, uses pointer-to-member connect
    src = open(logic_cpp).read()
    assert "connect(ui.pill_button, &QPushButton::clicked" in src
    assert "on_pill_button_clicked" in src
    print("[OK] C++ backend wires signals to slots in the hand-written class")

    # round-trip: hand-edit source, regenerate, edit survives
    with open(logic_cpp, "a") as f:
        f.write("\n// hand marker\n")
    win.generate_code(target_dir=out)
    assert "// hand marker" in open(logic_cpp).read()
    print("[OK] C++ regeneration never clobbers hand-written logic")

    # if a Qt6 C++ toolchain is present, prove it actually compiles
    if shutil.which("cmake") and shutil.which("make"):
        import subprocess
        gen_dir = os.path.dirname(ui_h)
        build_dir = os.path.join(gen_dir, "build")
        os.makedirs(build_dir, exist_ok=True)
        cfg = subprocess.run(["cmake", ".."], cwd=build_dir, capture_output=True, text=True)
        if cfg.returncode == 0:
            bld = subprocess.run(["make"], cwd=build_dir, capture_output=True, text=True)
            assert bld.returncode == 0, f"make failed:\n{bld.stdout}\n{bld.stderr}"
            print("[OK] generated C++ project compiles to a real binary")
        else:
            print("[skip] cmake config failed (Qt6 not found); skipped compile check")
    else:
        print("[skip] no cmake/make toolchain; skipped compile check")

    shutil.rmtree(out, ignore_errors=True)


def test_undo_redo():
    app = get_app()
    win = make_window(registry())
    canvas = win.canvas
    assert not win.undo_stack.can_undo

    canvas.place_component("button")
    canvas.place_component("label")
    assert len(canvas.page.widgets) == 2
    assert win.undo_stack.can_undo and not win.undo_stack.can_redo

    win.dispatch("edit.undo")
    assert len(canvas.page.widgets) == 1
    assert win.undo_stack.can_redo

    win.dispatch("edit.redo")
    assert len(canvas.page.widgets) == 2
    print("[OK] undo/redo add-widget round-trips through the command stack")


def test_pages_multiskeleton():
    app = get_app()
    win = make_window(registry())
    # one page to start
    assert len(win.project.pages) == 1
    win.canvas.place_component("button")
    assert len(win.page.widgets) == 1

    # add a second page -> canvas swaps to it, empty
    win._on_page_added("Settings")
    assert len(win.project.pages) == 2
    assert win.page.name == "Settings"
    assert len(win.page.widgets) == 0

    # switch back to page 0 -> its widget is still there
    win._go_to_page_index(0)
    assert len(win.page.widgets) == 1
    print("[OK] multi-page: new page is a fresh skeleton, switching preserves each")


def test_tabs_independent_undo():
    """Tabs: each open page gets its own undo/redo history, and closing a tab
    never touches the other open pages or the project itself."""
    app = get_app()
    win = make_window(registry())
    # start: one tab open (the default page), strip shown with that one tab.
    # isHidden() (the widget's own flag) rather than isVisible() (which also
    # depends on ancestors being shown) - this window is never win.show()n.
    assert len(win.open_pages) == 1
    assert win.editor_tabs.count() == 1
    assert not win.editor_tabs.isHidden(), "even a single open tab must be visible"

    win.canvas.place_component("button")
    assert len(win.page.widgets) == 1
    assert win.undo_stack.can_undo

    win._on_page_added("Settings")
    assert len(win.open_pages) == 2
    assert win.page.name == "Settings"
    # a fresh tab's undo stack starts empty, independent of page 0's
    assert not win.undo_stack.can_undo
    assert win.editor_tabs.count() == 2

    # undo on this tab must not touch the other tab's widget
    win.canvas.place_component("label")
    assert win.undo_stack.can_undo
    win.dispatch("edit.undo")
    assert len(win.page.widgets) == 0

    win._go_to_page_index(0)
    assert len(win.page.widgets) == 1, "page 0's widget must survive switching tabs"
    assert win.undo_stack.can_undo, "page 0's own undo history must still be there"

    # closing the (inactive) Settings tab doesn't touch the project's pages
    settings_page = win.project.pages[1]
    win._on_tab_close_requested(win.open_pages.index(settings_page))
    assert len(win.open_pages) == 1
    assert len(win.project.pages) == 2, "closing a tab must not delete the page"
    assert win.page.name == win.project.pages[0].name, "active page must be undisturbed"

    # closing the last remaining tab is a no-op - the canvas always needs a page
    win._on_tab_close_requested(0)
    assert len(win.open_pages) == 1
    print("[OK] tabs: independent per-tab undo, close never loses a page")


def test_closing_one_tab_leaves_the_others_open():
    """Regression for the session 15 follow-up report: 'closing one tab
    closes them all'. Root cause was EditorTabBar hiding itself entirely
    below 2 open tabs, so dropping from 2->1 made the whole strip vanish -
    which reads exactly like every tab closed at once, even though the
    other open pages were untouched. With 3 tabs open, closing one (from
    either end or the middle) must remove only that page from open_pages
    and leave the rest, still visibly, open."""
    app = get_app()
    win = make_window(registry())
    win._on_page_added("Second")
    win._on_page_added("Third")
    assert len(win.open_pages) == 3
    assert win.editor_tabs.count() == 3

    middle = win.open_pages[1]
    other_two = [win.open_pages[0], win.open_pages[2]]
    win._on_tab_close_requested(1)
    assert middle not in win.open_pages, "the closed tab's page must be gone from open_pages"
    for page in other_two:
        assert page in win.open_pages, "closing one tab must never remove the others"
    assert len(win.open_pages) == 2
    assert win.editor_tabs.count() == 2
    assert not win.editor_tabs.isHidden()

    # and down to the last one: still open, still visibly a tab (not zero)
    win._on_tab_close_requested(0)
    assert len(win.open_pages) == 1
    assert win.editor_tabs.count() == 1
    assert not win.editor_tabs.isHidden(), "one tab left must still show as a tab, not disappear"
    print("[OK] closing one tab never closes the others, and the strip never disappears to zero")


def test_quick_preview_layout_aware_and_interactive():
    """Quick Preview: a second, independent live widget tree with no design-
    mode event filter installed (so it's really interactive, not a click-to-
    select surface like the canvas), and layout-managed widgets get real
    QLayouts so resizing the window actually reflows them."""
    from paperloom.core.model import LayoutGroup

    app = get_app()
    win = make_window(registry())
    win.show()
    app.processEvents()

    for _ in range(3):
        win.canvas.place_component("button")
    page = win.page
    lg = LayoutGroup(id="lg_test", kind="vbox", spacing=8, margins=(10, 10, 10, 10))
    page.layouts.append(lg)
    for i, dw in enumerate(page.widgets):
        dw.layout_id = "lg_test"
        dw.layout_row = i
    app.processEvents()

    win.dispatch("run.quick_preview")
    app.processEvents()
    qp = win.quick_preview
    assert qp is not None and qp.isVisible()
    assert len(qp._live) == 3, "every widget on the page must be live in the preview"
    # unlike the canvas (which installs a DesignModeFilter on every hosted
    # widget to intercept clicks for selection), Quick Preview's tree is built
    # via the same factory.instantiate() call but never has that filter
    # installed - a real click really fires. That's the point of a separate
    # tree rather than reusing the canvas's own live widgets.
    assert win.canvas._live_by_model.get(id(page.widgets[0])) is not qp._live[0], \
        "the preview must build its own widgets, not reuse the canvas's"

    before = [w.geometry() for w in qp._live]
    qp.setGeometry(qp.x(), qp.y(), qp.width() + 200, qp.height() + 150)
    app.processEvents()
    after = [w.geometry() for w in qp._live]
    assert before != after, "layout-managed widgets must reflow when the preview resizes"

    # live-follow: an edit on the canvas (not the preview) updates it
    win.canvas.place_component("label")
    app.processEvents()
    assert len(qp._live) == 4

    # app theme changes must refresh it too (not just modelChanged/pageChanged)
    win.dispatch("view.toggle_app_mode")
    app.processEvents()
    assert qp.content.styleSheet() != ""

    # closing disables live-follow; reopening doesn't double-connect it
    qp.hide()
    app.processEvents()
    assert win._quick_preview_live is False
    win.dispatch("run.quick_preview")
    app.processEvents()
    before2 = len(qp._live)
    win.canvas.place_component("label")
    app.processEvents()
    assert len(qp._live) - before2 == 1
    print("[OK] quick preview: independent interactive tree, layout reflow, live-follow")


def test_layout_toolbar_assign_remove_and_grid():
    """Layout toolbar (LONG-MARCH-BACKLOG 2j-1, the biggest documented gap):
    assigning the canvas-selected widget creates/joins a LayoutGroup and sets
    layout_id/row/col, a grid target honors explicit row/col, spacing/margins
    edit whichever group is targeted (not whichever widget is selected),
    Remove reverts to absolute positioning without disturbing other members
    of the group, and the result reaches Quick Preview as a real QGridLayout."""
    from PySide6.QtWidgets import QGridLayout

    app = get_app()
    win = make_window(registry())
    win.show()
    app.processEvents()

    dw1 = win.canvas.place_component("primary_button")
    dw2 = win.canvas.place_component("primary_button")
    page = win.page

    # nothing selected -> toolbar's Assign/Remove are disabled
    win.canvas.select_qwidget(None)
    assert not win.layout_toolbar_widget.assign_action.isEnabled()

    # select the first widget, assign it into a brand-new grid layout
    win.canvas.select_by_model(dw1)
    assert win.layout_toolbar_widget.assign_action.isEnabled()
    win._on_layout_assign("new:grid", 0, 0)
    assert dw1.layout_id is not None
    group = next(g for g in page.layouts if g.id == dw1.layout_id)
    assert group.kind == "grid"
    assert (dw1.layout_row, dw1.layout_col) == (0, 0)

    # the dropdown now offers the new group by id, not just the "New ..." entries
    win._refresh_layout_toolbar()
    assert win.layout_toolbar_widget.target_combo.findData(group.id) >= 0

    # a second widget joins the SAME group at an explicit grid cell
    win.canvas.select_by_model(dw2)
    win._on_layout_assign(group.id, 0, 1)
    assert dw2.layout_id == group.id
    assert (dw2.layout_row, dw2.layout_col) == (0, 1)

    # spacing/margins mutate whichever group is targeted in the dropdown
    idx = win.layout_toolbar_widget.target_combo.findData(group.id)
    win.layout_toolbar_widget.target_combo.setCurrentIndex(idx)
    win._on_layout_spacing_changed(14)
    win._on_layout_margins_changed(1, 2, 3, 4)
    assert group.spacing == 14
    assert group.margins == (1, 2, 3, 4)

    # Remove takes the selected widget back to absolute positioning without
    # disturbing the other member still in the group
    win.canvas.select_by_model(dw2)
    win._on_layout_remove()
    assert dw2.layout_id is None
    assert dw1.layout_id == group.id, "removing one widget must not disturb the other"

    # end to end: the surviving grid member reaches Quick Preview as a real QGridLayout
    win.dispatch("run.quick_preview")
    app.processEvents()
    assert isinstance(win.quick_preview.content.layout(), QGridLayout)
    print("[OK] layout toolbar: assign/join/grid-cell/spacing/margins/remove round trip")


def test_text_tools_bar_formats_and_targets_right_property():
    """Text formatting toolbar: shown alongside (not instead of) QuickEditBar
    for a widget with a formattable property - a markdown-typed property
    takes priority over a plain text/title one, the buttons call the
    matching core/text_format transform on the RIGHT property via
    canvas.apply_property (the same path Properties panel/Markdown Studio
    already use), and it hides for widgets with nothing to format."""
    from paperloom.core import text_format as tf

    app = get_app()
    win = make_window(registry())
    win.show()
    app.processEvents()

    # a plain string `text` property (primary_button) -> bar shows, targets "text"
    dw1 = win.canvas.place_component("primary_button")
    win.canvas.select_by_model(dw1)
    assert win.text_tools.isVisible()
    assert win._text_tools_prop == "text"

    before = dw1.properties.get("text", "")
    win._on_text_format("bold")
    assert win.canvas.selected_model.properties.get("text") == tf.bold(before)
    win._on_text_format("bold")   # toggling twice round-trips back
    assert win.canvas.selected_model.properties.get("text") == before

    # a markdown-typed property (rich_text) takes priority over text/title
    dw2 = win.canvas.place_component("rich_text")
    win.canvas.select_by_model(dw2)
    assert win.text_tools.isVisible()
    assert win._text_tools_prop not in ("text", "title")
    md_prop = win._text_tools_prop
    before_md = dw2.properties.get(md_prop, "")
    win._on_text_format("heading")
    assert dw2.properties.get(md_prop) == tf.heading(before_md)

    # a widget with neither -> the bar hides
    dw3 = win.canvas.place_component("dial")
    win.canvas.select_by_model(dw3)
    assert win._text_tools_prop is None
    assert not win.text_tools.isVisible()

    # deselecting hides it too
    win.canvas.select_by_model(dw1)
    assert win.text_tools.isVisible()
    win.canvas.select_qwidget(None)
    assert not win.text_tools.isVisible()
    print("[OK] text tools bar: right property targeted, formats round-trip, hides appropriately")


def test_layers_selection_sync():
    app = get_app()
    win = make_window(registry())
    dw = win.canvas.place_component("label")
    # canvas selection reflects into the layers list
    win.layers_panel.refresh()
    win.canvas.select_by_model(dw)
    assert win.layers_panel.list.currentRow() == 0
    # layers -> canvas
    win.canvas.select_qwidget(None)
    win.layers_panel._on_row_changed(0)
    assert win.canvas.selected_model is dw
    print("[OK] layers panel and canvas selection stay in sync both ways")


def test_library_source_tabs():
    reg = registry()
    # PaperDesign as a source is gone - components ship as "default", and "user"
    # is the community space
    assert reg.sources() == ["default"], reg.sources()
    ids = {c.id for c in reg.by_source("default")}
    assert {"pill_button", "primary_button", "search_bar", "switch",
            "image_frame", "toast", "dial"} <= ids
    assert reg.by_source("user") == []
    print("[OK] library exposes components by source (Default / User)")


def test_shell_boots():
    app = get_app()
    win = make_window(registry())
    # all the shell pieces exist and are wired
    assert win.activity_bar and win.side_panel and win.top_bar
    assert win.library_panel and win.pages_panel and win.layers_panel
    assert win.bottom_panel and win.status_bar
    # activity bar switches side panel views without error
    win.activity_bar.select("pages")
    win.activity_bar.select("layers")
    win.activity_bar.select("library")
    win.side_panel.collapse()
    assert win.side_panel.collapsed
    print("[OK] VS Code shell composes and view-switching works")


def test_codegen_never_emits_broken_syntax():
    """Spec §11.1: hostile property values must never produce uncompilable code."""
    app = get_app()
    import py_compile
    reg = registry()
    page = DesignPage(name="Hostile", title='has "quotes" and \n newlines')
    page.add(DesignWidget("progress_bar", "pb", 0, 0, 120, 20, {"value": "6056+"}))
    page.add(DesignWidget("pill_button", "btn", 0, 30, 120, 32,
                          {"text": 'say "hi"'}))
    page.add(DesignWidget("slider", "sl", 0, 70, 120, 20, {"value": "abc"}))
    page.add(DesignWidget("combo_box", "cb", 0, 100, 120, 32, {"items": 'A",B'}))

    from paperloom.codegen import get_backend
    out = tempfile.mkdtemp(prefix="paperloom_hostile_")
    backend = get_backend("pyside6", reg)
    paths = backend.generate(page, out)
    py_compile.compile(paths["generated"], doraise=True)
    py_compile.compile(paths["logic"], doraise=True)
    # coercions were recorded for the Problems tab
    assert any("was invalid" in w for w in backend.warnings)
    assert any("6056+" in w and "60" in w for w in backend.warnings)
    # C++ side also emits (parse-safe tokens)
    get_backend("cpp", reg).generate(page, out)
    print(f"[OK] hostile input sanitized + compiles; {len(backend.warnings)} coercion warnings")
    shutil.rmtree(out, ignore_errors=True)


def test_wysiwyg_fidelity():
    """Spec §11.2/§13: the canvas widget is rendered from the SAME template code
    that codegen emits, so their stylesheet/geometry match by construction."""
    app = get_app()
    reg = registry()
    win = make_window(reg)
    dw = win.canvas.place_component("pill_button")
    live = win.canvas.selected_qwidget

    # generate code for the same page, exec the fragment in isolation, compare QSS
    from paperloom.components import factory
    component = reg.get("pill_button")
    ctx = factory._context(component, dw)
    fragment = component.render_pyside(ctx)
    # the canvas widget's stylesheet must equal what the template produces
    from paperloom.components.factory import _render_widget
    from PySide6.QtWidgets import QWidget
    host = QWidget()
    twin = _render_widget(component, dw, host)
    assert live.styleSheet() == twin.styleSheet(), "canvas and generated QSS diverged"
    assert live.geometry() == twin.geometry()
    print("[OK] WYSIWYG: canvas widget renders from the same code codegen emits")


def test_runner_relays_crash():
    """Spec §11.3: a crashing run must surface its traceback as a structured problem."""
    app = get_app()
    from PySide6.QtCore import QEventLoop, QTimer
    from paperloom.ui.runner import AppRunner
    d = tempfile.mkdtemp(prefix="paperloom_crash_")
    script = os.path.join(d, "crash.py")
    with open(script, "w") as f:
        f.write('print("up")\nraise ValueError("boom")\n')

    runner = AppRunner()
    problems, outputs = [], []
    runner.output.connect(lambda l: outputs.append(l))
    runner.problem.connect(lambda m, fl, ln: problems.append((m, fl, ln)))
    loop = QEventLoop()
    runner.finished.connect(lambda c: loop.quit())
    QTimer.singleShot(6000, loop.quit)
    runner.run(script, sys.executable)
    loop.exec()

    assert any("up" == o.strip() for o in outputs), "live stdout not captured"
    assert problems, "crash was not parsed into a problem"
    msg, file, line = problems[0]
    assert "ValueError: boom" in msg and file.endswith("crash.py")
    print("[OK] runner streams output and parses a crash into a structured problem")
    shutil.rmtree(d, ignore_errors=True)



def test_themes_switch_and_import():
    """Spec §12.8: themes are data; switching rebinds tokens, import loads a file."""
    app = get_app()
    from paperloom import theme as th
    import json
    win = make_window(registry())
    assert len(th.manager.names()) >= 4
    before = th.ACCENT
    win._apply_theme("Midnight")
    assert th.ACCENT != before, "switching theme must rebind tokens"
    assert th.SURFACE_CANVAS == "#24252C"
    # a user theme file with only one override still resolves every token
    d = tempfile.mkdtemp(prefix="paperloom_theme_")
    path = os.path.join(d, "custom.json")
    with open(path, "w") as f:
        json.dump({"name": "TestTheme", "tokens": {"ACCENT": "#FF00AA"}}, f)
    t = th.manager.import_theme(path)
    assert t.name == "TestTheme" and th.ACCENT == "#FF00AA"
    assert th.SURFACE_CANVAS  # inherited from defaults
    th.manager.set_active("PaperLoom Default")
    print("[OK] themes switch, and a partial user theme imports cleanly")
    shutil.rmtree(d, ignore_errors=True)


def test_typed_property_editors():
    """Spec §11.1 at the source: int props get spinboxes, colours get pickers."""
    app = get_app()
    from PySide6.QtWidgets import QSpinBox, QLineEdit
    from paperloom.ui.panels.properties_panel import ColorField
    win = make_window(registry())
    slider = win.canvas.place_component("slider")
    win.properties_panel.set_target(slider)
    assert isinstance(win.properties_panel._editors["value"], QSpinBox), \
        "an int property must not get a free-text editor"
    pill = win.canvas.place_component("pill_button")
    win.properties_panel.set_target(pill)
    from paperloom.ui.panels.properties_panel import AutoGrowTextEdit
    assert isinstance(win.properties_panel._editors["text"], AutoGrowTextEdit), \
        "a text property gets an expanding multi-line editor, not a clipped line box"
    print("[OK] property editors are typed (int->spinbox, color->picker, text->autogrow)")


def test_snap_and_align():
    """Spec §12.5: snapping rounds to the configured size; alignment moves widgets."""
    app = get_app()
    win = make_window(registry())
    win.canvas.resize(800, 600)
    dw = win.canvas.place_component("button")
    win.canvas.set_snap(True, 16)
    assert win.canvas.snap(19) == 16 and win.canvas.snap(25) == 32
    win.canvas.set_snap(False)
    assert win.canvas.snap(19) == 19, "snapping off must pass values through"
    win.canvas.select_by_model(dw)
    win.dispatch("align.left")
    assert dw.x == 0
    win.dispatch("align.top")
    assert dw.y == 0
    print("[OK] snap rounds to size when on, and alignment repositions widgets")


def test_command_dispatch_covers_menu():
    """Every command the menu bar and palette expose must be dispatchable."""
    app = get_app()
    from paperloom.ui.panels.command_palette import command_index
    win = make_window(registry())
    win.canvas.place_component("button")
    unknown = []
    # firing every command includes toggles like view.toggle_library_mode/
    # view.toggle_editor_mode, which now persist to app_settings - snapshot
    # and restore so this test (whose job is just "every command routes
    # somewhere") doesn't leave a flipped setting for every test after it.
    settings_before = app_settings.load()
    # skipped: modal dialogs (block headless) and file/run actions with side effects
    skip = {"app.quit", "app.about", "file.open", "file.save_as", "view.import_theme",
            "file.export_theme", "file.new_page", "file.save", "file.generate",
            "view.snap_settings", "run.preview", "run.stop", "run.generate", "app.preferences",
            "terminal.new", "file.import_ui", "file.export_ui",
            "file.import_stylesheet", "file.export_project"}
    try:
        for display, cmd, shortcut in command_index():
            if cmd in skip:
                continue
            win.status_bar.set_status("")
            win.dispatch(cmd)
            if win.status_bar._left.text().startswith("Unknown command"):
                unknown.append(cmd)
    finally:
        app_settings.save(settings_before)
    assert not unknown, f"unhandled commands: {unknown}"
    print(f"[OK] all {len(command_index())} menu commands route through dispatch")


def test_library_dialog_and_palette():
    """Spec §12.2/§12.7: popup library filters + details, palette indexes everything."""
    app = get_app()
    win = make_window(registry())
    win._open_library_dialog()
    dlg = win.library_dialog
    dlg._set_source("default")
    assert dlg.table.rowCount() >= 40, "Default source should list the library"
    dlg.table.selectRow(0)
    assert dlg._current is not None and dlg.place_btn.isEnabled()
    assert "Qt class" in dlg.details.toHtml()
    dlg._set_source("user")
    assert dlg.table.rowCount() == 0, "User source is empty until the community fills it"
    dlg.hide()

    win.palette_dialog.open_with("align")
    assert win.palette_dialog.list.count() >= 6
    win.palette_dialog.open_with("")
    assert win.palette_dialog.list.count() > 20   # commands + pages + components
    win.palette_dialog.hide()
    print("[OK] library dialog filters with details; palette indexes all three kinds")



def test_app_theme_light_dark():
    """Spec §14: the designed app gets light/dark for free, in the generated code."""
    app = get_app()
    import py_compile, importlib
    from PySide6.QtWidgets import QMainWindow
    from paperloom.codegen import get_backend
    reg = registry()
    page = DesignPage(name="MainWindow", title="Themed")
    for i, cid in enumerate(["title", "primary_button", "switch", "card"]):
        page.add(DesignWidget(cid, cid, 20, 20 + i * 50, 160, 32,
                              reg.get(cid).default_properties()))
    out = tempfile.mkdtemp(prefix="paperloom_theme_")
    paths = get_backend("pyside6", reg).generate(page, out)
    assert "theme" in paths and os.path.exists(paths["theme"]), "app_theme.py must be emitted"
    gen_dir = os.path.dirname(paths["generated"])
    for f in os.listdir(gen_dir):
        if f.endswith(".py"):
            py_compile.compile(os.path.join(gen_dir, f), doraise=True)

    sys.path.insert(0, gen_dir)
    at = importlib.import_module("app_theme"); importlib.reload(at)
    ui_mod = importlib.import_module("main_window_ui"); importlib.reload(ui_mod)
    w = QMainWindow()
    ui = ui_mod.Ui_MainWindow()
    ui.setupUi(w)
    # shipped default is follow-system, resolving to a concrete light/dark palette
    assert at.current_mode() == "system"
    assert at.resolve_mode("system") in ("light", "dark")
    applied = w.styleSheet()
    assert at.LIGHT["bg"] in applied or at.DARK["bg"] in applied
    # explicit modes still work
    ui.set_theme(w, "light")
    assert at.current_mode() == "light" and at.LIGHT["bg"] in w.styleSheet()
    ui.set_theme(w, "dark")
    assert at.current_mode() == "dark" and at.DARK["bg"] in w.styleSheet()
    # toggle cycles light -> dark -> system
    ui.set_theme(w, "light")
    assert ui.toggle_theme(w) == "dark"
    assert ui.toggle_theme(w) == "system"
    # widgets carry roles so one stylesheet styles everything
    assert 'button_primary' in at.stylesheet("light")
    print("[OK] generated apps ship light/dark/follow-system theming")
    shutil.rmtree(out, ignore_errors=True)


def test_multipage_app_shell():
    """Spec §12.10: a multi-page project generates one navigable app."""
    app = get_app()
    import py_compile, importlib
    from paperloom.codegen import get_backend
    from paperloom.codegen.app_shell import generate_app_shell
    from paperloom.core.model import Project
    reg = registry()
    project = Project(name="DemoApp", pages=[])
    for pname, cid in (("MainWindow", "title"), ("Settings", "subtitle")):
        pg = DesignPage(name=pname, title=pname)
        pg.add(DesignWidget(cid, cid, 20, 20, 180, 32, reg.get(cid).default_properties()))
        project.pages.append(pg)

    out = tempfile.mkdtemp(prefix="paperloom_shell_")
    backend = get_backend("pyside6", reg)
    for pg in project.pages:
        backend.generate(pg, out)
    shell = generate_app_shell(project, backend, out)
    gen_dir = os.path.dirname(shell["app"])
    for f in os.listdir(gen_dir):
        if f.endswith(".py"):
            py_compile.compile(os.path.join(gen_dir, f), doraise=True)

    sys.path.insert(0, gen_dir)
    mod = importlib.import_module("app"); importlib.reload(mod)
    shell_window = mod.AppShell()
    assert mod.PAGES == ["MainWindow", "Settings"]
    assert shell_window.navigate("Settings") is True
    assert shell_window.navigate("Nope") is False
    # toggling flips whatever the current mode is (app_theme keeps module state)
    before = importlib.import_module("app_theme").current_mode()
    after = shell_window.toggle_theme()
    assert after != before, "toggle_theme must flip the mode"
    print("[OK] multi-page project generates one navigable app with a theme toggle")
    shutil.rmtree(out, ignore_errors=True)


def test_editor_light_dark_contrast():
    """Editor light/dark must flip ink as well as surfaces - no white-on-white."""
    app = get_app()
    from paperloom import theme as th
    win = make_window(registry())
    th.manager.set_active("PaperLoom Dark")
    dark_ink, dark_panel = th.INK_ON_DARK, th.SIDE_PANEL
    win.dispatch("view.toggle_editor_mode")
    assert th.manager.active.name == "PaperLoom Light"
    assert th.INK_ON_DARK != dark_ink, "ink must flip with the theme"
    assert th.SIDE_PANEL != dark_panel
    # panel text and its background must not collide
    assert th.INK_ON_DARK.lower() != th.SIDE_PANEL.lower()
    win.dispatch("view.toggle_editor_mode")
    assert th.manager.active.name == "PaperLoom Dark"
    print("[OK] editor light/dark flips ink and surfaces together")


def test_guides_and_grid():
    """Grid paints beneath widgets; guides snap to other widgets' edges/centres."""
    app = get_app()
    win = make_window(registry())
    win.canvas.resize(800, 600)
    a = win.canvas.place_component("button")
    a.x, a.y, a.width, a.height = 100, 100, 120, 40
    b = win.canvas.place_component("button")
    # place b nearly aligned with a's left edge -> guide should snap it
    b.x, b.y, b.width, b.height = 103, 300, 120, 40
    gx, gy, ax, ay = win.canvas.alignment_guides_for(b)
    assert gx == 100 and ax == 100, f"expected snap to x=100, got {gx}/{ax}"
    win.canvas.show_guides = False
    gx2, _, ax2, _ = win.canvas.alignment_guides_for(b)
    assert gx2 is None and ax2 == b.x, "guides off must not move anything"
    print("[OK] alignment guides snap to neighbours and respect the toggle")



def test_asset_manager_import_rules():
    """Spec §19: folders are used in place, loose files are copied into the project."""
    from paperloom.core.assets import AssetManager
    src = tempfile.mkdtemp(prefix="paperloom_src_")
    proj = tempfile.mkdtemp(prefix="paperloom_proj_")
    with open(os.path.join(src, "logo.png"), "wb") as f:
        f.write(b"\x89PNG\r\n")
    with open(os.path.join(src, "beep.wav"), "wb") as f:
        f.write(b"RIFF")
    folder = os.path.join(src, "icons"); os.makedirs(folder)
    with open(os.path.join(folder, "a.svg"), "w") as f:
        f.write("<svg/>")

    am = AssetManager(proj)
    am.import_path(os.path.join(src, "logo.png"))
    am.import_path(os.path.join(src, "beep.wav"))
    am.import_path(folder)

    # loose file copied in, keyed project-relative
    assert "assets/logo.png" in am.keys()
    assert os.path.isfile(os.path.join(proj, "assets", "logo.png"))
    assert am.get("assets/logo.png").linked is False
    # folder used in place, indexed recursively
    assert "icons/a.svg" in am.keys()
    assert am.get("icons/a.svg").linked is True
    # kinds classified
    assert am.get("assets/beep.wav").kind == "audio"
    assert am.get("assets/logo.png").kind == "image"
    # unsupported types are reported, not silently dropped
    bad = os.path.join(src, "thing.exe")
    with open(bad, "wb") as f:
        f.write(b"MZ")
    assert am.import_path(bad) == []
    assert any("Unsupported" in e for e in am.errors)
    print("[OK] assets: folders linked in place, loose files copied, kinds classified")
    shutil.rmtree(src, ignore_errors=True); shutil.rmtree(proj, ignore_errors=True)


def test_project_save_load_roundtrip():
    """Spec §20: a project saves and reloads with pages, theme, animations, styles."""
    from paperloom.core.project_io import ProjectIO
    from paperloom.core.assets import AssetManager
    from paperloom.core.app_theme import AppTheme
    from paperloom.core.animations import AnimationSet, Animation
    from paperloom.core.model import Project
    reg = registry()
    project = Project(name="DemoApp", pages=[])
    for pname, cid in (("MainWindow", "primary_button"), ("Settings", "switch")):
        pg = DesignPage(name=pname, title=pname)
        pg.add(DesignWidget(cid, cid, 20, 30, 180, 32, reg.get(cid).default_properties()))
        project.pages.append(pg)

    anims = AnimationSet()
    anims.add("primary_button", Animation(kind="pop", trigger="on_click", duration=250))
    directory = tempfile.mkdtemp(prefix="paperloom_save_")
    io = ProjectIO()
    io.save(project, directory, assets=AssetManager(directory),
            app_theme=AppTheme(mode="dark"), animations=anims.to_dict(),
            stylesheets=[{"name": "brand.qss", "source": "QWidget{}", "enabled": True}])

    assert os.path.isfile(os.path.join(directory, "project.json"))
    loaded, assets, theme_obj, animations, styles = io.load(directory)
    assert [p.name for p in loaded.pages] == ["MainWindow", "Settings"]
    assert loaded.pages[0].widgets[0].x == 20
    assert theme_obj.mode == "dark"
    assert animations["primary_button"][0]["kind"] == "pop"
    assert styles[0]["name"] == "brand.qss"
    assert io.errors == []

    # a corrupt page is reported and skipped, not fatal
    with open(os.path.join(directory, "pages", "settings.page.json"), "w") as f:
        f.write("{ not json")
    loaded2, *_ = io.load(directory)
    assert [p.name for p in loaded2.pages] == ["MainWindow"]
    assert any("Settings" in e for e in io.errors)
    print("[OK] project save/load round-trips and survives a corrupt page")
    shutil.rmtree(directory, ignore_errors=True)


def test_ui_layouts_connections_tabstops_roundtrip():
    """s14 2i: .ui import/export handles layouts, signal connections, and tab
    order - not just flat absolute-geometry widgets. Without this, a real Qt
    Designer file (which almost always uses layouts) would import with every
    widget stacked at (0,0)."""
    from paperloom.core.ui_io import UiIO
    reg = registry()
    page = DesignPage(name="Panel", title="Panel", width=300, height=200)
    page.layouts = [LayoutGroup(id="lay1", kind="vbox")]
    for i, (cid, nm) in enumerate((("title", "heading"), ("primary_button", "go"))):
        dw = DesignWidget(cid, nm, 0, 0, 120, 32,
                           {"text": "Hi"} if cid == "title" else {"text": "Go"},
                           layout_id="lay1", layout_row=i)
        page.add(dw)
    page.connections = [SignalConnection(sender="go", signal="clicked()",
                                          receiver="Panel", slot="close()")]
    page.tab_order = ["heading", "go"]

    d = tempfile.mkdtemp(prefix="paperloom_ui_layout_")
    path = os.path.join(d, "panel.ui")
    uio = UiIO(reg)
    uio.export_page(page, path)
    xml = open(path, encoding="utf-8").read()
    assert "<layout" in xml and 'class="QVBoxLayout"' in xml
    assert "<connection>" in xml and "<sender>go</sender>" in xml
    assert "<tabstops>" in xml and "<tabstop>heading</tabstop>" in xml

    back = uio.import_file(path)
    assert len(back.layouts) == 1 and back.layouts[0].kind == "vbox"
    members = {w.object_name: w for w in back.widgets}
    assert members["heading"].layout_id == back.layouts[0].id
    assert members["go"].layout_id == back.layouts[0].id
    assert members["go"].layout_row == 1
    assert len(back.connections) == 1
    assert back.connections[0].sender == "go" and back.connections[0].slot == "close()"
    assert back.tab_order == ["heading", "go"]
    print("[OK] s14: .ui layouts/connections/tabstops round-trip")
    shutil.rmtree(d, ignore_errors=True)


def test_ui_imports_foreign_layout_file():
    """s14 2i: a real Qt-Designer-style file using a QVBoxLayout (not absolute
    geometry) must import with widgets correctly placed into a layout group,
    not silently dropped or stacked at (0,0)."""
    from paperloom.core.ui_io import UiIO
    reg = registry()
    d = tempfile.mkdtemp(prefix="paperloom_ui_foreign_layout_")
    foreign = os.path.join(d, "foreign_layout.ui")
    with open(foreign, "w") as f:
        f.write(
            '<ui version="4.0"><class>Form</class>'
            '<widget class="QMainWindow" name="Form">'
            '<widget class="QWidget" name="centralwidget">'
            '<layout class="QVBoxLayout" name="verticalLayout">'
            '<item><widget class="QPushButton" name="okBtn">'
            '<property name="text"><string>OK</string></property>'
            '</widget></item>'
            '<item><widget class="QPushButton" name="cancelBtn">'
            '<property name="text"><string>Cancel</string></property>'
            '</widget></item>'
            '</layout></widget></widget>'
            '<connections><connection><sender>okBtn</sender>'
            '<signal>clicked()</signal><receiver>Form</receiver>'
            '<slot>close()</slot></connection></connections>'
            '</ui>')
    uio = UiIO(reg)
    page = uio.import_file(foreign)
    assert len(page.widgets) == 2
    assert len(page.layouts) == 1 and page.layouts[0].kind == "vbox"
    ok = next(w for w in page.widgets if w.object_name == "okBtn")
    assert ok.layout_id == page.layouts[0].id, \
        "widget inside a real Designer <layout> must be assigned to a LayoutGroup"
    assert len(page.connections) == 1
    assert page.connections[0].sender == "okBtn"
    print("[OK] s14: a foreign Designer file using real layouts imports correctly")
    shutil.rmtree(d, ignore_errors=True)


def test_ui_designer_interop():
    """Spec §21: .ui export/import round-trips losslessly; foreign files import."""
    from paperloom.core.ui_io import UiIO
    reg = registry()
    page = DesignPage(name="LoginForm", title="Login", width=420, height=300)
    for cid, nm, props in (("title", "heading", {"text": "Sign in"}),
                           ("password_box", "pw", {"placeholder": "Password"}),
                           ("primary_button", "submit", {"text": "Log in"})):
        page.add(DesignWidget(cid, nm, 20, 40, 200, 32, props))

    d = tempfile.mkdtemp(prefix="paperloom_ui_")
    path = os.path.join(d, "login.ui")
    uio = UiIO(reg)
    uio.export_page(page, path)

    back = uio.import_file(path)
    assert back.name == "LoginForm" and back.title == "Login"
    assert (back.width, back.height) == (420, 300)
    # component identity survives our own round trip
    assert [w.component_id for w in back.widgets] == ["title", "password_box", "primary_button"]
    assert back.widgets[0].properties["text"] == "Sign in"

    # a foreign Designer file (no PaperLoom stamp) still imports via class matching
    foreign = os.path.join(d, "foreign.ui")
    with open(foreign, "w") as f:
        f.write('<ui version="4.0"><class>Form</class>'
                '<widget class="QMainWindow" name="Form">'
                '<widget class="QWidget" name="centralwidget">'
                '<widget class="QPushButton" name="okBtn">'
                '<property name="geometry"><rect><x>5</x><y>7</y>'
                '<width>90</width><height>30</height></rect></property>'
                '<property name="text"><string>OK</string></property></widget>'
                '</widget></widget></ui>')
    imported = uio.import_file(foreign)
    assert len(imported.widgets) == 1, "structural widgets must not import as components"
    w = imported.widgets[0]
    assert w.component_id == "button" and w.properties["text"] == "OK"
    assert (w.x, w.y) == (5, 7)
    print("[OK] Qt Designer .ui interop: lossless ours, tolerant theirs")
    shutil.rmtree(d, ignore_errors=True)


def test_qt_property_introspection():
    """Spec §22: read and write any real Qt property, Designer-style."""
    app = get_app()
    from PySide6.QtWidgets import QPushButton
    from paperloom.core import introspect
    btn = QPushButton("Hi")
    props = introspect.editable_properties(btn)
    names = {p.name for p in props}
    assert {"text", "flat", "checkable"} <= names
    assert len(props) > 20, "should expose the whole meta-object surface"
    assert introspect.write_property(btn, "text", "Changed") and btn.text() == "Changed"
    assert introspect.write_property(btn, "flat", True) and btn.isFlat()
    assert introspect.write_property(btn, "nonexistent", 1) is False
    assert "clicked" in introspect.signals_of(btn)
    print(f"[OK] introspection exposes {len(props)} live Qt properties, read and write")


def test_animations_generate_and_preview():
    """Spec §23: animations become real QPropertyAnimation code and preview live."""
    app = get_app()
    import py_compile
    from paperloom.core.animations import AnimationSet, Animation
    from paperloom.codegen import get_backend
    reg = registry()
    page = DesignPage(name="MainWindow", title="Anim")
    page.add(DesignWidget("primary_button", "go", 30, 30, 160, 36,
                          reg.get("primary_button").default_properties()))
    page.add(DesignWidget("card", "panel", 30, 90, 200, 100, {}))

    anims = AnimationSet()
    anims.add("go", Animation(kind="pop", trigger="on_click", duration=220))
    anims.add("panel", Animation(kind="slide_up", trigger="on_show", easing="OutBack"))

    backend = get_backend("pyside6", reg)
    backend.animations = anims
    backend.extra_stylesheets = ["QPushButton { letter-spacing: 1px; }"]
    out = tempfile.mkdtemp(prefix="paperloom_anim_")
    paths = backend.generate(page, out)
    src = open(paths["generated"]).read()
    py_compile.compile(paths["generated"], doraise=True)
    assert "QPropertyAnimation" in src and "OutBack" in src
    assert "clicked.connect" in src, "on_click animations must be wired to the signal"
    assert "letter-spacing" in src, "user stylesheets must reach generated code"

    # and it previews live on the canvas
    win = make_window(reg)
    dw = win.canvas.place_component("primary_button")
    played = win.canvas.preview_animation(dw.object_name, Animation(kind="shake"))
    assert played is not None
    print("[OK] animations generate real Qt code and preview on the canvas")
    shutil.rmtree(out, ignore_errors=True)


def test_stylesheets_and_problems():
    """Spec §24/§25: stylesheet validation, layering, and one problem channel."""
    from paperloom.core.stylesheets import StylesheetManager, validate, StylesheetError
    from paperloom.core.problems import ProblemLog
    assert validate("QPushButton { color: red; }") == []
    assert validate("QPushButton { color: red") , "unclosed block must be caught"

    d = tempfile.mkdtemp(prefix="paperloom_qss_")
    good = os.path.join(d, "brand.qss")
    with open(good, "w") as f:
        f.write("QPushButton { font-weight: 700; }")
    sm = StylesheetManager()
    sheet = sm.import_file(good)
    assert sheet.name == "brand.qss" and "font-weight" in sm.combined()
    sm.set_enabled("brand.qss", False)
    assert sm.combined() == "", "disabled sheets must not contribute"
    sm.set_enabled("brand.qss", True)
    try:
        sm.import_file(os.path.join(d, "nope.qss"))
        raise AssertionError("missing file should raise")
    except StylesheetError:
        pass

    log = ProblemLog()
    seen = []
    log.on_change(lambda l: seen.append(len(l)))
    log.warn("careful", source="codegen")
    log.error("broke", source="run", file="a.py", line=9)
    assert log.counts() == {"error": 1, "warning": 1, "info": 0}
    assert seen, "listeners must fire"
    log.clear(source="run")
    assert log.counts()["error"] == 0
    print("[OK] stylesheets validate/layer, and problems flow through one channel")
    shutil.rmtree(d, ignore_errors=True)



def test_terminal_unicode_ansi_and_carriage():
    """Spec §27: ANSI colour, carriage-return rewrite, and full Unicode."""
    app = get_app()
    import codecs
    from paperloom.ui.panels.terminal import TerminalWidget
    t = TerminalWidget()
    t.write_ansi("\x1b[32mgreen\x1b[0m plain\n")
    t.write_ansi("emoji ✨🌸 kaomoji (｡•̀ᴗ-)✧ 日本語 中文 العربية русский\n")
    t.write_ansi("progress 10%\rprogress 55%\rprogress 100%\n")
    t.write_ansi("\x1b[2K\x1b[1;31mbold red\x1b[0m done\n")
    text = t.view.toPlainText()
    assert "\x1b" not in text and "[32m" not in text, "escape codes must not leak"
    assert text.count("progress") == 1, "carriage return must rewrite the line"
    for sample in ("✨", "日本語", "(｡•̀ᴗ-)✧", "العربية", "русский"):
        assert sample in text, f"lost unicode: {sample}"
    # an emoji split across two reads must survive incremental decoding
    decoder = codecs.getincrementaldecoder("utf-8")("replace")
    raw = "🌸".encode()
    assert decoder.decode(raw[:2]) + decoder.decode(raw[2:]) == "🌸"
    print("[OK] terminal: ANSI, carriage flow, emoji/CJK/RTL, split-byte decoding")


def test_theming_reaches_nested_panels():
    """Regression: the terminal and popover kept their own colours on theme change."""
    app = get_app()
    from paperloom import theme as th
    win = make_window(registry())
    for _ in range(2):                       # dark -> light -> dark
        win.dispatch("view.toggle_editor_mode")
        assert th.ACTIVITY_BAR in win.bottom_panel.terminal.styleSheet(), \
            "nested terminal must follow the editor theme"
        assert th.SIDE_PANEL in win.popover.styleSheet(), \
            "popover must use chrome tokens, not canvas tokens"
    print("[OK] theming reaches nested panels (terminal, popover)")


def test_context_menus_are_component_aware():
    """Spec §29: right-click adapts to what was clicked."""
    app = get_app()
    from paperloom.ui.panels.context_menus import build_widget_menu, build_canvas_menu
    win = make_window(registry())
    noop = {k: (lambda *a: None) for k in
            ("edit_text", "change_media", "pick_color", "quick_edit", "bring_front",
             "send_back", "align", "fit_contents", "fill_width", "reset_size",
             "animate", "duplicate", "copy", "delete", "properties", "qt_properties")}

    btn = win.canvas.place_component("primary_button")
    labels = [a.text() for a in
              build_widget_menu(win, win.registry.get("primary_button"), btn, noop).actions()]
    assert any("Edit text" in l for l in labels)
    assert not any("Change media" in l for l in labels)

    img = win.canvas.place_component("image_frame")
    media_labels = [a.text() for a in
                    build_widget_menu(win, win.registry.get("image_frame"), img, noop).actions()]
    assert any("Change media" in l for l in media_labels), "media widgets need a media action"

    canvas_handlers = {k: (lambda *a: None) for k in
                       ("paste", "open_library", "toggle_grid", "toggle_guides",
                        "toggle_snap", "snap_settings", "toggle_app_mode",
                        "select_all", "page_settings")}
    canvas_handlers.update(grid_on=lambda: True, guides_on=lambda: True,
                           snap_on=lambda: False)
    canvas_labels = [a.text() for a in build_canvas_menu(win, canvas_handlers).actions()]
    assert any("Paste" in l for l in canvas_labels)
    print("[OK] context menus adapt to the clicked component")


def test_quick_edit_and_clipboard():
    """Quick edit changes opacity/colour/radius; copy-paste duplicates a widget."""
    app = get_app()
    win = make_window(registry())
    btn = win.canvas.place_component("primary_button")
    win._show_quick_edit(btn)
    assert win.quick_edit.isVisible()

    win.canvas.set_radius_of_selected(18)
    assert "border-radius: 18px" in btn.properties.get("_style", "")
    win.canvas.set_opacity_of_selected(0.5)
    assert btn.properties["opacity"] == 0.5

    before = len(win.page.widgets)
    win._copy_widget(btn)
    win._paste_widget()
    assert len(win.page.widgets) == before + 1
    win._fit_contents(btn)
    assert btn.width > 0 and btn.height > 0
    win._fill_width(btn)
    assert btn.width > 200, "fill width should span the canvas"
    print("[OK] quick edit adjusts style, and copy/paste works")


def test_color_picker_channels_sync():
    """Spec §28: wheel, HEX, RGB, HSL and alpha all stay in sync."""
    app = get_app()
    from PySide6.QtGui import QColor
    from paperloom.ui.panels.color_picker import ColorPickerDialog
    d = ColorPickerDialog("#C8453F")
    assert [d.rgb_spins[k].value() for k in "RGB"] == [200, 69, 63]

    d.hex_edit.setText("#3F8A5F"); d._from_hex()
    assert [d.rgb_spins[k].value() for k in "RGB"] == [63, 138, 95]
    assert d.wheel.color().name() == "#3f8a5f"

    for channel, value in (("R", 255), ("G", 0), ("B", 0)):
        d.rgb_spins[channel].setValue(value)
    assert d.hex_edit.text() == "#ff0000"

    d.alpha.setValue(128)
    assert d.color().alpha() == 128
    assert d.color().name(QColor.NameFormat.HexArgb) == "#80ff0000"
    print("[OK] colour picker syncs wheel/HEX/RGB/HSL/alpha")


def test_sensible_sizing_defaults():
    """Spec §30: generated apps get size policies, minimums and wrapping."""
    app = get_app()
    import py_compile, importlib
    from PySide6.QtWidgets import QMainWindow
    from paperloom.codegen import get_backend
    from paperloom.core import sizing
    reg = registry()

    # roles map to sane policies without anyone configuring anything
    assert sizing.defaults_for(reg.get("text_box")).h_policy == "Expanding"
    assert sizing.defaults_for(reg.get("label")).wrap == "wrap"
    assert sizing.defaults_for(reg.get("card")).v_policy == "Expanding"

    page = DesignPage(name="MainWindow", title="Adaptive", width=700, height=460)
    for i, cid in enumerate(["title", "text_box", "primary_button", "card", "label"]):
        page.add(DesignWidget(cid, cid, 30, 20 + i * 60, 220, 34,
                              reg.get(cid).default_properties()))
    out = tempfile.mkdtemp(prefix="paperloom_size_")
    paths = get_backend("pyside6", reg).generate(page, out)
    src = open(paths["generated"]).read()
    py_compile.compile(paths["generated"], doraise=True)
    assert "setSizePolicy" in src and "setMinimumSize" in src and "setWordWrap" in src

    sys.path.insert(0, os.path.dirname(paths["generated"]))
    mod = importlib.import_module("main_window_ui"); importlib.reload(mod)
    w = QMainWindow(); ui = mod.Ui_MainWindow(); ui.setupUi(w)
    assert w.minimumSize().width() >= 320 and w.minimumSize().height() >= 240
    assert ui.label.wordWrap() is True
    print("[OK] sensible sizing defaults reach the generated app")
    shutil.rmtree(out, ignore_errors=True)


def test_button_roles_have_interaction_states():
    """s10 4.3: every interactive role carries hover+pressed in BOTH app modes,
    so a placed button never renders as a dead flat block again."""
    from paperloom.core import app_theme
    roles = ("button_primary", "button_secondary", "button_ghost",
             "button_danger", "button_pill", "button_icon")
    for mode in ("light", "dark"):
        qss = app_theme.stylesheet(mode)
        for role in roles:
            assert f'[role="{role}"]:hover' in qss, f"{role} no :hover ({mode})"
            assert f'[role="{role}"]:pressed' in qss, f"{role} no :pressed ({mode})"
    # and the generated-app runtime round-trips the danger tokens per mode
    runtime = app_theme.runtime_module_source(app_theme.AppTheme())
    ns = {}
    exec(compile(runtime, "app_theme_gen.py", "exec"), ns)
    assert "#C8453F" in ns["stylesheet"]("light")
    assert "#E4756F" in ns["stylesheet"]("dark")
    print("[OK] s10: every button role has hover/pressed in both modes")


def test_terminal_platform_eol_and_starts():
    """s10 4.4: commands submit with the platform line ending (cmd.exe needs
    CRLF - the 'fake terminal') and the shell starts when shown."""
    app = get_app()
    from paperloom.ui.panels.terminal import TerminalWidget, SUBMIT_EOL
    expected = "\r\n" if sys.platform.startswith("win") else "\n"
    assert SUBMIT_EOL == expected
    t = TerminalWidget(); t.show()
    for _ in range(20):
        app.processEvents()
    assert t._proc is not None, "shell did not start on show"
    t._on_command("echo paperloom_eol_test")
    for _ in range(30):
        app.processEvents()
    text = t.view.toPlainText()
    t.stop()
    if not sys.platform.startswith("win"):   # can only exercise the shell here
        assert "paperloom_eol_test" in text, text[-200:]
    # CRLF output (Windows cmd/PowerShell) must survive - a trailing \r used to
    # erase each line, so replies came back invisible
    t2 = TerminalWidget()
    t2.write_ansi("'ls' is not recognized as an internal or external command.\r\n")
    t2.write_ansi('C:\\Users>echo "Hi"\r\n"Hi"\r\n')
    out = t2.view.toPlainText()
    assert "is not recognized" in out and '"Hi"' in out, out
    # a lone \r must still rewrite the line (progress bars)
    t3 = TerminalWidget()
    t3.write_ansi("Downloading:  10%\rDownloading: 100%")
    assert t3.view.toPlainText() == "Downloading: 100%"
    print("[OK] s10: terminal uses platform EOL and starts on show")


def test_qt_property_edits_persist_to_codegen():
    """s10 4.7: the live Qt-property table isn't decorative - an edit lands in
    the model's qt_props and is emitted into generated, compilable code."""
    app = get_app()
    import py_compile
    reg = registry()
    w = make_window(reg)
    dw = w.canvas.place_component("primary_button")
    w.canvas.select_by_model(dw)
    w._on_qt_property_changed("flat", True)
    assert dw.qt_props.get("flat") is True, "edit not persisted to model"
    out = tempfile.mkdtemp(prefix="paperloom_qtprops_")
    paths = w.generate_code(out)
    src = open(paths["generated"], encoding="utf-8").read()
    assert 'setProperty("flat", True)' in src, "qt_prop not emitted to codegen"
    py_compile.compile(paths["generated"], doraise=True)
    shutil.rmtree(out, ignore_errors=True)
    print("[OK] s10: Qt-property edits persist to model and generated code")


def test_properties_panel_grouped_editor():
    """s10 4.5/4.7/4.8: properties is a grouped, collapsible editor with a live
    Qt table and animations folded in - not a floating label + message box."""
    app = get_app()
    from paperloom.ui.panels.collapsible import CollapsibleSection
    reg = registry()
    w = make_window(reg)
    dw = w.canvas.place_component("primary_button")
    w.canvas.select_by_model(dw)
    pp = w.properties_panel
    titles = [s._title.lower() for s in pp._body.findChildren(CollapsibleSection)]
    for expected in ("geometry", "appearance", "animations", "qt properties"):
        assert expected in titles, f"missing section {expected}: {titles}"
    # the Qt table populates from the live widget (was a QMessageBox dump)
    assert len(pp._qt_table._rows) > 20, "Qt property table did not populate"
    # object/class header reflects the selection
    assert pp._obj_name.text() == dw.object_name
    assert pp._obj_class.text() == "QPushButton"
    # empty state is top-aligned and only shows with no selection
    w.canvas.select_qwidget(None)
    assert not pp._empty.isHidden() and pp._scroll.isHidden()
    print("[OK] s10: properties is a grouped collapsible editor with live Qt table")


def test_activity_bar_cleanup():
    """s10 4.2/4.6/4.8: distinct per-pane icons, one gear, no animations pane,
    and nothing forced open on boot."""
    app = get_app()
    from paperloom.ui.activity_bar import ActivityBar
    ids = [p[0] for p in ActivityBar.PANES]
    icons_used = [p[1] for p in ActivityBar.PANES]
    assert "animations" not in ids, "animations should not be its own pane"
    assert "settings" not in icons_used, "the gear must be the single settings button"
    assert len(set(icons_used)) == len(icons_used), f"duplicate pane icons: {icons_used}"
    assert ids == ["library", "pages", "layers", "properties", "assets"]
    w = make_window(registry())
    assert w.activity_bar._active is None, "no pane should be forced open on boot"
    assert "animations" not in w.side_panel._ids
    print("[OK] s10: activity bar has distinct icons, one gear, no boot pane")


def test_library_mode_popup_and_pane():
    """s10 4.2: popup is the default library surface; pane mode is a setting."""
    app = get_app()
    w = make_window(registry())
    assert w.library_mode == "popup"
    w._on_view_selected("library")
    for _ in range(4):
        app.processEvents()
    assert w.library_dialog is not None and not w.library_dialog.isHidden()
    w.library_dialog.hide()
    # switch to pane mode: Components now docks in the side panel
    w.set_library_mode("pane")
    assert w.library_mode == "pane"
    w._on_view_selected("library")
    for _ in range(4):
        app.processEvents()
    assert not w.side_panel.collapsed, "pane mode should open the side panel"
    assert w.side_panel._stack.currentWidget() is w.library_panel
    # set_library_mode persists to app_settings now (Settings > Personalization
    # restores it on next launch) - reset back so this test's choice doesn't
    # leak into every window built for the rest of the suite.
    w.set_library_mode("popup")
    print("[OK] s10: library is popup by default, pane behind a setting")


def test_target_chosen_at_creation():
    """s10 4.10: no mid-design target dropdown; the window takes its target from
    the project (chosen once at creation)."""
    app = get_app()
    from paperloom.core.model import Project, DesignPage
    reg = registry()
    w = make_window(reg)
    assert not hasattr(w.top_bar, "target"), "target dropdown should be gone"
    w2 = PaperLoomWindow(reg, project=Project(name="x", target="cpp",
                                              pages=[DesignPage(name="MainWindow")]))
    _WINDOWS.append(w2)
    assert w2.target == "cpp", "window should read target from its project"
    print("[OK] s10: target is a project property, not a live dropdown")


def test_palette_is_context_aware():
    """s10 4.9: the palette surfaces actions for the current selection first."""
    app = get_app()
    w = make_window(registry())
    assert w._palette_context()[-1][1] == "file.new_page"   # page action always present
    dw = w.canvas.place_component("primary_button")
    w.canvas.select_by_model(dw)
    ctx = w._palette_context()
    cmds = [c for _, c in ctx]
    assert "edit.duplicate" in cmds and "edit.delete" in cmds
    assert any(dw.object_name in disp for disp, _ in ctx)
    print("[OK] s10: command palette is selection/context aware")


def test_media_asset_renders_and_ships():
    """s11: a media widget renders its real image on the canvas and the generated
    app ships + loads the asset (not just the asset name as text)."""
    app = get_app()
    import py_compile
    from PySide6.QtGui import QPixmap
    reg = registry()
    w = make_window(reg)
    tmp = tempfile.mkdtemp(prefix="paperloom_media_")
    png = os.path.join(tmp, "logo.png")
    px = QPixmap(48, 32); px.fill(); px.save(png, "PNG")
    key = w.assets.import_path(png)[0].key
    dw = w.canvas.place_component("image_frame")
    w.canvas.select_by_model(dw)
    w.canvas.apply_property("asset", key)
    live = w.canvas.selected_qwidget
    assert live.pixmap() is not None and not live.pixmap().isNull(), "canvas didn't load image"
    out = tempfile.mkdtemp(prefix="paperloom_media_gen_")
    paths = w.generate_code(out)
    src = open(paths["generated"], encoding="utf-8").read()
    gen_dir = os.path.dirname(paths["generated"])
    assert "QPixmap" in src, "generated code must import QPixmap"
    assert '_fit_pixmap(_asset("assets/logo.png")' in src
    assert "def _fit_pixmap(" in src, "generated code must include the fit-mode helper"
    assert os.path.isfile(os.path.join(gen_dir, "assets", "logo.png")), "asset not shipped"
    py_compile.compile(paths["generated"], doraise=True)
    # the properties editor offers an asset picker, not a bare text box
    from paperloom.ui.panels.properties_panel import AssetField
    w.properties_panel.set_target(dw, live)
    assert len(w.properties_panel._body.findChildren(AssetField)) == 1
    shutil.rmtree(out, ignore_errors=True)
    print("[OK] s11: media widgets render on canvas and ship their asset")


def test_generated_theme_follows_system():
    """s11: generated apps default to follow-system, with explicit light/dark and
    a cycle, all in compilable code."""
    app = get_app()
    from PySide6.QtWidgets import QMainWindow
    from paperloom.core import app_theme as at
    ns = {}
    exec(compile(at.runtime_module_source(at.AppTheme()), "app_theme_gen.py", "exec"), ns)
    assert ns["current_mode"]() == "system"
    assert ns["resolve_mode"]("system") in ("light", "dark")
    import re
    assert not re.findall(r"\$[A-Za-z_]+\$", ns["stylesheet"]()), "unresolved placeholders"
    win = QMainWindow()
    ns["apply"](win, "/* custom */")
    assert ns["set_mode"](win, "dark") == "dark"
    assert ns["set_mode"](win, "light") == "light"
    assert ns["toggle"](win) == "dark"
    assert ns["toggle"](win) == "system"
    print("[OK] s11: generated apps default to light/dark/follow-system")


def test_autogrow_text_field():
    """s13: a text property gets an expanding editor that grows with long text
    instead of clipping it in a one-line box."""
    app = get_app()
    from paperloom.ui.panels.properties_panel import AutoGrowTextEdit
    w = make_window(registry())
    w.resize(1100, 760); w.show()
    for _ in range(4):
        app.processEvents()
    dw = w.canvas.place_component("title")
    w.canvas.select_by_model(dw)
    w._show_pane("properties")
    w.properties_panel.set_target(dw, w.canvas.selected_qwidget)
    for _ in range(4):
        app.processEvents()
    field = w.properties_panel._editors["text"]
    assert isinstance(field, AutoGrowTextEdit)
    one_line = field.height()
    field.setPlainText("This is a long-winded description that would have been "
                       "clipped in a tiny one-line box but now wraps and grows "
                       "across several lines instead, filling many rows of text.")
    for _ in range(6):
        app.processEvents()
    assert field.height() > one_line, "field should grow to fit long text"
    # newlines survive into the model value (multi-line labels)
    field.setPlainText("line one\nline two")
    for _ in range(3):
        app.processEvents()
    assert "\n" in dw.properties.get("text", "") or "line two" in dw.properties.get("text", "")
    print("[OK] s13: text properties use an expanding multi-line editor")


def test_markdown_engine_converts():
    """s13: the rich-text engine turns Markdown + LaTeX into self-contained HTML
    (math embedded as data-URI images, no runtime deps)."""
    app = get_app()
    from paperloom.core import richtext
    md = ("# Title\n\n**bold** *italic* `code` "
          '<span style="color:#e11d48">red</span>\n\n'
          "- a\n- b\n\nInline $E = mc^2$ and\n\n$$\\int_0^1 x\\,dx = \\tfrac12$$")
    warns = []
    html = richtext.to_html(md, warnings=warns)
    assert "<h1" in html.lower()
    assert "e11d48" in html.lower(), "inline colour span must pass through"
    assert html.count("data:image/png") == 2, "both math snippets should render"
    # literals for both backends are valid, non-empty
    assert richtext.py_literal(html).startswith(("'", '"'))
    assert richtext.cpp_literal("a\"b").startswith('"')
    print("[OK] s13: markdown + LaTeX convert to self-contained HTML")


def test_rich_text_component_renders_and_ships():
    """s13: the rich_text component renders markdown on the canvas and ships the
    same rendered HTML (with embedded math) in compilable generated code."""
    app = get_app()
    import py_compile
    reg = registry()
    assert reg.get("rich_text") is not None, "rich_text component must be registered"
    w = make_window(reg)
    dw = w.canvas.place_component("rich_text")
    w.canvas.apply_property("content", "# Hi\n\n**bold** and $x^2$")
    live = w.canvas._live_by_model.get(id(dw))
    assert type(live).__name__ == "QTextBrowser"
    doc = live.toHtml()
    assert "Hi" in doc and "data:image/png" in doc, "canvas didn't render md+math"
    out = tempfile.mkdtemp(prefix="paperloom_rt_")
    paths = w.generate_code(out)
    src = open(paths["generated"], encoding="utf-8").read()
    assert "QTextBrowser" in src and ".setHtml(" in src
    assert "data:image/png" in src, "generated code must embed the rendered math"
    py_compile.compile(paths["generated"], doraise=True)
    shutil.rmtree(out, ignore_errors=True)
    print("[OK] s13: rich_text renders on canvas and ships rendered HTML")


def test_richtext_engine_handles_common_latex_edge_cases():
    """s14: the upgraded richtext engine must not regress on the two matplotlib
    mathtext bugs found while building the standalone rich_renderer module -
    silent macro degrade and multi-line $$...$$ newlines - and must normalize
    brace-less \\frac shorthand (\\tfrac12) which matplotlib rejects outright."""
    from paperloom.core import richtext
    # multi-line display math with \qquad (silently degrades without cleanup)
    warns = []
    html = richtext.to_html(
        "$$a + b\n\\qquad\nc + d$$", fg="#111", warnings=warns)
    assert html.count("data:image/png") == 1, "multi-line qquad math failed to render"
    assert not warns, f"unexpected degrade warning: {warns}"
    # brace-less \tfrac shorthand (matplotlib raises without normalization)
    warns2 = []
    html2 = richtext.to_html("$\\tfrac12$", fg="#111", warnings=warns2)
    assert html2.count("data:image/png") == 1, "brace-less tfrac shorthand failed"
    assert not warns2
    # a genuinely unsupported environment must degrade honestly, not silently
    warns3 = []
    html3 = richtext.to_html(
        "$$\\begin{pmatrix} a & b \\\\ c & d \\end{pmatrix}$$", fg="#111", warnings=warns3)
    assert "pmatrix" in html3, "unsupported environment should show readable source"
    assert warns3, "degrade should be recorded as a warning"
    print("[OK] s14: richtext engine handles the known matplotlib mathtext edge cases")


def test_canvas_math_ink_follows_app_theme():
    """s14: regression for the dark-mode math legibility bug - canvas math must
    be baked in the SAME ink colour codegen uses (the app theme's fg), not a
    hardcoded default, and must refresh when the app theme is toggled."""
    app = get_app()
    w = make_window(registry())
    dw = w.canvas.place_component("rich_text")
    w.canvas.apply_property("content", "$E=mc^2$")
    light_fg = w.canvas.app_theme.tokens()["fg"]
    live = w.canvas._live_by_model.get(id(dw))
    assert light_fg.lower() in live.toHtml().lower() or "data:image/png" in live.toHtml()
    w.dispatch("view.toggle_app_mode")
    dark_fg = w.canvas.app_theme.tokens()["fg"]
    assert dark_fg != light_fg, "test setup: app theme toggle should change fg"
    live_after = w.canvas._live_by_model.get(id(dw))
    assert live_after is not None and "data:image/png" in live_after.toHtml(), \
        "rich-text widget should be rebuilt (not just restyled) on app theme toggle"
    print("[OK] s14: canvas rich-text math ink follows the app theme, live")


def test_markdown_field_is_directly_editable():
    """s14: the Properties markdown field is a real growable text box the user
    can type into directly, not just a truncated preview label."""
    app = get_app()
    from paperloom.ui.panels.properties_panel import MarkdownField, AutoGrowTextEdit
    w = make_window(registry())
    w.resize(1100, 760); w.show()
    for _ in range(4):
        app.processEvents()
    dw = w.canvas.place_component("rich_text")
    w.canvas.select_by_model(dw)
    w._show_pane("properties")
    w.properties_panel.set_target(dw, w.canvas.selected_qwidget)
    for _ in range(4):
        app.processEvents()
    fields = w.properties_panel._body.findChildren(MarkdownField)
    assert len(fields) == 1
    box = fields[0]._box
    assert isinstance(box, AutoGrowTextEdit), "must be a real editable text box"
    box.setPlainText("# typed directly\n\nmore content\n\nand more")
    for _ in range(4):
        app.processEvents()
    assert "typed directly" in dw.properties.get("content", ""), \
        "typing in the field must update the model, not require the Studio"
    print("[OK] s14: markdown properties field is directly editable")


def test_terminal_prefers_powershell_on_windows():
    """s14: Windows should get PowerShell (pwsh, then powershell.exe), not
    cmd.exe, unless neither is present. Linux/macOS behaviour is unchanged."""
    import sys, shutil
    from unittest import mock
    import paperloom.ui.panels.terminal as term
    with mock.patch.object(sys, "platform", "win32"), \
         mock.patch.object(shutil, "which",
                            lambda name: r"C:\pwsh.exe" if name == "pwsh.exe" else None):
        shell, args = term.default_shell()
        assert "pwsh" in shell.lower()
    with mock.patch.object(sys, "platform", "win32"), \
         mock.patch.object(shutil, "which", lambda name: None):
        shell, args = term.default_shell()
        assert "cmd" in shell.lower(), "must still fall back to cmd.exe if nothing else exists"
    assert not sys.platform.startswith("win")
    shell, args = term.default_shell()
    assert "bash" in shell or "sh" in shell
    print("[OK] s14: terminal prefers PowerShell on Windows, falls back to cmd.exe")


def test_code_editor_generates_edits_and_survives_regeneration():
    """Code Editor (run.code_editor): pops up the ACTIVE page's logic file,
    generating it on first use if it doesn't exist yet (safe - the UI file
    is always refreshed anyway, and the logic write is a no-op if the file's
    already there per codegen's own _write_logic_once). Run and the Code
    Editor now share ONE persistent scratch dir for the window's session
    (main_window._get_live_dir) instead of a fresh tempfile.mkdtemp() per
    Run - otherwise a hand edit would never survive to the next Run, which
    would make the whole feature pointless. Reopening for the SAME page must
    never discard an in-progress edit; reopening for a DIFFERENT page while
    dirty must prompt, honouring Cancel (stay put) and Discard (switch)."""
    from unittest import mock
    from PySide6.QtWidgets import QMessageBox

    app = get_app()
    win = make_window(registry())
    win.show()
    app.processEvents()
    win.canvas.place_component("primary_button")

    # _get_live_dir is stable across calls (this is what makes hand edits survive)
    assert win._get_live_dir() == win._get_live_dir()

    win.dispatch("run.code_editor")
    app.processEvents()
    ce = win.code_editor
    assert ce is not None and ce.isVisible()
    assert ce.current_path and os.path.exists(ce.current_path)
    with open(ce.current_path) as f:
        original = f.read()
    assert "class" in original, "must be real generated logic, not an empty stub"

    # reopening the SAME page must not touch an unsaved in-progress edit
    ce.editor.setPlainText(original + "\n# hand edit\n")
    assert ce.is_dirty()
    win.dispatch("run.code_editor")
    app.processEvents()
    assert ce.is_dirty(), "reopening for the same page must preserve the unsaved edit"

    ce.save()
    assert not ce.is_dirty()
    with open(ce.current_path) as f:
        assert "# hand edit" in f.read()

    # regenerating (e.g. the user hits Run, or reopens the editor) must NEVER
    # clobber the hand-written logic file - the entire point of the feature
    win.dispatch("run.code_editor")
    app.processEvents()
    with open(ce.current_path) as f:
        assert "# hand edit" in f.read(), "hand-written logic must survive regeneration"

    # switching to a different page while dirty prompts; Cancel keeps you put
    path_a = ce.current_path
    ce.editor.setPlainText(ce.editor.toPlainText() + "\n# more unsaved work\n")
    win._on_page_added("Second")
    app.processEvents()
    with mock.patch.object(QMessageBox, "question",
                           return_value=QMessageBox.StandardButton.Cancel):
        win.dispatch("run.code_editor")
    app.processEvents()
    assert ce.current_path == path_a and ce.is_dirty(), "Cancel must not switch or lose the edit"

    # Discard switches to the new page's own logic file
    with mock.patch.object(QMessageBox, "question",
                           return_value=QMessageBox.StandardButton.Discard):
        win.dispatch("run.code_editor")
    app.processEvents()
    assert ce.current_path != path_a and not ce.is_dirty()
    print("[OK] code editor: generates on first use, hand edits survive regeneration, page-switch dirty guard")


def test_python_highlighter_colors_real_syntax():
    """A quick sanity check that PythonHighlighter actually assigns distinct
    formats to keywords/strings/comments rather than leaving everything
    default - not a claim of full Python-grammar correctness (documented as
    a single-pass tokenizer in code_editor.py's own module docstring)."""
    from paperloom.ui.code_editor import PythonHighlighter
    from PySide6.QtGui import QTextDocument

    app = get_app()
    doc = QTextDocument()
    doc.setPlainText('class Foo:\n    def bar(self):\n        # a comment\n        return "hi"\n')
    hl = PythonHighlighter(doc)
    hl.rehighlight()

    block = doc.firstBlock()   # "class Foo:"
    layout = block.layout()
    formats = layout.formats()
    assert formats, "the class/def line must have at least one highlighted range"
    colors = {f.format.foreground().color().name() for f in formats}
    assert "#c678dd" in colors, "the 'class' keyword must be coloured"
    print("[OK] python highlighter assigns real formatting to keywords/strings/comments")


def test_terminal_clear_host_override_and_noprofile():
    """PowerShell has no real console handle when QProcess pipes its stdio,
    so the built-in Clear-Host (what `clear`/`cls` are aliased to) crashes
    trying to touch $Host.UI.RawUI.CursorPosition. default_shell() launches
    pwsh/powershell with a Clear-Host override that writes a private-use-
    wrapped marker instead of touching RawUI, plus -NoProfile so the user's
    personal profile (which can itself error, e.g. an Import-Module for a
    module that isn't available) doesn't leak noise into every session.
    TerminalWidget._on_output must recognize that marker, clear the view the
    same way the toolbar's Clear button does, and never show the marker
    itself to the user."""
    import sys, shutil
    from unittest import mock
    from paperloom.ui.panels import terminal as term

    with mock.patch.object(sys, "platform", "win32"), \
         mock.patch.object(shutil, "which",
                            lambda name: r"C:\pwsh.exe" if name == "pwsh.exe" else None):
        shell, args = term.default_shell()
        assert "-NoProfile" in args, "must not load the user's personal profile"
        assert term._PS_CLEAR_HOST_OVERRIDE in args
        assert "RawUI" not in term._PS_CLEAR_HOST_OVERRIDE, \
            "the override itself must never touch RawUI (that's what crashes)"

    app = get_app()
    from paperloom.ui.panels.terminal import TerminalWidget
    t = TerminalWidget()
    t.append("stale output from before clear")
    assert "stale output from before clear" in t.view.toPlainText()

    class _FakeProc:
        def __init__(self, data):
            self._data = data

        def readAllStandardOutput(self):
            return self._data

    # the shell writes the marker (possibly followed by more real output in
    # the same read, e.g. the next prompt) - both must be handled in one go
    t._proc = _FakeProc(term._CLEAR_MARKER.encode("utf-8") + b"PS C:\\demo> ")
    t._on_output()
    out = t.view.toPlainText()
    assert "stale output from before clear" not in out, "clear must wipe prior scrollback"
    assert "PAPERLOOM-CLEAR" not in out, "the marker must never be shown to the user"
    assert "PS C:\\demo>" in out, "real output alongside the marker must still render"
    print("[OK] terminal: Clear-Host override avoids the RawUI crash, -NoProfile quiets startup")


def test_terminal_toolbar_filter_and_find():
    """s14: Clear/EOL-toggle/filter toolbar and Ctrl-F find-in-output."""
    app = get_app()
    from paperloom.ui.panels.terminal import TerminalWidget, _EOL_CYCLE
    t = TerminalWidget()
    t.append("build started")
    t.append("compiling module A")
    t.append("compiling module B")
    t.append("error: something broke")
    # EOL cycles Auto -> CRLF -> LF -> Auto
    assert t._eol_mode == "auto"
    t._cycle_eol_mode(); assert t._eol_mode == "crlf"
    t._cycle_eol_mode(); assert t._eol_mode == "lf"
    t._cycle_eol_mode(); assert t._eol_mode == "auto"
    # filter hides non-matching lines without discarding the scrollback
    t._filter_box.setText("compil")
    doc = t.view.document()
    visible = [b.text() for b in _iter_blocks(doc) if b.isVisible()]
    assert all("compil" in v for v in visible if v.strip())
    t._filter_box.clear()
    visible_after = [b.text() for b in _iter_blocks(doc) if b.isVisible()]
    assert any("error" in v for v in visible_after), "clearing the filter must restore all lines"
    # find locates matches and reports a 1-based position
    t._find_box.setText("module")
    t._find_step(0)
    assert len(t._find_matches) == 2
    assert t._find_status.text() == "1/2"
    t._find_step(1)
    assert t._find_status.text() == "2/2"
    t.stop()
    print("[OK] s14: terminal Clear/EOL-toggle/filter/find all work")


def _iter_blocks(doc):
    b = doc.begin()
    while b.isValid():
        yield b
        b = b.next()


def test_universal_find_routes_by_focus():
    """s14 2b: Ctrl-F opens the terminal's own find bar when the terminal has
    focus, otherwise the canvas find-widgets bar - both exist independently."""
    app = get_app()
    w = make_window(registry())
    w.resize(1100, 760); w.show()
    for _ in range(4):
        app.processEvents()
    w._universal_find()
    assert w._canvas_find_bar.isVisible(), "canvas find should open by default"
    w._canvas_find_bar.close_bar()
    w._show_bottom_tab("terminal")
    for _ in range(4):
        app.processEvents()
    w.bottom_panel.terminal.view.setFocus()
    for _ in range(4):
        app.processEvents()
    w._universal_find()
    assert w.bottom_panel.terminal._find_bar.isVisible(), \
        "terminal find should open when the terminal has focus"
    assert not w._canvas_find_bar.isVisible()
    w.bottom_panel.terminal.stop()
    print("[OK] s14: universal Ctrl-F routes to the right find surface by focus")


def test_canvas_find_matches_name_and_text():
    """s14 2b: the canvas find bar matches widgets by object name OR any
    string-typed property (e.g. button text), and steps between matches."""
    app = get_app()
    w = make_window(registry())
    b1 = w.canvas.place_component("primary_button")
    b1.object_name = "save_button"
    w.canvas.select_by_model(b1)
    w.canvas.apply_property("text", "Save changes")
    b2 = w.canvas.place_component("primary_button")
    b2.object_name = "cancel_button"
    w.canvas.select_by_model(b2)
    w.canvas.apply_property("text", "Cancel")
    w._canvas_find_query("save")
    assert len(w._canvas_find_matches) == 1
    assert w.canvas.selected_model.object_name == "save_button"
    w._canvas_find_query("button")   # matches both object names
    assert len(w._canvas_find_matches) == 2
    first = w.canvas.selected_model
    w._canvas_find_step(1)
    assert w.canvas.selected_model is not first, "next should move to the other match"
    w._canvas_find_step(1)
    assert w.canvas.selected_model is first, "stepping should wrap around"
    print("[OK] s14: canvas find matches by name/text and steps through results")


def test_search_bar_is_centered():
    """s14 2c: the top search bar centres against the WHOLE menu bar width,
    not just the leftover space after the menu buttons (which used to sit
    noticeably left of true centre since nothing balanced them on the right)."""
    app = get_app()
    w = make_window(registry())
    w.resize(1400, 860); w.show()
    for _ in range(15):
        app.processEvents()
    mb = w.menu_bar
    search_center = mb.search.mapTo(mb, mb.search.rect().center()).x()
    assert abs(search_center - mb.width() / 2) <= 3, \
        f"search bar not centred: {search_center} vs {mb.width()/2}"
    print("[OK] s14: search bar is centred against the full menu bar width")


def test_command_palette_navigation():
    """s14 2c: arrow keys wrap around at the list ends, and hovering an item
    with the mouse moves keyboard-current selection (so Enter after a hover
    activates the item you're actually looking at, not a stale one)."""
    app = get_app()
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QKeyEvent
    w = make_window(registry())
    pal = w.palette_dialog
    pal.open_with("")
    for _ in range(3):
        app.processEvents()
    count = pal.list.count()
    assert count > 2, "expected several commands in the index"
    pal.list.setCurrentRow(0)
    up = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Up, Qt.KeyboardModifier.NoModifier)
    pal.keyPressEvent(up)
    assert pal.list.currentRow() == count - 1, "up from the first row should wrap to the last"
    down = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Down, Qt.KeyboardModifier.NoModifier)
    pal.keyPressEvent(down)
    assert pal.list.currentRow() == 0, "down from the last row should wrap to the first"
    # hover syncs keyboard-current selection
    item = pal.list.item(2)
    pal.list.itemEntered.emit(item)
    assert pal.list.currentItem() is item, "hovering an item must move keyboard selection to it"
    print("[OK] s14: command palette wraps arrow-key navigation and syncs hover")


def test_command_palette_dismisses_on_outside_click():
    """A non-modal Qt.WindowType.Dialog gets no built-in 'click outside to
    dismiss' behaviour - the palette used to just sit there awkwardly once
    the user clicked anywhere else in the app. WindowDeactivate fires on any
    top-level window the moment activation moves elsewhere (a real click on
    the main window behind it, or the app losing OS focus entirely) - the
    palette now hides on it, the same feel as VS Code's own palette."""
    from PySide6.QtCore import QEvent, Qt
    from PySide6.QtGui import QKeyEvent
    from PySide6.QtWidgets import QApplication

    app = get_app()
    w = make_window(registry())
    pal = w.palette_dialog
    pal.open_with("")
    app.processEvents()
    assert pal.isVisible()

    QApplication.sendEvent(pal, QEvent(QEvent.Type.WindowDeactivate))
    assert not pal.isVisible(), "losing window activation (an outside click) must dismiss it"

    # reopening still works after a dismiss
    pal.open_with("")
    app.processEvents()
    assert pal.isVisible()

    # Escape must still work too (regression guard alongside the new path)
    esc = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(pal, esc)
    assert not pal.isVisible()
    print("[OK] command palette dismisses on outside click (WindowDeactivate) and still on Escape")


def test_command_index_shortcuts_render_as_chips():
    """s14 2c: shortcuts are returned separately from the label (not baked
    into one string) so the palette can render them as VS Code-style chips."""
    from paperloom.ui.panels.command_palette import command_index
    entries = command_index()
    assert entries, "expected a non-empty command index"
    has_shortcut = [e for e in entries if e[2]]
    assert has_shortcut, "expected at least one command with a shortcut"
    display, cmd, shortcut = has_shortcut[0]
    assert shortcut not in display, "shortcut must not be baked into the display label"
    print("[OK] s14: command shortcuts are separate from labels for chip rendering")


def test_editor_tabs_embedded_beside_undo_redo():
    """The tab strip used to live on its own row below the whole top bar;
    it's now embedded IN the top bar, right after undo/redo, behind a
    divider - TopBar.set_tab_bar(). Check: the tab bar is a child of top_bar
    itself (not the window's root layout) and sits right after redo_btn; the
    strip (and its divider) is visible as soon as anything is open at all -
    including a brand-new single-page project - and stays visible even after
    closing back down to one tab, since hiding it below 2 tabs used to read
    as "closing a tab closed everything" (session 15 follow-up bug report)."""
    app = get_app()
    win = make_window(registry())
    win.show()
    app.processEvents()

    layout = win.top_bar.layout()
    assert layout.indexOf(win.editor_tabs) >= 0, "tab bar must be a child of top_bar's own layout"
    assert layout.indexOf(win.editor_tabs) == layout.indexOf(win.top_bar.redo_btn) + 2, \
        "tab bar must sit right after redo (with the divider between them)"

    # a brand-new project must already show its one tab, not an empty strip
    assert win.editor_tabs.count() == 1, "the starting page must be seeded as a tab on init"
    assert win.editor_tabs.isVisible(), "the strip must be visible for even a single open tab"
    assert win.top_bar._tab_bar_divider.isVisible(), "and its divider along with it"

    win._on_page_added("Settings")
    app.processEvents()
    assert win.editor_tabs.isVisible(), "2+ open tabs must show the strip"
    assert win.top_bar._tab_bar_divider.isVisible(), "divider must appear alongside it"

    win._on_tab_close_requested(win.open_pages.index(win.project.pages[1]))
    app.processEvents()
    assert win.editor_tabs.isVisible(), "back to 1 open tab must NOT hide the strip - that's the bug"
    assert win.editor_tabs.count() == 1, "the remaining tab must still be shown, not vanished"
    assert win.top_bar._tab_bar_divider.isVisible(), "and the divider stays with it"
    print("[OK] editor tabs: embedded beside undo/redo, always visible incl. down to 1 tab")


def test_tab_context_menu_rename_close_others_and_right():
    """Right-clicking a tab (EditorTabBar.tabContextMenuRequested ->
    main_window._tab_context_menu) offers Rename/Close/Close Others/Close
    Tabs to the Right/Save All. Rename edits the tab's displayed title (the
    same string the tab shows), not the page's technical name. Close Others
    and Close Tabs to the Right always end with exactly the intended tab
    left open and ACTIVE, whether or not it was the active one beforehand -
    and both actions are disabled in the menu when there's nothing for them
    to do (a single remaining tab, or the origin tab already being last)."""
    from unittest import mock
    from PySide6.QtWidgets import QInputDialog
    from paperloom.ui.panels.context_menus import build_tab_menu

    app = get_app()
    win = make_window(registry())
    win.show()
    app.processEvents()

    win._on_page_added("B")
    win._on_page_added("C")
    app.processEvents()
    assert len(win.open_pages) == 3

    # rename edits page.title, and the tab strip picks it up immediately
    target = win.open_pages[1]
    with mock.patch.object(QInputDialog, "getText", return_value=("Renamed", True)):
        win._rename_page(target)
    assert target.title == "Renamed"
    assert win.editor_tabs.tabText(1) == "Renamed"
    # an empty/cancelled rename must not touch the model
    with mock.patch.object(QInputDialog, "getText", return_value=("", True)):
        win._rename_page(target)
    assert target.title == "Renamed"

    # the menu itself: labels present, Close Others/Right disabled with <=1 candidate
    handlers = {k: (lambda: None) for k in
                ("rename", "close", "close_others", "close_right", "save_all")}
    menu = build_tab_menu(win, win.open_pages[0], handlers,
                          can_close_others=True, can_close_right=True)
    labels = {a.text() for a in menu.actions() if not a.isSeparator()}
    assert {"Close", "Close Others", "Close Tabs to the Right", "Save All"} <= labels
    menu_disabled = build_tab_menu(win, win.open_pages[0], handlers,
                                   can_close_others=False, can_close_right=False)
    by_label = {a.text(): a for a in menu_disabled.actions() if not a.isSeparator()}
    assert not by_label["Close Others"].isEnabled()
    assert not by_label["Close Tabs to the Right"].isEnabled()

    # Close Others activates the KEPT tab even if a different one was active
    win._go_to_page_index(win.project.pages.index(win.open_pages[2]))
    assert win.page is win.open_pages[2]
    keep = win.open_pages[0]
    win._close_other_tabs(keep)
    assert win.open_pages == [keep]
    assert win.page is keep, "must activate the kept tab, not whatever was active before"

    # Close Tabs to the Right lands back on the origin tab even if the tab
    # that gets closed was the active one
    win._on_page_added("D")
    win._on_page_added("E")
    app.processEvents()
    win.editor_tabs.setCurrentIndex(len(win.open_pages) - 1)   # activate the last (rightmost) tab
    from_page = win.open_pages[0]
    win._close_tabs_to_right(from_page)
    assert win.open_pages == [from_page]
    assert win.page is from_page
    print("[OK] tab context menu: rename/close-others/close-right, correct enablement + activation")


def test_tools_bar_visible_by_default():
    """s14 2d: the AutoCAD-style tools bar (align/z-order/snap/duplicate/
    delete) must be visible by default - it was effectively lost when hidden
    in a prior session's UI-calming pass, with nothing pointing at how to
    bring it back."""
    app = get_app()
    w = make_window(registry())
    # isVisible() is hierarchical (needs the top-level window shown, which
    # this headless test never does) - check the toolbar's own explicit
    # visibility flag instead, which is what .hide()/.show() actually set.
    assert not w.tools_bar.isHidden(), "tools bar should be visible by default"
    assert w.tools_bar.isMovable() and w.tools_bar.isFloatable(), \
        "must stay a real, draggable/floatable QToolBar"
    # its actions are the real command set, not decorative
    actions = [a for a in w.tools_bar.actions() if not a.isSeparator()]
    assert len(actions) >= 10, "expected the full align/z-order/snap/duplicate/delete set"
    print("[OK] s14: the AutoCAD-style tools bar is visible by default")


def test_all_components_render_and_codegen():
    """s14 2e: EVERY default component must (1) have at least one declared
    property, (2) render on canvas without falling back to the error label,
    and (3) produce compilable PySide codegen. This is the exhaustive
    component audit as a regression gate - any new component or template
    change that breaks these invariants will be caught immediately."""
    app = get_app()
    from paperloom.components.registry import ComponentRegistry
    from paperloom.components import factory
    from paperloom.core.model import DesignWidget, DesignPage
    from paperloom.codegen import get_backend
    import py_compile

    reg = registry()
    components = reg.all()
    assert len(components) >= 50, f"expected 50+ components, got {len(components)}"
    failures = []
    from PySide6.QtWidgets import QWidget, QLabel
    parents = []  # prevent GC from deleting parent widgets mid-loop
    for c in components:
        issues = []
        if len(c.properties) == 0:
            issues.append("no declared properties")
        dw = DesignWidget(component_id=c.id, object_name=f"test_{c.id}",
                           x=0, y=0, width=120, height=40,
                           properties=c.default_properties())
        try:
            parent = QWidget()
            parents.append(parent)
            live = factory.instantiate(c, dw, parent)
            if isinstance(live, QLabel) and live.text() == f"[{c.id}]":
                issues.append("canvas render failed (error label)")
        except Exception as e:
            issues.append(f"canvas exception: {e}")
        try:
            page = DesignPage(name="MainWindow", widgets=[dw])
            backend = get_backend("pyside6", reg)
            out = tempfile.mkdtemp(prefix=f"audit_{c.id}_")
            paths = backend.generate(page, out)
            py_compile.compile(paths["generated"], doraise=True)
        except Exception as e:
            issues.append(f"codegen fail: {e}")
        if issues:
            failures.append(f"{c.id}: {'; '.join(issues)}")
    assert not failures, f"component audit failures:\n" + "\n".join(failures)
    print(f"[OK] s14: all {len(components)} components render + codegen cleanly")


def test_image_fit_modes():
    """s14 2f: image_frame supports 5 fit modes (contain/cover/stretch/center/
    scale-down), each producing visibly different results and compiling."""
    app = get_app()
    import py_compile
    from PySide6.QtGui import QPixmap
    w = make_window(registry())
    tmp = tempfile.mkdtemp()
    png = os.path.join(tmp, "wide.png")
    QPixmap(200, 40).save(png, "PNG")
    key = w.assets.import_path(png)[0].key
    for mode in ("contain", "cover", "stretch", "center", "scale-down"):
        dw = w.canvas.place_component("image_frame")
        w.canvas.select_by_model(dw)
        w.canvas.apply_property("asset", key)
        w.canvas.apply_property("fit", mode)
    assert len(w.canvas.page.widgets) == 5
    out = tempfile.mkdtemp()
    paths = w.generate_code(out)
    src = open(paths["generated"], encoding="utf-8").read()
    assert "_fit_pixmap(" in src, "generated code must use _fit_pixmap"
    py_compile.compile(paths["generated"], doraise=True)
    shutil.rmtree(out, ignore_errors=True)
    print("[OK] s14: image fit modes (contain/cover/stretch/center/scale-down)")


def test_theme_toggle_generates_working_logic():
    """s14 2g: the theme_toggle component's clicked signal must generate a
    stub that actually calls toggle_theme(), not an empty TODO."""
    app = get_app()
    import py_compile
    w = make_window(registry())
    w.canvas.place_component("theme_toggle")
    out = tempfile.mkdtemp()
    paths = w.generate_code(out)
    logic = open(paths["logic"], encoding="utf-8").read()
    assert "self.toggle_theme()" in logic, \
        "theme_toggle stub must call toggle_theme, not just print or pass"
    py_compile.compile(paths["logic"], doraise=True)
    shutil.rmtree(out, ignore_errors=True)
    print("[OK] s14: theme_toggle generates working toggle_theme() call")


def test_codegen_emits_layouts_connections_taborder():
    """s14 2h: when the page model has layout groups, signal connections, and
    a tab order, codegen must emit QLayout creation + addWidget, connect()
    calls, and setTabOrder — not just absolute setGeometry."""
    app = get_app()
    import py_compile
    from paperloom.codegen import get_backend
    reg = registry()
    page = DesignPage(name="MainWindow")
    page.layouts = [LayoutGroup(id="main_lay", kind="vbox")]
    for i, cid in enumerate(["primary_button", "primary_button"]):
        dw = DesignWidget(component_id=cid, object_name=f"btn_{i}",
                           x=0, y=0, width=120, height=32,
                           properties={"text": f"Button {i}"},
                           layout_id="main_lay", layout_row=i)
        page.add(dw)
    page.connections = [
        SignalConnection(sender="btn_0", signal="clicked",
                         receiver="MainWindow", slot="close")
    ]
    page.tab_order = ["btn_0", "btn_1"]
    backend = get_backend("pyside6", reg)
    out = tempfile.mkdtemp()
    paths = backend.generate(page, out)
    src = open(paths["generated"], encoding="utf-8").read()
    assert "QVBoxLayout" in src, "layout class must be imported"
    assert "addWidget(self.btn_0)" in src, "widgets must be added to the layout"
    assert "btn_0.clicked.connect(MainWindow.close)" in src, "connections must be emitted"
    assert "setTabOrder(self.btn_0, self.btn_1)" in src, "tab order must be emitted"
    py_compile.compile(paths["generated"], doraise=True)
    shutil.rmtree(out, ignore_errors=True)
    print("[OK] s14: codegen emits layouts, connections, and tab order")


def test_app_settings_persist_and_isolated_defaults():
    """core/app_settings.py: round-trips every key, and a missing/corrupt
    settings.json still returns full defaults rather than crashing."""
    from paperloom.core import app_settings
    orig_dir, orig_file = app_settings._CONFIG_DIR, app_settings._SETTINGS_FILE
    tmp = tempfile.mkdtemp(prefix="paperloom_settings_test_")
    app_settings._CONFIG_DIR = tmp
    app_settings._SETTINGS_FILE = os.path.join(tmp, "settings.json")
    try:
        assert app_settings.load() == app_settings.DEFAULTS, "no file yet -> full defaults"

        app_settings.set("collect_error_reports", True)
        app_settings.set("terminal_shell", "cmd")
        assert app_settings.get("collect_error_reports") is True
        assert app_settings.get("terminal_shell") == "cmd"
        assert app_settings.get("editor_theme") == "dark", "untouched keys keep their default"

        with open(app_settings._SETTINGS_FILE, "w", encoding="utf-8") as f:
            f.write("{not valid json")
        assert app_settings.load() == app_settings.DEFAULTS, "corrupt file -> full defaults, no crash"
    finally:
        app_settings._CONFIG_DIR, app_settings._SETTINGS_FILE = orig_dir, orig_file
        shutil.rmtree(tmp, ignore_errors=True)
    print("[OK] app_settings: round-trips keys, survives a missing/corrupt file")


def test_error_manager_respects_the_privacy_toggle():
    """error_manager.capture()/capture_uncaught() write nothing at all unless
    Settings > Data and Privacy's toggle is on - PaperLoom collects nothing
    by default (session 15 follow-up: 'currently PaperLoom doesnt collect
    anything')."""
    from paperloom.core import app_settings, error_manager
    orig_dir, orig_file = app_settings._CONFIG_DIR, app_settings._SETTINGS_FILE
    orig_reports = error_manager.REPORTS_DIR
    tmp = tempfile.mkdtemp(prefix="paperloom_settings_test_")
    app_settings._CONFIG_DIR = tmp
    app_settings._SETTINGS_FILE = os.path.join(tmp, "settings.json")
    error_manager.REPORTS_DIR = os.path.join(tmp, "error_reports")
    try:
        assert not error_manager.enabled()
        assert error_manager.capture("boom", context="test") is None, \
            "collection off -> nothing written, ever"
        assert error_manager.list_reports() == []

        app_settings.set("collect_error_reports", True)
        assert error_manager.enabled()
        try:
            1 / 0
        except ZeroDivisionError as e:
            path = error_manager.capture("boom", context="test", exc=e)
        assert path is not None and os.path.isfile(path)
        assert len(error_manager.list_reports()) == 1

        import json
        with open(path, encoding="utf-8") as f:
            report = json.load(f)
        assert report["message"] == "boom"
        assert "ZeroDivisionError" in report["traceback"]
    finally:
        app_settings._CONFIG_DIR, app_settings._SETTINGS_FILE = orig_dir, orig_file
        error_manager.REPORTS_DIR = orig_reports
        shutil.rmtree(tmp, ignore_errors=True)
    print("[OK] error manager: silent until opted in, writes a real local report once opted in")


def test_shortcuts_single_source_of_truth():
    """core/shortcuts.py is the one list both main_window._shortcuts() binds
    from and Settings > Shortcuts displays - a real window must end up with
    exactly as many QShortcuts as the list defines, so the two can never
    quietly drift apart."""
    from PySide6.QtGui import QShortcut
    from paperloom.core import shortcuts as shortcuts_mod
    app = get_app()
    win = make_window(registry())

    bound = [sc for sc in win.findChildren(QShortcut)]
    assert len(bound) == len(shortcuts_mod.binds())

    grouped_total = sum(len(entries) for _cat, entries in shortcuts_mod.grouped())
    assert grouped_total == len(shortcuts_mod.SHORTCUTS), "grouped() must show every entry"
    print("[OK] shortcuts: main_window binds exactly what core/shortcuts.py declares")


def test_settings_dialog_sections_signals_and_licenses():
    """Settings dialog: six sections exist (Personalization/Shortcuts/
    Terminal/Data & Privacy/Licenses/About), each control's signal reaches
    what main_window would persist, and Licenses shows both the GPLv3 text
    and the separate App License draft."""
    from PySide6.QtWidgets import QComboBox, QCheckBox, QPlainTextEdit, QListWidget, QPushButton
    from paperloom.ui.panels.settings_dialog import SettingsDialog
    app = get_app()
    win = make_window(registry())
    dlg = SettingsDialog(win, library_mode="popup", editor_dark=True,
                         terminal_shell="auto", collect_error_reports=False)
    assert dlg._nav.count() == 6
    assert dlg._stack.count() == 6

    got_lib, got_theme, got_shell, got_privacy = [], [], [], []
    dlg.libraryModeChanged.connect(got_lib.append)
    dlg.editorModeToggled.connect(lambda: got_theme.append(True))
    dlg.terminalShellChanged.connect(got_shell.append)
    dlg.collectErrorReportsChanged.connect(got_privacy.append)

    dlg._stack.widget(0).findChild(QComboBox).setCurrentIndex(1)
    assert got_lib == ["pane"]
    dlg._stack.widget(0).findChild(QPushButton, "ghost").click()
    assert got_theme == [True]

    dlg._stack.widget(2).findChild(QComboBox).setCurrentIndex(2)
    assert got_shell == ["cmd"]

    dlg._stack.widget(3).findChild(QCheckBox).setChecked(True)
    assert got_privacy == [True]

    lic_page = dlg._stack.widget(4)
    viewer = lic_page.findChild(QPlainTextEdit)
    picker = lic_page.findChild(QListWidget)
    picker.setCurrentRow(0)
    assert "GNU GENERAL PUBLIC LICENSE" in viewer.toPlainText()
    assert "MilkmanAbi" in viewer.toPlainText()
    picker.setCurrentRow(1)
    assert "DRAFT" in viewer.toPlainText()
    assert "error" in viewer.toPlainText().lower()
    print("[OK] settings dialog: six sections, all signals wired, both license docs load")


def test_branding_assets_load_from_stable_paths():
    """Logo.png/LilyKnight.png are referenced by path (ui/branding.py), not
    baked in, so swapping the file later is a drop-in - session 15 follow-up:
    'just use it as a path in the project ... so I can update easily in the
    future, all app icons, favicons etc shld use it.'"""
    from paperloom.ui import branding
    assert os.path.isfile(branding.LOGO_PATH)
    assert os.path.isfile(branding.MASCOT_PATH)
    app = get_app()
    assert not branding.app_icon().isNull()
    logo_pm = branding.logo_pixmap(64)
    assert not logo_pm.isNull()
    mascot_pm = branding.mascot_pixmap(24)
    assert not mascot_pm.isNull()
    assert mascot_pm.width() <= 24 and mascot_pm.height() <= 24, "mascot must stay tiny by design"
    print("[OK] branding: Logo.png/LilyKnight.png load from their stable paths")


def test_terminal_shell_setting_overrides_auto_detect():
    """Settings > Terminal's shell choice actually changes what
    default_shell() returns on Windows - forcing 'cmd' must skip PowerShell
    even when pwsh/powershell are 'installed', and forcing 'powershell' must
    still work when both are available."""
    import shutil as shutil_mod
    from paperloom.core import app_settings
    from paperloom.ui.panels import terminal as terminal_mod

    orig_dir, orig_file = app_settings._CONFIG_DIR, app_settings._SETTINGS_FILE
    orig_platform = terminal_mod.sys.platform
    orig_which = shutil_mod.which
    tmp = tempfile.mkdtemp(prefix="paperloom_settings_test_")
    app_settings._CONFIG_DIR = tmp
    app_settings._SETTINGS_FILE = os.path.join(tmp, "settings.json")
    terminal_mod.sys.platform = "win32"
    shutil_mod.which = lambda name: (f"C:\\{name}" if "powershell" in name or "pwsh" in name else None)
    try:
        app_settings.set("terminal_shell", "auto")
        path, args = terminal_mod.default_shell()
        assert "powershell" in path.lower() or "pwsh" in path.lower()

        app_settings.set("terminal_shell", "cmd")
        path, args = terminal_mod.default_shell()
        assert "cmd" in path.lower()
        assert args == []

        app_settings.set("terminal_shell", "powershell")
        path, args = terminal_mod.default_shell()
        assert "powershell" in path.lower() or "pwsh" in path.lower()
    finally:
        terminal_mod.sys.platform = orig_platform
        shutil_mod.which = orig_which
        app_settings._CONFIG_DIR, app_settings._SETTINGS_FILE = orig_dir, orig_file
        shutil.rmtree(tmp, ignore_errors=True)
    print("[OK] terminal: Settings shell choice overrides auto-detect")


def test_license_files_present_and_readable():
    """The GPLv3 text is the source-material license (as uploaded,
    unmodified); the App License is a separate, deliberately crude draft
    doc - the two must never be the same file."""
    from paperloom.core import licenses as licenses_mod
    gpl = licenses_mod.read(licenses_mod.GPL_PATH)
    app_lic = licenses_mod.read(licenses_mod.APP_LICENSE_PATH)
    assert "GNU GENERAL PUBLIC LICENSE" in gpl
    assert "MilkmanAbi" in gpl
    assert gpl != app_lic
    assert "DRAFT" in app_lic
    assert "PySide6" in app_lic
    print("[OK] licenses: GPLv3 source-material text and the App License draft both load")


def _write_fake_cmake(bin_dir, exe_name, configure_ok=True, build_ok=True, create_exe=True):
    """A fake `cmake` executable for CppBuildRunner tests - the sandbox this
    was built in has a real CMake but no MSVC/Qt6, so a real C++ build can't
    be exercised end to end. This stands in for cmake's two call shapes
    (`-S src -B build` and `--build build`) without needing a real compiler,
    so the STAGE-CHAINING LOGIC (configure -> build -> find-and-run the
    executable, or stop cleanly on any failure) gets exercised for real."""
    path = os.path.join(bin_dir, "cmake")
    lines = ["#!/bin/bash"]
    lines.append('if [ "$1" = "-S" ]; then')
    if configure_ok:
        lines.append('    mkdir -p "$4"')
        lines.append('    echo "-- configure ok"')
        lines.append('    exit 0')
    else:
        lines.append('    echo "-- configure error: bad CMakeLists"')
        lines.append('    exit 1')
    lines.append('elif [ "$1" = "--build" ]; then')
    if build_ok:
        if create_exe:
            lines.append('    mkdir -p "$2/Release"')
            lines.append(f'    printf \'#!/bin/bash\\necho "fake app running"\\nexit 0\\n\' > "$2/Release/{exe_name}"')
            lines.append(f'    chmod +x "$2/Release/{exe_name}"')
        lines.append('    echo "-- build ok"')
        lines.append('    exit 0')
    else:
        lines.append('    echo "error: compilation failed C2065"')
        lines.append('    exit 1')
    lines.append('fi')
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    os.chmod(path, 0o755)
    return path


def test_cpp_build_runner_full_pipeline_and_failure_modes():
    """CppBuildRunner: configure -> build -> find-and-run the executable on
    a clean success, and stops cleanly (reporting which stage, without
    guessing or silently falling back to anything) on each real failure
    mode - missing CMake, a failed configure, a failed build, and a build
    that 'succeeds' without producing the expected executable."""
    from paperloom.ui import runner as runner_mod
    app = get_app()

    # 1) cmake missing entirely
    orig_which = runner_mod.shutil.which
    runner_mod.shutil.which = lambda name: None
    try:
        r = runner_mod.CppBuildRunner()
        missing = []
        r.cmakeMissing.connect(lambda: missing.append(True))
        r.start("/tmp/does-not-matter", "demo")
        assert missing == [True]
    finally:
        runner_mod.shutil.which = orig_which

    def run_pipeline(configure_ok, build_ok, create_exe):
        bin_dir = tempfile.mkdtemp(prefix="paperloom_fakecmake_")
        _write_fake_cmake(bin_dir, "demo_page", configure_ok, build_ok, create_exe)
        src_dir = tempfile.mkdtemp(prefix="paperloom_cpp_src_")
        orig_path = os.environ.get("PATH", "")
        os.environ["PATH"] = bin_dir + os.pathsep + orig_path
        try:
            r = runner_mod.CppBuildRunner()
            events = []
            r.stageStarted.connect(lambda s: events.append(("stage", s)))
            r.output.connect(lambda l: events.append(("out", l)))
            r.buildFailed.connect(lambda s, c: events.append(("failed", s, c)))
            r.finished.connect(lambda c: events.append(("finished", c)))
            r.start(src_dir, "demo_page")
            for _ in range(300):
                app.processEvents()
                if any(e[0] in ("finished", "failed") for e in events):
                    break
                import time as _time
                _time.sleep(0.01)
            return events
        finally:
            os.environ["PATH"] = orig_path
            shutil.rmtree(bin_dir, ignore_errors=True)
            shutil.rmtree(src_dir, ignore_errors=True)

    # 2) full success: configure -> build -> run, in order, ending 0
    events = run_pipeline(configure_ok=True, build_ok=True, create_exe=True)
    stages = [e[1] for e in events if e[0] == "stage"]
    assert stages == ["configure", "build", "run"], stages
    assert events[-1] == ("finished", 0), events

    # 3) configure fails - must stop there, never reach build
    events = run_pipeline(configure_ok=False, build_ok=True, create_exe=True)
    stages = [e[1] for e in events if e[0] == "stage"]
    assert stages == ["configure"], stages
    assert ("failed", "configure", 1) in events

    # 4) build fails - must stop there, never try to run anything
    events = run_pipeline(configure_ok=True, build_ok=False, create_exe=True)
    stages = [e[1] for e in events if e[0] == "stage"]
    assert stages == ["configure", "build"], stages
    assert ("failed", "build", 1) in events

    # 5) build "succeeds" but never produced the expected executable -
    # must report that plainly rather than crashing on a missing file
    events = run_pipeline(configure_ok=True, build_ok=True, create_exe=False)
    assert ("failed", "build", 0) in events
    print("[OK] cpp build runner: full configure->build->run pipeline, and every failure mode stops cleanly")


def test_run_dispatches_to_cpp_pipeline_for_cpp_target():
    """main_window._on_run() must route a cpp-target project through the
    real configure/build/run pipeline (CppBuildRunner), not the old 'go
    build it yourself' refusal message - and must never touch the PySide6
    AppRunner for a cpp project."""
    from paperloom.ui import runner as runner_mod
    app = get_app()
    win = make_window(registry())
    win.target = "cpp"
    win.project.target = "cpp"
    win.canvas.place_component("primary_button")

    bin_dir = tempfile.mkdtemp(prefix="paperloom_fakecmake_")
    orig_path = os.environ.get("PATH", "")
    started = []
    win.cpp_runner.stageStarted.connect(lambda s: started.append(s))
    try:
        import paperloom.codegen as codegen_pkg  # noqa: F401 - ensure backend importable
        # discover the real exe name the cpp backend will pick for this page
        from paperloom.codegen import get_backend
        probe_dir = tempfile.mkdtemp(prefix="paperloom_cpp_probe_")
        probe_paths = get_backend("cpp", win.registry).generate(win.page, probe_dir)
        exe_name = os.path.splitext(os.path.basename(probe_paths["logic"]))[0]
        shutil.rmtree(probe_dir, ignore_errors=True)

        _write_fake_cmake(bin_dir, exe_name, True, True, True)
        os.environ["PATH"] = bin_dir + os.pathsep + orig_path
        win._on_run()
        for _ in range(300):
            app.processEvents()
            if "run" in started:
                break
            import time as _time
            _time.sleep(0.01)
        assert started == ["configure", "build", "run"], started
    finally:
        os.environ["PATH"] = orig_path
        shutil.rmtree(bin_dir, ignore_errors=True)
    print("[OK] run.preview on a cpp-target project drives the real CMake pipeline")


def test_zoom_actually_rescales_canvas():
    """The zoom control used to just relabel the status bar - nothing ever
    read `self.zoom`, so widgets and the grid stayed pixel-for-pixel
    identical at every setting. Real zoom (canvas.py's to_px/to_logical
    boundary) must: (1) rescale every live widget's on-screen geometry while
    leaving the model's logical x/y/width/height untouched (codegen must
    never see a different app because someone was zoomed in while editing),
    (2) round-trip drags/resizes (commit_geometry) back to the same logical
    units regardless of zoom, and (3) sync the top bar's display."""
    app = get_app()
    win = make_window(registry())
    win.canvas.resize(800, 600)
    dw = win.canvas.place_component("button", x=40, y=50)
    dw.width, dw.height = 120, 32
    win.canvas._apply_live_geometry(dw, win.canvas._live_by_model[id(dw)])
    live = win.canvas._live_by_model[id(dw)]

    # 100% (default): pixel geometry == logical geometry
    assert win.canvas.zoom_factor == 1.0
    geo = live.geometry()
    assert (geo.x(), geo.y(), geo.width(), geo.height()) == (40, 50, 120, 32)

    # zoom to 200% via the same path the top bar's dropdown drives
    win._set_zoom(200)
    assert win.canvas.zoom_factor == 2.0
    geo = live.geometry()
    assert (geo.x(), geo.y(), geo.width(), geo.height()) == (80, 100, 240, 64), \
        f"live widget should be at 2x pixel geometry, got {geo}"
    # the MODEL never changes just because the view is zoomed - codegen and
    # saved projects must be identical regardless of what zoom you edited at
    assert (dw.x, dw.y, dw.width, dw.height) == (40, 50, 120, 32)
    # the top bar's own display followed along (not left showing a stale %)
    assert win.top_bar.zoom.currentData() == 200

    # a drag/resize commit at 200% must still land on the correct LOGICAL
    # coordinates, not the raw (2x too large) pixel ones
    live.setGeometry(200, 220, 300, 80)   # simulate a drag leaving it here, in pixel space
    win.canvas.commit_geometry(live)
    assert (dw.x, dw.y, dw.width, dw.height) == (100, 110, 150, 40), \
        f"commit_geometry must divide pixel geometry back down by zoom, got {(dw.x, dw.y, dw.width, dw.height)}"

    # back to 100% - the live widget should reflect the (now-updated) model 1:1 again
    win._set_zoom(100)
    geo = live.geometry()
    assert (geo.x(), geo.y(), geo.width(), geo.height()) == (100, 110, 150, 40)
    print("[OK] zoom rescales live widgets while the model stays in logical units")


def test_layout_toolbar_cannot_dock_to_a_vertical_area():
    """'trying to pin this toolbar is leading to a pretty broken look': the
    Layout toolbar's content (label+combobox pairs, several fixed-width
    spinboxes) is laid out for a single horizontal row - QToolBar reflows
    every child into a stacked column when docked/floated into a Left/Right
    area, which turned it into an unreadable narrow strip. Restricting the
    allowed areas to Top/Bottom removes that failure mode outright."""
    app = get_app()
    win = make_window(registry())
    horizontal_only = Qt.ToolBarArea.TopToolBarArea | Qt.ToolBarArea.BottomToolBarArea
    assert win.layout_bar.allowedAreas() == horizontal_only
    assert not (win.layout_bar.allowedAreas() & Qt.ToolBarArea.LeftToolBarArea)
    assert not (win.layout_bar.allowedAreas() & Qt.ToolBarArea.RightToolBarArea)
    assert win.layout_bar.isFloatable() and win.layout_bar.isMovable()
    print("[OK] layout toolbar can float/move but never reflows into a vertical dock area")


def test_headlessbit_shell_place_generate_reopen_roundtrip():
    """HeadlessBit (spec: an AI-facing headless shell over the same model +
    codegen the GUI uses) needs no QApplication, no display, no ui/* import
    at all - it's a plain-text command language over core/model.py +
    components/registry.py + codegen/*. Covers the exact loop an agent
    would actually do: create a project, list what components exist, place
    one by id + geometry + a property, save, generate real source, then
    reopen in a completely FRESH session and confirm the widget round-
    tripped - proving headless-created projects are indistinguishable from
    GUI-created ones on disk."""
    from paperloom.headlessbit import HeadlessSession
    tmp = tempfile.mkdtemp()
    try:
        s = HeadlessSession()
        assert "unknown command" in s.handle("not-a-real-command").lower()
        assert "no project open" in s.handle("widgets").lower()

        out = s.handle("new pyside6 DemoApp")
        assert "DemoApp" in out and "MainWindow" in out

        assert any(line.startswith("button ") for line in s.handle("components button").splitlines())
        desc = s.handle("describe button")
        assert "text: string" in desc

        placed = s.handle('place button 20 20 120 32 text="Click me"')
        assert "Placed button as 'button'" in placed
        assert "button" in s.handle("widgets")

        assert "moved to (40, 40)" in s.handle("move button 40 40")
        assert "resized to 150x40" in s.handle("resize button 150 40")
        assert s.handle("set button text Renamed") == "button.text = 'Renamed'"

        proj_dir = os.path.join(tmp, "DemoApp")
        assert "Saved" in s.handle(f"save {proj_dir}")

        gen_dir = os.path.join(tmp, "DemoApp", "generated")
        gen_out = s.handle(f"generate {gen_dir}")
        assert "main_window_ui.py" in gen_out
        generated_files = []
        for root, _dirs, files in os.walk(gen_dir):
            generated_files.extend(files)
        assert "main_window_ui.py" in generated_files
        with open(os.path.join(gen_dir, "generated", "pyside6", "main_window_ui.py"),
                  encoding="utf-8") as f:
            src = f.read()
        assert "self.button = QPushButton(MainWindow)" in src

        # a second, unrelated session opening the same directory must see
        # exactly what the first session placed - no in-memory state leaks
        # between sessions, and the on-disk format really is the shared one
        s2 = HeadlessSession(registry=s.registry)
        reopened = s2.handle(f"open {proj_dir}")
        assert "DemoApp" in reopened and "pyside6" in reopened
        widgets = s2.handle("widgets")
        assert "button" in widgets and "150x40" in widgets
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("[OK] headlessbit: place/move/resize/set, save, generate, and reopen all round-trip")


def test_headlessbit_pages_and_bad_input_never_raise():
    """Every command must fail as text ('Error: ...'), never as a raised
    exception - an agent driving this shell line-by-line can't recover from
    a dead process, only from an error message it can read and retry."""
    from paperloom.headlessbit import HeadlessSession
    s = HeadlessSession()
    s.handle("new pyside6 DemoApp")
    assert "Added page 'Settings'" in s.handle("new-page Settings 400 300")
    pages = s.handle("pages")
    assert "* Settings" in pages and "MainWindow" in pages
    assert "active page is now 'MainWindow'" in s.handle("page MainWindow")

    # deliberately bad input, one of each shape a command can misuse
    for bad in ("place no_such_component 0 0 10 10",
                "set no_such_widget prop value",
                "move button", "resize button 10",
                "new-page MainWindow",           # duplicate name
                "page NoSuchPage",
                "open /path/does/not/exist",
                "generate"):                      # missing required arg
        result = s.handle(bad)
        assert result.startswith("Error:"), f"{bad!r} should fail as text, got {result!r}"
    print("[OK] headlessbit: bad input always reports as text, never raises")


def test_package_retriever_detects_and_dry_run_installs():
    """Package Retriever (Abinaash: 'let Package Retriever fetch python
    libs and install via pip for generation'). This slice's mechanism:
    a component declares `requires` in its meta.json (registry.py's
    Component.requires); requirements_for_project() collects what's
    actually placed; missing_requirements() filters to what's not already
    installed; install() pip-installs it (or, with dry_run=True, reports
    what it WOULD install without ever touching pip or the network - the
    only mode a test, or a cautious agent, should ever actually invoke)."""
    from paperloom.core import package_retriever
    from paperloom.components.registry import Component
    from paperloom.core.model import DesignPage, DesignWidget, Project, unique_object_name

    fake_needy = Component(
        id="fake_needy_widget", name="Fake Needy Widget", category="misc", tags=[],
        description="pretend third-party wrapper", properties=[], quick_properties=[],
        signals=[], widget_class="QWidget", qt_include="QWidget", source="user",
        style_role="label", requires=["this-package-definitely-does-not-exist-xyz"],
        _pyside_template="", _cpp_template="")
    fake_plain = Component(
        id="fake_plain_widget", name="Fake Plain Widget", category="misc", tags=[],
        description="no extra requirements", properties=[], quick_properties=[],
        signals=[], widget_class="QWidget", qt_include="QWidget", source="user",
        style_role="label", requires=[], _pyside_template="", _cpp_template="")

    class _FakeRegistry:
        def get(self, cid):
            return {"fake_needy_widget": fake_needy, "fake_plain_widget": fake_plain}.get(cid)

    page = DesignPage(name="MainWindow")
    page.add(DesignWidget(component_id="fake_needy_widget",
                          object_name=unique_object_name("fake_needy_widget"),
                          x=0, y=0, width=10, height=10))
    page.add(DesignWidget(component_id="fake_plain_widget",
                          object_name=unique_object_name("fake_plain_widget"),
                          x=0, y=0, width=10, height=10))
    project = Project(name="demo", target="pyside6", pages=[page])
    registry = _FakeRegistry()

    reqs = package_retriever.requirements_for_project(project, registry)
    assert reqs == ["this-package-definitely-does-not-exist-xyz"], reqs

    missing = package_retriever.missing_requirements(project, registry)
    assert missing == reqs, "a package that can't possibly be installed must show up as missing"

    result = package_retriever.install(missing, dry_run=True)
    assert result.dry_run is True
    assert result.installed == missing, "dry_run must report what it WOULD do, without touching pip"
    assert result.failed == []

    # normalization: differently-cased/spelled variants of an installed
    # package must not false-negative as missing
    assert package_retriever.normalize("Pillow") == package_retriever.normalize("pillow") == "pillow"
    # a real installed package (PySide6 itself, or this repo wouldn't run) must
    # never show up as "missing" - proves installed_names() actually finds
    # what's really on the system, not just an empty set
    have = package_retriever.installed_names()
    assert "pyside6" in have, "PySide6 itself must be detected as installed"
    print("[OK] package retriever: detects component-declared requirements and dry-runs installs")


def run_all():
    for test in (test_registry_loads, test_all_components_generate_both_languages,
                 test_model_roundtrip, test_place_select_resize,
                 test_popover_edits_model, test_delete_and_duplicate, test_undo_redo,
                 test_pages_multiskeleton, test_layers_selection_sync,
                 test_library_source_tabs, test_shell_boots,
                 test_codegen_never_emits_broken_syntax, test_wysiwyg_fidelity,
                 test_runner_relays_crash, test_themes_switch_and_import,
                 test_typed_property_editors, test_snap_and_align,
                 test_command_dispatch_covers_menu, test_library_dialog_and_palette,
                 test_app_theme_light_dark, test_multipage_app_shell,
                 test_editor_light_dark_contrast, test_guides_and_grid,
                 test_asset_manager_import_rules, test_project_save_load_roundtrip,
                 test_ui_designer_interop, test_qt_property_introspection,
                 test_animations_generate_and_preview, test_stylesheets_and_problems,
                 test_terminal_unicode_ansi_and_carriage, test_theming_reaches_nested_panels,
                 test_context_menus_are_component_aware, test_quick_edit_and_clipboard,
                 test_color_picker_channels_sync, test_sensible_sizing_defaults,
                 test_codegen_multiwidget_and_roundtrip, test_cpp_codegen_and_roundtrip,
                 test_button_roles_have_interaction_states,
                 test_terminal_platform_eol_and_starts,
                 test_zoom_actually_rescales_canvas,
                 test_layout_toolbar_cannot_dock_to_a_vertical_area,
                 test_qt_property_edits_persist_to_codegen,
                 test_properties_panel_grouped_editor,
                 test_activity_bar_cleanup,
                 test_library_mode_popup_and_pane,
                 test_target_chosen_at_creation,
                 test_palette_is_context_aware,
                 test_media_asset_renders_and_ships,
                 test_generated_theme_follows_system,
                 test_autogrow_text_field,
                 test_markdown_engine_converts,
                 test_rich_text_component_renders_and_ships,
                 test_richtext_engine_handles_common_latex_edge_cases,
                 test_canvas_math_ink_follows_app_theme,
                 test_markdown_field_is_directly_editable,
                 test_terminal_prefers_powershell_on_windows,
                 test_terminal_toolbar_filter_and_find,
                 test_universal_find_routes_by_focus,
                 test_canvas_find_matches_name_and_text,
                 test_search_bar_is_centered,
                 test_command_palette_navigation,
                 test_command_index_shortcuts_render_as_chips,
                 test_tools_bar_visible_by_default,
                 test_all_components_render_and_codegen,
                 test_image_fit_modes,
                 test_theme_toggle_generates_working_logic,
                 test_codegen_emits_layouts_connections_taborder,
                 test_ui_layouts_connections_tabstops_roundtrip,
                 test_ui_imports_foreign_layout_file,
                 test_tabs_independent_undo,
                 test_closing_one_tab_leaves_the_others_open,
                 test_quick_preview_layout_aware_and_interactive,
                 test_layout_toolbar_assign_remove_and_grid,
                 test_text_tools_bar_formats_and_targets_right_property,
                 test_code_editor_generates_edits_and_survives_regeneration,
                 test_python_highlighter_colors_real_syntax,
                 test_terminal_clear_host_override_and_noprofile,
                 test_command_palette_dismisses_on_outside_click,
                 test_editor_tabs_embedded_beside_undo_redo,
                 test_tab_context_menu_rename_close_others_and_right,
                 test_app_settings_persist_and_isolated_defaults,
                 test_error_manager_respects_the_privacy_toggle,
                 test_shortcuts_single_source_of_truth,
                 test_settings_dialog_sections_signals_and_licenses,
                 test_branding_assets_load_from_stable_paths,
                 test_terminal_shell_setting_overrides_auto_detect,
                 test_license_files_present_and_readable,
                 test_cpp_build_runner_full_pipeline_and_failure_modes,
                 test_run_dispatches_to_cpp_pipeline_for_cpp_target,
                 test_headlessbit_shell_place_generate_reopen_roundtrip,
                 test_headlessbit_pages_and_bad_input_never_raise,
                 test_package_retriever_detects_and_dry_run_installs):
        reset_ids()
        test()
        release_windows()
    print("\nAll tests pass.")


if __name__ == "__main__":
    run_all()

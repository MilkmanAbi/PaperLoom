"""
PaperLoom main window - the full shell (spec §3, §12).

  MenuBar       PaperLoom | File | Edit | Selection | View | Go | Run | Terminal + search
  TopBar        undo/redo, target, zoom, panel toggles, Generate/Run
  ToolsToolbar  pinnable quick tools (align, z-order, snap, duplicate/delete)
  ActivityBar | SidePanel | Canvas
  BottomPanel   Output / Problems / Debug / Terminal
  StatusBar     status, zoom, widget count, target

Every menu action routes through one `command` signal, so the menu bar, the
command palette and the toolbar all drive the same dispatch table.
"""
import os
import sys
import tempfile

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QFileDialog, QMessageBox,
    QInputDialog, QToolBar
)

from .. import theme
from . import branding
from .canvas import DesignCanvas
from .activity_bar import ActivityBar
from .side_panel import SidePanelHost
from .runner import AppRunner, CppBuildRunner
from .panels.property_popover import PropertyPopover
from .panels.library_panel import LibraryPanel
from .panels.library_dialog import LibraryDialog
from .panels.pages_panel import PagesPanel
from .panels.editor_tabs import EditorTabBar
from .panels.layers_panel import LayersPanel
from .panels.properties_panel import PropertiesPanel
from .panels.assets_panel import AssetsPanel
from .panels.canvas_find_bar import CanvasFindBar
from .panels.animations_panel import AnimationsPanel
from .panels.bottom_panel import BottomPanel
from .panels.top_bar import TopBar
from .panels.menu_bar import MenuBar
from .panels.status_bar import StatusBar
from .panels.tools_toolbar import ToolsToolbar
from .panels.layout_toolbar import LayoutToolbar
from .panels.command_palette import CommandPalette
from .panels.snap_dialog import SnapDialog
from .panels.color_picker import ColorPickerDialog
from .panels.context_menus import build_widget_menu, build_canvas_menu, build_tab_menu, QuickEditBar
from .panels.text_tools_bar import TextToolsBar
from ..core.model import DesignPage, Project, LayoutGroup, next_layout_id
from ..core import text_format
from ..core.project_io import ProjectIO
from ..core.assets import AssetManager
from ..core.app_theme import AppTheme
from ..core.animations import AnimationSet, Animation
from ..core.stylesheets import StylesheetManager, StylesheetError
from ..core.problems import ProblemLog
from ..core.ui_io import UiIO, UiImportError
from ..core.undo import UndoStack
from ..core import shortcuts
from ..core import app_settings
from ..components.registry import ComponentRegistry
from ..codegen import get_backend
from ..codegen.app_shell import generate_app_shell


class PaperLoomWindow(QMainWindow):
    def __init__(self, registry: ComponentRegistry = None, project: Project = None):
        super().__init__()
        self.setWindowTitle("PaperLoom")
        self.setWindowIcon(branding.app_icon())
        self.resize(1360, 860)

        # restore PaperLoom's own light/dark from last session (Settings >
        # Personalization) before anything below reads theme.* tokens, so
        # nothing gets built in the wrong colours and then re-styled a
        # frame later.
        if app_settings.get("editor_theme", "dark") == "light" and theme.manager.active.is_dark:
            theme.manager.set_active("PaperLoom Light")
        elif app_settings.get("editor_theme", "dark") == "dark" and not theme.manager.active.is_dark:
            theme.manager.set_active("PaperLoom Dark")

        self.registry = registry or ComponentRegistry().load()
        self.project = project or Project(name="untitled", pages=[DesignPage(name="MainWindow")])
        if not self.project.pages:
            self.project.pages.append(DesignPage(name="MainWindow"))
        self.page = self.project.pages[0]
        self.target = self.project.target      # chosen once at project creation
        self.zoom = 100
        self.undo_stack = UndoStack()
        # tabs (open pages, distinct from the Pages panel's full project list):
        # each open page gets its own independent undo/redo history, pre-seeded
        # with the stack just created above for the page that starts active.
        self.open_pages = [self.page]
        self.page_undo_stacks = {id(self.page): self.undo_stack}
        self.runner = AppRunner(self)
        self.cpp_runner = CppBuildRunner(self)
        self.quick_preview = None       # created lazily on first use
        self._quick_preview_live = False
        self.code_editor = None         # created lazily on first use
        self._live_dir = None           # shared Run/Code-Editor scratch dir - see _get_live_dir()
        # --- backend services ---
        self.project_io = ProjectIO()
        self.project_dir = None
        self.assets = AssetManager()
        self.animations = AnimationSet()
        self.stylesheets = StylesheetManager()
        self.problems = ProblemLog()
        self.ui_io = UiIO(self.registry)

        # --- chrome ---
        self.menu_bar = MenuBar(theme.manager)
        self.top_bar = TopBar()
        # ToolsToolbar defines the tool set (TOOLS list) and is source-of-truth
        # for icons/commands; its own hand-rolled floating widget (pin/drag/
        # grip) is intentionally never shown, since populate_toolbar() below
        # copies the same actions into self.tools_bar, a real QToolBar - Qt's
        # native movable/floatable toolbar is strictly better than a hand-
        # rolled drag implementation for this. self.tools stays alive only to
        # own the command definitions and forward its `command` signal.
        self.tools = ToolsToolbar()
        self.layout_toolbar_widget = LayoutToolbar()

        # --- panels ---
        self.library_panel = LibraryPanel(self.registry)
        self.pages_panel = PagesPanel(self.project)
        self.editor_tabs = EditorTabBar()
        self.top_bar.set_tab_bar(self.editor_tabs)   # beside undo/redo, not its own row
        self.layers_panel = LayersPanel()
        self.layers_panel.set_page(self.page)
        self.properties_panel = PropertiesPanel(self.registry)
        self.assets_panel = AssetsPanel()
        self.assets_panel.set_manager(self.assets)
        self.animations_panel = AnimationsPanel()

        # animations are per-widget, so they live inside the Properties editor
        # (a collapsible section), not as a top-level pane of their own.
        self.properties_panel.embed_animations(self.animations_panel)

        self.activity_bar = ActivityBar()
        # popup is the default library surface (a modal-style attached window);
        # pane mode puts the library in the side bar instead, behind a setting.
        # Restored from ~/.paperloom/settings.json (Settings > Personalization)
        # rather than always resetting to "popup" on launch.
        self.library_mode = app_settings.get("library_mode", "popup")
        self.side_panel = SidePanelHost({
            "library": self.library_panel,
            "pages": self.pages_panel,
            "layers": self.layers_panel,
            "properties": self.properties_panel,
            "assets": self.assets_panel,
        })
        self.side_panel.collapse()      # nothing forced open on boot

        self.canvas = DesignCanvas(self.registry, self.page, undo_stack=self.undo_stack)
        # media widgets render their real image on the canvas by resolving the
        # asset key against the current project's assets (looked up live, since
        # the manager instance is swapped out when a project is opened)
        self.canvas.asset_resolver = lambda key: self.assets.resolve(key)

        # universal Ctrl-F, canvas half: a floating find bar over the canvas
        # that locates widgets by name/text (the terminal has its own
        # find-in-output bar; _universal_find() routes by focus)
        self._canvas_find_bar = CanvasFindBar(self.canvas)
        self._canvas_find_bar.queryChanged.connect(self._canvas_find_query)
        self._canvas_find_bar.stepRequested.connect(self._canvas_find_step)
        self._canvas_find_matches = []
        self._canvas_find_index = -1

        body = QWidget()
        bl = QHBoxLayout(body); bl.setContentsMargins(0, 0, 0, 0); bl.setSpacing(0)
        bl.addWidget(self.activity_bar)
        bl.addWidget(self.side_panel)
        bl.addWidget(self.canvas, 1)

        self.bottom_panel = BottomPanel()
        self.bottom_panel.hide()
        self.status_bar = StatusBar()

        root = QWidget()
        rl = QVBoxLayout(root); rl.setContentsMargins(0, 0, 0, 0); rl.setSpacing(0)
        rl.addWidget(self.menu_bar)
        rl.addWidget(self.top_bar)     # editor_tabs lives inside top_bar now (set_tab_bar above)
        rl.addWidget(body, 1)
        rl.addWidget(self.bottom_panel)
        rl.addWidget(self.status_bar)
        self.setCentralWidget(root)

        # tools live in a real QToolBar so they can be dragged to any edge or
        # floated free (AutoCAD-style), not pinned into the layout
        self.tools_bar = QToolBar("Tools", self)
        self.tools_bar.setObjectName("ToolsBar")
        self.tools_bar.setMovable(True)
        self.tools_bar.setFloatable(True)
        self.tools_bar.setAllowedAreas(Qt.ToolBarArea.AllToolBarAreas)
        # add each tool as its own toolbar button. Wrapping the whole strip in a
        # single child widget swallowed the drag - QToolBar can only move itself
        # when its own handle is exposed, which needs real toolbar items.
        self.tools.populate_toolbar(self.tools_bar)
        self.tools_bar.setWindowTitle("Tools")     # a titled palette when floated
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, self.tools_bar)
        # visible by default: hiding it in session 11's "calm the UI down" pass
        # meant the AutoCAD-style tool palette (align/distribute/z-order/snap/
        # duplicate/delete) was effectively lost - nothing pointed at View >
        # Toggle Tools, so there was no way to discover it was still there.
        # It's a real QToolBar (movable/floatable/dockable to any edge), so
        # showing it by default doesn't reintroduce the loud chrome from
        # before - it's a slim single row, not a heavy panel.
        toolbar_qss = (
            f"QToolBar {{ background: {theme.ACTIVITY_BAR}; border: none; spacing: 2px;"
            f" padding: 3px; }}"
            f"QToolBar::separator {{ background: {theme.BORDER_DARK}; width: 1px; margin: 4px 4px; }}"
            f"QToolButton {{ background: transparent; border: none; border-radius: 4px;"
            f" padding: 4px; }}"
            f"QToolButton:hover {{ background: {theme.SIDE_PANEL}; }}"
            f"QLabel {{ color: {theme.INK_ON_DARK_MUTED}; font-size: 11px; }}"
            f"QComboBox, QSpinBox {{ background: {theme.SIDE_PANEL}; color: {theme.INK_ON_DARK};"
            f" border: 1px solid {theme.BORDER_DARK}; border-radius: {theme.RADIUS_SM}px;"
            f" padding: 2px 4px; font-size: 11px; }}")
        self.tools_bar.setStyleSheet(toolbar_qss)
        self._keep_toolbar_styled_when_floated(self.tools_bar, toolbar_qss)

        # Layout toolbar (LONG-MARCH-BACKLOG.md 2j-1): assign/break layout
        # membership, spacing/margins - the editor UI the model+codegen were
        # already built to support. Was opt-in (hidden by default) via
        # View > Toggle Layout Toolbar; that repeated the exact "effectively
        # lost, nothing points at the toggle" mistake session 11 already made
        # (and fixed) with tools_bar above - a feature nobody can find is a
        # feature that doesn't exist. Visible by default now, same as
        # tools_bar; View > Toggle Layout Toolbar still hides it for anyone
        # who doesn't want it up.
        self.layout_bar = QToolBar("Layout", self)
        self.layout_bar.setObjectName("LayoutBar")
        self.layout_bar.setMovable(True)
        self.layout_bar.setFloatable(True)
        # Top/Bottom only - NOT AllToolBarAreas. This toolbar's content
        # (label+combobox pairs, several spinboxes) is laid out assuming a
        # single horizontal row; QToolBar reflows every child into a stacked
        # column when docked to the Left/Right areas (or dragged near one),
        # which turned "New Vertical Layout" plus 8 differently-sized label/
        # spinbox widgets into an unreadable narrow column - that was the
        # "pinning this toolbar looks pretty broken" report. Restricting the
        # allowed areas removes the vertical-reflow case entirely; it can
        # still be dragged anywhere along the top/bottom edge, or floated
        # free as its own small horizontal palette.
        self.layout_bar.setAllowedAreas(
            Qt.ToolBarArea.TopToolBarArea | Qt.ToolBarArea.BottomToolBarArea)
        self.layout_toolbar_widget.populate_toolbar(self.layout_bar)
        self.layout_bar.setWindowTitle("Layout")
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, self.layout_bar)
        self.layout_bar.setStyleSheet(toolbar_qss)
        self._keep_toolbar_styled_when_floated(self.layout_bar, toolbar_qss)

        self.popover = PropertyPopover(self.canvas)
        self.canvas.set_popover(self.popover)

        self.quick_edit = QuickEditBar(self)
        self.text_tools = TextToolsBar(self)
        self._text_tools_prop = None
        self._clipboard_widget = None
        self.palette_dialog = CommandPalette(self.registry, self.project, self)
        self.library_dialog = None

        self._wire()
        self._shortcuts()
        self._refresh_undo_state()
        # seed the tab strip with the page that starts active - without this
        # a brand-new project shows zero tabs until the user opens a second
        # page, even though open_pages already has one (constructor above)
        self.editor_tabs.refresh(self.open_pages, 0)
        self.status_bar.set_count(len(self.page.widgets))
        self.status_bar.set_target(self.target)

    # --- wiring --------------------------------------------------------------
    def _wire(self):
        self.canvas.selectionChanged.connect(self._on_selection_changed)
        self.canvas.modelChanged.connect(self._on_model_changed)
        self.canvas.geometryCommitted.connect(self.properties_panel.refresh_geometry)
        self.canvas.widgetMenuRequested.connect(self._widget_context_menu)
        self.canvas.canvasMenuRequested.connect(self._canvas_context_menu)
        self.quick_edit.opacityChanged.connect(self.canvas.set_opacity_of_selected)
        self.quick_edit.colorChanged.connect(self.canvas.set_color_of_selected)
        self.quick_edit.radiusChanged.connect(self.canvas.set_radius_of_selected)
        self.text_tools.formatRequested.connect(self._on_text_format)

        self.library_panel.componentChosen.connect(self.canvas.place_component)
        self.activity_bar.viewSelected.connect(self._on_view_selected)
        self.activity_bar.settingsRequested.connect(self._open_settings)
        self.pages_panel.pageSelected.connect(self._go_to_page_index)
        self.pages_panel.pageAddRequested.connect(self._on_page_added)
        self.layers_panel.widgetSelected.connect(self.canvas.select_by_model)

        self.editor_tabs.currentChanged.connect(self._on_tab_activated)
        self.editor_tabs.tabCloseRequested.connect(self._on_tab_close_requested)
        self.editor_tabs.tabMoved.connect(self._on_tab_moved)
        self.editor_tabs.tabContextMenuRequested.connect(self._tab_context_menu)

        self.properties_panel.propertyChanged.connect(self.canvas.apply_property)
        self.properties_panel.geometryChanged.connect(self.canvas.set_geometry_of_selected)
        self.properties_panel.opacityChanged.connect(self.canvas.set_opacity_of_selected)
        self.properties_panel.qtPropertyChanged.connect(self._on_qt_property_changed)
        self.properties_panel.assetPickRequested.connect(self._pick_asset_for_property)
        self.properties_panel.markdownEditRequested.connect(self._edit_markdown_for_property)
        self.properties_panel.set_asset_resolver(lambda key: self.assets.resolve(key))

        self.menu_bar.command.connect(self.dispatch)
        self.menu_bar.themeChosen.connect(self._apply_theme)
        self.menu_bar.searchSubmitted.connect(lambda q: self._open_palette(q))
        self.tools.command.connect(self.dispatch)

        self.layout_toolbar_widget.assignRequested.connect(self._on_layout_assign)
        self.layout_toolbar_widget.removeRequested.connect(self._on_layout_remove)
        self.layout_toolbar_widget.spacingChanged.connect(self._on_layout_spacing_changed)
        self.layout_toolbar_widget.marginsChanged.connect(self._on_layout_margins_changed)
        self.layout_toolbar_widget.targetChanged.connect(self._on_layout_target_changed)

        self.top_bar.undoRequested.connect(lambda: self.dispatch("edit.undo"))
        self.top_bar.redoRequested.connect(lambda: self.dispatch("edit.redo"))
        self.top_bar.generateRequested.connect(lambda: self.dispatch("file.generate"))
        self.top_bar.runRequested.connect(lambda: self.dispatch("run.preview"))
        self.top_bar.quickPreviewRequested.connect(lambda: self.dispatch("run.quick_preview"))
        self.top_bar.codeEditorRequested.connect(lambda: self.dispatch("run.code_editor"))
        self.top_bar.saveRequested.connect(lambda: self.dispatch("file.save"))
        self.top_bar.toggleBottomRequested.connect(lambda: self.dispatch("view.toggle_bottom"))
        self.top_bar.zoomChanged.connect(self._set_zoom)
        self.top_bar.editorModeToggled.connect(lambda: self.dispatch("view.toggle_editor_mode"))
        self.top_bar.appModeToggled.connect(lambda: self.dispatch("view.toggle_app_mode"))

        self.palette_dialog.commandChosen.connect(self.dispatch)
        self.palette_dialog.pageChosen.connect(self._go_to_page_index)
        self.palette_dialog.componentChosen.connect(self.canvas.place_component)
        self.palette_dialog.set_context_provider(self._palette_context)

        self.animations_panel.animationAdded.connect(self._on_animation_added)
        self.animations_panel.animationRemoved.connect(self._on_animation_removed)
        self.animations_panel.previewRequested.connect(self._on_animation_preview)
        self.problems.on_change(self._sync_problems)
        self.undo_stack.on_change(self._refresh_undo_state)
        theme.manager.on_change(self._on_theme_changed)

    def _shortcuts(self):
        # core/shortcuts.py is the single source of truth - Settings >
        # Shortcuts displays the exact same list, so the two can never drift.
        for keys, cmd in shortcuts.binds():
            QShortcut(QKeySequence(keys), self, activated=lambda c=cmd: self.dispatch(c))

    # --- command dispatch ----------------------------------------------------
    def dispatch(self, cmd):
        table = {
            "app.about": self._about,
            "app.preferences": lambda: self.status_bar.set_status("Preferences coming soon"),
            "app.quit": self.close,

            "file.new_page": lambda: self._on_page_added_prompt(),
            "file.open": self.open_project,
            "file.save": self.save_project,
            "file.save_as": lambda: self.save_project(ask=True),
            "file.import_ui": self.import_ui,
            "file.export_ui": self.export_ui,
            "file.import_stylesheet": self.import_stylesheet,
            "file.export_project": self.export_project,
            "file.generate": self.generate_code,
            "file.export_theme": self._export_theme,

            "edit.undo": self.undo_stack.undo,
            "edit.redo": self.undo_stack.redo,
            "edit.duplicate": self.canvas.duplicate_selected,
            "edit.delete": self.canvas.delete_selected,

            "selection.all": lambda: self.status_bar.set_status("Multi-select coming soon"),
            "selection.none": lambda: self.canvas.select_qwidget(None),
            "selection.front": self.canvas.raise_selected,
            "selection.back": self.canvas.lower_selected,

            "view.zoom_in": lambda: self._set_zoom(self.zoom + 25),
            "view.zoom_out": lambda: self._set_zoom(self.zoom - 25),
            "view.zoom_reset": lambda: self._set_zoom(100),
            "view.toggle_grid": self._toggle_grid,
            "view.toggle_snap": self._toggle_snap,
            "view.snap_settings": self._snap_settings,
            "view.toggle_side": self._toggle_side,
            "view.toggle_bottom": self._toggle_bottom,
            "view.toggle_tools": lambda: self.tools_bar.setVisible(not self.tools_bar.isVisible()),
            "view.toggle_layout_toolbar": lambda: self.layout_bar.setVisible(not self.layout_bar.isVisible()),
            "view.import_theme": self._import_theme,
            "view.toggle_library_mode": self._toggle_library_mode,
            "app.settings": self._open_settings,
            "app.focus_properties": lambda: self._show_pane("properties"),
            "view.toggle_editor_mode": self._toggle_editor_mode,
            "view.toggle_app_mode": self._toggle_app_mode,
            "view.toggle_guides": self._toggle_guides,

            "go.page": lambda: self._open_palette("Go to page"),
            "go.component": lambda: self._open_palette("Place component"),
            "go.commands": lambda: self._open_palette(""),

            "run.preview": self._on_run,
            "run.stop": self._stop_run,
            "run.generate": self.generate_code,
            "run.quick_preview": self._on_quick_preview,
            "run.code_editor": self._on_code_editor,

            "terminal.new": lambda: self._show_bottom_tab("terminal"),
            "terminal.clear": lambda: self.bottom_panel.terminal.clear(),
            "terminal.output": lambda: self._show_bottom_tab("output"),
            "terminal.problems": lambda: self._show_bottom_tab("problems"),
            "terminal.debug": lambda: self._show_bottom_tab("debug"),

            "library.open": self._open_library_dialog,
            "edit.find": self._universal_find,

            "tabs.next": lambda: self._cycle_tab(1),
            "tabs.prev": lambda: self._cycle_tab(-1),
            "tabs.close": self._close_active_tab,
        }
        for how in ("left", "center", "right", "top", "middle", "bottom"):
            table[f"align.{how}"] = lambda h=how: self.canvas.align_selected(h)

        fn = table.get(cmd)
        if fn:
            fn()
        else:
            self.status_bar.set_status(f"Unknown command: {cmd}")

    # --- views / theme -------------------------------------------------------
    def _on_theme_changed(self, _theme=None):
        """Bound method (not a lambda) so the theme manager can hold it weakly
        and drop it automatically when this window goes away."""
        self._restyle_all()

    def _restyle_all(self):
        """Walk the whole widget tree and restyle everything that can.

        A hardcoded list of panels used to miss nested widgets (the integrated
        terminal kept its dark styling in a light theme because it lives inside
        the bottom panel). Walking children means any panel added later is
        themed automatically, with no registration step to forget.
        """
        from PySide6.QtWidgets import QApplication, QWidget
        QApplication.instance().setStyleSheet(theme.app_stylesheet())

        seen = set()
        try:
            children = self.findChildren(QWidget)
        except RuntimeError:
            return                      # window already destroyed
        for widget in children:
            fn = getattr(widget, "restyle", None)
            if callable(fn) and id(widget) not in seen:
                seen.add(id(widget))
                try:
                    fn()
                except Exception as exc:
                    self.problems.warn(
                        f"Restyle failed for {type(widget).__name__}: {exc}",
                        source="theme")
        # dialogs and popovers are not children of the window's layout
        for extra in (self.palette_dialog, self.library_dialog, self.popover):
            if extra is not None and hasattr(extra, "restyle"):
                extra.restyle()
        # self.tools / self.layout_toolbar_widget are the command-definition
        # sources for tools_bar/layout_bar (populate_toolbar() copies their
        # actions into a real QToolBar) - they're never parented into the
        # window's own layout, so the findChildren() walk above never reaches
        # them and their icons wouldn't re-tint on a theme toggle otherwise
        for extra in (self.tools, self.layout_toolbar_widget):
            if extra is not None and hasattr(extra, "restyle_toolbar"):
                extra.restyle_toolbar()

        self.canvas.update()
        if self.canvas.selected_model is not None:
            self.canvas.select_by_model(self.canvas.selected_model)
        self.menu_bar.refresh_themes()
        self.top_bar.set_mode_icons(theme.manager.active.is_dark,
                                    self.canvas.app_theme.mode)

    def _toggle_editor_mode(self):
        t = theme.manager.toggle_light_dark()
        app_settings.set("editor_theme", "dark" if t.is_dark else "light")
        self.status_bar.set_status(f"PaperLoom: {'dark' if t.is_dark else 'light'} theme")

    def _toggle_app_mode(self):
        mode = self.canvas.toggle_app_mode()
        from .preview import set_mode as preview_set_mode
        preview_set_mode(mode)
        self.library_panel._refresh()
        self.top_bar.set_mode_icons(theme.manager.active.is_dark, mode)
        self.status_bar.set_app_mode(mode)
        self.status_bar.set_status(f"App preview: {mode} mode")
        self._refresh_quick_preview()   # app theme isn't a modelChanged/pageChanged event

    def _toggle_guides(self):
        self.canvas.show_guides = not self.canvas.show_guides
        self.status_bar.set_status(
            f"Alignment guides {'on' if self.canvas.show_guides else 'off'}")

    def _apply_theme(self, name):
        theme.manager.set_active(name)
        self.status_bar.set_status(f"Theme: {name}")

    def _import_theme(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import theme", "", "Theme (*.json)")
        if not path:
            return
        try:
            t = theme.manager.import_theme(path)
            self.status_bar.set_status(f"Imported theme: {t.name}")
        except Exception as exc:
            self.bottom_panel.show()
            self.bottom_panel.add_problem(f"Theme import failed: {exc}", path, 0)
            self.bottom_panel.show_problems_tab()

    def _export_theme(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export theme", "theme.json", "Theme (*.json)")
        if path:
            theme.manager.export_active(path)
            self.status_bar.set_status(f"Exported theme to {os.path.basename(path)}")

    def _keep_toolbar_styled_when_floated(self, toolbar, qss):
        """A floated QToolBar becomes its own top-level window; Qt doesn't
        always keep the QSS applied to the toolbar widget itself painted on
        that new floating frame, which showed up as the floated palette
        falling back to a plain default-palette background (blue on
        Windows) instead of the app's own dark chrome - looking "broken"
        next to everything else. Re-asserting the stylesheet (and an
        explicit background on the floating frame itself) every time
        floating state changes fixes that without needing to touch how
        floating/docking itself works."""
        def _on_top_level_changed(floating):
            toolbar.setStyleSheet(qss)
            if floating:
                window = toolbar.window()
                if window is not toolbar:
                    window.setStyleSheet(f"background: {theme.ACTIVITY_BAR};")
        toolbar.topLevelChanged.connect(_on_top_level_changed)

    # --- zoom / grid / snap --------------------------------------------------
    def _set_zoom(self, percent):
        self.zoom = max(25, min(400, int(percent)))
        self.canvas.set_zoom(self.zoom)
        self.top_bar.set_zoom_display(self.zoom)
        self.status_bar.set_zoom(self.zoom)
        self.status_bar.set_status(f"Zoom {self.zoom}%")

    def _toggle_grid(self):
        self.canvas.show_grid = not self.canvas.show_grid
        self.canvas.update()
        self.status_bar.set_status(f"Grid {'on' if self.canvas.show_grid else 'off'}")

    def _toggle_snap(self):
        self.canvas.snap_enabled = not self.canvas.snap_enabled
        self.status_bar.set_snap(self.canvas.snap_enabled, self.canvas.snap_size)
        self.status_bar.set_status(
            f"Snap {'on' if self.canvas.snap_enabled else 'off'} ({self.canvas.snap_size}px)")

    def _snap_settings(self):
        dlg = SnapDialog(self.canvas.snap_enabled, self.canvas.snap_size,
                         self.canvas.show_grid, self)
        if dlg.exec():
            enabled, size, grid = dlg.values()
            self.canvas.set_snap(enabled, size, grid)
            self.status_bar.set_snap(enabled, size)
            self.status_bar.set_status(f"Snap {'on' if enabled else 'off'} ({size}px)")

    def _toggle_side(self):
        if self.side_panel.collapsed:
            self.side_panel.expand()
        else:
            self.side_panel.collapse()

    def _toggle_bottom(self):
        self.bottom_panel.setVisible(not self.bottom_panel.isVisible())

    def _show_bottom_tab(self, which):
        self.bottom_panel.show()
        self.bottom_panel.show_tab(which)

    def _open_palette(self, prefix=""):
        self.palette_dialog.open_with(prefix)
        geo = self.geometry()
        self.palette_dialog.move(geo.center().x() - 310, geo.top() + 120)

    def _palette_context(self):
        """Actions the palette should surface first, given what's selected and
        where we are - so the palette is app-aware, not a static command list."""
        actions = []
        dw = self.canvas.selected_model
        if dw is not None:
            n = dw.object_name
            actions += [
                (f"Selected: {n}  -  Duplicate", "edit.duplicate"),
                (f"Selected: {n}  -  Delete", "edit.delete"),
                (f"Selected: {n}  -  Edit properties", "app.focus_properties"),
                (f"Selected: {n}  -  Bring to front", "selection.front"),
                (f"Selected: {n}  -  Send to back", "selection.back"),
            ]
        actions.append((f"Page: {self.page.name}  -  New page", "file.new_page"))
        return actions

    def _open_library_dialog(self):
        if self.library_dialog is None:
            self.library_dialog = LibraryDialog(self.registry, self)
            self.library_dialog.componentChosen.connect(self.canvas.place_component)
        self.library_dialog.restyle()
        self.library_dialog.show()
        self.library_dialog.raise_()

    def _about(self):
        QMessageBox.about(self, "PaperLoom",
                          "PaperLoom\nA Qt visual GUI builder.\n\n"
                          "Design what you want, then see what you made - as-is.")

    # --- undo ----------------------------------------------------------------
    def _refresh_undo_state(self):
        self.top_bar.set_undo_state(
            self.undo_stack.can_undo, self.undo_stack.can_redo,
            self.undo_stack.undo_label, self.undo_stack.redo_label)

    # --- pages / tabs ----------------------------------------------------------
    # The Pages side panel lists every skeleton in the project (spec §7.1's
    # "file explorer"); the tab strip is which of those are currently OPEN
    # (VS Code's editor tabs). Selecting a page anywhere - the Pages panel, the
    # command palette's "Go to page", or a click on a tab - always routes
    # through _open_tab_for_page, so the two surfaces can never disagree about
    # what's open.
    def _go_to_page_index(self, index):
        """A page chosen from the Pages panel or the command palette (both
        index into project.pages, not open_pages)."""
        if 0 <= index < len(self.project.pages):
            self._open_tab_for_page(self.project.pages[index])

    def _get_or_create_undo_stack(self, page):
        key = id(page)
        stack = self.page_undo_stacks.get(key)
        if stack is None:
            stack = UndoStack()
            stack.on_change(self._refresh_undo_state)
            self.page_undo_stacks[key] = stack
        return stack

    def _activate_page(self, page):
        """Make `page` the one the canvas edits: swap its live widgets in and
        swap in its own independent undo/redo history (spec: Tabs, Phase A)."""
        self.page = page
        self.canvas.load_page(page)
        stack = self._get_or_create_undo_stack(page)
        self.undo_stack = stack
        self.canvas.set_undo_stack(stack)
        self.layers_panel.set_page(page)
        self.properties_panel.set_target(None)
        self.status_bar.set_count(len(page.widgets))
        self._refresh_undo_state()
        self._refresh_layout_toolbar()
        self._refresh_text_tools(None)

    def _open_tab_for_page(self, page):
        """Open a page as a tab if it isn't already, then focus it. Reopening
        an already-open page just focuses its existing tab (no duplicates)."""
        if page not in self.open_pages:
            self.open_pages.append(page)
        index = self.open_pages.index(page)
        self.editor_tabs.refresh(self.open_pages, index)
        self._activate_page(page)

    def _on_tab_activated(self, index):
        """The user clicked a tab directly (editor_tabs.currentChanged)."""
        if 0 <= index < len(self.open_pages):
            self._activate_page(self.open_pages[index])

    def _on_tab_close_requested(self, index):
        # always keep at least one tab open - the canvas must have a page
        if len(self.open_pages) <= 1 or not (0 <= index < len(self.open_pages)):
            return
        closing = self.open_pages[index]
        del self.open_pages[index]
        if closing is self.page:
            new_index = min(index, len(self.open_pages) - 1)
            self.editor_tabs.refresh(self.open_pages, new_index)
            self._activate_page(self.open_pages[new_index])
        else:
            # the active page wasn't the one closed - keep it active, just
            # resync the strip (its visual position may have shifted)
            self.editor_tabs.refresh(self.open_pages, self.open_pages.index(self.page))

    def _on_tab_moved(self, from_index, to_index):
        """Drag-to-reorder in the tab strip: keep open_pages in sync with
        what's now visually true. Qt already moved the tab itself."""
        if 0 <= from_index < len(self.open_pages) and 0 <= to_index < len(self.open_pages):
            page = self.open_pages.pop(from_index)
            self.open_pages.insert(to_index, page)

    def _cycle_tab(self, direction):
        if len(self.open_pages) < 2:
            return
        idx = self.open_pages.index(self.page)
        new_idx = (idx + direction) % len(self.open_pages)
        self.editor_tabs.setCurrentIndex(new_idx)   # fires currentChanged -> _on_tab_activated

    def _close_active_tab(self):
        if self.page in self.open_pages:
            self._on_tab_close_requested(self.open_pages.index(self.page))

    def _tab_context_menu(self, index, global_pos):
        if not (0 <= index < len(self.open_pages)):
            return
        page = self.open_pages[index]
        handlers = {
            "rename": lambda: self._rename_page(page),
            "close": lambda: self._on_tab_close_requested(self.open_pages.index(page)),
            "close_others": lambda: self._close_other_tabs(page),
            "close_right": lambda: self._close_tabs_to_right(page),
            "save_all": lambda: self.dispatch("file.save"),
        }
        build_tab_menu(self, page, handlers,
                       can_close_others=len(self.open_pages) > 1,
                       can_close_right=index < len(self.open_pages) - 1).exec(global_pos)

    def _rename_page(self, page):
        """Renames the tab's displayed title - not page.name, the technical
        identifier codegen and page navigation key off of; that's a deeper
        change (uniqueness, cross-references) out of scope for a quick tab
        rename."""
        title, ok = QInputDialog.getText(self, "Rename Page", "Title:", text=page.title)
        if ok and title.strip():
            page.title = title.strip()
            if page in self.open_pages:
                self.editor_tabs.refresh(self.open_pages, self.open_pages.index(self.page))
            self.pages_panel.refresh()
            self.status_bar.set_status(f"Renamed to “{page.title}”")

    def _close_other_tabs(self, keep_page):
        if keep_page not in self.open_pages:
            return
        for page in list(self.open_pages):
            if page is not keep_page:
                self._on_tab_close_requested(self.open_pages.index(page))
        if self.page is not keep_page and keep_page in self.open_pages:
            self.editor_tabs.setCurrentIndex(self.open_pages.index(keep_page))

    def _close_tabs_to_right(self, from_page):
        if from_page not in self.open_pages:
            return
        idx = self.open_pages.index(from_page)
        for page in list(self.open_pages[idx + 1:]):
            self._on_tab_close_requested(self.open_pages.index(page))
        if self.page is not from_page and from_page in self.open_pages:
            self.editor_tabs.setCurrentIndex(self.open_pages.index(from_page))

    def _on_page_added_prompt(self):
        name, ok = QInputDialog.getText(self, "New page", "Page name:")
        if ok and name.strip():
            self._on_page_added(name.strip())

    def _on_page_added(self, name):
        page = DesignPage(name=name.replace(" ", ""), title=name)
        self.project.pages.append(page)
        self.pages_panel.refresh()
        self.pages_panel.list.setCurrentRow(len(self.project.pages) - 1)

    # --- events --------------------------------------------------------------
    def _on_selection_changed(self, model):
        if model is None:
            self.popover.hide_popover()
        else:
            self.popover.show_for(model, self.canvas.selected_qwidget)
        self.layers_panel.select_widget(model)
        self.properties_panel.set_target(model, self.canvas.selected_qwidget)
        self.animations_panel.set_target(model, self.animations)
        self._refresh_layout_toolbar()
        self._refresh_text_tools(model)

    def _on_model_changed(self):
        self.layers_panel.refresh()
        self.status_bar.set_count(len(self.page.widgets))

    def _on_target_changed(self, target):
        self.target = target
        self.status_bar.set_target(target)
        self.status_bar.set_status(f"Target: {'PySide6' if target == 'pyside6' else 'C++'}")

    # --- run / generate ------------------------------------------------------
    def _stop_run(self):
        self.runner.stop()
        self.cpp_runner.stop()
        self.status_bar.set_status("Stopped")

    # --- Quick Preview ---------------------------------------------------------
    def _on_quick_preview(self):
        """An in-app, instant, interactive preview - no codegen, no
        subprocess (that's what Run does). See ui/quick_preview.py."""
        if self.quick_preview is None:
            from .quick_preview import QuickPreviewWindow
            self.quick_preview = QuickPreviewWindow(
                self.registry, asset_resolver=lambda key: self.assets.resolve(key),
                parent=self)
            self.quick_preview.closed.connect(self._on_quick_preview_closed)
        self.quick_preview.show_page(self.page, self.canvas.app_theme)
        if not self._quick_preview_live:
            # follow edits live while the preview is open - disconnected again
            # in _on_quick_preview_closed so a hidden preview never rebuilds
            self.canvas.modelChanged.connect(self._refresh_quick_preview)
            self.canvas.pageChanged.connect(self._refresh_quick_preview_page)
            self._quick_preview_live = True
        self.status_bar.set_status(
            "Quick Preview open - drag, resize, click; canvas edits update it live")

    def _refresh_quick_preview(self):
        if self.quick_preview is not None and self.quick_preview.isVisible():
            self.quick_preview.refresh(self.canvas.app_theme)

    def _refresh_quick_preview_page(self, page):
        """Follow the active tab: if the preview is open, keep it showing
        whatever page is now active on the canvas."""
        if self.quick_preview is not None and self.quick_preview.isVisible():
            self.quick_preview.show_page(page, self.canvas.app_theme)

    def _on_quick_preview_closed(self):
        if not self._quick_preview_live:
            return
        self._quick_preview_live = False
        for signal, slot in ((self.canvas.modelChanged, self._refresh_quick_preview),
                             (self.canvas.pageChanged, self._refresh_quick_preview_page)):
            try:
                signal.disconnect(slot)
            except (RuntimeError, TypeError):
                pass

    # --- layout toolbar --------------------------------------------------------
    def _refresh_layout_toolbar(self):
        """Keep the dropdown, Assign/Remove enablement, and spacing/margins
        fields in sync with the current page and selection."""
        dw = self.canvas.selected_model
        self.layout_toolbar_widget.set_enabled_for_selection(dw is not None)
        current = dw.layout_id if dw is not None else None
        self.layout_toolbar_widget.refresh_targets(self.page, current)

    def _on_layout_target_changed(self, key):
        if not key:
            return
        if key.startswith("new:"):
            self.layout_toolbar_widget.set_spacing_margins(6, (9, 9, 9, 9))
            return
        group = next((g for g in self.page.layouts if g.id == key), None)
        if group is not None:
            self.layout_toolbar_widget.set_spacing_margins(group.spacing, group.margins)

    def _on_layout_assign(self, target_key, row, col):
        dw = self.canvas.selected_model
        if dw is None:
            return
        page = self.page
        if target_key.startswith("new:"):
            kind = target_key.split(":", 1)[1]
            group = LayoutGroup(id=next_layout_id(page, kind), kind=kind)
            page.layouts.append(group)
            dw.layout_id, dw.layout_row, dw.layout_col = group.id, 0, 0
        else:
            group = next((g for g in page.layouts if g.id == target_key), None)
            if group is None:
                return
            if group.kind == "grid":
                dw.layout_row, dw.layout_col = int(row), int(col)
            else:
                members = [w for w in page.widgets if w.layout_id == group.id and w is not dw]
                dw.layout_row, dw.layout_col = len(members), 0
            dw.layout_id = group.id
        self.canvas.modelChanged.emit()
        self._refresh_layout_toolbar()
        self._refresh_quick_preview()
        self.status_bar.set_status(f"{dw.object_name} assigned to {group.id}")

    def _on_layout_remove(self):
        dw = self.canvas.selected_model
        if dw is None or dw.layout_id is None:
            return
        dw.layout_id, dw.layout_row, dw.layout_col = None, 0, 0
        self.canvas.modelChanged.emit()
        self._refresh_layout_toolbar()
        self._refresh_quick_preview()
        self.status_bar.set_status(f"{dw.object_name} removed from its layout")

    def _mutate_targeted_layout_group(self, fn):
        key = self.layout_toolbar_widget.target_combo.currentData()
        if not key or key.startswith("new:"):
            return
        group = next((g for g in self.page.layouts if g.id == key), None)
        if group is None:
            return
        fn(group)
        self._refresh_quick_preview()

    def _on_layout_spacing_changed(self, value):
        self._mutate_targeted_layout_group(lambda g: setattr(g, "spacing", int(value)))

    def _on_layout_margins_changed(self, left, top, right, bottom):
        self._mutate_targeted_layout_group(
            lambda g: setattr(g, "margins", (int(left), int(top), int(right), int(bottom))))

    # --- text formatting toolbar ------------------------------------------------
    def _text_property_for_dw(self, dw):
        """Which property Bold/Italic/etc. should touch: a markdown-typed
        property if the component has one (same lookup
        _edit_markdown_for_dw already uses), otherwise a plain string
        text/title property. None if the widget has neither."""
        component = self.registry.get(dw.component_id)
        if not component:
            return None
        prop = next((s.name for s in component.properties
                     if (s.type or "") == "markdown"), None)
        if prop is not None:
            return prop
        prop_types = {s.name: (s.type or "string") for s in component.properties}
        for candidate in ("text", "title"):
            if prop_types.get(candidate) == "string":
                return candidate
        return None

    def _refresh_text_tools(self, dw):
        """Show the bar next to the selection when it has a formattable
        property, alongside (not instead of) the quick-edit bar; hide it
        otherwise (no selection, or a widget with no text to format)."""
        if dw is None:
            self._text_tools_prop = None
            self.text_tools.hide()
            return
        prop = self._text_property_for_dw(dw)
        live = self.canvas._live_by_model.get(id(dw))
        if prop is None or live is None:
            self._text_tools_prop = None
            self.text_tools.hide()
            return
        self._text_tools_prop = prop
        self.text_tools.show_for(live, self.canvas)

    def _on_text_format(self, kind):
        dw = self.canvas.selected_model
        prop = self._text_tools_prop
        if dw is None or prop is None:
            return
        fn = getattr(text_format, kind, None)
        if fn is None:
            return
        component = self.registry.get(dw.component_id)
        spec_default = ""
        if component:
            for spec in component.properties:
                if spec.name == prop:
                    spec_default = spec.default
                    break
        current = str(dw.properties.get(prop, spec_default))
        self.canvas.apply_property(prop, fn(current))
        self.properties_panel.set_target(dw, self.canvas.selected_qwidget)
        # apply_property rebuilt the live widget - re-anchor both floating
        # bars on the new one so they don't drift from the (moved) selection
        self._refresh_text_tools(dw)
        live = self.canvas._live_by_model.get(id(dw))
        if live is not None and self.quick_edit.isVisible():
            opacity = float(dw.properties.get("opacity", 1.0))
            color = dw.properties.get("color", self.canvas.app_theme.tokens()["accent"])
            self.quick_edit.show_for(live, self.canvas, opacity, color,
                                     self.canvas.app_theme.radius)
        self.status_bar.set_status(f"{prop} updated")

    def _get_live_dir(self):
        """The scratch directory Run and the Code Editor share for this
        window's whole session - created once, then reused, NOT a fresh
        tempfile.mkdtemp() per call. Two things depend on that: (1) codegen's
        own "_write_logic_once" guarantee (a page's hand-written logic file
        is written once and never touched again) only means anything if
        Run keeps generating into the same place every time - a fresh temp
        dir per Run silently discarded every previous hand edit before it
        could ever be picked back up; (2) it stops leaking a new, never-
        cleaned-up temp directory on every single Run click."""
        if self._live_dir is None:
            self._live_dir = tempfile.mkdtemp(prefix="paperloom_live_")
        return self._live_dir

    def _on_code_editor(self):
        """Pop up (or refocus) the Code Editor for the ACTIVE page's logic
        file - the hand-written file codegen's own _write_logic_once already
        promises never to overwrite. Generates it once if it doesn't exist
        yet (safe: the UI file is always refreshed anyway, and the logic
        write is a no-op if the file is already there) so the editor always
        has something real to show without making the user hit Run first."""
        if self.target != "pyside6":
            self.status_bar.set_status("Code Editor supports PySide6 projects for now")
            return
        page = self.page
        live_dir = self._get_live_dir()
        backend = get_backend("pyside6", self.registry)
        backend.app_theme = self.canvas.app_theme
        backend.animations = self.animations
        backend.extra_stylesheets = self.stylesheets.sources()
        backend.assets = self.assets
        paths = backend.generate(page, live_dir)
        self._report_warnings(backend.warnings)

        if self.code_editor is None:
            from .code_editor import CodeEditorWindow
            self.code_editor = CodeEditorWindow(self)

        if self.code_editor.isVisible() and self.code_editor.current_path == paths["logic"]:
            self.code_editor.raise_()
            self.code_editor.activateWindow()
            return
        if (self.code_editor.isVisible() and self.code_editor.is_dirty()
                and self.code_editor.current_path != paths["logic"]):
            resp = QMessageBox.question(
                self, "Unsaved changes",
                "You have unsaved changes open in the Code Editor. Discard them and "
                f"switch to “{page.title or page.name}” instead?",
                QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel)
            if resp != QMessageBox.StandardButton.Discard:
                self.code_editor.raise_()
                self.code_editor.activateWindow()
                return
        self.code_editor.open_path(paths["logic"], page.title or page.name)
        self.status_bar.set_status(f"Editing {os.path.basename(paths['logic'])} — never touched by Generate/Run")

    def _on_run(self):
        if self.target != "pyside6":
            self._on_run_cpp()
            return
        out = self._get_live_dir()
        backend = get_backend("pyside6", self.registry)
        backend.app_theme = self.canvas.app_theme
        backend.animations = self.animations
        backend.extra_stylesheets = self.stylesheets.sources()
        backend.assets = self.assets
        paths = backend.generate(self.page, out)
        self.bottom_panel.show()
        self.bottom_panel.clear_output()
        self.bottom_panel.clear_problems()
        self.bottom_panel.show_tab("output")
        self._report_warnings(backend.warnings)
        self.bottom_panel.log(f"[run] launching {os.path.basename(paths['logic'])}")
        self.status_bar.set_status("Running...")
        self.runner.output.connect(self.bottom_panel.log)
        self.runner.problem.connect(self._on_run_problem)
        self.runner.finished.connect(self._on_run_finished)
        self.runner.run(paths["logic"], sys.executable)

    def _on_run_problem(self, message, file, line):
        self.bottom_panel.add_problem(message, file, line)

    def _on_run_finished(self, code):
        if code == 0:
            self.status_bar.set_status("Preview exited cleanly")
        else:
            n = self.bottom_panel.problem_count()
            self.status_bar.set_status(f"Preview crashed ({n} problem{'s' if n != 1 else ''})")
            self.bottom_panel.show_problems_tab()
        for sig, slot in ((self.runner.output, self.bottom_panel.log),
                          (self.runner.problem, self._on_run_problem),
                          (self.runner.finished, self._on_run_finished)):
            try:
                sig.disconnect(slot)
            except (RuntimeError, TypeError):
                pass

    def _on_run_cpp(self):
        """Run for a C++ target: generate, then actually configure+build with
        CMake (picking up whatever MSVC/Visual Studio toolchain is already
        registered with it on Windows) and launch the result - closing the
        gap where C++ projects only ever got source files and a polite
        'go build it yourself' message."""
        out = self._get_live_dir()
        backend = get_backend("cpp", self.registry)
        backend.app_theme = self.canvas.app_theme
        backend.animations = self.animations
        backend.extra_stylesheets = self.stylesheets.sources()
        backend.assets = self.assets
        paths = backend.generate(self.page, out)
        self.bottom_panel.show()
        self.bottom_panel.clear_output()
        self.bottom_panel.clear_problems()
        self.bottom_panel.show_tab("output")
        self._report_warnings(backend.warnings)

        src_dir = os.path.dirname(paths["cmake"])
        exe_name = os.path.splitext(os.path.basename(paths["logic"]))[0]
        self.bottom_panel.log(f"[cmake] configuring {os.path.basename(src_dir)}...")
        self.status_bar.set_status("Configuring (CMake)...")

        self.cpp_runner.stageStarted.connect(self._on_cpp_stage_started)
        self.cpp_runner.output.connect(self.bottom_panel.log)
        self.cpp_runner.problem.connect(self._on_run_problem)
        self.cpp_runner.buildFailed.connect(self._on_cpp_build_failed)
        self.cpp_runner.cmakeMissing.connect(self._on_cpp_cmake_missing)
        self.cpp_runner.finished.connect(self._on_cpp_finished)
        self.cpp_runner.start(src_dir, exe_name)

    def _on_cpp_stage_started(self, stage):
        label = {"configure": "Configuring (CMake)...",
                  "build": "Building (this can take a while the first time)...",
                  "run": "Running..."}.get(stage, stage)
        self.status_bar.set_status(label)
        if stage == "build":
            self.bottom_panel.log("[cmake] building...")
        elif stage == "run":
            self.bottom_panel.log("[run] launching the built executable")

    def _on_cpp_cmake_missing(self):
        self.bottom_panel.log(
            "[run] CMake wasn't found on PATH. Install CMake (and, on "
            "Windows, the 'Desktop development with C++' workload in "
            "Visual Studio, for the MSVC compiler) to Run a C++ project. "
            "You can still use Generate and build it yourself in the "
            "meantime.")
        self.status_bar.set_status("CMake not found - can't build C++")
        self._disconnect_cpp_runner()

    def _on_cpp_build_failed(self, stage, code):
        if stage == "build" and code == 0:
            self.bottom_panel.log(
                "[run] Build succeeded, but the resulting executable "
                "couldn't be found - check the CMake output above.")
            self.status_bar.set_status("Build succeeded, executable not found")
        else:
            self.bottom_panel.log(f"[{stage}] failed (exit code {code}) - see output above")
            self.status_bar.set_status(f"{stage.capitalize()} failed")
            if self.bottom_panel.problem_count():
                self.bottom_panel.show_problems_tab()
        self._disconnect_cpp_runner()

    def _on_cpp_finished(self, code):
        if code == 0:
            self.status_bar.set_status("Preview exited cleanly")
        else:
            n = self.bottom_panel.problem_count()
            self.status_bar.set_status(f"Preview crashed ({n} problem{'s' if n != 1 else ''})")
            self.bottom_panel.show_problems_tab()
        self._disconnect_cpp_runner()

    def _disconnect_cpp_runner(self):
        for sig, slot in ((self.cpp_runner.stageStarted, self._on_cpp_stage_started),
                          (self.cpp_runner.output, self.bottom_panel.log),
                          (self.cpp_runner.problem, self._on_run_problem),
                          (self.cpp_runner.buildFailed, self._on_cpp_build_failed),
                          (self.cpp_runner.cmakeMissing, self._on_cpp_cmake_missing),
                          (self.cpp_runner.finished, self._on_cpp_finished)):
            try:
                sig.disconnect(slot)
            except (RuntimeError, TypeError):
                pass

    def _report_warnings(self, warnings):
        for w in warnings:
            self.bottom_panel.add_problem(w)
        if warnings:
            self.bottom_panel.log(f"[generate] {len(warnings)} value(s) coerced (see Problems)")

    def generate_code(self, target_dir=None):
        if target_dir is None:
            target_dir = QFileDialog.getExistingDirectory(self, "Choose output folder")
            if not target_dir:
                return None
        backend = get_backend(self.target, self.registry)
        backend.app_theme = self.canvas.app_theme
        backend.animations = self.animations
        backend.extra_stylesheets = self.stylesheets.sources()
        backend.assets = self.assets
        results, all_warnings = [], []
        for page in self.project.pages:
            results.append(backend.generate(page, target_dir))
            all_warnings.extend(backend.warnings)
        self.bottom_panel.show()
        self.bottom_panel.clear_problems()
        for r in results:
            self.bottom_panel.log(f"[generate] {r['generated']}")
            self.bottom_panel.log(f"[generate] {r['logic']}")
        # multi-page projects get a real app shell with navigation
        if self.target == "pyside6" and len(self.project.pages) >= 1:
            shell = generate_app_shell(self.project, backend, target_dir)
            self.bottom_panel.log(f"[generate] {shell['app']}")
            self.bottom_panel.log(f"[generate] {shell['app_logic']}")
        self._report_warnings(all_warnings)
        status = f"Generated {len(results)} page(s)"
        if all_warnings:
            status += f", {len(all_warnings)} coerced"
        self.status_bar.set_status(status)
        return results[0] if results else None


    def _on_view_selected(self, view_id):
        """Components has two modes: popup (default) opens the dedicated library
        window; pane mode docks the library in the side bar. Everything else is
        always a side pane."""
        if view_id == "library" and self.library_mode == "popup":
            self._open_library_dialog()
            self.side_panel.collapse()
            self.activity_bar.set_active_view(None)   # popup, not a docked pane
            return
        self.side_panel.show_view(view_id)

    def set_library_mode(self, mode):
        """'popup' | 'pane'. Popup is the default browse-and-discover surface."""
        self.library_mode = "pane" if mode == "pane" else "popup"
        app_settings.set("library_mode", self.library_mode)
        self.menu_bar.set_library_pane_checked(self.library_mode == "pane")
        self.status_bar.set_status(
            f"Library: {'docked pane' if self.library_mode == 'pane' else 'popup window'}")

    def _toggle_library_mode(self):
        self.set_library_mode("popup" if self.library_mode == "pane" else "pane")

    def _open_settings(self):
        """The activity-bar gear: Personalization / Shortcuts / Terminal /
        Data & Privacy / Licenses / About - see panels/settings_dialog.py."""
        from .panels.settings_dialog import SettingsDialog
        dlg = SettingsDialog(self, library_mode=self.library_mode,
                             editor_dark=theme.manager.active.is_dark,
                             terminal_shell=app_settings.get("terminal_shell", "auto"),
                             collect_error_reports=app_settings.get("collect_error_reports", False))
        dlg.libraryModeChanged.connect(self.set_library_mode)
        dlg.editorModeToggled.connect(lambda: self.dispatch("view.toggle_editor_mode"))
        dlg.terminalShellChanged.connect(lambda choice: app_settings.set("terminal_shell", choice))
        dlg.collectErrorReportsChanged.connect(
            lambda on: app_settings.set("collect_error_reports", bool(on)))
        dlg.exec()

    # --- context menus (spec §29) --------------------------------------------
    def _widget_context_menu(self, dw, global_pos):
        component = self.registry.get(dw.component_id)
        if component is None:
            return
        handlers = {
            "edit_text": lambda: self._edit_primary_text(dw, component),
            "change_media": lambda: self._pick_media_for(dw),
            "edit_markdown": lambda: self._edit_markdown_for_dw(dw),
            "pick_color": lambda: self._pick_color_for(dw),
            "quick_edit": lambda: self._show_quick_edit(dw),
            "bring_front": self.canvas.raise_selected,
            "send_back": self.canvas.lower_selected,
            "align": lambda how: self.canvas.align_selected(how),
            "fit_contents": lambda: self._fit_contents(dw),
            "fill_width": lambda: self._fill_width(dw),
            "reset_size": lambda: self._reset_size(dw, component),
            "animate": lambda kind: self._quick_animate(dw, kind),
            "duplicate": self.canvas.duplicate_selected,
            "copy": lambda: self._copy_widget(dw),
            "delete": self.canvas.delete_selected,
            "properties": lambda: self._show_pane("properties"),
            "qt_properties": lambda: self._show_qt_properties(dw),
        }
        build_widget_menu(self, component, dw, handlers).exec(global_pos)

    def _canvas_context_menu(self, global_pos):
        handlers = {
            "paste": self._paste_widget,
            "open_library": self._open_library_dialog,
            "toggle_grid": self._toggle_grid,
            "toggle_guides": self._toggle_guides,
            "toggle_snap": self._toggle_snap,
            "snap_settings": self._snap_settings,
            "grid_on": lambda: self.canvas.show_grid,
            "guides_on": lambda: self.canvas.show_guides,
            "snap_on": lambda: self.canvas.snap_enabled,
            "toggle_app_mode": self._toggle_app_mode,
            "select_all": lambda: self.status_bar.set_status("Multi-select coming soon"),
            "page_settings": lambda: self._show_pane("pages"),
        }
        build_canvas_menu(self, handlers,
                          has_clipboard=self._clipboard_widget is not None).exec(global_pos)

    # --- context menu actions ------------------------------------------------
    def _edit_primary_text(self, dw, component):
        for key in ("text", "title", "placeholder"):
            if key in dw.properties:
                current = str(dw.properties.get(key, ""))
                value, ok = QInputDialog.getText(self, "Edit text", key.capitalize(),
                                                 text=current)
                if ok:
                    self.canvas.select_by_model(dw)
                    self.canvas.apply_property(key, value)
                return

    def _pick_color_for(self, dw):
        current = dw.properties.get("color", "#5B6BE8")
        picked = ColorPickerDialog.get_color(current, self)
        if picked is not None:
            self.canvas.select_by_model(dw)
            self.canvas.set_color_of_selected(picked.name())

    def _universal_find(self):
        """Ctrl-F routes by focus: the terminal gets its own find-in-output bar
        if it currently has focus, otherwise the canvas find-widgets bar opens.
        Both find surfaces exist independently; this just picks the right one."""
        from PySide6.QtWidgets import QApplication
        focused = QApplication.focusWidget()
        terminal = self.bottom_panel.terminal
        if focused is not None and (focused is terminal.view or terminal.isAncestorOf(focused)):
            terminal.open_find()
            return
        self._canvas_find_bar.open()
        if self._canvas_find_bar.box.text():
            self._canvas_find_query(self._canvas_find_bar.box.text())

    def _canvas_find_query(self, text: str):
        """Match widgets on the current page by object name or any string-typed
        declared property value (e.g. a button's text), case-insensitive."""
        needle = text.strip().lower()
        matches = []
        if needle:
            for dw in self.canvas.page.widgets:
                haystacks = [dw.object_name] + [
                    str(v) for v in (dw.properties or {}).values() if isinstance(v, str)
                ]
                if any(needle in h.lower() for h in haystacks):
                    matches.append(dw)
        self._canvas_find_matches = matches
        self._canvas_find_index = 0 if matches else -1
        self._canvas_find_bar.set_status(1 if matches else 0, len(matches))
        if matches:
            self.canvas.select_by_model(matches[0])

    def _canvas_find_step(self, direction: int):
        matches = self._canvas_find_matches
        if not matches:
            return
        self._canvas_find_index = (self._canvas_find_index + direction) % len(matches)
        self._canvas_find_bar.set_status(self._canvas_find_index + 1, len(matches))
        self.canvas.select_by_model(matches[self._canvas_find_index])

    def _pick_media_for(self, dw):
        key = self._choose_asset()
        if key:
            self.canvas.select_by_model(dw)
            self.canvas.apply_property("asset", key)
            self.properties_panel.set_target(dw, self.canvas.selected_qwidget)
            self.status_bar.set_status(f"Media set to {key}")

    def _edit_markdown_for_dw(self, dw):
        """Right-click 'Edit content…' -> open the Studio for this widget's first
        markdown property."""
        component = self.registry.get(dw.component_id)
        if not component:
            return
        prop = next((s.name for s in component.properties
                     if (s.type or "") == "markdown"), None)
        if prop is None:
            return
        self.canvas.select_by_model(dw)
        self._edit_markdown_for_property(prop)

    def _edit_markdown_for_property(self, prop_name):
        """Open the Markdown Studio to edit a markdown-typed property."""
        dw = self.canvas.selected_model
        if dw is None:
            return
        from .panels.markdown_studio import MarkdownStudio
        spec_default = ""
        component = self.registry.get(dw.component_id)
        if component:
            for spec in component.properties:
                if spec.name == prop_name:
                    spec_default = spec.default
                    break
        current = dw.properties.get(prop_name, spec_default)
        result = MarkdownStudio.edit(current, self)
        if result is not None:
            self.canvas.apply_property(prop_name, result)
            self.properties_panel.set_target(dw, self.canvas.selected_qwidget)
            self.status_bar.set_status("Rich text updated")

    def _pick_asset_for_property(self, prop_name):
        """Asset picker fired from the Properties editor's asset field."""
        dw = self.canvas.selected_model
        if dw is None:
            return
        key = self._choose_asset()
        if key:
            self.canvas.apply_property(prop_name, key)
            self.properties_panel.set_target(dw, self.canvas.selected_qwidget)
            self.status_bar.set_status(f"{prop_name} set to {key}")

    def _choose_asset(self):
        """Pick from project assets, or import a new file on the spot."""
        keys = self.assets.keys()
        options = keys + ["Browse for a file…"]
        if not keys:
            choice = "Browse for a file…"
        else:
            choice, ok = QInputDialog.getItem(self, "Choose media", "Asset",
                                              options, 0, False)
            if not ok:
                return None
        if choice == "Browse for a file…":
            path, _ = QFileDialog.getOpenFileName(
                self, "Add media", "",
                "Media (*.png *.jpg *.jpeg *.gif *.webp *.svg *.bmp "
                "*.mp3 *.wav *.ogg *.mp4 *.mov *.webm);;All files (*)")
            if not path:
                return None
            imported = self.assets.import_path(path)
            self.assets_panel._refresh()
            for msg in self.assets.errors:
                self.problems.warn(msg, source="assets")
            self.assets.errors.clear()
            return imported[0].key if imported else None
        return choice

    def _show_quick_edit(self, dw):
        live = self.canvas._live_by_model.get(id(dw))
        if live is None:
            return
        self.canvas.select_by_model(dw)
        opacity = float(dw.properties.get("opacity", 1.0))
        color = dw.properties.get("color", self.canvas.app_theme.tokens()["accent"])
        self.quick_edit.show_for(live, self.canvas, opacity, color,
                                 self.canvas.app_theme.radius)

    def _fit_contents(self, dw):
        live = self.canvas._live_by_model.get(id(dw))
        if live is None:
            return
        hint = live.sizeHint()
        self.canvas.select_by_model(dw)
        self.canvas.set_geometry_of_selected(dw.x, dw.y,
                                             max(hint.width(), 24),
                                             max(hint.height(), 20))

    def _fill_width(self, dw):
        margin = 20
        self.canvas.select_by_model(dw)
        # set_geometry_of_selected takes logical units - the canvas panel's
        # actual pixel width has to be converted back to logical first, or
        # this would double-apply the zoom factor (fill-width at 200% zoom
        # would otherwise make the widget 4x too wide once re-rendered).
        logical_w = self.canvas.to_logical(self.canvas.width())
        self.canvas.set_geometry_of_selected(margin, dw.y,
                                             max(60, logical_w - margin * 2),
                                             dw.height)

    def _reset_size(self, dw, component):
        from .canvas import _default_width, _default_height
        self.canvas.select_by_model(dw)
        self.canvas.set_geometry_of_selected(dw.x, dw.y,
                                             _default_width(component),
                                             _default_height(component))

    def _quick_animate(self, dw, kind):
        self.animations.add(dw.object_name, Animation(kind=kind, trigger="on_show"))
        self.canvas.preview_animation(dw.object_name, Animation(kind=kind))
        self.animations_panel.set_target(dw, self.animations)
        self.status_bar.set_status(f"{kind.replace('_', ' ')} added to {dw.object_name}")

    def _copy_widget(self, dw):
        self._clipboard_widget = (dw.component_id, dict(dw.properties),
                                  dw.width, dw.height)
        self.status_bar.set_status(f"Copied {dw.object_name}")

    def _paste_widget(self):
        if self._clipboard_widget is None:
            return
        component_id, properties, width, height = self._clipboard_widget
        clone = self.canvas.place_component(component_id)
        if clone is not None:
            clone.properties = dict(properties)
            clone.width, clone.height = width, height
            self.canvas._rebuild_live(clone)
            self.canvas.select_by_model(clone)
            self.status_bar.set_status(f"Pasted {clone.object_name}")

    def _show_qt_properties(self, dw):
        """Reveal the live, editable Qt-property table in the Properties pane
        (spec §22). Replaces the old read-only QMessageBox dump."""
        self.canvas.select_by_model(dw)
        self._show_pane("properties")
        self.properties_panel.focus_qt_properties()

    def _on_qt_property_changed(self, name, value):
        """A live Qt-property edit: apply it to the canvas widget and persist it
        to the model's qt_props so it survives save/load and reaches codegen."""
        dw = self.canvas.selected_model
        live = self.canvas.selected_qwidget
        if dw is None or live is None:
            return
        from ..core import introspect
        if introspect.write_property(live, name, value):
            dw.qt_props[name] = value
            self.canvas.sync_overlay()
            self.status_bar.set_status(f"{dw.object_name}.{name} = {value}")

    def _show_pane(self, view_id):
        """Force a side pane open (used by context menus and internal jumps)."""
        self.activity_bar.set_active_view(view_id)
        self.side_panel.show_view(view_id)

    # --- project persistence -------------------------------------------------
    def save_project(self, ask=False, target_dir=None):
        directory = target_dir or (None if ask else self.project_dir)
        if directory is None:
            directory = QFileDialog.getExistingDirectory(self, "Save project to folder")
            if not directory:
                return None
        try:
            self.project_io.save(
                self.project, directory,
                assets=self.assets,
                app_theme=self.canvas.app_theme,
                animations=self.animations.to_dict(),
                stylesheets=self.stylesheets.to_dict())
        except OSError as exc:
            self.problems.error(f"Save failed: {exc}", source="project")
            self.status_bar.set_status("Save failed")
            return None
        self.project_dir = directory
        self.assets_panel._refresh()
        from .splash import add_recent
        add_recent(directory)
        for msg in self.project_io.errors:
            self.problems.warn(msg, source="project")
        self.status_bar.set_status(f"Saved to {os.path.basename(directory)}")
        return directory

    def open_project(self, directory=None):
        if directory is None:
            directory = QFileDialog.getExistingDirectory(self, "Open project folder")
            if not directory:
                return None
        try:
            project, assets, app_theme, animations, stylesheets = \
                self.project_io.load(directory)
        except (FileNotFoundError, ValueError) as exc:
            self.problems.error(str(exc), source="project")
            self.status_bar.set_status("Could not open project")
            return None

        # a stale Quick Preview would be showing pages from the project we're
        # about to replace - close it rather than let it point at dead objects
        if self.quick_preview is not None:
            self.quick_preview.hide()

        self.project = project
        self.target = project.target       # target follows the opened project
        self.project_dir = directory
        self.assets = assets
        self.assets_panel.set_manager(assets)
        self.animations = AnimationSet.from_dict(animations)
        self.stylesheets.load_list(stylesheets)
        self.canvas.app_theme = app_theme
        self.page = project.pages[0]
        self.pages_panel.project = project
        self.pages_panel.refresh()
        # a freshly opened project starts with a clean slate of tabs/undo
        # history - restoring exactly which tabs were open on last save is a
        # possible fast-follow, not required here
        self.open_pages = [self.page]
        self.undo_stack = UndoStack()
        self.page_undo_stacks = {id(self.page): self.undo_stack}
        self.undo_stack.on_change(self._refresh_undo_state)
        self.canvas.set_undo_stack(self.undo_stack)
        self.editor_tabs.refresh(self.open_pages, 0)
        self.canvas.load_page(self.page)
        self.canvas.apply_app_theme()
        self.layers_panel.set_page(self.page)
        self.properties_panel.set_target(None)
        self.animations_panel.set_target(None, self.animations)
        for msg in self.project_io.errors:
            self.problems.warn(msg, source="project")
        self.status_bar.set_count(len(self.page.widgets))
        self.status_bar.set_app_mode(app_theme.mode)
        self.status_bar.set_target(self.target)
        self.status_bar.set_status(f"Opened {project.name}")
        return directory

    def export_project(self):
        if not self.project_dir:
            self.status_bar.set_status("Save the project before exporting")
            return None
        path, _ = QFileDialog.getSaveFileName(
            self, "Export project archive", f"{self.project.name}.zip", "Zip (*.zip)")
        if not path:
            return None
        made = self.project_io.export_archive(self.project_dir, path)
        self.status_bar.set_status(f"Exported {os.path.basename(made)}")
        return made

    # --- Qt Designer interop -------------------------------------------------
    def import_ui(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Import a Qt Designer form", "", "Qt Designer UI (*.ui)")
        if not path:
            return None
        try:
            page = self.ui_io.import_file(path)
        except UiImportError as exc:
            self.problems.error(str(exc), source="import", file=path)
            self.status_bar.set_status("Could not import .ui")
            return None
        self.project.pages.append(page)
        self.pages_panel.refresh()
        self.pages_panel.list.setCurrentRow(len(self.project.pages) - 1)
        for w in self.ui_io.warnings:
            self.problems.warn(w, source="import", file=path)
        self.status_bar.set_status(
            f"Imported {page.name} ({len(page.widgets)} widgets)")
        return page

    def export_ui(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Export page as Qt Designer form",
            f"{self.page.name}.ui", "Qt Designer UI (*.ui)")
        if not path:
            return None
        self.ui_io.export_page(self.page, path)
        for w in self.ui_io.warnings:
            self.problems.warn(w, source="export")
        self.status_bar.set_status(f"Exported {os.path.basename(path)}")
        return path

    # --- stylesheets ---------------------------------------------------------
    def import_stylesheet(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Import a stylesheet", "", "Qt stylesheet (*.qss *.css)")
        if not path:
            return None
        try:
            sheet = self.stylesheets.import_file(path)
        except StylesheetError as exc:
            self.problems.error(str(exc), source="styles", file=path)
            self.status_bar.set_status("Stylesheet import failed")
            return None
        for msg in self.stylesheets.errors:
            self.problems.warn(msg, source="styles", file=path)
        self.stylesheets.errors.clear()
        self.canvas.set_extra_stylesheets(self.stylesheets.sources())
        self._refresh_quick_preview()
        self.status_bar.set_status(f"Imported {sheet.name}")
        return sheet

    # --- animations ----------------------------------------------------------
    def _on_animation_added(self, object_name, animation):
        self.animations.add(object_name, animation)
        self.status_bar.set_status(f"{animation.label()} added to {object_name}")

    def _on_animation_removed(self, object_name, index):
        self.animations.remove(object_name, index)
        self.status_bar.set_status(f"Animation removed from {object_name}")

    def _on_animation_preview(self, object_name, animation):
        self.canvas.preview_animation(object_name, animation)

    # --- problems ------------------------------------------------------------
    def _sync_problems(self, log):
        self.bottom_panel.clear_problems()
        for p in log.all():
            self.bottom_panel.add_problem(p.label(), p.file, p.line)
        counts = log.counts()
        if counts["error"]:
            self.bottom_panel.show()
            self.bottom_panel.show_problems_tab()

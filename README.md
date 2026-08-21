# PaperLoom

A Qt visual GUI builder that gets out of your way. Browse a searchable component
library with live previews, drop pieces onto a blank canvas, drag and edit what
you can see, and PaperLoom writes real, runnable Qt code underneath - PySide6 or
C++, chosen per project, both proven to compile and run.

The shell is VS Code-shaped: an activity bar, collapsible side panels, the
canvas, a collapsible bottom panel, and a status strip. Nothing is forced open.

See `qt_gui_builder_spec.md` for the full design.


## Features

**Shell** — VS Code-shaped: menu bar (`PaperLoom | File | Edit | Selection | View | Go | Run |
Terminal`) with global search, command strip, pinnable tools toolbar, activity bar,
collapsible side panels, tabbed bottom panel, status bar.

**Panels** — Components (source tabs + live previews), Pages (multi-skeleton),
Layers (object tree, two-way selection sync), Properties (typed editors),
Assets (images/fonts).

**Library** — 40 components (buttons, inputs, knobs, cards, tabs, tables, app chrome...); side panel for quick access, plus an EasyEDA-style popup dialog
(`Ctrl+L`) with source/category filters, a result table, a large live preview and
a details pane showing properties, types, defaults and signals.

**Editing** — direct manipulation with resize handles, snap-to-grid with settable
snap size, PowerPoint-style alignment guides, alignment (6 ways), z-order,
opacity, duplicate/delete, undo/redo.

**App theming** — the app you design gets light/dark for free. Toggle the preview
with the second sun/moon button (Ctrl+Alt+D); generated projects ship
`app_theme.py` and a one-call `toggle_theme()`.

**Multi-page** — pages generate one navigable app (`app.py` with `navigate()`),
not a folder of unrelated windows.

**Command palette** (`Ctrl+Shift+P`) — indexes every menu command, every page and
every component in one filter.

**Themes** — PaperLoom itself has a light/dark pair (sun/moon toggle, Ctrl+Shift+D) plus Midnight and Forest (PaperLoom Default, Paper Light, Midnight, Forest);
users can import their own JSON theme via View > Import Theme. A theme file may
override any subset of tokens; the rest inherit from the default.

**Bottom panel** — Output (live process text), Problems (structured, clickable
file/line entries from tracebacks and codegen coercions), Debug, and a real
integrated Terminal.

**Codegen** — PySide6 and C++ Qt Widgets, both round-trip safe (generated file
always regenerable, hand-written logic never overwritten) and both value-sanitized
so PaperLoom can never emit code that fails to parse.

## Run

```bash
pip install -r requirements.txt
python3 main.py
```

## Test (headless)

```bash
QT_QPA_PLATFORM=offscreen python3 tests/test_app.py
```

Covers registry loading, all components generating in both languages, model
round-trip, place/select/resize with model sync, schema-driven property editing,
delete/duplicate, undo/redo, multi-page skeletons, layers-selection sync,
library source tabs, shell composition, and a real C++ compile when a Qt6
toolchain is present.

## Layout

```
paperloom/
  theme.py                design tokens - colour, spacing, radius, motion, one accent
  core/
    model.py              DesignWidget / DesignPage / Project - serializable model
    undo.py               command stack for undo/redo
  components/
    registry.py           loads component folders, renders templates, source tabs
    factory.py            model -> live QWidget (metadata-driven, no per-widget code)
    library/<id>/         one folder per component:
      meta.json             metadata + property schema + signals + source + qt class
      template.pyside.jinja / template.cpp.jinja
  codegen/
    base.py               round-trip write-once guarantee
    pyside_backend.py     PySide6 generation
    cpp_backend.py        C++ generation (ui header + class + main + CMakeLists)
  ui/
    icons.py              inline Lucide icons, tinted to theme
    preview.py            renders a component to a preview pixmap
    activity_bar.py       VS Code icon rail (switches side panels)
    side_panel.py         collapsible host stacking the panels
    canvas.py             hosts live widgets, design-mode filter, multi-page load
    selection.py          selection outline + resize handles
    main_window.py        the full shell composition + wiring
    panels/
      library_panel.py    source tabs + search + live preview cards
      pages_panel.py      multi-skeleton page navigator
      layers_panel.py     object tree for the current page
      property_popover.py schema-driven contextual quick-property editor
      top_bar.py          command strip (menu, undo/redo, target, zoom, Run)
      bottom_panel.py     tabbed Output/Problems
      status_bar.py       thin accent status strip
```

## Adding a component

Drop a folder in `components/library/`:

```
components/library/my_widget/
  meta.json               id, name, category, source, widget_class, properties, signals
  template.pyside.jinja
  template.cpp.jinja
```

No code changes needed - the registry loads it, the factory instantiates it from
`widget_class`, both codegen backends emit it, and it appears under its `source`
tab in the library with an auto-rendered preview. `source` is one of
`paperdesign` / `default` / `user`.

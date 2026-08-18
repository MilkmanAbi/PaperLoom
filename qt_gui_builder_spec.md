# PaperLoom — a Qt visual GUI builder

**Project spec, draft v0.2.** This document is a synthesis of a planning conversation, not a spec handed down from nowhere — everywhere below marked **Decided** reflects something explicitly settled in that discussion; everywhere marked **Proposed** or **Open question** is a recommendation or a gap that still needs a call before or during coding. Nothing marked Proposed should be treated as locked.

**v0.2 changelog:** name settled (PaperLoom); builder language settled (PySide6); generated-app language is now a per-project choice (PySide6 or C++), not fixed to one; bottom bar scope, component format, and project file format all resolved. See §9 for what's still genuinely open.

---

## 0. Vision

A desktop GUI builder for Qt that gets out of your way. You open it, you get a blank canvas with a real window frame already drawn, you search a library for the piece you want (a button, a search bar, a modal, whatever), you drag it in, you drag its handles and click its color, you hit Ctrl+S, and somewhere underneath, real Qt code is being written for you — PySide6 or C++, whichever you picked when you started the project — a working skeleton with example handlers already wired, not a diagram that pretends to be an app.

The existing options in this space (Qt Designer, Glade, Cambalache) are built for people who already know the toolkit. This one is built so a complete beginner can produce a native Qt app, and so an experienced dev can still reach for precision and raw code the moment they want it. Neither audience should have to fight the tool to get what they came for.

**The bar, stated plainly: MS Paint.** Pick a tool, drop it, drag it, change what you can see, done. Nothing else about the tool should be harder to reach than that, and the power-user stuff should still be one click away for the people who want it — not baked into the default view.

---

## 1. Design philosophy

### 1.1 Compact vs. cramped — these are different axes

**Decided.** "Compact" is about not wasting space on what's actually shown. "Cramped" is about how much gets forced onto the screen at once, with no way to send any of it away. Qt Designer is cramped, not compact: Object Inspector, Property Editor, and Resource Browser are all docked and visible the instant you launch it, whether you asked for them or not. That's the thing being explicitly rejected here, not density itself.

The fix isn't "make everything bigger" or "make the property table nicer." It's: **most of what Qt Designer permanently shows becomes something you go and open, not something you're handed.**

### 1.2 Direct manipulation is the default mode; panels are the precision mode

**Decided.** The things people touch constantly — position, size, color, text content — live on the object itself, not in a table you read numbers off of:

- Drop a widget on the canvas, it gets resize handles right there. Drag them, it resizes. (Paint's selection box, basically.)
- Click it, a small color/style affordance appears next to the selection. You're not opening a docked panel and scrolling to find a `fill` property row.
- Right-click gives you quick actions (delete, duplicate, common property tweaks) without opening anything.

The full property table, the object/hierarchy tree, and the raw-code drop-in still exist in full — they don't get dumbed down or removed — but they are **panels you open**, closed by default, not a permanent fixture. Closing the property panel doesn't cost functionality; it means you're doing that thing through direct manipulation instead. This is the actual noob-to-power-user bridge: the same underlying capability, reached two different ways depending on what you opened.

### 1.3 Visual language: PaperDesign

**Decided.** The builder's own chrome follows the user's existing personal design system, [PaperDesign](https://github.com/MilkmanAbi/PaperDesign) (see `PaperDesign.md`, `PaperImplementation.md`, `PaperPatterns.md` in that repo for the full spec — this section only pulls the pieces that bear directly on this tool). Key things that actually apply here:

- **8px base unit, 12-column desktop grid.** All builder chrome — sidebar, bottom bar, popovers — snaps to this. The canvas itself defaults to an 8px grid too (toggleable, see §4.3), since that's the tool's own house grid.
- **Panels are grid-column-wide and push content, never float over it or dim it.** No modal-style property editor. When the property panel opens, the canvas area gets narrower; it doesn't get covered.
- **One muted accent color**, used only for the primary action (Run/Build) and active/selected states. Everything else — warnings, hover states, secondary buttons — is a duller version of it, never a second saturated color competing for attention.
- **Object/hierarchy tree (when opened) follows the Tree View pattern:** flat 32px rows with indentation, not nested cards; a 16px disclosure triangle rotating 90° in 100ms; children appear immediately on expand, no stagger animation; selection is an accent-muted fill across the full row width.
- **Update locality is a hard requirement, not a nicety.** Dragging a resize handle updates only that widget's on-canvas rendering and (if the property panel happens to be open) its own fields — never the object tree, never the output panel, never the library sidebar. This is specifically what makes large forms in Qt Designer start to feel sluggish; getting this right is most of what makes the tool *feel* fast, independent of how fast it actually is.
- **Motion has a job.** 100ms for anything the tool already knows for certain (a selection outline appearing, a toggle flipping) — shown immediately, not eased in. 180ms for a dropdown or tab switch. 260ms only for a large element traveling real distance (a side panel opening). A selection box should appear the instant you click, not fade in.
- **Icons: [Lucide](https://lucide.dev)**, one family, one weight, throughout. No mixing icon sets.

---

## 2. Application architecture

### 2.1 Build the tool itself in Qt — no window embedding, anywhere

**Decided.** The single most important architectural call: the builder is itself a Qt application, and the canvas hosts real, live `QWidget` instances as children within its own widget tree, in the same process. This is exactly how Qt Designer, Xcode's Interface Builder, and the old WinForms designer all work under the hood — hosting widgets inside other widgets is just normal Qt composition, no OS-specific plumbing required, identical on Windows/Linux/macOS.

The only non-obvious piece is a **design-mode event filter**: an event filter installed on every child widget on the canvas that intercepts mouse events *before* they reach the widget's normal handling, so clicking a `QPushButton` in the canvas selects/drags it instead of actually firing its click. That filter, plus the selection/resize-handle overlay drawn on top of it, is the entire mechanism. No cross-process or cross-toolkit window embedding (XEmbed, `SetParent`, etc.) is needed anywhere in this design, and none should be added later just to support GTK — a GTK version, if it ever happens, is a separate native tool, not a widget hosted inside this one.

### 2.2 Builder language: PySide6

**Decided.** The builder itself is written in PySide6 — no compile step to fight through while iterating on the UI/UX, and Python is a substantially easier target for AI-assisted coding sessions, which matters given how much of this is being shaped through exactly that kind of back-and-forth. This is the builder's own implementation language only — it does not constrain what the builder can *generate* (§2.2a).

### 2.2a Generated app language: a per-project choice, not fixed

**Decided.** The builder being PySide6 does not mean every app it produces is PySide6. At project creation, the user picks the target for *that project* — **PySide6** or **C++ (Qt Widgets)** — and the builder accommodates whichever was picked for the lifetime of that project. This means the codegen layer (§6) needs two real backends, not one, fairly early on.

Sequencing implication for v0 (see §10): build and prove the PySide6 codegen path first, since it's the same language as the builder itself and has the shortest path to a working end-to-end slice. Add the C++ backend once that path is proven, not simultaneously — standing up both codegen targets in the very first milestone is exactly the kind of scope creep the rest of this spec is trying to avoid.

### 2.3 Styling and effects: QSS is the codegen target, not custom animation code

**Decided.** Hover-flip, press/depress, and similar state-based visual feedback should compile down to Qt Style Sheets (`QPushButton:hover { ... }`, `:pressed { ... }`), because that's idiomatic Qt and it's what a Qt dev would hand-write anyway. `QPropertyAnimation` is the target for genuine motion/transition effects on top of that, not for state-swap styling.

### 2.4 Custom/raw-code escape hatch: promoted widgets

**Decided.** For anything the library doesn't cover, the user drops a placeholder on the canvas and "promotes" it to a custom class + header, the same way Qt Designer's promoted-widget feature already works — the canvas just draws it as a labeled box at design time without needing to understand its internals, and the generated code instantiates the real class. This is direct prior art, not something being invented from scratch.

---

## 3. UI layout

```
┌─────────┬──────────────────────────────────────┬───────────────┐
│         │                                      │  (closed by   │
│ Library │              Canvas                  │   default)    │
│ sidebar │        blank page, real window        │  Inspector /  │
│         │      chrome, grid overlay toggle       │  Object tree  │
│ search  │                                      │  panel        │
│ +       │      [selected widget: resize          │               │
│ filter  │       handles + contextual popover]    │               │
│         │                                      │               │
├─────────┴──────────────────────────────────────┴───────────────┤
│  Bottom bar — pinnable / collapsible, VS Code style              │
│  (build output, warnings/errors — exact contents: open question) │
└───────────────────────────────────────────────────────────────┘
```

### 3.1 Left sidebar — the component library

Always visible (this is the one panel that's on by default, alongside the canvas itself — everything else is opt-in). Search box at the top, category filter below it, results as a scrollable list. See §5 for what lives in it.

### 3.2 Bottom bar — pinnable/collapsible, VS Code-style

**Decided.** Collapses to a thin strip or expands to a working panel, same interaction model as VS Code's terminal/problems panel. Carries both: build output/warnings/errors (matches the "1 warning · 0 errors" status-bar instinct from the earlier mockup) *and* quick global actions. **Open question, narrower now:** the exact action set beyond output/status — likely candidates are Run/Preview, a target-language indicator (PySide6/C++ for the current project), and switch-active-page, but the final list is still worth choosing deliberately rather than growing by accretion.

### 3.3 Canvas

- **Decided.** Starts blank. Real OS window chrome is drawn automatically (this is free — `QMainWindow` gets the native title bar on every platform by default, no extra work, unless/until frameless chrome becomes a deliberate v2 goal — see §9).
- **Decided.** A grid overlay is available (PaperDesign's 8px unit as the default spacing, toggleable/adjustable).
- **Decided.** Selected widgets get on-canvas resize handles (drag to resize) and a small contextual property popover (the 2-4 properties that matter most for that widget type — text, color, maybe font — not a full property list).
- **Decided.** Right-click gives a context menu for quick actions: delete, duplicate, and likely a handful of common property toggles.

### 3.4 Optional/closeable panels

- **Object/hierarchy tree** — full widget tree for the current page, Tree View pattern (§1.3).
- **Full property panel** — the complete, precise property list (this absorbs what the earlier mockup's GENERAL/STYLE/GEOMETRY/LAYOUT sectioned table was doing) for when the contextual popover isn't enough.
- **Raw code / promoted-widget panel** — where the escape hatch (§2.4) lives.

All three: closed by default, opened explicitly, docked (not floating, not modal) when open, and closing any of them costs zero functionality — everything reachable there is also reachable through direct manipulation or the right-click menu for common cases.

---

## 4. Component library system

### 4.1 What it is

**Decided.** Not just a palette of raw Qt widget types (`QPushButton`, `QLineEdit`, ...) — a large, searchable/filterable catalog of ready-made, modular pieces of Qt code: complete small patterns, not just bare widget classes. Framed explicitly against EasyEDA's component library model: browse, search, filter, drop in, then customize — rather than starting every button from a blank generic widget.

### 4.2 Initial catalog (starting list, not exhaustive)

From the planning discussion directly:

- Search bar
- Pill button
- Toggle button
- Traffic-light window controls (macOS-style)
- Blank/plain button
- Text box
- Overlay
- Modal dialog

Plus the obvious baseline set underneath these (label, checkbox, radio, combo box, slider, basic layouts) as raw building blocks the composed examples above are themselves built from.

### 4.3 Component format

**Decided.** One directory per component:

```
components/pill_button/
  meta.json               — metadata (see below)
  template.pyside.jinja   — PySide6 code template
  template.cpp.jinja      — C++ Qt code template
  preview.png             — auto-generated, not hand-drawn (see below)
```

**Why a directory per component, not one big registry file or a single all-languages template:** the library is meant to grow to "a shitton" of entries. A single registry file (one giant JSON array, one big Python dict) becomes an editing bottleneck and a merge-conflict magnet at that scale; a folder per component means adding one is purely additive — drop in a new folder, nothing else has to be touched or re-indexed by hand. The catalog is just "load every `meta.json` under `components/` at startup."

**`meta.json` shape:**

```json
{
  "id": "pill_button",
  "name": "Pill button",
  "category": "buttons",
  "tags": ["button", "rounded", "pill", "cta"],
  "description": "A fully rounded button, radius = height / 2.",
  "properties": [
    {"name": "text", "type": "string", "default": "Button", "control": "text"},
    {"name": "color", "type": "color", "default": "#6B7CFF", "control": "color_picker"},
    {"name": "width", "type": "int", "default": 120, "control": "number"},
    {"name": "height", "type": "int", "default": 32, "control": "number"}
  ],
  "quick_properties": ["text", "color"],
  "signals": [
    {"name": "clicked", "stub": "on_{id}_clicked"}
  ]
}
```

- `properties` is the full list — what the full property panel (§3.4) shows.
- `quick_properties` is a subset — what the on-canvas contextual popover (§1.2, §3.3) shows. This is the field that actually implements the direct-manipulation/precision-panel split from a data standpoint: one property list drives both surfaces, just filtered differently.
- `signals` declares which signals get an example stub generated and wired on placement (§6.2) — the stub name is templated so multiple instances of the same component on one page don't collide.
- `control` tells the property panel/popover which editing widget to render for that property (a color picker for `color`, a spinbox for `int`, and so on) — a small fixed enum, not open-ended, so the property-rendering UI code stays generic instead of special-casing every component.

**Two template files per component, one per codegen target, using [Jinja2](https://jinja.palletsprojects.com/) for substitution.** This is the "extra effort is fine if it serves the goal" call: a single language-agnostic intermediate representation (build one abstract description, generate both languages from it through a shared codegen engine) would be more elegant on paper, but for genuinely "ultra short implementations" it's disproportionate engineering — two small, readable, independently-maintainable templates per component is *less* total complexity than one generic cross-language codegen system, at this component size. Revisit only if the two templates start drifting out of sync with each other in practice — not before.

**Previews are rendered, not drawn.** Since the builder can actually instantiate any PySide6 widget headlessly, a component's preview thumbnail is generated once by rendering `template.pyside.jinja` with default property values and screenshotting the result, then cached. Nobody has to hand-illustrate "a shitton" of preview icons, and previews stay perfectly accurate to what actually gets placed, by construction.

### 4.4 Icons

**Decided.** Lucide, for both the builder's own chrome and as the default icon option offered to users placing icon-bearing components (buttons with icons, etc.).

---

## 5. Starter templates

**Decided.** Two options on project creation:

1. **Blank sketch** — only the window titlebar exists. True blank-page start.
2. **PaperDesign starter** — a small sample app, fully built in the PaperDesign visual language, that the user can edit and build outward from rather than starting from nothing. Aimed specifically at people who want a real starting point rather than an empty canvas.

---

## 6. Code generation philosophy

### 6.1 Pragmatic over pure

**Decided.** The generated output should prioritize being an easy, working starting point over being a maximally clean/minimal abstract skeleton. Stitch the library pieces together into something a beginner can immediately extend, rather than spending effort making the generated code architecturally pristine at the cost of being harder to build on. "Ease of implementation later" is the explicit design goal for the codegen layer, not code-golf-minimal output.

### 6.2 Function stubs, wired up

**Decided.** Components placed from the library should come with example handler stubs already connected where relevant — a button's `clicked` signal already hooked to a named (empty or example-filled) slot, not left disconnected for the user to wire up from scratch. The user's job is to fill in logic, not to first go learn how signals/slots connect.

### 6.3 Round-trip safety — generated skeleton vs. hand-written logic, kept physically separate

**Decided.** This is the exact problem that damaged Cambalache's reputation (hand-edit the generated file, reimport, and your edits get mangled) — and Qt's own toolchain already has a clean answer for it that predates this project, for *both* codegen targets:

- **C++:** `uic` generates `ui_MainWindow.h` (never hand-edited, safely regenerated any time); `MainWindow.h`/`.cpp` are hand-written and simply `#include` the generated header.
- **PySide6:** `pyside6-uic` generates a `Ui_MainWindow` class in its own module (never hand-edited); a hand-written class composes or inherits it and calls `setupUi()` — Python's version of the exact same convention.

Both targets already have this pattern natively, so nothing needed to be invented — the split is identical in spirit regardless of which language a given project targets:

- **Generated, always safe to regenerate:** the layout/skeleton code produced from the visual design.
- **Hand-written, never touched by regeneration:** a separate logic file per page, which imports/includes the generated skeleton and is where the wired-up stub handlers (§6.2) actually live once the user starts filling them in.

This means re-opening a page in the builder and changing its layout never risks clobbering logic the user already wrote — the two live in different files by construction, not by convention the user has to remember to follow, in either language.

---

## 7. Project & file model

### 7.1 Multi-page / multi-skeleton structure

**Decided.** A project is a collection of **skeletons** (pages/windows/screens):

- **A whole new page/window/screen → a new skeleton** within the same project.
- **Element-level changes on an existing page (add/remove/move/restyle widgets) → stay under the existing skeleton.** No new skeleton is created for this.

This is the project's core organizational unit — closer to Figma's multi-frame model or a multi-form desktop app than to a single-file Qt Designer `.ui`.

### 7.2 Save flow

**Decided.** Ctrl+S saves. Fast, standard, no ceremony.

### 7.3 On-disk structure

**Decided.** Two distinct artifacts per page, matching §6.3's split exactly: a JSON design-time source of truth (what the builder actually reads and writes) versus real generated code (what actually runs) — these were never in tension, they're different layers.

`.page` files are **JSON**. Reasoning: no legacy format to interoperate with since this is a from-scratch tool, so there's no reason to take on XML's verbosity; JSON is in the Python standard library (matches the PySide6 builder directly), diffs and reviews cleanly in git, and is trivial to version/migrate later if the schema changes.

```
myapp.paperloom/
  project.json                — app metadata, accent color, page list, target
                                 language for this project (pyside6 | cpp),
                                 PaperDesign starter vs blank origin, etc.
  pages/
    main_window.page.json     — design-time source of truth for one skeleton
                                 (widget tree + properties + bindings)
    settings_dialog.page.json
  generated/
    pyside6/                  — present if project target is pyside6
      main_window_ui.py       — regenerated freely, never hand-edited (§6.3)
      main_window.py          — hand-written logic, imports the generated
                                 module, created once, never overwritten
    cpp/                      — present if project target is cpp
      ui_main_window.h        — regenerated freely, never hand-edited (§6.3)
      main_window.h / .cpp    — hand-written logic, #includes the generated
                                 header, created once, never overwritten
```

A project targets one language, chosen at creation (§2.2a) — the `generated/` tree only ever has one of the two subfolders populated for a given project, not both.

---

## 8. Scope for v0 — what's explicitly out

**Decided/carried over from earlier discussion, restated as hard scope boundaries:**

- **Qt only.** No GTK support in v0, no attempt at a shared cross-toolkit abstraction. If a GTK version ever happens, it's a second, native tool — not embedded inside this one.
- **No custom/frameless window chrome.** Native OS title bar only for v0; frameless/custom chrome is real per-platform work (Windows DWM/`WM_NCHITTEST` handling, Linux window-manager dependence) and is explicitly a v2+ stretch goal, not day one.
- **No cross-process widget embedding of any kind** — not needed given §2.1, and shouldn't be reached for later either.
- **Small widget/component set to start**, covering the initial catalog in §4.2 well rather than covering Qt's full widget surface shallowly.

---

## 9. Open questions — things that need an answer before or during coding

All five original open questions from draft v0.1 are resolved as of v0.2 — builder language, bottom bar scope, component format, project file format, naming (see the changelog at the top). What's still actually open:

1. **Exact bottom bar action set** beyond output/status (§3.2) — narrowed, not closed.
2. **Jinja template conventions** — shared macros/partials across component templates so the two-file-per-component approach (§4.3) doesn't drift into duplicated boilerplate as the library grows. Not a blocker for the first milestone; worth revisiting once there are enough components to see the pattern.
3. **Exact timing of the C++ codegen backend** relative to PySide6 — sequencing is proposed in §2.2a (PySide6 first) but not scheduled.

---

## 10. Suggested first milestone

Not a full roadmap — just the smallest slice that proves the hardest architectural bet (§2.1, the design-mode event filter over real hosted widgets) actually works before building anything else on top of it. All PySide6, per §2.2a's sequencing call:

1. A blank `QMainWindow` canvas (PySide6) that can host one real `QPushButton` as a child widget.
2. A design-mode event filter that intercepts clicks on it for selection instead of firing the button, plus a visible selection outline.
3. On-canvas resize handles that actually resize the real widget (proving direct manipulation works against a real `QWidget`, not a mock).
4. One property (button text) editable via a minimal contextual popover, driven by that component's `quick_properties` (§4.3) rather than hardcoded.
5. A "generate code" step that emits a real, runnable `main_window_ui.py` / `main_window.py` pair (§6.3, §7.3) for that one button in that one window — proving the full codegen path end to end, before the library, the multi-page model, the C++ backend, or any of the panel UI exists.

Once that slice works: build out the component format (§4.3) for real with two or three components, then the C++ codegen backend, then the rest of the panel UI. Everything in this document builds outward from step 5 once it's proven.

---

# PaperLoom v0.4 — two themes, one truth (Long March 2)

## 14. The editor theme / app theme split

The white-on-white and black-on-black bugs, the "grid renders over widgets"
glitching, and the muddy component previews were all **one root cause**:
component templates set no colours, so hosted widgets inherited *PaperLoom's own
chrome stylesheet* (light text) and sat on the design canvas (light surface).
Invisible text reads as "the grid is on top".

The fix separates two things that were being conflated:

- **Editor theme** (`core/themes.py`) — PaperLoom's own chrome. Now ships a real
  light/dark pair where every ink token flips alongside every surface token, so
  a light theme can never leave light text on a light panel. Toggle: the sun/moon
  button, `View > Toggle PaperLoom Light/Dark`, or `Ctrl+Shift+D`.
- **App theme** (`core/app_theme.py`) — the theme of the *app being designed*.
  Light and dark palettes, and a `role` system: a component declares
  `style_role` in its meta, the template does `setProperty("role", ...)`, and one
  window-level stylesheet styles every role. Toggle: the second sun/moon button,
  `View > Toggle App Light/Dark`, or `Ctrl+Alt+D`.

Because the canvas applies the *app* stylesheet to itself, the canvas, the
library previews and the generated app are three renderings of one definition —
the §13 fidelity invariant, now extended to colour.

### 14.1 Every generated app gets light/dark for free

Light/dark is the most basic thing an app should support, so PaperLoom provides
it rather than making the user build it. Every generated PySide6 project now
ships `app_theme.py` containing both palettes, and the generated `Ui_` class
exposes `toggle_theme(window)`. Switching the whole app is one call. The library
also ships a `theme_toggle` component (a sun/moon button) to wire it to.

Adding a component costs no QSS: pick an existing role and it is themed, in both
modes, on the canvas, in previews and in generated code.

## 15. Canvas: CAD grid and alignment guides

- The grid is painted in the canvas **background**, beneath every hosted widget.
  Child widgets always paint after their parent, so the grid can never cover or
  glitch over the design. Major lines every 5 steps; the step follows the snap
  size when snapping is on.
- **PowerPoint-style alignment guides**: while dragging, a widget snaps to other
  widgets' left/right/centre and top/bottom/middle edges, plus the canvas centre
  lines, and a dashed accent line shows the match. Toggleable
  (`View > Toggle Alignment Guides`), independent of grid snapping.
- Placement flows down and wraps into a new column instead of cascading into a
  pile, and each component has a role-appropriate default size.

## 16. Library expansion

40 components across buttons, inputs, display, containers, data and app chrome —
including primary/secondary/ghost/danger/pill/icon/toggle buttons, password and
search fields, text areas, spin boxes, date pickers, switches, sliders, **knobs**,
titles/subtitles/captions/badges/avatars, cards, panels, group boxes, tabs,
scroll areas, lists, trees, tables, app bars, sidebars, status strips and the
theme toggle.

The library is generated from `tools/build_library.py` — one spec table produces
every component's meta and both language templates, so expanding it further is
editing a list, not writing files by hand.

## 17. Multi-page cohesion

A project's pages now generate a real application, not a folder of unrelated
windows: `app.py` hosts every page in a `QStackedWidget`, exposes
`navigate(page_name)`, and owns the app-wide theme toggle. `app_logic.py` is the
hand-written, never-overwritten place for cross-page logic. Same round-trip
guarantee as everything else.

## 18. Toolbars

The quick-tools strip is a real `QToolBar`: movable, floatable, dockable to any
edge, hideable from `View > Toggle Tools Toolbar`.

---

# PaperLoom v0.5 — the backend gets smart (Long March 3)

UI work paused; this pass makes PaperLoom actually capable underneath.

## 19. Assets

`core/assets.py`. Two import rules, as specified:

- **A folder is used as-is** — indexed recursively in place, keyed by path
  relative to its parent (`icons/a.svg`). Nothing is copied.
- **Loose files are copied** into `<project>/assets/<filename.ext>`, with
  collision-safe renaming, so the project stays self-contained.

Everything is addressed by a stable project-relative key, so a project folder can
be moved or zipped without breaking references. Supported: images, animated
images, audio, video, fonts, stylesheets and data files, each classified by kind.
Unsupported types are *reported*, never silently dropped. Assets imported before
a project has a directory are held as links and migrated in on first save.

The library ships media components (`image_frame`, `gif_frame`, `video_frame`,
`audio_player`) that reference an asset by key.

## 20. Project persistence

`core/project_io.py`. The §7.3 format, implemented:

    myapp/
      project.json              metadata, target, app theme, page list,
                                 asset index, animations, stylesheets
      pages/<page>.page.json    one skeleton each
      assets/                   imported media
      generated/                codegen output

Writes are **atomic** (temp file then replace), so an interrupted save can't
leave a half-written project. Loads are **tolerant**: a missing or corrupt page is
reported as a problem and skipped rather than taking the project down. Page files
for deleted pages are cleaned up. `export_archive()` zips a project for sharing,
excluding generated output.

## 21. Qt Designer interop

`core/ui_io.py`. PaperLoom is no longer an island:

- **Import** any `.ui` file. Widgets are matched to components by Qt class, with
  Qt's structural scaffolding (`centralwidget`, menu/status bars, layouts)
  correctly skipped rather than imported as design elements. Anything unmappable
  is reported as a warning, not a failure.
- **Export** any page to valid `.ui`, usable in Qt Designer, `uic` or `QUiLoader`.
- **Lossless for our own files**: export stamps a `paperloomComponent` property,
  so a PaperLoom → `.ui` → PaperLoom trip preserves exact component identity
  (a `title` comes back a `title`, not a generic `QLabel`). Qt Designer ignores
  the extra property.

## 22. Live Qt property introspection

`core/introspect.py`. Qt's meta-object system already knows every property a
widget exposes, its type, and whether it's writable — this reads that live. A
`QPushButton` surfaces 33 editable properties with no hardcoding, plus its
signals for a future signal/slot editor. This is the Qt Designer property-editor
capability, and it means PaperLoom can edit properties it was never taught about.

## 23. Animations

`core/animations.py` + `ui/panels/animations_panel.py`. Attach an animation to a
widget — fade, slide (4 ways), pop, pulse, shake — with a trigger (`on_show`,
`on_click`, `on_hover`), duration and easing. PaperLoom generates real
`QPropertyAnimation` code wired to the trigger, and previews it on the canvas
immediately. Animations are data, so they serialize into the project and emit
into generated code from one definition.

## 24. Stylesheets

`core/stylesheets.py`. Import `.qss`/`.css`, validated for unmatched braces,
unterminated comments and missing semicolons — the mistakes that make Qt fail
silently. Sheets layer on top of the app theme in order, can be toggled
individually, travel with the project, and are embedded into generated code so
what you see is what ships.

## 25. One problem channel

`core/problems.py`. Codegen coercions, asset failures, stylesheet issues, crashed
previews and corrupt project files all report to a single `ProblemLog` with
severity, source, file and line. The Problems panel renders that one list, and
errors surface it automatically instead of each subsystem inventing its own
channel.

## 26. Library restructure

The **PaperDesign** source tab is gone — it was a theme, not a component
category. Components now ship under **Default** (PaperLoom's collection of Qt
widgets); **User** is reserved as the community space: by the community, for the
community. 52 components, now including media frames and a full overlay set
(scrim, modal, toast, tooltip, drawer, popover).

---

# PaperLoom v0.6 — sane defaults, real tools (Long March 4)

## 27. Terminal, properly

Rewritten (`ui/panels/terminal.py`). You type **inline at the prompt** — the
separate input box is gone. Everything before the prompt is read-only; Up/Down
walk history; Ctrl+C interrupts.

Text handling is the substance:
- **Incremental UTF-8 decoding**, so a multi-byte character split across two
  reads (routine with emoji) is never mangled into replacement characters.
- **Carriage return rewrites the current line** instead of adding one — what
  progress bars and spinners actually do.
- **ANSI SGR becomes real colour**; cursor/erase sequences are consumed rather
  than printed as garbage.
- A font stack with emoji and CJK coverage. Verified against emoji, kaomoji,
  Japanese, Chinese, Arabic and Cyrillic in one line.
- The child process gets `PYTHONUTF8`, `PYTHONIOENCODING=utf-8` and
  `TERM=xterm-256color`, so tools emit UTF-8 and colour by default.

## 28. Colour picker

`ui/panels/color_picker.py`. Hue wheel with a saturation/value square, plus
**HEX / RGB / HSL / ARGB** entry, an alpha channel, curated palettes and a
recent-colours history. Every model is bound to one source of truth, so dragging
the wheel updates the sliders and hex, and typing hex moves the wheel.

## 29. Context menus and quick edit

Right-click carries real work and **adapts to what was clicked**: a button
offers "Edit text", a media widget offers "Change media", everything offers
colour, arrange, size, animate, duplicate/copy/delete, and both the PaperLoom
properties and the full live Qt property list. Empty canvas offers paste, the
library, grid/guides/snap toggles and page settings.

The **quick-edit bar** floats by the selection for the three things people change
constantly: opacity, colour and corner radius.

## 30. Sensible defaults (`core/sizing.py`)

Absolute positioning is seductive while building and disastrous at another
window size. Every component now carries a default **size policy**, **minimum
size** and **text-overflow strategy** by role, emitted into generated code:
labels get `setWordWrap(True)`, inputs and cards expand, icon buttons stay fixed,
and the window gets a sensible minimum so the design can't be crushed.

The governing rule, from the project's own philosophy: **sane defaults, not
hidden opinions.** Every value is a starting point; `adaptive=False` on a widget
keeps the exact geometry it was drawn with.

## 31. Fixes in this pass

- **Theming reached nested panels.** `_restyle_all` walked a hardcoded list, so
  the integrated terminal kept dark styling in a light theme. It now walks the
  whole widget tree, and any panel added later is themed with no registration
  step to forget.
- **The property popover used canvas tokens**, so it rendered light-on-dark.
  It now uses chrome tokens like the rest of PaperLoom's UI.
- **The tools toolbar wouldn't drag.** Wrapping the whole strip in one child
  widget swallowed the drag; the tools are now real `QToolBar` actions, so
  Qt's own handle, float and dock behaviour work.
- **Previews disagreed with the canvas** because they used their own sizes. They
  now use exactly the canvas default size for the component.
- **The library opens as a popup** from the Components entry, and the
  PaperDesign source tab is gone from both library surfaces.
- **Listeners are held weakly.** Every window registered a permanent callback on
  the global theme manager; a closed window then got called back into and raised
  "Internal C++ object already deleted". Listeners are now weak and drop out
  automatically.
- **The terminal survives shutdown races** — a shell can outlive the widget and
  emit `finished()` after the view is gone.

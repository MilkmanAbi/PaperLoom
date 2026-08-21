"""
HeadlessBit (Abinaash's name for it): PaperLoom's functions exposed over a
plain-text shell, entirely without a display - no QApplication, no window,
no live QWidgets anywhere in this file.

Why: "some AI's struggle to write qt from the base up, or it's hard to
write like the basics... paperloom runs ENTIRELY headless, ai just uses it
to extremely fastly accelerate." An agent (Claude Code, Kimi, whatever) can
list what components exist, see each one's exact property schema (the
"positional arguments" Abinaash means), place components onto pages by
component id + x/y/width/height + property values, and generate real code -
all through a small line-oriented command language, never through Qt.

This is possible at all because the model layer already deliberately
doesn't depend on live Qt (see core/model.py's own docstring: "decoupled
from live Qt widgets... so the same model feeds the canvas, the object
tree, every codegen backend, and the .page.json on disk without any of
them depending on Qt being live"). HeadlessBit is that same claim taken
literally: it only ever imports core/*, components/registry.py, and
codegen/* - never ui/* - so it works in a plain terminal with no display
server at all, not even Qt's offscreen platform plugin.

Scope for this first slice (Abinaash: "i just wanna write a bit for these,
continue in the future, slowly") - see LONG-MARCH-BACKLOG.md's HeadlessBit
entry for the fuller plan. Today: new/open/save a project, list pages,
list+describe components, place/set/move/resize/remove widgets, generate
code, and the Package Retriever hooks (requires / install-requirements).
Not yet: layouts, signal connections, tab order, themes/stylesheets/
animations editing (a project round-trips them faithfully through open/
save even though this shell can't yet edit them itself), multi-session/
concurrent editing with the GUI.

Usage:
    python headlessbit.py                      interactive shell (or piped stdin)
    python headlessbit.py <command> [args...]   one shot, then exit
    echo "components button" | python headlessbit.py    scripted, e.g. by an agent
"""
from __future__ import annotations
import json
import shlex
import sys

from .components.registry import ComponentRegistry
from .core import package_retriever
from .core.animations import AnimationSet
from .core.app_theme import AppTheme
from .core.assets import AssetManager
from .core.model import DesignPage, DesignWidget, Project, unique_object_name
from .core.project_io import ProjectIO
from .core.stylesheets import StylesheetManager
from .codegen import get_backend
from .codegen.app_shell import generate_app_shell

PROMPT = "headlessbit> "


def _parse_value(raw: str):
    """prop=value values arrive as plain strings from the shell; try to
    recover their real type (42, 3.5, true, ["a","b"]) via JSON first, and
    only fall back to the literal string - so `place button 0 0 100 32
    checked=true` sets a real bool, not the string "true"."""
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        return raw


class HeadlessBitError(Exception):
    """A command failed in an expected way (bad args, unknown id, ...) -
    caught by the shell loop and reported as text, never a traceback."""


class HeadlessSession:
    """All the state one shell session holds: the loaded component library,
    the current project (if any), and whichever page is active. `handle()`
    is the one entry point - takes one command line, returns the text
    response - so this class is exactly as easy to drive from a test as
    from a real terminal."""

    def __init__(self, registry: ComponentRegistry = None):
        self.registry = registry or ComponentRegistry().load()
        self.project: Project | None = None
        self.project_dir: str | None = None
        self.page: DesignPage | None = None
        self.assets = None
        self.app_theme = None
        self.animations = None
        self.stylesheets = None
        self.project_io = ProjectIO()

    # --- dispatch ----------------------------------------------------------
    def handle(self, line: str) -> str:
        line = line.strip()
        if not line or line.startswith("#"):
            return ""
        try:
            parts = shlex.split(line)
        except ValueError as exc:
            return f"Error: {exc}"
        if not parts:
            return ""
        name, args = parts[0].lower(), parts[1:]
        method = getattr(self, f"_cmd_{name.replace('-', '_')}", None)
        if method is None:
            return f"Error: unknown command '{name}' (try 'help')"
        try:
            return method(args)
        except HeadlessBitError as exc:
            return f"Error: {exc}"
        except Exception as exc:   # never let a bad command kill the session
            return f"Error: {type(exc).__name__}: {exc}"

    def _require_project(self) -> Project:
        if self.project is None:
            raise HeadlessBitError("no project open - try 'new <pyside6|cpp>' or 'open <dir>'")
        return self.project

    def _require_page(self) -> DesignPage:
        self._require_project()
        if self.page is None:
            raise HeadlessBitError("no active page")
        return self.page

    def _find_widget(self, object_name: str) -> DesignWidget:
        page = self._require_page()
        for dw in page.widgets:
            if dw.object_name == object_name:
                return dw
        raise HeadlessBitError(f"no widget named '{object_name}' on page '{page.name}'")

    # --- project lifecycle ---------------------------------------------------
    def _cmd_new(self, args):
        if not args:
            raise HeadlessBitError("usage: new <pyside6|cpp> [project-name]")
        target = args[0]
        if target not in ("pyside6", "cpp"):
            raise HeadlessBitError(f"target must be 'pyside6' or 'cpp', got '{target}'")
        name = args[1] if len(args) > 1 else "untitled"
        page = DesignPage(name="MainWindow")
        self.project = Project(name=name, target=target, pages=[page])
        self.page = page
        self.project_dir = None
        self.assets = AssetManager()
        self.animations = AnimationSet()
        self.stylesheets = StylesheetManager()
        return f"New {target} project '{name}', active page 'MainWindow'"

    def _cmd_open(self, args):
        if not args:
            raise HeadlessBitError("usage: open <directory>")
        directory = args[0]
        try:
            project, assets, app_theme, animations, stylesheets = self.project_io.load(directory)
        except (FileNotFoundError, ValueError) as exc:
            raise HeadlessBitError(str(exc))
        self.project = project
        self.project_dir = directory
        self.assets = assets
        self.app_theme = app_theme
        self.animations = AnimationSet.from_dict(animations)
        self.stylesheets = StylesheetManager()
        self.stylesheets.load_list(stylesheets)
        self.page = project.pages[0]
        warnings = f" ({len(self.project_io.errors)} warning(s): {'; '.join(self.project_io.errors)})" \
            if self.project_io.errors else ""
        return (f"Opened '{project.name}' ({project.target}) from {directory}, "
                f"{len(project.pages)} page(s), active page '{self.page.name}'{warnings}")

    def _cmd_save(self, args):
        project = self._require_project()
        directory = args[0] if args else self.project_dir
        if not directory:
            raise HeadlessBitError("usage: save <directory>  (no directory known yet for this project)")
        self.project_io.save(
            project, directory, assets=self.assets, app_theme=self.app_theme,
            animations=self.animations.to_dict() if self.animations else None,
            stylesheets=self.stylesheets.to_dict() if self.stylesheets else None)
        self.project_dir = directory
        warnings = f" ({len(self.project_io.errors)} warning(s))" if self.project_io.errors else ""
        return f"Saved to {directory}{warnings}"

    def _cmd_target(self, args):
        project = self._require_project()
        if not args:
            return f"target: {project.target}"
        if args[0] not in ("pyside6", "cpp"):
            raise HeadlessBitError(f"target must be 'pyside6' or 'cpp', got '{args[0]}'")
        project.target = args[0]
        return f"target set to {args[0]}"

    # --- pages -----------------------------------------------------------
    def _cmd_pages(self, args):
        project = self._require_project()
        lines = []
        for p in project.pages:
            marker = "*" if p is self.page else " "
            lines.append(f"{marker} {p.name}  ({p.width}x{p.height}, {len(p.widgets)} widget(s))")
        return "\n".join(lines) if lines else "(no pages)"

    def _cmd_page(self, args):
        project = self._require_project()
        if not args:
            return f"active page: {self.page.name if self.page else '(none)'}"
        name = args[0]
        for p in project.pages:
            if p.name == name:
                self.page = p
                return f"active page is now '{name}'"
        raise HeadlessBitError(f"no page named '{name}' (see 'pages')")

    def _cmd_new_page(self, args):
        project = self._require_project()
        if not args:
            raise HeadlessBitError("usage: new-page <name> [width] [height]")
        name = args[0]
        if any(p.name == name for p in project.pages):
            raise HeadlessBitError(f"a page named '{name}' already exists")
        width = int(args[1]) if len(args) > 1 else 900
        height = int(args[2]) if len(args) > 2 else 600
        page = DesignPage(name=name, width=width, height=height)
        project.pages.append(page)
        self.page = page
        return f"Added page '{name}' ({width}x{height}), now active"

    # --- component library --------------------------------------------------
    def _cmd_components(self, args):
        query = " ".join(args) if args else ""
        matches = [c for c in self.registry.all() if c.matches(query)]
        if not matches:
            return "(no matching components)"
        return "\n".join(f"{c.id:<20} {c.category:<12} {c.description}" for c in matches)

    def _cmd_describe(self, args):
        if not args:
            raise HeadlessBitError("usage: describe <component_id>")
        component = self.registry.get(args[0])
        if component is None:
            raise HeadlessBitError(f"no component '{args[0]}' (see 'components')")
        lines = [f"{component.id} - {component.name} ({component.category})",
                 component.description or "(no description)", "properties:"]
        for p in component.properties:
            quick = " [quick]" if p.name in component.quick_properties else ""
            lines.append(f"  {p.name}: {p.type} = {p.default!r}{quick}")
        if component.signals:
            lines.append("signals:")
            for s in component.signals:
                lines.append(f"  {s.name} -> {s.stub}")
        if component.requires:
            lines.append(f"requires (pip, python target only): {', '.join(component.requires)}")
        return "\n".join(lines)

    # --- widgets -----------------------------------------------------------
    def _cmd_place(self, args):
        page = self._require_page()
        if len(args) < 5:
            raise HeadlessBitError(
                "usage: place <component_id> <x> <y> <width> <height> [prop=value ...]")
        component_id, x, y, width, height, *prop_args = args
        component = self.registry.get(component_id)
        if component is None:
            raise HeadlessBitError(f"no component '{component_id}' (see 'components')")
        properties = component.default_properties()
        for pa in prop_args:
            if "=" not in pa:
                raise HeadlessBitError(f"bad property arg '{pa}' - expected name=value")
            key, _, raw = pa.partition("=")
            properties[key] = _parse_value(raw)
        dw = DesignWidget(
            component_id=component_id, object_name=unique_object_name(component_id),
            x=int(x), y=int(y), width=int(width), height=int(height),
            properties=properties)
        page.add(dw)
        return f"Placed {component_id} as '{dw.object_name}' at ({dw.x}, {dw.y}) {dw.width}x{dw.height}"

    def _cmd_widgets(self, args):
        page = self._require_page()
        if not page.widgets:
            return "(no widgets on this page)"
        return "\n".join(
            f"{dw.object_name:<20} {dw.component_id:<16} "
            f"({dw.x},{dw.y}) {dw.width}x{dw.height}" for dw in page.widgets)

    def _cmd_set(self, args):
        if len(args) < 3:
            raise HeadlessBitError("usage: set <object_name> <property> <value>")
        dw = self._find_widget(args[0])
        prop, raw = args[1], " ".join(args[2:])
        dw.properties[prop] = _parse_value(raw)
        return f"{dw.object_name}.{prop} = {dw.properties[prop]!r}"

    def _cmd_move(self, args):
        if len(args) < 3:
            raise HeadlessBitError("usage: move <object_name> <x> <y>")
        dw = self._find_widget(args[0])
        dw.x, dw.y = int(args[1]), int(args[2])
        return f"{dw.object_name} moved to ({dw.x}, {dw.y})"

    def _cmd_resize(self, args):
        if len(args) < 3:
            raise HeadlessBitError("usage: resize <object_name> <width> <height>")
        dw = self._find_widget(args[0])
        dw.width, dw.height = int(args[1]), int(args[2])
        return f"{dw.object_name} resized to {dw.width}x{dw.height}"

    def _cmd_remove(self, args):
        if not args:
            raise HeadlessBitError("usage: remove <object_name>")
        page = self._require_page()
        dw = self._find_widget(args[0])
        page.remove(dw)
        return f"Removed '{dw.object_name}'"

    # --- codegen -----------------------------------------------------------
    def _cmd_generate(self, args):
        project = self._require_project()
        if not args:
            raise HeadlessBitError("usage: generate <output_dir>")
        target_dir = args[0]
        backend = get_backend(project.target, self.registry)
        backend.app_theme = self.app_theme or AppTheme()
        backend.animations = self.animations or AnimationSet()
        backend.extra_stylesheets = self.stylesheets.sources() if self.stylesheets else []
        backend.assets = self.assets
        lines = []
        all_warnings = []
        for page in project.pages:
            r = backend.generate(page, target_dir)
            lines.append(f"[{page.name}] {r['generated']}")
            lines.append(f"[{page.name}] {r['logic']}")
            all_warnings.extend(backend.warnings)
        if project.target == "pyside6" and len(project.pages) >= 1:
            shell = generate_app_shell(project, backend, target_dir)
            lines.append(f"[app shell] {shell['app']}")
            lines.append(f"[app shell] {shell['app_logic']}")
        for w in all_warnings:
            lines.append(f"warning: {w}")
        return "\n".join(lines)

    # --- Package Retriever ---------------------------------------------------
    def _cmd_requires(self, args):
        project = self._require_project()
        pkgs = package_retriever.requirements_for_project(project, self.registry)
        if not pkgs:
            return "(this project's placed components declare no extra pip requirements)"
        missing = set(package_retriever.missing_requirements(project, self.registry))
        return "\n".join(f"{p}{'  (missing)' if p in missing else '  (satisfied)'}" for p in pkgs)

    def _cmd_install_requirements(self, args):
        project = self._require_project()
        dry_run = "--dry-run" in args
        missing = package_retriever.missing_requirements(project, self.registry)
        if not missing:
            return "Nothing to install - all requirements already satisfied."
        result = package_retriever.install(missing, dry_run=dry_run)
        lines = []
        if result.installed:
            verb = "Would install" if dry_run else "Installed"
            lines.append(f"{verb}: {', '.join(result.installed)}")
        if result.already_satisfied:
            lines.append(f"Already satisfied: {', '.join(result.already_satisfied)}")
        for pkg, err in result.failed:
            lines.append(f"FAILED: {pkg} - {err}")
        return "\n".join(lines) if lines else "Nothing to install."

    # --- misc --------------------------------------------------------------
    def _cmd_help(self, args):
        return (
            "new <pyside6|cpp> [name]        start a fresh project\n"
            "open <directory>                open a project saved by PaperLoom (GUI or headless)\n"
            "save [directory]                save the current project\n"
            "target [pyside6|cpp]            show or change the project's codegen target\n"
            "pages                           list this project's pages ('*' = active)\n"
            "page <name>                     switch the active page\n"
            "new-page <name> [w] [h]         add a page, make it active\n"
            "components [query]              list library components, optionally filtered\n"
            "describe <component_id>         full property/signal schema for one component\n"
            "place <id> <x> <y> <w> <h> [prop=value ...]   add a component to the active page\n"
            "widgets                         list widgets on the active page\n"
            "set <name> <prop> <value>       change a placed widget's property\n"
            "move <name> <x> <y>             reposition a placed widget\n"
            "resize <name> <w> <h>           resize a placed widget\n"
            "remove <name>                   delete a placed widget\n"
            "generate <output_dir>           emit real source code for every page\n"
            "requires                        list pip packages this project's components need\n"
            "install-requirements [--dry-run]   pip-install whatever's missing (python target only)\n"
            "help                            this text\n"
            "exit | quit                     leave the shell"
        )

    def _cmd_exit(self, args):
        raise SystemExit(0)

    _cmd_quit = _cmd_exit


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    session = HeadlessSession()
    if argv:
        # one-shot mode: the whole argv is one command line
        print(session.handle(" ".join(shlex.quote(a) for a in argv)))
        return
    interactive = sys.stdin.isatty()
    while True:
        if interactive:
            sys.stdout.write(PROMPT)
            sys.stdout.flush()
        line = sys.stdin.readline()
        if not line:   # EOF - piped input ran out, or Ctrl+D
            break
        try:
            response = session.handle(line)
        except SystemExit:
            break
        if response:
            print(response)


if __name__ == "__main__":
    main()

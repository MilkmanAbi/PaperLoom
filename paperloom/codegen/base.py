"""
Codegen backend base (spec §6). Every backend emits the same two-file split
(§6.3): a generated file that's always safe to overwrite, and a hand-written
logic file created exactly once and never touched again. The base class enforces
the "write logic once" rule so no individual backend can get it wrong.
"""
from __future__ import annotations
import os
import shutil
from abc import ABC, abstractmethod

from ..core.model import DesignPage
from ..core import sanitize
from ..components.registry import ComponentRegistry


def _py_literal(value) -> str:
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, (int, float)):
        return repr(value)
    return '"' + sanitize.escape_string(str(value)) + '"'


def _cpp_literal(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    return '"' + sanitize.escape_string(str(value)) + '"'


def pyside_qt_prop_lines(name, qt_props):
    """`self.<name>.setProperty("prop", literal)` for each Qt-property override.
    setProperty honours any Q_PROPERTY, so this persists real Qt-property edits
    into generated PySide code without the component template knowing about them.
    """
    return [f'self.{name}.setProperty("{k}", {_py_literal(v)})'
            for k, v in (qt_props or {}).items()]


def cpp_qt_prop_lines(name, qt_props):
    return [f'{name}->setProperty("{k}", {_cpp_literal(v)});'
            for k, v in (qt_props or {}).items()]


class CodegenBackend(ABC):
    target = "base"
    assets = None          # AssetManager, set by the caller before generate()

    def __init__(self, registry: ComponentRegistry):
        self.registry = registry
        self.warnings = []          # populated during generate(): list of str

    def _attach_asset(self, dw, ctx, gen_dir) -> str | None:
        """If a widget references an asset, copy it into <gen_dir>/assets/ and set
        ctx['asset_path'] to the project-relative path the generated code loads.
        Returns the asset kind (image/animated/...) or None. This is what makes a
        generated app actually ship and display its media."""
        key = (dw.properties or {}).get("asset")
        if not key or self.assets is None:
            return None
        src = self.assets.resolve(key)
        if not src or not os.path.isfile(src):
            self.warnings.append(f"{dw.object_name}: asset {key!r} not found; skipped")
            return None
        assets_out = os.path.join(gen_dir, "assets")
        os.makedirs(assets_out, exist_ok=True)
        fname = os.path.basename(key)
        try:
            shutil.copyfile(src, os.path.join(assets_out, fname))
        except OSError as exc:
            self.warnings.append(f"{dw.object_name}: could not copy asset ({exc})")
            return None
        ctx["asset_path"] = f"assets/{fname}"
        asset = self.assets.get(key)
        return asset.kind if asset else "image"

    @abstractmethod
    def generate(self, page: DesignPage, target_dir: str) -> dict:
        """Emit files for one page. Returns {"generated": path, "logic": path}."""

    def _write_generated(self, path: str, source: str) -> None:
        """Always overwrite - this file is owned by PaperLoom."""
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(source)

    def _write_logic_once(self, path: str, source: str) -> None:
        """Write only if absent - never clobber the user's hand-written logic (§6.3)."""
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if not os.path.exists(path):
            with open(path, "w", encoding="utf-8") as f:
                f.write(source)

    def _widget_context(self, dw, component=None) -> dict:
        """Flatten a DesignWidget into the template context: geometry + properties.

        Every property is coerced to a code-safe value for its declared type
        (spec §11.1) - the hard invariant that codegen never emits broken syntax.
        String values are escaped for double-quoted literals. Any coercion that
        changed a value is recorded in self.warnings for the Problems tab.
        """
        ctx = {
            "name": dw.object_name,
            "x": int(dw.x), "y": int(dw.y),
            "width": int(dw.width), "height": int(dw.height),
        }
        if component is None:
            component = self.registry.get(dw.component_id)

        specs = {p.name: p for p in component.properties} if component else {}
        for prop_name, raw in dw.properties.items():
            spec = specs.get(prop_name)
            prop_type = spec.type if spec else "string"
            default = spec.default if spec else None
            safe = sanitize.coerce(raw, prop_type, default)
            if str(safe) != str(raw):
                self.warnings.append(
                    f"{dw.object_name}.{prop_name} was invalid "
                    f"({raw!r}), reset to {safe!r}")
            # escape strings for embedding; ints/bools/colours are already safe tokens
            if prop_type == "string":
                safe = sanitize.escape_string(safe)
            ctx[prop_name] = safe
        # render Markdown/LaTeX content to HTML (same converter the canvas uses)
        from ..core import richtext
        fg = "#1a1a1a"
        try:
            fg = self.app_theme.tokens().get("fg", fg)
        except Exception:
            pass
        richtext.attach_to_context(component, dw, ctx, fg=fg, warnings=self.warnings)
        return ctx

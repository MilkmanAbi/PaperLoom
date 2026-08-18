"""
Rich-text engine (spec §46, upgraded session 14). Turns Markdown - with
`$inline$` / `$$display$$` LaTeX math - into self-contained HTML that any Qt
rich-text widget (QTextBrowser) can show with zero runtime dependencies:

- Markdown is parsed by markdown-it-py (GFM: tables, task lists, footnotes,
  strikethrough, autolinks) with math handled by the `dollarmath` TOKENIZER
  plugin - so `$...$` can never be mangled by emphasis parsing or grabbed from
  inside a code span, unlike a regex pass over raw markdown text. Inline HTML
  (`<span style="color:...">` from the Studio's toolbar) still passes through.
- Fenced code blocks are syntax-highlighted by Pygments to *inline* styles
  (QTextBrowser has no CSS class-sheet support), themed for the current app
  mode.
- LaTeX math is rendered to small PNGs with matplotlib's mathtext and embedded
  as base64 `data:` images, so the generated app needs no LaTeX and no
  matplotlib at runtime - the picture travels inside the HTML string. If
  matplotlib isn't available the raw `$...$` is left in place and a warning is
  recorded, never a crash.

Two bugs worth remembering if this is ever touched again (both covered by
PaperLoom's test suite - see test_richtext_math_* in tests/test_app.py):

  1. matplotlib's mathtext does NOT raise for macros it doesn't recognise
     (\\qquad, \\tfrac, ...) - it silently prints the literal characters with
     zero warning. So a common-macro cleanup pass must run unconditionally
     before every render attempt, never only as a fallback after a "successful"
     raw attempt (a "successful" raw attempt can still be garbage).
  2. A `$$...$$` block that spans multiple markdown source lines keeps its
     literal newline characters in the extracted LaTeX. An embedded `\\n`
     silently breaks matplotlib's math-mode parsing (it drops out of math mode
     at each line break). Whitespace must be collapsed before rendering.

The same function feeds the canvas, the Markdown Studio preview, and codegen,
so what you write is what you see is what ships.
"""
from __future__ import annotations
import base64
import io
import re

from markdown_it import MarkdownIt
from pygments import highlight as _pyg_highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import get_lexer_by_name
from pygments.util import ClassNotFound

try:
    from mdit_py_plugins.dollarmath import dollarmath_plugin
    from mdit_py_plugins.footnote import footnote_plugin
    from mdit_py_plugins.tasklists import tasklists_plugin
    _HAS_MDIT_PLUGINS = True
except Exception:
    _HAS_MDIT_PLUGINS = False

_MATH_CACHE: dict = {}

# macros matplotlib's mathtext does not recognise but that are common in
# everyday LaTeX; matched literally, never inside an unsupported environment.
_MATHTEXT_CLEANUP = [
    (re.compile(r"\\tfrac"), r"\\frac"),
    (re.compile(r"\\dfrac"), r"\\frac"),
    (re.compile(r"\\qquad"), r"\\ \\ \\ \\ "),
    (re.compile(r"\\quad"), r"\\ \\ "),
    (re.compile(r"\\,"), r"\\ "),
    (re.compile(r"\\text\{([^}]*)\}"), r"\\mathrm{\1}"),
]
# matplotlib's mathtext requires explicit braces for \frac - real LaTeX's
# brace-less shorthand (\frac12, \tfrac1n) raises a ParseSyntaxException.
# Applied after the tfrac/dfrac -> frac substitutions above.
_FRAC_SHORTHAND = re.compile(r"\\frac([0-9A-Za-z])([0-9A-Za-z])")
# environments matplotlib's mathtext cannot render at all
_UNSUPPORTED_ENV = re.compile(r"\\begin\{(pmatrix|bmatrix|matrix|aligned|cases|array)\}")


def _mathtext_cleanup(latex: str) -> str:
    # collapse embedded newlines/whitespace FIRST - see bug (2) in the module
    # docstring - then apply macro substitutions. Order matters.
    out = re.sub(r"\s+", " ", latex).strip()
    for pattern, repl in _MATHTEXT_CLEANUP:
        out = pattern.sub(repl, out)
    out = _FRAC_SHORTHAND.sub(r"\\frac{\1}{\2}", out)
    return out


def _math_png_data_uri(latex: str, display: bool, fg: str) -> str | None:
    key = (latex, display, fg)
    if key in _MATH_CACHE:
        return _MATH_CACHE[key]
    if _UNSUPPORTED_ENV.search(latex):
        _MATH_CACHE[key] = None
        return None
    try:
        import matplotlib
        matplotlib.use("Agg")
        from matplotlib.figure import Figure
    except Exception:
        return None
    try:
        # ALWAYS clean before rendering - see bug (1) in the module docstring:
        # a "successful" render of the raw string can still be silent garbage.
        tex = _mathtext_cleanup(latex)
        fig = Figure(figsize=(0.01, 0.01))
        fig.patch.set_alpha(0.0)
        size = 16 if display else 13
        fig.text(0, 0, f"${tex}$", fontsize=size, color=fg)
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=160, transparent=True,
                    bbox_inches="tight", pad_inches=0.02)
        uri = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
        _MATH_CACHE[key] = uri
        return uri
    except Exception:
        _MATH_CACHE[key] = None
        return None


_md_engine_cache: dict = {}


def _get_md():
    if "md" in _md_engine_cache:
        return _md_engine_cache["md"]
    md = MarkdownIt("gfm-like", {"html": True, "linkify": True, "typographer": True})
    if _HAS_MDIT_PLUGINS:
        md.use(dollarmath_plugin, double_inline=True, allow_space=True,
               allow_digits=True, allow_labels=True)
        md.use(footnote_plugin)
        md.use(tasklists_plugin, enabled=True, label=True)

        def _math_inline(_renderer, tokens, idx, options, env):
            key = f"\x00M{len(env.setdefault('_math', []))}\x00"
            env["_math"].append((tokens[idx].content, False))
            return key

        def _math_block(_renderer, tokens, idx, options, env):
            key = f"\x00M{len(env.setdefault('_math', []))}\x00"
            env["_math"].append((tokens[idx].content, True))
            return f'<div class="pl-math-block">{key}</div>\n'

        md.add_render_rule("math_inline", _math_inline)
        md.add_render_rule("math_inline_double", _math_block)
        md.add_render_rule("math_block", _math_block)
        md.add_render_rule("math_block_label", _math_block)

    def _highlight(code: str, lang: str, attrs: str = "") -> str:
        import html as _html
        lang = (lang or "").strip().lower()
        try:
            lexer = get_lexer_by_name(lang) if lang else None
        except ClassNotFound:
            lexer = None
        if lexer is None:
            return f'<pre><code>{_html.escape(code)}</code></pre>'
        try:
            fmt = HtmlFormatter(nowrap=True, noclasses=True, style="default")
            inner = _pyg_highlight(code, lexer, fmt)
        except Exception:
            inner = _html.escape(code)
        return f'<pre><code>{inner}</code></pre>'

    md.options["highlight"] = _highlight
    _md_engine_cache["md"] = md
    return md


def to_html(markdown: str, fg: str = "#1a1a1a", warnings: list | None = None) -> str:
    """Markdown (+ LaTeX math) -> self-contained HTML. `fg` colours the rendered
    math so it reads against the app's text colour."""
    md_src = markdown or ""
    md = _get_md()
    env: dict = {}
    html = md.render(md_src, env)

    # drop the rendered (or honestly degraded) math back into the placeholders
    for i, (latex, display) in enumerate(env.get("_math", [])):
        uri = _math_png_data_uri(latex, display, fg)
        if uri is not None:
            style = ("display:block;margin:6px auto;" if display
                     else "vertical-align:middle;")
            repl = f'<img src="{uri}" style="{style}"/>'
        else:
            if warnings is not None:
                warnings.append("LaTeX math could not be rendered; shown as source")
            # honest degrade, styled and readable rather than a bare dump
            import html as _html
            box = ("display:block;margin:6px auto;padding:6px 10px;" if display
                   else "padding:0 4px;")
            repl = (f'<code style="{box}font-family:monospace;font-size:.85em;'
                    f'background:rgba(127,127,127,.15);border-radius:4px;">'
                    f'{_html.escape(latex.strip())}</code>')
        html = html.replace(f"\x00M{i}\x00", repl)
    return html


def attach_to_context(component, dw, ctx, fg: str = "#1a1a1a", warnings: list | None = None):
    """For any `markdown`-typed property, convert its raw value to HTML once and
    add `<name>_html` / `<name>_py` / `<name>_cpp` to the render context, so the
    canvas factory and both codegen backends all emit the exact same rendered
    rich text from one conversion (spec §13 fidelity)."""
    for spec in getattr(component, "properties", []):
        if (spec.type or "").lower() != "markdown":
            continue
        raw = (dw.properties or {}).get(spec.name, spec.default) or ""
        html = to_html(raw, fg=fg, warnings=warnings)
        ctx[f"{spec.name}_html"] = html
        ctx[f"{spec.name}_py"] = py_literal(html)
        ctx[f"{spec.name}_cpp"] = cpp_literal(html)
    return ctx


def py_literal(s: str) -> str:
    """A Python string literal for embedding HTML in generated PySide code."""
    return repr(s)


def cpp_literal(s: str) -> str:
    """A C++ string literal (QString) for the HTML."""
    escaped = (s.replace("\\", "\\\\").replace('"', '\\"')
               .replace("\n", "\\n").replace("\r", ""))
    return '"' + escaped + '"'

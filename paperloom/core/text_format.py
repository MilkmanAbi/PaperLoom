"""
Pure Markdown wrap/prefix transforms for the Text formatting toolbar
(ui/panels/text_tools_bar.py). Deliberately Qt-free and stateless - each
function takes the whole current property value and returns the whole new
value - so the toolbar's Bold/Italic/Strikethrough/Heading/Bullet list/Link
buttons can be unit tested without booting a QApplication, and so the same
insertion conventions Markdown Studio's toolbar established
(ui/panels/markdown_studio.py's _wrap/_line_prefix: "**bold**", "*italic*",
"~~strike~~", "# heading", "- bullet") round-trip identically no matter which
surface last touched the value.

Unlike Markdown Studio - which wraps a text *selection* inside a QTextEdit -
these operate on a whole property string (there's no cursor/selection concept
for a value sitting in dw.properties), so each action is a *toggle*: pressing
Bold on already-bold text un-bolds it, rather than piling on another pair of
asterisks every click. That's a deliberate improvement over naive one-way
wrapping, not a deviation from the plan's "wrap/prefix with matching Markdown
syntax" - toggling still produces (and removes) exactly that syntax.
"""
from __future__ import annotations
import re


def _toggle_wrap(value: str, marker: str) -> str:
    n = len(marker)
    if len(value) >= 2 * n and value.startswith(marker) and value.endswith(marker):
        return value[n:-n]
    return f"{marker}{value}{marker}"


def bold(value: str) -> str:
    return _toggle_wrap(value, "**")


def italic(value: str) -> str:
    # Guard against "**text**" (bold) being mistaken for italic-wrapped just
    # because it also starts/ends with a single "*" - only toggle single-star
    # wraps that are not themselves double-star wraps.
    if (len(value) >= 2 and value.startswith("*") and value.endswith("*")
            and not value.startswith("**") and not value.endswith("**")):
        return value[1:-1]
    return f"*{value}*"


def strike(value: str) -> str:
    return _toggle_wrap(value, "~~")


def heading(value: str) -> str:
    """Toggles a level-1 '# ' prefix on the first line only - multi-line
    values (markdown-typed properties) keep the rest of the text untouched."""
    first, sep, rest = value.partition("\n")
    if first.startswith("# "):
        first = first[2:]
    else:
        first = f"# {first}"
    return first + sep + rest


def bullet(value: str) -> str:
    """Toggles a '- ' prefix on every non-blank line."""
    lines = value.split("\n")
    content_lines = [ln for ln in lines if ln.strip()]
    already = bool(content_lines) and all(ln.startswith("- ") for ln in content_lines)
    if already:
        return "\n".join(ln[2:] if ln.startswith("- ") else ln for ln in lines)
    return "\n".join(f"- {ln}" if ln.strip() else ln for ln in lines)


_LINK_RE = re.compile(r"^\[(.*)\]\(([^()]*)\)$", re.S)


def link(value: str) -> str:
    """Toggles wrapping the whole value as a Markdown link. Re-pressing on an
    already-linked value unwraps back to just the label, discarding the
    placeholder URL - editing the real URL belongs in the Markdown Studio."""
    m = _LINK_RE.match(value)
    if m:
        return m.group(1)
    return f"[{value}](https://)"

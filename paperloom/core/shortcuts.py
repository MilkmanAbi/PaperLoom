"""
Single source of truth for PaperLoom's global keyboard shortcuts. Two
consumers read this same list so they can never drift apart:
  - ui/main_window.py's _shortcuts() - actually binds each QShortcut
  - ui/panels/settings_dialog.py's Shortcuts section - shows them to a person

Each entry is (category, keys, command_id, label). `label` is the friendly
name shown in Settings; `command_id` is the same dispatch() id
_shortcuts() already wired everything through, so nothing here invents a
second command-routing path.

v1 is read-only in the UI - rebinding a key is real scope (conflict
detection, persistence, a capture-a-keypress widget) or a fast-follow, not
squeezed into this pass. Flagged here, not hidden, same convention the rest
of this codebase uses for "not yet, but not forgotten" gaps.
"""

SHORTCUTS = [
    ("File", "Ctrl+S", "file.save", "Save project"),
    ("File", "Ctrl+G", "file.generate", "Generate code"),
    ("File", "Ctrl+N", "file.new_page", "New page"),
    ("Edit", "Ctrl+Z", "edit.undo", "Undo"),
    ("Edit", "Ctrl+Y", "edit.redo", "Redo"),
    ("Edit", "Del", "edit.delete", "Delete selection"),
    ("Edit", "Ctrl+D", "edit.duplicate", "Duplicate selection"),
    ("Edit", "Ctrl+F", "edit.find", "Find on canvas"),
    ("View", "Ctrl+B", "view.toggle_side", "Toggle side panel"),
    ("View", "Ctrl+J", "view.toggle_bottom", "Toggle bottom panel"),
    ("View", "Ctrl+=", "view.zoom_in", "Zoom in"),
    ("View", "Ctrl+-", "view.zoom_out", "Zoom out"),
    ("View", "Ctrl+0", "view.zoom_reset", "Reset zoom"),
    ("View", "Ctrl+'", "view.toggle_grid", "Toggle grid"),
    ("View", "Ctrl+;", "view.toggle_snap", "Toggle snap"),
    ("Go", "Ctrl+Shift+P", "go.commands", "Command palette"),
    ("Go", "Ctrl+P", "go.page", "Go to page"),
    ("Go", "Ctrl+L", "library.open", "Open component library"),
    ("Run", "F5", "run.preview", "Run"),
    ("Run", "Ctrl+Shift+R", "run.quick_preview", "Quick Preview"),
    ("Run", "Ctrl+Shift+E", "run.code_editor", "Code Editor"),
    ("Tabs", "Ctrl+Tab", "tabs.next", "Next tab"),
    ("Tabs", "Ctrl+Shift+Tab", "tabs.prev", "Previous tab"),
    ("Tabs", "Ctrl+W", "tabs.close", "Close active tab"),
    ("Terminal", "Ctrl+`", "terminal.new", "New terminal"),
]


def binds():
    """(keys, command_id) pairs, in the exact order/shape
    main_window._shortcuts() wires QShortcuts from."""
    return [(keys, cmd) for _cat, keys, cmd, _label in SHORTCUTS]


def grouped():
    """Category -> ordered list of (keys, label), for display. Preserves
    SHORTCUTS' own ordering, both of categories (first appearance) and of
    entries within a category."""
    order = []
    by_cat = {}
    for cat, keys, _cmd, label in SHORTCUTS:
        if cat not in by_cat:
            by_cat[cat] = []
            order.append(cat)
        by_cat[cat].append((keys, label))
    return [(cat, by_cat[cat]) for cat in order]

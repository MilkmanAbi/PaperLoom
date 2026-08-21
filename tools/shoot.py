"""
Dev-only render harness. Boots PaperLoom offscreen, optionally drives it, and
grabs a screenshot so changes can be *looked at*, not guessed from QSS strings.

    QT_QPA_PLATFORM=offscreen python3 tools/shoot.py <out.png> [action ...]

actions:
    place:<component_id>     place a component on the canvas
    select:0                 select the Nth placed widget
    view:<id>                activity view (library/pages/layers/properties/assets)
    bottom:<tab>             show bottom tab (output/problems/debug/terminal)
    appdark                  toggle the designed-app dark mode
    editordark               toggle PaperLoom's own dark mode
    resize:WxH               resize the window
"""
import sys
import time
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtWidgets import QApplication
from paperloom import theme
from paperloom.ui.main_window import PaperLoomWindow
from paperloom.components.registry import ComponentRegistry


def pump(app, n=8):
    for _ in range(n):
        app.processEvents()
        time.sleep(0.03)


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else "/home/claude/shots/out.png"
    actions = sys.argv[2:]

    app = QApplication(sys.argv[:1])
    app.setStyleSheet(theme.app_stylesheet())
    reg = ComponentRegistry().load()
    w = PaperLoomWindow(reg)
    w.resize(1400, 860)
    w.show()
    pump(app)

    placed = []
    for a in actions:
        if a.startswith("place:"):
            placed.append(w.canvas.place_component(a.split(":", 1)[1]))
        elif a.startswith("select:"):
            i = int(a.split(":", 1)[1])
            if 0 <= i < len(placed) and placed[i] is not None:
                w.canvas.select_by_model(placed[i])
        elif a.startswith("view:"):
            w.activity_bar.select(a.split(":", 1)[1])
        elif a.startswith("bottom:"):
            w._show_bottom_tab(a.split(":", 1)[1])
        elif a == "appdark":
            w._toggle_app_mode()
        elif a == "editordark":
            w._toggle_editor_mode()
        elif a.startswith("resize:"):
            wd, ht = a.split(":", 1)[1].split("x")
            w.resize(int(wd), int(ht))
        pump(app)

    pump(app, 6)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    w.grab().save(out)
    print("saved", out, w.size())


if __name__ == "__main__":
    main()

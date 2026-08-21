"""
Animations (spec §23). You attach an animation to a widget - slide, fade, pop,
whatever - and PaperLoom generates the real `QPropertyAnimation` code that does
it, wired to the trigger you chose.

An Animation is data, not code: kind + trigger + duration + easing. That keeps it
serializable into the project file, previewable on the canvas, and emittable into
both PySide6 and C++ from one definition.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict

# kind -> (label, description, animated Qt property)
KINDS = {
    "fade_in":    ("Fade in", "Fades from transparent to solid", "windowOpacity"),
    "fade_out":   ("Fade out", "Fades from solid to transparent", "windowOpacity"),
    "slide_left": ("Slide in from left", "Slides in from off-screen left", "geometry"),
    "slide_right": ("Slide in from right", "Slides in from off-screen right", "geometry"),
    "slide_up":   ("Slide up", "Rises into place from below", "geometry"),
    "slide_down": ("Slide down", "Drops into place from above", "geometry"),
    "pop":        ("Pop", "Scales up briefly on trigger", "geometry"),
    "shake":      ("Shake", "Quick horizontal shake, good for errors", "pos"),
    "pulse":      ("Pulse", "Gentle grow-and-return", "geometry"),
}

TRIGGERS = {
    "on_show": "When the page appears",
    "on_click": "When the widget is clicked",
    "on_hover": "When the pointer enters",
}

EASINGS = ["OutCubic", "InOutCubic", "OutBack", "OutBounce", "Linear", "InOutQuad"]


@dataclass
class Animation:
    kind: str = "fade_in"
    trigger: str = "on_show"
    duration: int = 300
    easing: str = "OutCubic"
    distance: int = 40          # px travelled for slide/shake

    def label(self):
        return KINDS.get(self.kind, (self.kind,))[0]

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, d):
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


class AnimationSet:
    """Animations attached to a page, keyed by widget object name."""

    def __init__(self):
        self._by_widget: dict[str, list[Animation]] = {}

    def add(self, object_name: str, animation: Animation):
        self._by_widget.setdefault(object_name, []).append(animation)
        return animation

    def set_for(self, object_name: str, animations):
        self._by_widget[object_name] = list(animations)

    def get(self, object_name: str) -> list:
        return self._by_widget.get(object_name, [])

    def remove(self, object_name: str, index: int = None):
        if index is None:
            self._by_widget.pop(object_name, None)
        elif object_name in self._by_widget:
            try:
                self._by_widget[object_name].pop(index)
            except IndexError:
                pass

    def all(self):
        return dict(self._by_widget)

    def is_empty(self):
        return not any(self._by_widget.values())

    def to_dict(self):
        return {name: [a.to_dict() for a in anims]
                for name, anims in self._by_widget.items() if anims}

    @classmethod
    def from_dict(cls, data):
        out = cls()
        for name, entries in (data or {}).items():
            out._by_widget[name] = [Animation.from_dict(e) for e in entries]
        return out


# --- code generation ---------------------------------------------------------
def pyside_setup(object_name: str, animations) -> list[str]:
    """Lines that build the animations for one widget, for the generated ui class."""
    lines = []
    for i, anim in enumerate(animations):
        var = f"self.{object_name}_anim{i or ''}"
        prop = KINDS.get(anim.kind, (None, None, "geometry"))[2]
        lines.append(f'{var} = QPropertyAnimation(self.{object_name}, b"{prop}")')
        lines.append(f"{var}.setDuration({int(anim.duration)})")
        lines.append(f"{var}.setEasingCurve(QEasingCurve.Type.{anim.easing})")

        if anim.kind in ("fade_in", "fade_out"):
            lines.append(f"{var}_effect = QGraphicsOpacityEffect(self.{object_name})")
            lines.append(f"self.{object_name}.setGraphicsEffect({var}_effect)")
            lines.append(f'{var} = QPropertyAnimation({var}_effect, b"opacity")')
            lines.append(f"{var}.setDuration({int(anim.duration)})")
            lines.append(f"{var}.setEasingCurve(QEasingCurve.Type.{anim.easing})")
            start, end = ("0.0", "1.0") if anim.kind == "fade_in" else ("1.0", "0.0")
            lines.append(f"{var}.setStartValue({start})")
            lines.append(f"{var}.setEndValue({end})")
        elif anim.kind.startswith("slide"):
            dx, dy = _offset(anim.kind, anim.distance)
            lines.append(f"_g = self.{object_name}.geometry()")
            lines.append(f"{var}.setStartValue(_g.translated({dx}, {dy}))")
            lines.append(f"{var}.setEndValue(_g)")
        elif anim.kind in ("pop", "pulse"):
            grow = 6 if anim.kind == "pulse" else 10
            lines.append(f"_g = self.{object_name}.geometry()")
            lines.append(f"{var}.setStartValue(_g)")
            lines.append(f"{var}.setKeyValueAt(0.5, _g.adjusted(-{grow}, -{grow}, {grow}, {grow}))")
            lines.append(f"{var}.setEndValue(_g)")
        elif anim.kind == "shake":
            d = int(anim.distance) // 3 or 6
            lines.append(f"_p = self.{object_name}.pos()")
            lines.append(f"{var}.setStartValue(_p)")
            lines.append(f"{var}.setKeyValueAt(0.25, _p + QPoint({d}, 0))")
            lines.append(f"{var}.setKeyValueAt(0.75, _p + QPoint(-{d}, 0))")
            lines.append(f"{var}.setEndValue(_p)")

        if anim.trigger == "on_show":
            lines.append(f"{var}.start()")
        elif anim.trigger == "on_click":
            lines.append(f"self.{object_name}.clicked.connect({var}.start)")
        # on_hover is wired in the logic file - it needs an event filter
    return lines


def needs_imports(animation_set: AnimationSet) -> set:
    """Which extra Qt imports the generated file requires."""
    if animation_set.is_empty():
        return set()
    imports = {"QPropertyAnimation", "QEasingCurve"}
    for anims in animation_set.all().values():
        for a in anims:
            if a.kind in ("fade_in", "fade_out"):
                imports.add("QGraphicsOpacityEffect")
            if a.kind == "shake":
                imports.add("QPoint")
    return imports


def _offset(kind: str, distance: int):
    d = int(distance)
    return {"slide_left": (-d, 0), "slide_right": (d, 0),
            "slide_up": (0, d), "slide_down": (0, -d)}.get(kind, (0, 0))

"""
Animations panel (spec §23). Attach animations to the selected widget: pick a
kind, a trigger, a duration and an easing, and PaperLoom generates the real
QPropertyAnimation code. Preview plays it on the canvas immediately.
"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QSpinBox,
    QPushButton, QListWidget, QListWidgetItem, QFormLayout
)

from ... import theme
from ...core.animations import Animation, KINDS, TRIGGERS, EASINGS


class AnimationsPanel(QWidget):
    animationAdded = Signal(str, object)     # object_name, Animation
    animationRemoved = Signal(str, int)
    previewRequested = Signal(str, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("AnimationsPanel")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._model = None
        self._set = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self._header = QLabel("ANIMATIONS")
        self._header.setObjectName("hdr")
        lay.addWidget(self._header)

        self._body = QWidget()
        form = QFormLayout(self._body)
        form.setContentsMargins(10, 8, 10, 8)
        form.setSpacing(6)

        self.kind = QComboBox()
        for key, (label, desc, _prop) in KINDS.items():
            self.kind.addItem(label, key)
            self.kind.setItemData(self.kind.count() - 1, desc, Qt.ItemDataRole.ToolTipRole)
        self.trigger = QComboBox()
        for key, label in TRIGGERS.items():
            self.trigger.addItem(label, key)
        self.duration = QSpinBox()
        self.duration.setRange(50, 5000); self.duration.setValue(300)
        self.duration.setSuffix(" ms"); self.duration.setSingleStep(50)
        self.easing = QComboBox()
        self.easing.addItems(EASINGS)
        self.distance = QSpinBox()
        self.distance.setRange(4, 600); self.distance.setValue(40)
        self.distance.setSuffix(" px")

        form.addRow("Effect", self.kind)
        form.addRow("Trigger", self.trigger)
        form.addRow("Duration", self.duration)
        form.addRow("Easing", self.easing)
        form.addRow("Distance", self.distance)
        lay.addWidget(self._body)

        row = QWidget()
        rl = QHBoxLayout(row); rl.setContentsMargins(10, 0, 10, 8); rl.setSpacing(6)
        self.add_btn = QPushButton("Add"); self.add_btn.setObjectName("primary")
        self.add_btn.clicked.connect(self._add)
        self.preview_btn = QPushButton("Preview"); self.preview_btn.setObjectName("ghost")
        self.preview_btn.clicked.connect(self._preview)
        rl.addWidget(self.add_btn); rl.addWidget(self.preview_btn); rl.addStretch(1)
        lay.addWidget(row)

        self.list = QListWidget()
        self.list.itemDoubleClicked.connect(self._remove_current)
        lay.addWidget(self.list, 1)

        self._empty = QLabel("Select a widget to animate it.")
        self._empty.setObjectName("empty"); self._empty.setWordWrap(True)
        lay.addWidget(self._empty)

        self.restyle()
        self.set_target(None, None)

    def set_target(self, model, animation_set):
        self._model = model
        self._set = animation_set
        has = model is not None
        self._body.setVisible(has)
        self.add_btn.parentWidget().setVisible(has)
        self.list.setVisible(has)
        self._empty.setVisible(not has)
        self._header.setText(
            f"ANIMATIONS — {model.object_name}" if has else "ANIMATIONS")
        self.refresh()

    def refresh(self):
        self.list.clear()
        if self._model is None or self._set is None:
            return
        for i, anim in enumerate(self._set.get(self._model.object_name)):
            item = QListWidgetItem(
                f"{anim.label()}  ·  {TRIGGERS.get(anim.trigger, anim.trigger)}"
                f"  ·  {anim.duration}ms")
            item.setToolTip("Double-click to remove")
            item.setData(Qt.ItemDataRole.UserRole, i)
            self.list.addItem(item)

    def _current_animation(self):
        return Animation(kind=self.kind.currentData(),
                         trigger=self.trigger.currentData(),
                         duration=self.duration.value(),
                         easing=self.easing.currentText(),
                         distance=self.distance.value())

    def _add(self):
        if self._model is None:
            return
        self.animationAdded.emit(self._model.object_name, self._current_animation())
        self.refresh()

    def _preview(self):
        if self._model is not None:
            self.previewRequested.emit(self._model.object_name, self._current_animation())

    def _remove_current(self, item):
        if self._model is None:
            return
        self.animationRemoved.emit(self._model.object_name,
                                   item.data(Qt.ItemDataRole.UserRole))
        self.refresh()

    def restyle(self):
        self.setStyleSheet(f"""
            #AnimationsPanel {{ background: {theme.SIDE_PANEL};
                                border-right: 1px solid {theme.BORDER_DARK}; }}
            QLabel#hdr {{ color: {theme.INK_ON_DARK_MUTED}; font-size: 11px;
                          font-weight: 600; letter-spacing: 0.5px; padding: 10px 12px; }}
            QLabel#empty {{ color: {theme.INK_ON_DARK_FAINT}; font-size: 11px; padding: 16px 12px; }}
            QLabel {{ color: {theme.INK_ON_DARK_MUTED}; font-size: 11px; }}
            QComboBox, QSpinBox {{ background: {theme.ACTIVITY_BAR};
                border: 1px solid {theme.BORDER_DARK}; border-radius: {theme.RADIUS_SM}px;
                padding: 3px 6px; color: {theme.INK_ON_DARK}; font-size: 11px; }}
            QComboBox QAbstractItemView {{ background: {theme.SIDE_PANEL};
                color: {theme.INK_ON_DARK}; selection-background-color: {theme.ACCENT_DIM}; }}
            QPushButton#primary {{ background: {theme.ACCENT}; color: {theme.INK_ON_ACCENT};
                border: none; border-radius: {theme.RADIUS_SM}px; padding: 5px 16px;
                font-size: 11px; font-weight: 600; }}
            QPushButton#ghost {{ background: transparent; color: {theme.INK_ON_DARK};
                border: 1px solid {theme.BORDER_DARK}; border-radius: {theme.RADIUS_SM}px;
                padding: 5px 12px; font-size: 11px; }}
            QListWidget {{ background: transparent; border: none; outline: none;
                color: {theme.INK_ON_DARK}; font-size: 11px; }}
            QListWidget::item {{ padding: 6px 12px; }}
            QListWidget::item:hover {{ background: {theme.ACTIVITY_BAR}; }}
        """)

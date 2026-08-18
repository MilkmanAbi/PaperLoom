"""Snap settings (spec §12.5): toggle snapping and set the snap size."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QSpinBox, QCheckBox, QHBoxLayout, QPushButton, QLabel
)
from ... import theme


class SnapDialog(QDialog):
    def __init__(self, enabled, size, grid_visible, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Snap settings")
        self.setObjectName("SnapDialog")
        self.setFixedWidth(300)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 16, 16, 12)
        form = QFormLayout(); form.setSpacing(10)
        self.enabled = QCheckBox(); self.enabled.setChecked(enabled)
        self.size = QSpinBox(); self.size.setRange(1, 200); self.size.setValue(size)
        self.size.setSuffix(" px")
        self.grid = QCheckBox(); self.grid.setChecked(grid_visible)
        form.addRow("Snap to grid", self.enabled)
        form.addRow("Snap size", self.size)
        form.addRow("Show grid", self.grid)
        lay.addLayout(form)
        row = QHBoxLayout(); row.addStretch(1)
        cancel = QPushButton("Cancel"); cancel.setObjectName("ghost"); cancel.clicked.connect(self.reject)
        ok = QPushButton("Apply"); ok.setObjectName("primary"); ok.clicked.connect(self.accept)
        row.addWidget(cancel); row.addWidget(ok)
        lay.addLayout(row)
        self.setStyleSheet(f"""
            #SnapDialog {{ background: {theme.SIDE_PANEL}; }}
            QLabel {{ color: {theme.INK_ON_DARK}; font-size: 12px; }}
            QSpinBox {{ background: {theme.ACTIVITY_BAR}; color: {theme.INK_ON_DARK};
                border: 1px solid {theme.BORDER_DARK}; border-radius: {theme.RADIUS_SM}px;
                padding: 4px 6px; }}
            QPushButton#primary {{ background: {theme.ACCENT}; color: {theme.INK_ON_ACCENT};
                border: none; border-radius: {theme.RADIUS_SM}px; padding: 6px 18px; font-weight: 600; }}
            QPushButton#ghost {{ background: transparent; color: {theme.INK_ON_DARK};
                border: 1px solid {theme.BORDER_DARK}; border-radius: {theme.RADIUS_SM}px;
                padding: 6px 14px; }}
        """)

    def values(self):
        return self.enabled.isChecked(), self.size.value(), self.grid.isChecked()

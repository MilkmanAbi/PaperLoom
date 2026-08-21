"""
Assets panel (spec §12.4). Users add image/font assets to a project; assets are
listed with thumbnails and can be referenced by components that take images.
Assets are copied into the project bundle on save and referenced by generated code.
"""
import os
import shutil

from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QPushButton, QFileDialog
)
from PySide6.QtGui import QPixmap, QIcon

from ... import theme
from ...core.assets import AssetManager, kind_of
from .. import icons

_IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".svg", ".webp"}
_FONT_EXT = {".ttf", ".otf", ".woff", ".woff2"}


class AssetsPanel(QWidget):
    assetAdded = Signal(str)
    assetActivated = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("AssetsPanel")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.manager = AssetManager()   # real backend (copies/links, project-relative keys)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        head = QWidget()
        hl = QHBoxLayout(head); hl.setContentsMargins(12, 8, 6, 6)
        hdr = QLabel("ASSETS"); hdr.setObjectName("hdr")
        hl.addWidget(hdr); hl.addStretch(1)
        add_folder = QPushButton(); add_folder.setIcon(icons.icon("files", theme.INK_ON_DARK_MUTED, 15))
        add_folder.setFixedSize(24, 24); add_folder.setToolTip("Add a folder (used in place)")
        add_folder.setCursor(Qt.CursorShape.PointingHandCursor)
        add_folder.clicked.connect(self.add_folder)
        hl.addWidget(add_folder)
        add = QPushButton(); add.setIcon(icons.icon("plus", theme.INK_ON_DARK_MUTED, 15))
        add.setFixedSize(24, 24); add.setToolTip("Add files (copied into the project)")
        add.setCursor(Qt.CursorShape.PointingHandCursor)
        add.clicked.connect(self.add_assets)
        hl.addWidget(add)
        lay.addWidget(head)

        self.list = QListWidget()
        self.list.setIconSize(QSize(36, 36))
        self.list.itemActivated.connect(
            lambda it: self.assetActivated.emit(it.data(Qt.ItemDataRole.UserRole)))
        lay.addWidget(self.list, 1)

        self._empty = QLabel("No assets yet.\nAdd files (copied into the project) or a folder (used in place).")
        self._empty.setObjectName("empty"); self._empty.setWordWrap(True)
        lay.addWidget(self._empty)

        self.restyle()
        self._refresh()

    def add_assets(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "Add assets", "",
            "Assets (*.png *.jpg *.jpeg *.gif *.bmp *.svg *.webp *.mp3 *.wav *.ogg "
            "*.mp4 *.mov *.webm *.ttf *.otf *.qss);;All files (*)")
        for a in self.manager.import_paths(files):
            self.assetAdded.emit(a.key)
        self._refresh()

    def add_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Add an assets folder")
        if folder:
            for a in self.manager.import_path(folder):
                self.assetAdded.emit(a.key)
            self._refresh()

    def add_asset_path(self, path):
        for a in self.manager.import_path(path):
            self.assetAdded.emit(a.key)
        self._refresh()

    def set_manager(self, manager):
        self.manager = manager
        self._refresh()

    def keys(self):
        return self.manager.keys()

    _KIND_ICON = {"image": "copy", "animated": "layers", "audio": "play",
                  "video": "play", "font": "files", "stylesheet": "files",
                  "data": "files", "other": "files"}

    def _refresh(self):
        self.list.clear()
        for asset in self.manager.all():
            item = QListWidgetItem(f"{asset.name}   ({asset.kind})")
            item.setData(Qt.ItemDataRole.UserRole, asset.key)
            item.setToolTip(asset.key + ("  · linked" if asset.linked else "  · in project"))
            resolved = self.manager.resolve(asset.key)
            if asset.kind in ("image", "animated") and resolved:
                pm = QPixmap(resolved)
                if not pm.isNull():
                    item.setIcon(QIcon(pm.scaled(36, 36, Qt.AspectRatioMode.KeepAspectRatio,
                                                 Qt.TransformationMode.SmoothTransformation)))
                else:
                    item.setIcon(icons.icon("copy", theme.INK_ON_DARK_MUTED, 18))
            else:
                item.setIcon(icons.icon(self._KIND_ICON.get(asset.kind, "files"),
                                        theme.INK_ON_DARK_MUTED, 18))
            self.list.addItem(item)
        has = bool(self.manager.assets)
        self.list.setVisible(has)
        self._empty.setVisible(not has)

    def restyle(self):
        self.setStyleSheet(f"""
            #AssetsPanel {{ background: {theme.SIDE_PANEL};
                            border-right: 1px solid {theme.BORDER_DARK}; }}
            QLabel#hdr {{ color: {theme.INK_ON_DARK_MUTED}; font-size: 11px;
                          font-weight: 600; letter-spacing: 0.5px; }}
            QLabel#empty {{ color: {theme.INK_ON_DARK_FAINT}; font-size: 11px; padding: 16px 12px; }}
            QListWidget {{ background: transparent; border: none; outline: none;
                           color: {theme.INK_ON_DARK}; font-size: 12px; }}
            QListWidget::item {{ padding: 6px; }}
            QListWidget::item:hover {{ background: {theme.ACTIVITY_BAR}; }}
            QListWidget::item:selected {{ background: {theme.ACCENT_DIM}; }}
            QPushButton {{ background: transparent; border: none;
                           border-radius: {theme.RADIUS_SM}px; }}
            QPushButton:hover {{ background: {theme.ACTIVITY_BAR}; }}
        """)

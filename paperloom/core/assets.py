"""
Asset manager (spec §19). Owns everything about files a project uses.

Import rules, as specified:
  - A folder dropped/added is used *as* the assets folder (referenced in place,
    its contents indexed recursively).
  - Loose files are copied into  <project-dir>/assets/<filename.ext>, with
    collision-safe renaming, so the project stays self-contained.

Every asset is addressed by a stable project-relative key ("assets/logo.png"),
which is what components store and what generated code references - so a project
folder can be moved or zipped without breaking.
"""
from __future__ import annotations
import os
import shutil
from dataclasses import dataclass, field

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".bmp", ".webp", ".svg", ".ico", ".tif", ".tiff"}
ANIMATED_EXT = {".gif", ".webp", ".apng"}
AUDIO_EXT = {".mp3", ".wav", ".ogg", ".flac", ".m4a", ".aac"}
VIDEO_EXT = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"}
FONT_EXT = {".ttf", ".otf", ".woff", ".woff2"}
STYLE_EXT = {".qss", ".css"}
DATA_EXT = {".json", ".csv", ".txt", ".md", ".xml"}

ALL_EXT = (IMAGE_EXT | ANIMATED_EXT | AUDIO_EXT | VIDEO_EXT
           | FONT_EXT | STYLE_EXT | DATA_EXT)


def kind_of(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    if ext in ANIMATED_EXT:
        return "animated"
    if ext in IMAGE_EXT:
        return "image"
    if ext in AUDIO_EXT:
        return "audio"
    if ext in VIDEO_EXT:
        return "video"
    if ext in FONT_EXT:
        return "font"
    if ext in STYLE_EXT:
        return "stylesheet"
    if ext in DATA_EXT:
        return "data"
    return "other"


@dataclass
class Asset:
    key: str                 # project-relative, e.g. "assets/logo.png"
    abspath: str             # where it currently lives on disk
    kind: str                # image | animated | audio | video | font | stylesheet | data
    size: int = 0
    linked: bool = False     # True when referenced in place (folder import)

    @property
    def name(self):
        return os.path.basename(self.key)

    def to_dict(self):
        return {"key": self.key, "kind": self.kind, "size": self.size,
                "linked": self.linked,
                # only store abspath for linked (out-of-project) assets
                "abspath": self.abspath if self.linked else ""}


class AssetManager:
    """Indexes a project's assets. Safe to use before a project has a directory -
    imports are then held as linked references until the project is saved."""

    def __init__(self, project_dir: str | None = None):
        self.project_dir = project_dir
        self.assets: dict[str, Asset] = {}
        self.errors: list[str] = []

    # --- location ------------------------------------------------------------
    @property
    def assets_dir(self):
        if not self.project_dir:
            return None
        return os.path.join(self.project_dir, "assets")

    def set_project_dir(self, path: str, migrate=True):
        """Point at a project directory. Any assets imported before the project
        had a home get copied in now."""
        self.project_dir = path
        os.makedirs(self.assets_dir, exist_ok=True)
        if not migrate:
            return
        for key, asset in list(self.assets.items()):
            if asset.linked and os.path.isfile(asset.abspath) \
                    and not asset.abspath.startswith(os.path.abspath(path)):
                self.import_file(asset.abspath, replace_key=key)

    # --- importing -----------------------------------------------------------
    def import_path(self, path: str) -> list[Asset]:
        """Import a file or a folder. Folders are indexed in place (used as-is);
        loose files are copied into the project's assets folder."""
        if os.path.isdir(path):
            return self.import_folder(path)
        return [a for a in [self.import_file(path)] if a]

    def import_paths(self, paths) -> list[Asset]:
        out = []
        for p in paths:
            out.extend(self.import_path(p))
        return out

    def import_folder(self, folder: str) -> list[Asset]:
        """Use a folder as-is: index every supported file inside it, recursively,
        keyed by its path relative to that folder's parent."""
        imported = []
        folder = os.path.abspath(folder)
        if not os.path.isdir(folder):
            self.errors.append(f"Not a folder: {folder}")
            return imported
        base = os.path.dirname(folder)
        for root, _dirs, files in os.walk(folder):
            for fn in files:
                ext = os.path.splitext(fn)[1].lower()
                if ext not in ALL_EXT:
                    continue
                abspath = os.path.join(root, fn)
                key = os.path.relpath(abspath, base).replace(os.sep, "/")
                asset = Asset(key=key, abspath=abspath, kind=kind_of(fn),
                              size=_size(abspath), linked=True)
                self.assets[key] = asset
                imported.append(asset)
        if not imported:
            self.errors.append(f"No supported assets found in {folder}")
        return imported

    def import_file(self, path: str, replace_key: str = None) -> Asset | None:
        """Copy a loose file into <project>/assets/. Without a project directory
        yet, the file is referenced in place and migrated on save."""
        if not os.path.isfile(path):
            self.errors.append(f"Missing file: {path}")
            return None
        ext = os.path.splitext(path)[1].lower()
        if ext not in ALL_EXT:
            self.errors.append(f"Unsupported asset type: {os.path.basename(path)}")
            return None

        if not self.assets_dir:
            key = f"assets/{os.path.basename(path)}"
            asset = Asset(key=key, abspath=os.path.abspath(path),
                          kind=kind_of(path), size=_size(path), linked=True)
            self.assets[key] = asset
            return asset

        os.makedirs(self.assets_dir, exist_ok=True)
        target = os.path.join(self.assets_dir, os.path.basename(path))
        target = _unique(target, self.assets)
        try:
            if os.path.abspath(path) != os.path.abspath(target):
                shutil.copy2(path, target)
        except OSError as exc:
            self.errors.append(f"Could not copy {os.path.basename(path)}: {exc}")
            return None

        key = f"assets/{os.path.basename(target)}"
        asset = Asset(key=key, abspath=target, kind=kind_of(target),
                      size=_size(target), linked=False)
        if replace_key and replace_key in self.assets and replace_key != key:
            del self.assets[replace_key]
        self.assets[key] = asset
        return asset

    # --- querying ------------------------------------------------------------
    def get(self, key):
        return self.assets.get(key)

    def resolve(self, key) -> str | None:
        """Absolute path for an asset key, or None."""
        asset = self.assets.get(key)
        if asset is None:
            return None
        if os.path.isfile(asset.abspath):
            return asset.abspath
        if self.project_dir:
            candidate = os.path.join(self.project_dir, key)
            if os.path.isfile(candidate):
                return candidate
        return None

    def by_kind(self, *kinds):
        return [a for a in self.assets.values() if a.kind in kinds]

    def all(self):
        return sorted(self.assets.values(), key=lambda a: (a.kind, a.key))

    def keys(self):
        return sorted(self.assets)

    def remove(self, key):
        self.assets.pop(key, None)

    # --- persistence ---------------------------------------------------------
    def to_dict(self):
        return {"assets": [a.to_dict() for a in self.all()]}

    def load_dict(self, data, project_dir=None):
        self.project_dir = project_dir or self.project_dir
        self.assets.clear()
        for entry in data.get("assets", []):
            key = entry["key"]
            abspath = entry.get("abspath") or (
                os.path.join(self.project_dir, key) if self.project_dir else key)
            asset = Asset(key=key, abspath=abspath, kind=entry.get("kind", "other"),
                          size=entry.get("size", 0), linked=entry.get("linked", False))
            if not os.path.isfile(asset.abspath):
                self.errors.append(f"Missing asset on load: {key}")
            self.assets[key] = asset
        return self


def _size(path):
    try:
        return os.path.getsize(path)
    except OSError:
        return 0


def _unique(target, existing):
    """Avoid clobbering a same-named asset already in the folder."""
    if not os.path.exists(target):
        return target
    stem, ext = os.path.splitext(target)
    n = 2
    while os.path.exists(f"{stem}_{n}{ext}"):
        n += 1
    return f"{stem}_{n}{ext}"

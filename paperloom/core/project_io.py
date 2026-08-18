"""
Project persistence (spec §20). Implements the on-disk format sketched in §7.3,
now for real:

    myapp/
      project.json              metadata, target language, app theme,
                                 page list, stylesheet + animation config
      pages/<page>.page.json    one skeleton each (widget tree + properties)
      assets/...                imported media (see core/assets.py)
      styles/...                imported .qss stylesheets
      generated/...             codegen output (never hand-edited except logic)

Saving is atomic per file (write to .tmp, then replace) so an interrupted save
can't leave a half-written project. Loading is tolerant: a missing or corrupt
page is reported as an error and skipped rather than taking the whole project
down with it.
"""
from __future__ import annotations
import json
import os
import shutil

from .model import DesignPage, Project
from .assets import AssetManager
from .app_theme import AppTheme

PROJECT_FILE = "project.json"
FORMAT_VERSION = 1


class ProjectIO:
    """Saves and loads a project. Collects non-fatal problems in `errors`."""

    def __init__(self):
        self.errors: list[str] = []

    # --- saving --------------------------------------------------------------
    def save(self, project: Project, directory: str,
             assets: AssetManager = None,
             app_theme: AppTheme = None,
             animations=None,
             stylesheets=None) -> str:
        self.errors = []
        os.makedirs(directory, exist_ok=True)
        os.makedirs(os.path.join(directory, "pages"), exist_ok=True)

        # bring any externally-referenced assets into the project folder
        if assets is not None:
            try:
                assets.set_project_dir(directory)
            except OSError as exc:
                self.errors.append(f"Asset migration failed: {exc}")

        meta = {
            "format": FORMAT_VERSION,
            "name": project.name,
            "target": project.target,
            "accent": project.accent,
            "pages": [p.name for p in project.pages],
            "app_theme": (app_theme or AppTheme()).to_dict(),
            "assets": (assets.to_dict() if assets else {"assets": []}),
            "animations": animations or {},
            "stylesheets": stylesheets or [],
        }
        _atomic_write(os.path.join(directory, PROJECT_FILE),
                      json.dumps(meta, indent=2))

        written = set()
        for page in project.pages:
            path = os.path.join(directory, "pages", f"{_slug(page.name)}.page.json")
            try:
                _atomic_write(path, json.dumps(page.to_dict(), indent=2))
                written.add(os.path.basename(path))
            except OSError as exc:
                self.errors.append(f"Could not save page {page.name}: {exc}")

        # drop page files for pages that no longer exist
        pages_dir = os.path.join(directory, "pages")
        for fn in os.listdir(pages_dir):
            if fn.endswith(".page.json") and fn not in written:
                try:
                    os.remove(os.path.join(pages_dir, fn))
                except OSError:
                    pass

        return directory

    # --- loading -------------------------------------------------------------
    def load(self, directory: str):
        """Returns (project, assets, app_theme, animations, stylesheets)."""
        self.errors = []
        meta_path = os.path.join(directory, PROJECT_FILE)
        if not os.path.isfile(meta_path):
            raise FileNotFoundError(f"No {PROJECT_FILE} in {directory}")
        try:
            with open(meta_path, encoding="utf-8") as f:
                meta = json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"Corrupt {PROJECT_FILE}: {exc}") from exc

        if meta.get("format", 1) > FORMAT_VERSION:
            self.errors.append(
                f"Project was written by a newer PaperLoom (format "
                f"{meta['format']} > {FORMAT_VERSION}); loading anyway.")

        project = Project(name=meta.get("name", "untitled"),
                          target=meta.get("target", "pyside6"),
                          accent=meta.get("accent", "#6B7CFF"),
                          pages=[])

        for page_name in meta.get("pages", []):
            path = os.path.join(directory, "pages", f"{_slug(page_name)}.page.json")
            if not os.path.isfile(path):
                self.errors.append(f"Missing page file for '{page_name}'")
                continue
            try:
                with open(path, encoding="utf-8") as f:
                    project.pages.append(DesignPage.from_dict(json.load(f)))
            except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
                self.errors.append(f"Could not load page '{page_name}': {exc}")

        if not project.pages:
            self.errors.append("Project has no loadable pages; started a blank one.")
            project.pages.append(DesignPage(name="MainWindow"))

        assets = AssetManager(directory).load_dict(meta.get("assets", {}), directory)
        self.errors.extend(assets.errors)

        app_theme = AppTheme.from_dict(meta.get("app_theme", {}))
        animations = meta.get("animations", {})
        stylesheets = meta.get("stylesheets", [])
        return project, assets, app_theme, animations, stylesheets

    # --- packaging -----------------------------------------------------------
    def export_archive(self, directory: str, zip_path: str) -> str:
        """Zip a project folder for sharing. Excludes generated output."""
        stem = zip_path[:-4] if zip_path.endswith(".zip") else zip_path
        tmp = stem + "_staging"
        if os.path.exists(tmp):
            shutil.rmtree(tmp)
        shutil.copytree(directory, tmp,
                        ignore=shutil.ignore_patterns("generated", "__pycache__", "*.pyc"))
        made = shutil.make_archive(stem, "zip", tmp)
        shutil.rmtree(tmp, ignore_errors=True)
        return made


def _slug(name: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in name).lower()


def _atomic_write(path: str, content: str):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(content)
    os.replace(tmp, path)

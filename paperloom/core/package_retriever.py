"""
Package Retriever (Abinaash's name for it): "some custom animations might
need additional packages - or even how some imported files/themes might
need extra libs? let Package Retriever fetch python libs and install via
pip for generation."

Scope for this first slice, deliberately: a component can declare
`requires: [...]` in its meta.json (see components/registry.py's
`Component.requires`) - pip package names its PYSide6 template needs at
RUN time for the generated app to actually work (not build time - this has
nothing to do with PaperLoom's own dependencies). This module can then (1)
collect which of those a given project actually needs, based on which
components are placed on its pages, (2) check which of those aren't
installed yet, and (3) install the missing ones with pip.

Explicitly NOT in this slice (see LONG-MARCH-BACKLOG.md's "Package
Retriever" entry for the plan): scanning imported themes/stylesheets or
custom animations for their own requirements - there's no such declaration
hook for those yet, so pretending to scan them would just be silently
finding nothing. Today's mechanism (declare on a component -> detect ->
install) is the real foundation those can plug into once they have a
similar `requires` field of their own.

C++ is out of scope on purpose, per Abinaash: "for the cpp side, itll be
generated later anyways, cmake will handle it" - CMake's own
find_package()/FetchContent already do this job for the C++ target.
"""
from __future__ import annotations
import subprocess
import sys
from dataclasses import dataclass, field
from importlib import metadata as _importlib_metadata

from .model import Project
from ..components.registry import ComponentRegistry


def normalize(name: str) -> str:
    """PEP 503 normalization - 'Pillow', 'pillow', 'PIL-low' style variance
    would otherwise false-negative an already-installed package as missing."""
    return name.strip().lower().replace("_", "-").replace(".", "-")


def installed_names() -> set:
    """Every distribution name pip already knows about, normalized."""
    names = set()
    for dist in _importlib_metadata.distributions():
        name = dist.metadata.get("Name") if dist.metadata else None
        if name:
            names.add(normalize(name))
    return names


def requirements_for_project(project: Project, registry: ComponentRegistry) -> list:
    """Every pip package name any component actually placed on any page of
    this project declares via `requires`, deduped, in first-seen order.
    Only meaningful for the pyside6 target - see module docstring."""
    seen = []
    for page in project.pages:
        for dw in page.widgets:
            component = registry.get(dw.component_id)
            if component is None:
                continue
            for pkg in (component.requires or []):
                if pkg not in seen:
                    seen.append(pkg)
    return seen


def missing_requirements(project: Project, registry: ComponentRegistry) -> list:
    """requirements_for_project(), filtered down to whatever isn't already
    installed in this Python environment."""
    have = installed_names()
    return [pkg for pkg in requirements_for_project(project, registry)
            if normalize(pkg) not in have]


@dataclass
class InstallResult:
    requested: list = field(default_factory=list)
    installed: list = field(default_factory=list)   # actually pip-installed this run
    already_satisfied: list = field(default_factory=list)
    failed: list = field(default_factory=list)       # (package, error_text)
    dry_run: bool = False
    log: str = ""


def install(packages: list, dry_run: bool = False) -> InstallResult:
    """pip-install whatever in `packages` isn't already satisfied. One pip
    invocation per package (rather than one big batch) so a single bad
    package name fails just that package, not the whole batch - matching
    CppBuildRunner's own "report exactly what failed, don't guess" stance.
    dry_run=True (the CLI's --dry-run) never touches pip or the network -
    it's what makes this safely testable and safely previewable before an
    AI agent (or Abinaash) actually commits to installing anything."""
    result = InstallResult(requested=list(packages), dry_run=dry_run)
    have = installed_names()
    for pkg in packages:
        if normalize(pkg) in have:
            result.already_satisfied.append(pkg)
            continue
        if dry_run:
            result.installed.append(pkg)   # "would install" - see dry_run flag
            continue
        proc = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--break-system-packages", pkg],
            capture_output=True, text=True,
        )
        result.log += proc.stdout + proc.stderr
        if proc.returncode == 0:
            result.installed.append(pkg)
            have.add(normalize(pkg))
        else:
            tail = (proc.stderr or proc.stdout or "").strip().splitlines()
            result.failed.append((pkg, tail[-1] if tail else f"exit code {proc.returncode}"))
    return result

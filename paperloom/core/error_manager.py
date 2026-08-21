"""
Error management system - v1.

Scope, deliberately small and honest: PaperLoom does not collect or send
anything anywhere today. This module is the first real piece of
infrastructure behind the "Collect error data and crash reports" toggle in
Settings > Data and Privacy - when a person turns that on, PaperLoom starts
writing a JSON report to their OWN machine (~/.paperloom/error_reports/)
whenever it hits an unhandled exception. That's it. Nothing is uploaded,
nothing phones home, there is no server on the other end of this yet. When
the toggle is off (the default), this module does nothing at all.

This is intentionally the small, boring first slice of a much bigger idea
Abinaash wants to build later - a full crash/error logging + debug + app
tracer + report tool, which he's named LilyKnight (session 15 follow-up:
"I do slowly wanna build a VERY intricate crash and error logging system,
debug system, app tracer and report tool - Call this LilyKnight"). That's
future work, tackled slowly - see LONG-MARCH-BACKLOG.md's LilyKnight entry.
This module is deliberately written so that bigger system can grow out of
it (capture()/capture_uncaught() are the two seams it would extend) rather
than needing a rewrite.
"""
from __future__ import annotations
import json
import os
import platform
import sys
import traceback
import uuid

from . import app_settings

REPORTS_DIR = os.path.join(os.path.expanduser("~"), ".paperloom", "error_reports")

# PaperLoom's own version string, for now - bump alongside real releases.
# Kept here (not scattered across modules) so the App License doc and any
# future crash report both cite the same one value.
APP_VERSION = "1.3.0"


def enabled() -> bool:
    return bool(app_settings.get("collect_error_reports", False))


def _write_report(report: dict) -> str | None:
    try:
        os.makedirs(REPORTS_DIR, exist_ok=True)
        report_id = report["id"]
        path = os.path.join(REPORTS_DIR, f"{report_id}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
        return path
    except OSError:
        return None


def capture(message: str, *, context: str = "", exc: BaseException | None = None) -> str | None:
    """Record one error report, locally, if and only if the person has
    opted in. Returns the path written (or None if collection is off, or
    the write itself failed - never raises; a broken error reporter must
    never be what crashes the app)."""
    if not enabled():
        return None
    report = {
        "id": uuid.uuid4().hex,
        "app_version": APP_VERSION,
        "platform": platform.platform(),
        "python_version": sys.version,
        "context": context,
        "message": message,
        "traceback": "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
                      if exc is not None else None,
    }
    return _write_report(report)


def capture_uncaught(exc_type, exc_value, exc_tb) -> str | None:
    """Wire this to sys.excepthook to catch crashes PaperLoom itself never
    saw coming. Still opt-in - if collection is off this is a no-op and the
    default excepthook behavior (print to stderr) is left untouched by the
    caller."""
    if not enabled():
        return None
    report = {
        "id": uuid.uuid4().hex,
        "app_version": APP_VERSION,
        "platform": platform.platform(),
        "python_version": sys.version,
        "context": "uncaught",
        "message": str(exc_value),
        "traceback": "".join(traceback.format_exception(exc_type, exc_value, exc_tb)),
    }
    return _write_report(report)


def list_reports() -> list[str]:
    """Report file paths on disk, newest first - so a future 'Show my error
    reports' button in Settings has something to point at without this
    module needing any new surface."""
    try:
        names = [n for n in os.listdir(REPORTS_DIR) if n.endswith(".json")]
    except OSError:
        return []
    names.sort(reverse=True)
    return [os.path.join(REPORTS_DIR, n) for n in names]

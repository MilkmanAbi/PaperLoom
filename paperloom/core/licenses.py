"""
Where PaperLoom's two license documents live on disk, and a safe way to read
them - backs Settings > Licenses.

Both files are kept at the repo root in licenses/ (alongside README.md,
LONG-MARCH-BACKLOG.md, and the spec - PaperLoom's other top-level docs),
not inside the paperloom/ package itself, so they read as project-level
documents rather than application resources. Located relative to this
package's own install location (parent of paperloom/), not the current
working directory, so this works the same whether PaperLoom is launched via
`python main.py` from the repo root or from anywhere else.

  GPL_PATH        - the GPLv3 text Abinaash uploaded, for source-material/
                     attribution use, verbatim.
  APP_LICENSE_PATH - a separate, deliberately crude/draft document about
                     PaperLoom the app itself (what it does, what it's
                     built on, what error collection might do) - meant to
                     be filled in gradually, not a finished legal document.
"""
import os

_PACKAGE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # .../paperloom
_REPO_ROOT = os.path.dirname(_PACKAGE_DIR)
_LICENSES_DIR = os.path.join(_REPO_ROOT, "licenses")

GPL_PATH = os.path.join(_LICENSES_DIR, "GPLv3-PaperLoom.md")
APP_LICENSE_PATH = os.path.join(_LICENSES_DIR, "APP-LICENSE.md")


def read(path: str) -> str:
    """Never raises - a missing/unreadable license file (e.g. a packaged
    build that didn't bundle licenses/) shows an honest message instead of
    crashing Settings."""
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ("This license document isn't available in this build.\n\n"
                f"Expected it at:\n{path}")

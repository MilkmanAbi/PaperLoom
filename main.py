import sys

from PySide6.QtWidgets import QApplication, QDialog


def _install_error_hook():
    """Chain onto sys.excepthook rather than replace it - the default
    behavior (print the traceback to stderr) must never go away just
    because someone opted into local crash reports too. capture_uncaught()
    itself is a no-op unless Settings > Data and Privacy has the "Collect
    error data and crash reports" toggle on (default: off)."""
    from paperloom.core import error_manager
    default_hook = sys.excepthook

    def _hook(exc_type, exc_value, exc_tb):
        try:
            error_manager.capture_uncaught(exc_type, exc_value, exc_tb)
        except Exception:
            pass   # the error reporter must never be what crashes the app
        default_hook(exc_type, exc_value, exc_tb)

    sys.excepthook = _hook


def _ensure_valid_font(app):
    """Guarantee the base application font has a real point size. Our chrome QSS
    uses pixel font-sizes, which leave a widget's pointSize() at -1; on Windows
    that surfaces as the harmless-but-noisy 'QFont::setPointSize: Point size <= 0
    (-1)' warning when a font gets copied. Seeding a valid point size heads it off.
    """
    f = app.font()
    if f.pointSize() <= 0:
        f.setPointSize(9)
        app.setFont(f)


def main():
    app = QApplication(sys.argv)

    # Show the boot splash BEFORE importing the rest of the app. Most of
    # PaperLoom's "slow to start" feeling is PySide6 + all the editor chrome
    # (main_window, every side panel, icons, themes) being imported and the
    # component library being parsed - none of which has happened yet at
    # this point, so this is the earliest a splash can appear. Deferring the
    # heavy imports to right here (instead of at module load time) is what
    # makes that possible.
    from paperloom.ui.loading_splash import LoadingSplash
    boot = LoadingSplash()
    boot.show()
    app.processEvents()

    _install_error_hook()
    _ensure_valid_font(app)

    boot.set_status("Loading editor...")
    app.processEvents()
    from paperloom import theme
    from paperloom.ui.main_window import PaperLoomWindow
    from paperloom.ui.splash import SplashScreen, add_recent
    from paperloom.ui import branding
    from paperloom.components.registry import ComponentRegistry
    from paperloom.core.model import Project, DesignPage

    app.setStyleSheet(theme.app_stylesheet())
    # every window inherits this as its default - taskbar/dock/alt-tab icon,
    # and every other window's own setWindowIcon() call below reads the same
    # Logo.png path (paperloom/ui/branding.py)
    app.setWindowIcon(branding.app_icon())

    boot.set_status("Loading component library...")
    app.processEvents()
    registry = ComponentRegistry().load()

    boot.close()

    # start screen: open an existing project or start fresh (language once, up front)
    splash = SplashScreen()
    if splash.exec() != QDialog.DialogCode.Accepted or splash.action is None:
        return

    # Building PaperLoomWindow itself (the canvas, every side panel, the
    # toolbars) is the single slowest step in the whole startup - up to
    # 10-15s reported - and it happens right here, AFTER the project-picker
    # dialog closes. That used to be a dead silent gap with nothing on
    # screen between "you picked a project" and "the editor appears" - the
    # boot splash is still alive (just hidden), so bringing it back for
    # this stretch covers exactly that gap instead of only the earlier one.
    boot.set_status("Opening your project..." if splash.action == "open"
                     else "Setting up your project...")
    boot.show()
    app.processEvents()

    if splash.action == "new":
        project = Project(name="untitled", target=splash.target,
                          pages=[DesignPage(name="MainWindow")])
        window = PaperLoomWindow(registry, project=project)
    else:  # open
        window = PaperLoomWindow(registry)
        if window.open_project(splash.directory):
            add_recent(splash.directory)

    boot.close()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

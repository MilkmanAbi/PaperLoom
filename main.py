import sys

from PySide6.QtWidgets import QApplication, QDialog

from paperloom import theme
from paperloom.ui.main_window import PaperLoomWindow
from paperloom.ui.splash import SplashScreen, add_recent
from paperloom.components.registry import ComponentRegistry
from paperloom.core.model import Project, DesignPage


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
    _ensure_valid_font(app)
    app.setStyleSheet(theme.app_stylesheet())

    registry = ComponentRegistry().load()

    # start screen: open an existing project or start fresh (language once, up front)
    splash = SplashScreen()
    if splash.exec() != QDialog.DialogCode.Accepted or splash.action is None:
        return

    if splash.action == "new":
        project = Project(name="untitled", target=splash.target,
                          pages=[DesignPage(name="MainWindow")])
        window = PaperLoomWindow(registry, project=project)
    else:  # open
        window = PaperLoomWindow(registry)
        if window.open_project(splash.directory):
            add_recent(splash.directory)

    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

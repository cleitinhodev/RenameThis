"""Ponto de entrada da interface gráfica."""

from __future__ import annotations

import sys

from PySide6.QtCore import QSettings
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from .. import __version__
from ..i18n import detect_language, set_language
from . import theme
from .resources import resource_path


def create_app(argv: list[str] | None = None) -> QApplication:
    app = QApplication.instance() or QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName("RenameThis")
    app.setOrganizationName("CleitinhoDEV")
    app.setApplicationVersion(__version__)
    # Tema colorido (claro/escuro conforme o sistema), sobre o estilo Fusion
    theme.apply_theme(app)
    icon = resource_path("Design/icone.ico")
    if icon:
        app.setWindowIcon(QIcon(str(icon)))
    return app


def main(argv: list[str] | None = None) -> int:
    app = create_app(argv)
    settings = QSettings("CleitinhoDEV", "RenameThis")
    set_language(str(settings.value("language", "") or detect_language()))
    from .main_window import MainWindow

    window = MainWindow(settings=settings)
    theme.follow_system_theme(app, on_change=window.rebuild_for_theme)
    window.show()
    return app.exec()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

"""Ponto de entrada da interface gráfica."""

from __future__ import annotations

import sys

from PySide6 import __version__ as pyside_version
from PySide6.QtCore import QSettings
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from .. import __version__
from ..i18n import detect_language, set_language
from .resources import resource_path


def _version_tuple(text: str) -> tuple[int, ...]:
    out = []
    for part in text.split(".")[:3]:
        digits = "".join(c for c in part if c.isdigit())
        out.append(int(digits or 0))
    return tuple(out)


def create_app(argv: list[str] | None = None) -> QApplication:
    app = QApplication.instance() or QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName("RenameThis")
    app.setOrganizationName("CleitinhoDEV")
    app.setApplicationVersion(__version__)
    # Tema claro/escuro segue o sistema. No Windows, antes do Qt 6.7 o estilo nativo
    # não suporta modo escuro, então usamos o Fusion (que segue o esquema de cores).
    if sys.platform == "win32" and _version_tuple(pyside_version) < (6, 7):
        app.setStyle("Fusion")
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
    window.show()
    return app.exec()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

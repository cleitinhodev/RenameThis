"""Tema visual: folha de estilo carrega e é aplicada (modo offscreen)."""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)

from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtGui import QPalette  # noqa: E402

from renamethis.core import Journal  # noqa: E402
from renamethis.gui import theme  # noqa: E402
from renamethis.gui.app import create_app  # noqa: E402
from renamethis.gui.main_window import MainWindow  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return create_app([])


def test_stylesheet_file_is_packaged():
    assert theme.STYLE_FILE.is_file()


@pytest.mark.parametrize("palette", [theme.LIGHT, theme.DARK])
def test_stylesheet_builds_without_placeholders(app, palette):
    qss = theme.build_stylesheet(palette)
    assert "{{" not in qss and "}}" not in qss
    assert palette.accent in qss
    assert "#PrimaryButton" in qss and "#DangerButton" in qss
    # os PNGs referenciados na QSS existem
    for name in ("check", "chevron-down", "chevron-up"):
        assert (theme._asset_dir(palette) / f"{name}.png").is_file()


@pytest.mark.parametrize("dark", [False, True])
def test_apply_theme_offscreen(app, tmp_path, dark):
    palette = theme.apply_theme(app, dark=dark)
    assert theme.current() is palette and palette.dark is dark
    assert app.property("renamethis_fusion") and app.property("renamethis_dark") is dark
    assert app.styleSheet()
    window_color = app.palette().color(QPalette.ColorRole.Window)
    assert (window_color.lightness() < 128) is dark

    w = MainWindow(
        settings=QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat),
        journal=Journal(tmp_path / "j"),
        check_incomplete=False,
    )
    assert w.apply_button.objectName() == "PrimaryButton"
    assert w.undo_button.objectName() == "DangerButton"
    assert w.top_bar.objectName() == "HeaderBar"
    assert not w.grab().isNull()
    w.rebuild_for_theme()
    w.close()
    theme.apply_theme(app, dark=False)


def test_env_forces_theme(monkeypatch, app):
    monkeypatch.setenv("RENAMETHIS_THEME", "dark")
    assert theme.system_prefers_dark(app) is True
    monkeypatch.setenv("RENAMETHIS_THEME", "light")
    assert theme.system_prefers_dark(app) is False


def test_icons_render(app):
    for name in theme._SVG:
        assert not theme.icon(name, "#ff0000").isNull()

"""Testes da interface em modo headless (QT_QPA_PLATFORM=offscreen)."""

import os
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)

from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from renamethis.core import Journal, Status  # noqa: E402
from renamethis.core.rules import CounterRule, PrefixSuffixRule  # noqa: E402
from renamethis.gui.app import create_app  # noqa: E402
from renamethis.gui.main_window import MainWindow  # noqa: E402
from renamethis.gui.resources import resource_path  # noqa: E402
from renamethis.gui.rule_editor import RuleEditor  # noqa: E402
from renamethis.i18n import set_language  # noqa: E402
from tests.conftest import make_files, snapshot  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return create_app([])


@pytest.fixture
def window(app, tmp_path):
    set_language("pt_BR")
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    w = MainWindow(settings=settings, journal=Journal(tmp_path / "journal"), check_incomplete=False)
    w.messages = []
    w.notify = lambda kind, title, text, details="": w.messages.append((kind, text))
    w.ask = lambda *a, **k: True
    yield w
    w._running = False
    w.close()
    w.deleteLater()


def wait_idle(w, timeout=10.0):
    deadline = time.monotonic() + timeout
    while w._running and time.monotonic() < deadline:
        QApplication.processEvents()
        time.sleep(0.01)
    for _ in range(5):
        QApplication.processEvents()
    assert not w._running, "worker não terminou"


def test_window_constructs(window):
    assert window.windowTitle().startswith("RenameThis!")
    assert not window.apply_button.isEnabled()
    assert not window.undo_button.isEnabled()
    assert "pasta" in window.summary_label.text().lower()


def test_icon_resource_found():
    assert resource_path("Design/icone.ico") is not None
    assert resource_path("nao/existe.png") is None


def test_preview_apply_and_undo(window, folder):
    make_files(folder, ["1.txt", "2.txt", "10.txt"])
    before = snapshot(folder)
    window.set_folder(str(folder))
    assert window.model.rowCount() == 3
    window.add_rule("counter")
    window.rules[0].position = "replace"
    window.desc_check.setChecked(True)  # 10, 2, 1
    window.refresh_preview()
    assert window.model.item_at(0).entry.name == "10.txt"
    assert window.model.item_at(0).new_name == "1.txt"
    assert window.apply_button.isEnabled()

    window.start_apply(confirm=False)
    assert not window.apply_button.isEnabled()  # desativado durante a execução
    wait_idle(window)
    assert window.last_result.ok
    assert snapshot(folder)["1.txt"] == before["10.txt"]
    assert window.messages and window.messages[-1][0] == "info"
    assert window.undo_button.isEnabled()

    window.undo()
    wait_idle(window)
    assert snapshot(folder) == before
    assert not window.undo_button.isEnabled()


def test_errors_disable_apply(window, folder):
    make_files(folder, ["a.txt"])
    window.set_folder(str(folder))
    window.rules = [PrefixSuffixRule(prefix="../")]
    window._refresh_rule_list(0)
    window.refresh_preview()
    assert window.plan.has_errors
    assert window.model.item_at(0).status is Status.ERROR
    assert not window.apply_button.isEnabled()
    window.start_apply(confirm=False)  # mesmo chamando direto, não faz nada
    assert not window._running
    assert snapshot(folder) == {"a.txt": "conteudo de a.txt"}


def test_invalid_folder_message(window, tmp_path):
    window.set_folder(str(tmp_path / "nao_existe"))
    assert "não existe" in window.summary_label.text()
    assert not window.apply_button.isEnabled()


def test_rule_list_operations(window):
    window.add_rule("prefix_suffix")
    window.add_rule("case")
    assert window.rule_list.count() == 2
    window.rule_list.setCurrentRow(1)
    window.move_rule(-1)
    assert [r.type for r in window.rules] == ["case", "prefix_suffix"]
    window.duplicate_rule()
    assert len(window.rules) == 3
    window.remove_rule()
    assert len(window.rules) == 2


def test_only_changes_filter(window, folder):
    make_files(folder, ["a.txt", "b.jpg"])
    window.set_folder(str(folder))
    window.rules = [PrefixSuffixRule(prefix="x")]
    window.rules[0].prefix = ""
    window.add_rule("extension")
    window.rules[-1].mode = "upper"
    window.refresh_preview()
    assert window.model.rowCount() == 2
    window.only_changes_check.setChecked(True)
    assert window.model.rowCount() == 2
    window.ext_edit.setText("jpg")
    window.refresh_preview()
    assert window.model.rowCount() == 1


def test_language_switch_rebuilds_ui(window):
    window.add_rule("counter")
    window.change_language("en")
    assert window.apply_button.text() == "Rename"
    assert len(window.rules) == 1 and window.rule_list.count() == 1
    window.change_language("pt_BR")
    assert window.apply_button.text() == "Renomear"


def test_preset_roundtrip_through_window(window, tmp_path):
    from renamethis.core import Preset, save_preset

    path = tmp_path / "p.json"
    save_preset(Preset(rules=[CounterRule(padding=4)]), path)
    assert window.load_preset_file(str(path))
    assert window.rules == [CounterRule(padding=4)]
    bad = tmp_path / "bad.json"
    bad.write_text("{")
    assert not window.load_preset_file(str(bad))
    assert window.messages[-1][0] == "error"


@pytest.mark.parametrize("kind", ["remove", "template", "date", "extension", "replace"])
def test_rule_editor_updates_rule(app, kind):
    from renamethis.core.rules import RULE_TYPES

    rule = RULE_TYPES[kind]()
    editor = RuleEditor(rule)
    hits = []
    editor.changed.connect(lambda: hits.append(1))
    first_text = next((f for f in rule.FIELDS if f.kind == "text"), None)
    if first_text:
        editor.field_widget(first_text.name).setText("abc")
        assert getattr(rule, first_text.name) == "abc"
        assert hits


def test_session_is_saved_and_restored(app, tmp_path):
    settings = QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat)
    j = Journal(tmp_path / "j")
    w = MainWindow(settings=settings, journal=j, check_incomplete=False)
    w.add_rule("letters")
    w._save_session()
    w.close()
    w2 = MainWindow(settings=settings, journal=j, check_incomplete=False)
    assert [r.type for r in w2.rules] == ["letters"]
    w2.close()

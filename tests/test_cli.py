import json

import pytest

from renamethis.cli import main, parse_rule_args
from renamethis.core.rules import CounterRule
from tests.conftest import make_files, snapshot


def test_parse_rule_args():
    r = parse_rule_args("counter", ["padding=3", "position=prefix", "reset_per_folder=sim"])
    assert r == CounterRule(padding=3, position="prefix", reset_per_folder=True)


def test_dry_run_changes_nothing(folder, capsys):
    make_files(folder, ["b.txt", "a.txt"])
    before = snapshot(folder)
    code = main(["--lang", "pt_BR", "rename", str(folder), "--prefix", "x_", "--dry-run"])
    assert code == 0
    assert snapshot(folder) == before
    out = capsys.readouterr().out
    assert "x_a.txt" in out and "Simulação" in out


def test_rename_with_yes_and_undo(folder, capsys):
    make_files(folder, ["1.txt", "2.txt", "10.txt"])
    before = snapshot(folder)
    code = main(
        [
            "--lang",
            "en",
            "rename",
            str(folder),
            "--add",
            "counter",
            "position=replace",
            "padding=2",
            "--sort",
            "name",
            "--desc",
            "--yes",
        ]
    )
    assert code == 0, capsys.readouterr()
    after = snapshot(folder)
    assert sorted(after) == ["01.txt", "02.txt", "03.txt"]
    assert after["01.txt"] == before["10.txt"]
    assert main(["--lang", "en", "history"]) == 0
    assert "Rename" in capsys.readouterr().out
    assert main(["--lang", "en", "undo", "--yes"]) == 0
    assert snapshot(folder) == before


def test_rules_are_applied_in_command_line_order(folder):
    make_files(folder, ["a b.txt"])
    main(["rename", str(folder), "--replace", " ", "_", "--case", "upper", "--yes"])
    assert list(snapshot(folder)) == ["A_B.txt"]


def test_errors_block_and_exit_1(folder, capsys):
    make_files(folder, ["a.txt"])
    code = main(["--lang", "en", "rename", str(folder), "--prefix", "../", "--yes"])
    assert code == 1
    assert snapshot(folder) == {"a.txt": "conteudo de a.txt"}


def test_no_rules(folder, capsys):
    assert main(["rename", str(folder)]) == 2


def test_bad_folder(tmp_path, capsys):
    assert main(["--lang", "en", "rename", str(tmp_path / "nope"), "--prefix", "x"]) == 2
    assert "not found" in capsys.readouterr().err


def test_confirmation_declined(folder, monkeypatch):
    make_files(folder, ["a.txt"])
    monkeypatch.setattr("builtins.input", lambda _p: "n")
    assert main(["rename", str(folder), "--prefix", "x"]) == 1
    assert list(snapshot(folder)) == ["a.txt"]


def test_preset_save_and_use(folder, tmp_path):
    make_files(folder, ["a.txt"])
    preset = tmp_path / "p.json"
    main(
        [
            "rename",
            str(folder),
            "--template",
            "novo_{n:02}",
            "--save-preset",
            str(preset),
            "--dry-run",
        ]
    )
    assert json.loads(preset.read_text())["rules"][0]["type"] == "template"
    assert main(["rename", str(folder), "--preset", str(preset), "--yes"]) == 0
    assert list(snapshot(folder)) == ["novo_01.txt"]


def test_bad_add_args():
    with pytest.raises(SystemExit):
        main(["rename", ".", "--add", "counter", "nada"])
    with pytest.raises(SystemExit):
        main(["rename", ".", "--add", "naoexiste"])


def test_rules_command(capsys):
    assert main(["--lang", "en", "rules"]) == 0
    assert "counter" in capsys.readouterr().out

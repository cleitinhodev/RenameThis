import json

import pytest

from renamethis.core import ScanOptions, apply_plan, recover_incomplete, undo_last
from renamethis.core.rules import PrefixSuffixRule
from tests.conftest import make_files, map_plan, plan_for, snapshot


def test_undo_restores_everything(folder, journal):
    make_files(folder, ["a", "b", "c"])
    before = snapshot(folder)
    assert apply_plan(map_plan(folder, {"a": "b", "b": "c", "c": "a"}), journal).ok
    assert snapshot(folder) != before
    result = undo_last(journal)
    assert result.ok
    assert snapshot(folder) == before
    assert journal.last_undoable() is None
    assert undo_last(journal) is None


def test_undo_multiple_levels(folder, journal):
    make_files(folder, ["a.txt"])
    apply_plan(plan_for(folder, [PrefixSuffixRule(prefix="1_")]), journal)
    apply_plan(plan_for(folder, [PrefixSuffixRule(prefix="2_")]), journal)
    assert list(snapshot(folder)) == ["2_1_a.txt"]
    assert undo_last(journal).ok
    assert list(snapshot(folder)) == ["1_a.txt"]
    assert undo_last(journal).ok
    assert list(snapshot(folder)) == ["a.txt"]


def test_undo_refuses_if_file_was_removed(folder, journal):
    make_files(folder, ["a.txt", "b.txt"])
    apply_plan(plan_for(folder, [PrefixSuffixRule(prefix="x_")]), journal)
    (folder / "x_b.txt").unlink()
    state = snapshot(folder)
    result = undo_last(journal)
    assert not result.ok and result.error_code == "source_missing"
    assert snapshot(folder) == state  # nada foi mexido
    assert journal.last_undoable() is not None  # continua disponível


def test_undo_refuses_to_overwrite_new_file(folder, journal):
    make_files(folder, ["a.txt"])
    apply_plan(plan_for(folder, [PrefixSuffixRule(prefix="x_")]), journal)
    (folder / "a.txt").write_text("arquivo novo do usuário")
    result = undo_last(journal)
    assert result.error_code == "target_exists"
    assert (folder / "a.txt").read_text() == "arquivo novo do usuário"
    assert (folder / "x_a.txt").exists()


def test_undo_recursive_folders(folder, journal):
    make_files(folder, ["album/1.jpg", "album/sub/2.jpg"])
    before = snapshot(folder)
    plan = plan_for(
        folder, [PrefixSuffixRule(prefix="x_")], ScanOptions(recursive=True, include_dirs=True)
    )
    assert apply_plan(plan, journal).ok
    assert undo_last(journal).ok
    assert snapshot(folder) == before


def test_recover_after_crash(folder, journal):
    """Simula queda no meio da operação (exceção que não é Exception)."""
    make_files(folder, ["a", "b", "c", "d"])
    before = snapshot(folder)
    plan = map_plan(folder, {"a": "b", "b": "c", "c": "d", "d": "a"})

    def crash(step):
        if step == 5:
            raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        apply_plan(plan, journal, fail_hook=crash)
    assert snapshot(folder) != before
    assert journal.incomplete()
    restored, errors = recover_incomplete(journal)
    assert not errors and restored == 4
    assert snapshot(folder) == before
    assert not journal.incomplete()


def test_corrupted_journal_files_are_ignored(folder, journal):
    journal.directory.mkdir(parents=True)
    (journal.directory / "lixo.json").write_text("{not json")
    (journal.directory / "x.json").write_text(json.dumps({"sem": "id"}))
    assert journal.entries() == []
    assert undo_last(journal) is None


def test_prune_keeps_recent(folder, journal):
    make_files(folder, ["a.txt"])
    for i in range(5):
        apply_plan(plan_for(folder, [PrefixSuffixRule(prefix=f"{i}")]), journal)
    journal.prune(keep=2)
    assert len(journal.entries()) == 2

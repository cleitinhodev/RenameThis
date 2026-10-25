import errno
import os

import pytest

from renamethis.core import ScanOptions, SortOptions, apply_plan, fsops
from renamethis.core.executor import TMP_PREFIX
from renamethis.core.rules import CounterRule, PrefixSuffixRule, TemplateRule
from tests.conftest import make_files, map_plan, plan_for, snapshot


def contents_by_original(folder, before, renamed_map):
    """Verifica que cada conteúdo original está no novo nome esperado."""
    after = snapshot(folder)
    for old, new in renamed_map.items():
        assert after[new] == before[old], (old, new)


def no_temp_files(folder):
    return not [p for p in folder.rglob("*") if p.name.startswith(TMP_PREFIX)]


def test_safe_rename_never_overwrites(folder):
    make_files(folder, ["a", "b"])
    with pytest.raises(FileExistsError):
        fsops.safe_rename(folder / "a", folder / "b")
    assert (folder / "b").read_text() == "conteudo de b"


def test_safe_rename_fallback_never_overwrites(folder, monkeypatch):
    monkeypatch.setattr(fsops, "_native_ok", False)
    make_files(folder, ["a", "b"])
    with pytest.raises(FileExistsError):
        fsops.safe_rename(folder / "a", folder / "b")
    fsops.safe_rename(folder / "a", folder / "c")
    assert (folder / "c").read_text() == "conteudo de a"


def test_safe_rename_refuses_other_folder(folder, tmp_path):
    make_files(folder, ["a"])
    with pytest.raises(ValueError):
        fsops.safe_rename(folder / "a", tmp_path / "a")


def test_counter_collision_preserves_every_file(folder, journal):
    names = [f"{i}.txt" for i in range(1, 13)]
    make_files(folder, names)
    before = snapshot(folder)
    plan = plan_for(folder, [CounterRule(position="replace")], sort=SortOptions(descending=True))
    result = apply_plan(plan, journal)
    assert result.ok, result
    after = snapshot(folder)
    assert len(after) == 12
    assert sorted(after.values()) == sorted(before.values())
    # 12.txt era o primeiro na ordem decrescente -> virou 1.txt
    assert after["1.txt"] == before["12.txt"]
    assert after["12.txt"] == before["1.txt"]
    assert no_temp_files(folder)


def test_swap_and_cycle(folder, journal):
    make_files(folder, ["a", "b", "c"])
    before = snapshot(folder)
    mapping = {"a": "b", "b": "c", "c": "a"}
    result = apply_plan(map_plan(folder, mapping), journal)
    assert result.ok
    contents_by_original(folder, before, mapping)
    assert len(result.renamed) == 3


def test_refuses_plan_with_errors(folder, journal):
    make_files(folder, ["a.txt"])
    plan = plan_for(folder, [PrefixSuffixRule(prefix="../")])
    result = apply_plan(plan, journal)
    assert result.error_code == "plan_has_errors"
    assert snapshot(folder) == {"a.txt": "conteudo de a.txt"}


@pytest.mark.parametrize("fail_at", [0, 1, 3, 5, 7, 9])
def test_rollback_on_failure_midway(folder, journal, fail_at):
    names = ["a", "b", "c", "d", "e"]
    make_files(folder, names)
    before = snapshot(folder)
    plan = map_plan(folder, {"a": "b", "b": "c", "c": "d", "d": "e", "e": "a"})

    def hook(step):
        if step == fail_at:
            raise OSError(errno.EACCES, "permissão negada (simulada)", "x")

    result = apply_plan(plan, journal, fail_hook=hook)
    assert not result.ok
    assert result.rolled_back and not result.rollback_errors
    assert result.renamed == []
    assert snapshot(folder) == before
    assert no_temp_files(folder)
    assert journal.entries()[0].status == "rolled_back"
    assert journal.last_undoable() is None


def test_preflight_detects_new_file_after_preview(folder, journal):
    make_files(folder, ["a.txt"])
    plan = map_plan(folder, {"a.txt": "b.txt"})
    (folder / "b.txt").write_text("criado depois da prévia")
    result = apply_plan(plan, journal)
    assert result.error_code == "target_exists"
    assert (folder / "b.txt").read_text() == "criado depois da prévia"
    assert (folder / "a.txt").exists()


def test_preflight_detects_missing_source(folder, journal):
    make_files(folder, ["a.txt", "b.txt"])
    plan = plan_for(folder, [PrefixSuffixRule(prefix="x_")])
    (folder / "b.txt").unlink()
    result = apply_plan(plan, journal)
    assert result.error_code == "source_missing"
    assert snapshot(folder) == {"a.txt": "conteudo de a.txt"}


def test_case_only_rename(folder, journal):
    make_files(folder, ["foto.txt"])
    result = apply_plan(map_plan(folder, {"foto.txt": "FOTO.txt"}), journal)
    assert result.ok
    assert os.listdir(folder) == ["FOTO.txt"]


def test_rename_folders_and_contents_recursively(folder, journal):
    make_files(folder, ["album/1.jpg", "album/2.jpg", "album/sub/3.jpg"])
    before = snapshot(folder)
    opts = ScanOptions(recursive=True, include_dirs=True)
    plan = plan_for(folder, [PrefixSuffixRule(prefix="x_")], opts)
    assert not plan.has_errors
    result = apply_plan(plan, journal)
    assert result.ok, result
    after = snapshot(folder)
    assert after == {
        "x_album/x_1.jpg": before["album/1.jpg"],
        "x_album/x_2.jpg": before["album/2.jpg"],
        "x_album/x_sub/x_3.jpg": before["album/sub/3.jpg"],
    }


def test_journal_is_written(folder, journal):
    make_files(folder, ["a.txt"])
    result = apply_plan(plan_for(folder, [TemplateRule(template="novo")]), journal)
    assert result.ok and result.journal_path and result.journal_path.exists()
    entry = journal.last_undoable()
    assert entry.count == 1 and entry.stages[0][0]["dst"].endswith("novo.txt")


def test_apply_without_journal(folder):
    make_files(folder, ["a.txt"])
    result = apply_plan(plan_for(folder, [TemplateRule(template="novo")]), journal=False)
    assert result.ok and result.journal_path is None

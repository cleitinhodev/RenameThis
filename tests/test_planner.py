from renamethis.core import ConflictPolicy, ScanOptions, SortOptions, Status
from renamethis.core.rules import CounterRule, ExtensionRule, PrefixSuffixRule, ReplaceRule
from tests.conftest import make_files, map_plan, plan_for


def by_name(plan):
    return {i.entry.name: i for i in plan.items}


def codes(item):
    return {i.code for i in item.issues}


def test_unchanged_is_skipped(folder):
    make_files(folder, ["a.txt", "b.txt"])
    plan = plan_for(folder, [ReplaceRule(find="zzz", replace="y")])
    assert all(i.status is Status.UNCHANGED for i in plan.items)
    assert plan.to_rename == []


def test_counter_collision_10_and_1_is_safe_chain(folder):
    """O bug clássico: 10.txt -> 1.txt enquanto 1.txt ainda existe."""
    make_files(folder, ["1.txt", "2.txt", "10.txt"])
    plan = plan_for(folder, [CounterRule(position="replace")], sort=SortOptions(descending=True))
    items = by_name(plan)
    assert items["10.txt"].new_name == "1.txt" and items["10.txt"].status is Status.OK
    assert items["2.txt"].status is Status.UNCHANGED
    assert items["1.txt"].new_name == "3.txt"
    assert not plan.has_errors


def test_conflict_with_file_outside_plan_suffix(folder):
    make_files(folder, ["a.jpg", "foto.png"])
    # só .jpg entra no plano; foto.png é um arquivo "de fora" que não pode ser sobrescrito
    plan = plan_for(
        folder,
        [ReplaceRule(find="a", replace="foto"), ExtensionRule(mode="change", new_ext="png")],
        ScanOptions(extensions=["jpg"]),
    )
    item = plan.items[0]
    assert item.new_name == "foto (2).png"
    assert {"conflict_existing", "suffix_added"} <= codes(item)
    assert item.status is Status.WARNING


def test_conflict_with_file_outside_plan_skip(folder):
    make_files(folder, ["a.jpg", "foto.jpg"])
    plan = plan_for(folder, [ReplaceRule(find="a", replace="foto")], policy=ConflictPolicy.SKIP)
    items = by_name(plan)
    assert items["a.jpg"].status is Status.SKIPPED
    assert "conflict_existing" in codes(items["a.jpg"])


def test_duplicates_inside_plan_get_suffix(folder):
    make_files(folder, ["x1.txt", "x2.txt", "x3.txt"])
    plan = plan_for(folder, [ReplaceRule(find=r"\d", replace="", regex=True)])
    assert [i.new_name for i in plan.items] == ["x.txt", "x (2).txt", "x (3).txt"]
    assert not plan.has_errors


def test_duplicates_inside_plan_skip_cascades(folder):
    # b -> c é duplicado (pulado), então "b" continua ocupado e c -> b também é pulado;
    # como "c" não sai do lugar, a -> c também precisa ser pulado. Nada é sobrescrito.
    make_files(folder, ["a", "b", "c"])
    plan = map_plan(folder, {"a": "c", "b": "c", "c": "b"}, policy=ConflictPolicy.SKIP)
    assert all(i.status is Status.SKIPPED for i in plan.items)
    assert plan.to_rename == []
    # com um nome livre, só o duplicado é pulado
    plan = map_plan(folder, {"a": "z", "b": "z"}, policy=ConflictPolicy.SKIP)
    items = by_name(plan)
    assert items["a"].status is Status.OK and items["b"].status is Status.SKIPPED


def test_swap_and_cycle_allowed(folder):
    make_files(folder, ["a", "b", "c"])
    plan = map_plan(folder, {"a": "b", "b": "c", "c": "a"})
    assert all(i.status is Status.OK for i in plan.items)


def test_path_traversal_is_error(folder):
    make_files(folder, ["a.txt"])
    plan = plan_for(folder, [PrefixSuffixRule(prefix="../")])
    assert plan.has_errors
    assert "path_separator" in codes(plan.items[0])
    plan = map_plan(folder, {"a.txt": ".."})
    assert "path_traversal" in codes(plan.items[0])


def test_invalid_and_reserved_names_are_errors(folder):
    make_files(folder, ["a.txt", "b.txt", "c.txt"])
    plan = map_plan(folder, {"a.txt": "x:y.txt", "b.txt": "CON.txt", "c.txt": "fim."})
    items = by_name(plan)
    assert "invalid_chars" in codes(items["a.txt"])
    assert "reserved_name" in codes(items["b.txt"])
    assert "trailing_dot_space" in codes(items["c.txt"])
    assert plan.has_errors


def test_empty_result_is_error(folder):
    make_files(folder, ["abc"])
    plan = plan_for(folder, [ReplaceRule(find="abc", replace="")])
    assert "empty_name" in codes(plan.items[0])


def test_rule_config_error_blocks_everything(folder):
    make_files(folder, ["a.txt", "b.txt"])
    plan = plan_for(folder, [ReplaceRule(find="(", regex=True)])
    assert all(i.status is Status.ERROR for i in plan.items)


def test_disabled_rules_do_not_validate(folder):
    make_files(folder, ["a.txt"])
    plan = plan_for(folder, [ReplaceRule(find="(", regex=True, enabled=False)])
    assert not plan.has_errors


def test_case_only_rename_on_case_insensitive_fs(folder):
    make_files(folder, ["foto.txt", "outro.txt"])
    plan = map_plan(folder, {"foto.txt": "FOTO.txt"}, case_insensitive=True)
    item = by_name(plan)["foto.txt"]
    assert item.status is Status.OK and "case_only" in codes(item)


def test_case_insensitive_duplicate_detection(folder):
    make_files(folder, ["a.txt", "B.txt"])
    plan = map_plan(folder, {"a.txt": "b.txt"}, case_insensitive=True)
    assert by_name(plan)["a.txt"].new_name == "b (2).txt"
    plan = map_plan(folder, {"a.txt": "b.txt"}, case_insensitive=False)
    item = by_name(plan)["a.txt"]
    assert item.new_name == "b.txt"
    assert "case_conflict_portable" in codes(item)


def test_hidden_and_ext_removed_warnings(folder):
    make_files(folder, ["a.txt"])
    item = map_plan(folder, {"a.txt": ".a"}).items[0]
    assert {"becomes_hidden", "ext_removed"} <= codes(item)
    assert item.status is Status.WARNING


def test_summary_counts(folder):
    make_files(folder, ["a.txt", "b.txt"])
    plan = map_plan(folder, {"a.txt": "c.txt"})
    s = plan.summary()
    assert s["ok"] == 1 and s["unchanged"] == 1 and s["total"] == 2


def test_subfolders_are_independent(folder):
    make_files(folder, ["x/1.txt", "y/1.txt"])
    plan = plan_for(folder, [PrefixSuffixRule(prefix="p")], ScanOptions(recursive=True))
    assert [i.new_name for i in plan.items] == ["p1.txt", "p1.txt"]
    assert not plan.has_errors

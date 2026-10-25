"""Construção e validação do plano de renomeação — nada é alterado no disco aqui."""

from __future__ import annotations

import os
from collections import defaultdict
from collections.abc import Callable, Sequence
from enum import Enum
from pathlib import Path

from .models import FileEntry, Level, Plan, PlanItem, Status, split_name
from .rules import Rule, RuleContext, RuleError, apply_rules
from .validation import MAX_WINDOWS_PATH, is_case_insensitive, normalize_key, validate_name


class ConflictPolicy(str, Enum):
    SKIP = "skip"  # não renomeia o item em conflito
    SUFFIX = "suffix"  # adiciona " (2)", " (3)"... até achar um nome livre


def build_plan(
    entries: Sequence[FileEntry],
    rules: Sequence[Rule],
    policy: ConflictPolicy = ConflictPolicy.SUFFIX,
    case_insensitive: bool | None = None,
    listdir: Callable[[Path], list[str]] | None = None,
) -> Plan:
    """Gera o plano "nome antigo -> nome novo" com todas as verificações de segurança.

    ``entries`` deve vir já ordenado (a ordem define contadores e prioridade em
    conflitos). ``case_insensitive=None`` detecta automaticamente por pasta.
    """
    policy = ConflictPolicy(policy)
    active = [r for r in rules if r.enabled]
    config_errors = [err for r in active for err in r.validate()]
    folder_counter: dict[Path, int] = defaultdict(int)
    items: list[PlanItem] = []
    total = len(entries)

    for index, entry in enumerate(entries):
        folder_index = folder_counter[entry.parent]
        folder_counter[entry.parent] += 1
        item = PlanItem(entry=entry, new_name=entry.name)
        items.append(item)
        if config_errors:
            for code, params in config_errors:
                item.add(code, Level.ERROR, **params)
            continue
        ctx = RuleContext(entry=entry, index=index, folder_index=folder_index, total=total)
        try:
            new_name = apply_rules(active, entry, ctx)
        except RuleError as exc:
            item.add(exc.code, Level.ERROR, **exc.params)
            continue
        item.new_name = new_name
        for code, params in ctx.warnings:
            item.add(code, Level.WARNING, **params)
        if new_name == entry.name:
            item.status = Status.UNCHANGED
            continue
        _validate_item(item)

    _resolve_conflicts(items, policy, case_insensitive, listdir or _safe_listdir)
    return Plan(items)


def _safe_listdir(folder: Path) -> list[str]:
    try:
        return os.listdir(folder)
    except OSError:
        return []


def _validate_item(item: PlanItem) -> None:
    entry, new_name = item.entry, item.new_name
    for code, level, params in validate_name(new_name):
        item.add(code, level, **params)
    if item.status is Status.ERROR:
        return
    # Defesa em profundidade contra "../": o destino tem que ficar na mesma pasta
    target = entry.parent / new_name
    if (
        os.path.normpath(target.parent) != os.path.normpath(entry.parent)
        or Path(new_name).name != new_name
    ):
        item.add("path_traversal", Level.ERROR)
        return
    if new_name.startswith(".") and not entry.name.startswith("."):
        item.add("becomes_hidden", Level.WARNING)
    if len(str(target)) >= MAX_WINDOWS_PATH:
        item.add("path_too_long", Level.WARNING, max=MAX_WINDOWS_PATH)
    if not entry.is_dir and entry.ext and not split_name(new_name)[1]:
        item.add("ext_removed", Level.WARNING)
    if normalize_key(new_name, True) == normalize_key(entry.name, True):
        item.add("case_only", Level.INFO)


def _suffixed(name: str, is_dir: bool, n: int) -> str:
    stem, ext = split_name(name, is_dir)
    return f"{stem} ({n}){ext}"


def _resolve_conflicts(
    items: list[PlanItem],
    policy: ConflictPolicy,
    case_insensitive: bool | None,
    listdir: Callable[[Path], list[str]],
) -> None:
    by_folder: dict[Path, list[PlanItem]] = defaultdict(list)
    for item in items:
        by_folder[item.entry.parent].append(item)

    for folder, group in by_folder.items():
        ci = is_case_insensitive(folder) if case_insensitive is None else case_insensitive

        def key(name: str, _ci: bool = ci) -> str:
            return normalize_key(name, _ci)

        existing = {key(n) for n in listdir(folder)} | {key(i.entry.name) for i in group}
        movers = [i for i in group if i.will_rename]
        proposed = {id(i): i.new_name for i in movers}

        # Repete até estabilizar: um item pulado continua ocupando o nome atual,
        # o que pode gerar novos conflitos para os demais.
        while True:
            stayers = existing - {key(i.entry.name) for i in movers}
            claimed: set[str] = set()
            dropped: list[tuple[PlanItem, str]] = []
            renames: dict[int, tuple[str, str]] = {}
            for item in movers:
                name = proposed[id(item)]
                k = key(name)
                reason = None
                if k in stayers:
                    reason = "conflict_existing"
                elif k in claimed:
                    reason = "conflict_duplicate"
                if reason:
                    if policy is ConflictPolicy.SKIP:
                        dropped.append((item, reason))
                        continue
                    n = 2
                    while True:
                        candidate = _suffixed(name, item.entry.is_dir, n)
                        ck = key(candidate)
                        if ck not in stayers and ck not in claimed:
                            break
                        n += 1
                    renames[id(item)] = (candidate, reason)
                    name, k = candidate, ck
                claimed.add(k)
            if not dropped:
                break
            for item, reason in dropped:
                item.add(reason, Level.WARNING, name=item.new_name)
                item.status = Status.SKIPPED
            dropped_ids = {id(i) for i, _ in dropped}
            movers = [i for i in movers if id(i) not in dropped_ids]

        for item in movers:
            if id(item) in renames:
                candidate, reason = renames[id(item)]
                item.add(reason, Level.WARNING, name=item.new_name)
                item.add("suffix_added", Level.WARNING, name=candidate)
                item.new_name = candidate
                for code, level, params in validate_name(candidate):
                    item.add(code, level, **params)

        # Aviso de portabilidade: nomes que só diferem em maiúsculas/minúsculas
        # funcionam aqui, mas colidem no Windows/macOS.
        if not ci:
            mover_sources = {i.entry.name for i in movers}
            taken: set[str] = {
                normalize_key(n, True) for n in listdir(folder) if n not in mover_sources
            }
            for item in movers:
                k = normalize_key(item.new_name, True)
                if k in taken:
                    item.add("case_conflict_portable", Level.WARNING)
                taken.add(k)

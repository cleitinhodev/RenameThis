"""Aplicação do plano em duas fases, com reversão automática em caso de falha."""

from __future__ import annotations

import os
import uuid
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from .fsops import file_id, safe_rename
from .journal import Journal
from .models import Plan

Progress = Callable[[int, int], None]
TMP_PREFIX = ".rt-tmp-"


class PreflightError(Exception):
    def __init__(self, code: str, path: Path) -> None:
        super().__init__(f"{code}: {path}")
        self.code = code
        self.path = path


@dataclass
class ApplyResult:
    renamed: list[tuple[Path, Path]] = field(default_factory=list)
    skipped: int = 0
    unchanged: int = 0
    error_code: str | None = None  # ex.: "target_exists", "source_missing", "os_error"
    error_path: str | None = None
    error_detail: str | None = None
    rolled_back: bool = False
    rollback_errors: list[str] = field(default_factory=list)
    journal_path: Path | None = None
    journal_id: str | None = None

    @property
    def ok(self) -> bool:
        return self.error_code is None


def plan_to_stages(plan: Plan) -> list[list[tuple[Path, Path]]]:
    """Agrupa por profundidade (mais profundo primeiro), para que renomear uma pasta
    não invalide o caminho dos itens dentro dela."""
    by_depth: dict[int, list[tuple[Path, Path]]] = defaultdict(list)
    for item in plan.to_rename:
        by_depth[len(item.source.parts)].append((item.source, item.target))
    return [by_depth[d] for d in sorted(by_depth, reverse=True)]


def _tmp_name(src: Path) -> Path:
    return src.parent / f"{TMP_PREFIX}{uuid.uuid4().hex[:16]}"


def _preflight(stage: list[tuple[Path, Path, Path]]) -> None:
    src_ids = set()
    for src, _tmp, _dst in stage:
        fid = file_id(src)
        if fid is None:
            raise PreflightError("source_missing", src)
        src_ids.add(fid)
    for _src, _tmp, dst in stage:
        if os.path.lexists(dst):
            # Só é permitido se o "destino" for um dos próprios arquivos que vão sair
            # (cadeias a->b, b->a ou troca de maiúsculas em sistemas que as ignoram)
            if file_id(dst) not in src_ids:
                raise PreflightError("target_exists", dst)


def execute_stages(
    stages: list[list[tuple[Path, Path, Path]]],
    progress: Progress | None = None,
    fail_hook: Callable[[int], None] | None = None,
) -> ApplyResult:
    """Executa (origem, temporário, destino) em duas fases por etapa.

    Fase 1: origem -> nome temporário único. Fase 2: temporário -> destino.
    Qualquer erro desfaz tudo o que foi feito, na ordem inversa.
    ``fail_hook`` existe só para testes (simular falhas).
    """
    result = ApplyResult()
    total = sum(len(s) for s in stages) * 2
    step = 0
    done: list[tuple[Path, Path]] = []
    try:
        for stage in stages:
            _preflight(stage)
            for src, tmp, _dst in stage:
                if fail_hook:
                    fail_hook(step)
                safe_rename(src, tmp)
                done.append((src, tmp))
                step += 1
                if progress:
                    progress(step, total)
            for src, tmp, dst in stage:
                if fail_hook:
                    fail_hook(step)
                safe_rename(tmp, dst)
                done.append((tmp, dst))
                result.renamed.append((src, dst))
                step += 1
                if progress:
                    progress(step, total)
    except PreflightError as exc:
        result.error_code, result.error_path = exc.code, str(exc.path)
    except FileExistsError as exc:
        result.error_code = "target_exists"
        result.error_path = str(exc.filename or "")
        result.error_detail = str(exc)
    except OSError as exc:
        result.error_code = "os_error"
        result.error_path = str(exc.filename or "")
        result.error_detail = exc.strerror or str(exc)
    except Exception as exc:  # falha inesperada: reverte do mesmo jeito
        result.error_code = "unexpected"
        result.error_detail = repr(exc)

    if result.error_code:
        result.renamed = []
        result.rolled_back = True
        for a, b in reversed(done):
            try:
                safe_rename(b, a)
            except OSError as exc:
                result.rollback_errors.append(f"{b} -> {a}: {exc}")
    return result


def execute_journaled(
    stages: list[list[tuple[Path, Path]]],
    journal: Journal | None,
    progress: Progress | None = None,
    kind: str = "rename",
    undoes: str | None = None,
    fail_hook: Callable[[int], None] | None = None,
) -> ApplyResult:
    prepared = [[(s, _tmp_name(s), d) for s, d in stage] for stage in stages if stage]
    entry = None
    if journal is not None:
        entry = journal.begin(
            [[{"src": str(s), "tmp": str(t), "dst": str(d)} for s, t, d in st] for st in prepared],
            kind=kind,
            undoes=undoes,
        )
    result = execute_stages(prepared, progress, fail_hook)
    if entry is not None and journal is not None:
        if result.ok:
            entry.status = "done"
        elif result.rollback_errors:
            entry.status = "rollback_failed"
            entry.errors = result.rollback_errors
        else:
            entry.status = "rolled_back"
        journal.update(entry)
        result.journal_path, result.journal_id = entry.path, entry.id
        if result.ok:
            journal.prune()
    return result


def apply_plan(
    plan: Plan,
    journal: Journal | None | bool = True,
    progress: Progress | None = None,
    fail_hook: Callable[[int], None] | None = None,
) -> ApplyResult:
    """Aplica o plano. Recusa planos com erros. ``journal=False`` desativa o histórico."""
    if plan.has_errors:
        return ApplyResult(error_code="plan_has_errors")
    if journal is True:
        journal = Journal()
    elif journal is False:
        journal = None
    stages = plan_to_stages(plan)
    result = execute_journaled(stages, journal, progress, fail_hook=fail_hook)
    from .models import Status

    result.skipped = plan.count(Status.SKIPPED)
    result.unchanged = plan.count(Status.UNCHANGED)
    return result

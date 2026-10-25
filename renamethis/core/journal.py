"""Histórico de operações (journal) para desfazer e recuperação após falhas."""

from __future__ import annotations

import json
import os
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from .. import APP_NAME

JOURNAL_VERSION = 1
MAX_ENTRIES = 200


def default_data_dir() -> Path:
    env = os.environ.get("RENAMETHIS_DATA_DIR")
    if env:
        return Path(env)
    try:
        from platformdirs import user_data_dir

        return Path(user_data_dir(APP_NAME, appauthor=False))
    except ImportError:  # pragma: no cover
        return Path.home() / ".renamethis"


@dataclass
class JournalEntry:
    id: str
    created: str
    kind: str  # "rename" | "undo"
    status: str  # pending | done | rolled_back | rollback_failed | recovered
    stages: list[list[dict[str, str]]]
    undone: bool = False
    undoes: str | None = None
    errors: list[str] = field(default_factory=list)
    path: Path | None = None

    @property
    def count(self) -> int:
        return sum(len(s) for s in self.stages)

    @property
    def folders(self) -> list[str]:
        seen: list[str] = []
        for stage in self.stages:
            for op in stage:
                parent = str(Path(op["src"]).parent)
                if parent not in seen:
                    seen.append(parent)
        return seen

    @property
    def created_dt(self) -> datetime:
        return datetime.fromisoformat(self.created)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": JOURNAL_VERSION,
            "id": self.id,
            "created": self.created,
            "kind": self.kind,
            "status": self.status,
            "undone": self.undone,
            "undoes": self.undoes,
            "errors": self.errors,
            "stages": self.stages,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any], path: Path | None = None) -> JournalEntry:
        return cls(
            id=data["id"],
            created=data["created"],
            kind=data.get("kind", "rename"),
            status=data.get("status", "pending"),
            stages=data.get("stages", []),
            undone=bool(data.get("undone", False)),
            undoes=data.get("undoes"),
            errors=list(data.get("errors", [])),
            path=path,
        )


class Journal:
    def __init__(self, directory: str | os.PathLike[str] | None = None) -> None:
        self.directory = Path(directory) if directory else default_data_dir() / "journal"

    def _write(self, entry: JournalEntry) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        if entry.path is None:
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            entry.path = self.directory / f"{stamp}-{entry.id}.json"
        tmp = entry.path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(entry.to_dict(), fh, ensure_ascii=False, indent=1)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, entry.path)  # escrita atômica

    def begin(
        self, stages: list[list[dict[str, str]]], kind: str = "rename", undoes: str | None = None
    ) -> JournalEntry:
        entry = JournalEntry(
            id=uuid.uuid4().hex[:12],
            created=datetime.now().isoformat(timespec="microseconds"),
            kind=kind,
            status="pending",
            stages=stages,
            undoes=undoes,
        )
        self._write(entry)
        return entry

    def update(self, entry: JournalEntry) -> None:
        self._write(entry)

    def entries(self) -> list[JournalEntry]:
        if not self.directory.is_dir():
            return []
        out = []
        for p in self.directory.glob("*.json"):
            try:
                with open(p, encoding="utf-8") as fh:
                    out.append(JournalEntry.from_dict(json.load(fh), p))
            except (OSError, ValueError, KeyError):
                continue
        out.sort(key=lambda e: (e.created, e.path.stat().st_mtime if e.path else 0), reverse=True)
        return out

    def last_undoable(self) -> JournalEntry | None:
        for entry in self.entries():
            if entry.kind == "rename" and entry.status == "done" and not entry.undone:
                return entry
        return None

    def incomplete(self) -> list[JournalEntry]:
        return [e for e in self.entries() if e.status in ("pending", "rollback_failed")]

    def prune(self, keep: int = MAX_ENTRIES) -> None:
        for entry in self.entries()[keep:]:
            if entry.path and entry.status not in ("pending", "rollback_failed"):
                try:
                    entry.path.unlink()
                except OSError:
                    pass


def undo_last(
    journal: Journal | None = None,
    progress: Callable[[int, int], None] | None = None,
):
    """Desfaz a última renomeação concluída. Retorna ``ApplyResult`` ou ``None``."""
    from .executor import execute_journaled

    journal = journal or Journal()
    entry = journal.last_undoable()
    if entry is None:
        return None
    # Ordem inversa: pastas mais rasas primeiro, trocando origem e destino
    reverse = [
        [(Path(op["dst"]), Path(op["src"])) for op in stage] for stage in reversed(entry.stages)
    ]
    result = execute_journaled(reverse, journal, progress, kind="undo", undoes=entry.id)
    if result.ok:
        entry.undone = True
        journal.update(entry)
    return result


def recover_incomplete(journal: Journal | None = None) -> tuple[int, list[str]]:
    """Restaura nomes originais de operações interrompidas (queda de energia, travamento).

    Retorna (itens restaurados, erros).
    """
    from .fsops import safe_rename

    journal = journal or Journal()
    restored, errors = 0, []
    for entry in journal.incomplete():
        entry_errors = []
        for stage in reversed(entry.stages):
            for op in stage:
                src, tmp, dst = Path(op["src"]), Path(op["tmp"]), Path(op["dst"])
                if os.path.lexists(src):
                    continue  # já está no lugar original
                for current in (tmp, dst):
                    if os.path.lexists(current):
                        try:
                            safe_rename(current, src)
                            restored += 1
                        except OSError as exc:
                            entry_errors.append(f"{current} -> {src}: {exc}")
                        break
                else:
                    entry_errors.append(f"{src}: not found")
        entry.status = "recovered" if not entry_errors else "rollback_failed"
        entry.errors.extend(entry_errors)
        journal.update(entry)
        errors.extend(entry_errors)
    return restored, errors

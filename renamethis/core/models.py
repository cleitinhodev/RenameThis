"""Estruturas de dados compartilhadas pelo núcleo."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class Level(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class Status(str, Enum):
    OK = "ok"  # será renomeado
    WARNING = "warning"  # será renomeado, mas há avisos
    UNCHANGED = "unchanged"  # nome não muda, nada a fazer
    SKIPPED = "skipped"  # ignorado por conflito (política "pular")
    ERROR = "error"  # nome inválido / erro de regra: bloqueia a aplicação


@dataclass(frozen=True)
class Issue:
    """Problema encontrado no planejamento. ``code`` é traduzido pela interface."""

    code: str
    level: Level
    params: dict[str, Any] = field(default_factory=dict)

    def __hash__(self) -> int:  # pragma: no cover - conveniência
        return hash((self.code, self.level, tuple(sorted(self.params.items()))))


@dataclass
class FileEntry:
    """Um arquivo ou pasta encontrado na varredura."""

    path: Path
    is_dir: bool
    size: int
    mtime: float
    ctime: float
    meta: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    @classmethod
    def from_path(cls, path: str | os.PathLike[str]) -> FileEntry:
        p = Path(path)
        st = p.stat()
        is_dir = p.is_dir()
        # st_birthtime existe no Windows (Python 3.12+) e no macOS; senão usa ctime
        ctime = getattr(st, "st_birthtime", None) or st.st_ctime
        return cls(
            path=p,
            is_dir=is_dir,
            size=0 if is_dir else st.st_size,
            mtime=st.st_mtime,
            ctime=ctime,
        )

    @property
    def name(self) -> str:
        return self.path.name

    @property
    def parent(self) -> Path:
        return self.path.parent

    @property
    def stem(self) -> str:
        return split_name(self.name, self.is_dir)[0]

    @property
    def ext(self) -> str:
        """Extensão com ponto (``.jpg``) ou ``""``."""
        return split_name(self.name, self.is_dir)[1]


def split_name(name: str, is_dir: bool = False) -> tuple[str, str]:
    """Separa ``nome.ext`` em (``nome``, ``.ext``).

    Pastas nunca têm extensão. Arquivos ocultos como ``.bashrc`` também não.
    """
    if is_dir:
        return name, ""
    idx = name.rfind(".")
    if idx <= 0 or idx == len(name) - 1:
        return name, ""
    return name[:idx], name[idx:]


@dataclass
class PlanItem:
    entry: FileEntry
    new_name: str
    status: Status = Status.OK
    issues: list[Issue] = field(default_factory=list)

    @property
    def source(self) -> Path:
        return self.entry.path

    @property
    def target(self) -> Path:
        return self.entry.parent / self.new_name

    @property
    def will_rename(self) -> bool:
        return self.status in (Status.OK, Status.WARNING)

    def add(self, code: str, level: Level, **params: Any) -> None:
        self.issues.append(Issue(code, level, params))
        if level is Level.ERROR:
            self.status = Status.ERROR
        elif level is Level.WARNING and self.status is Status.OK:
            self.status = Status.WARNING


@dataclass
class Plan:
    items: list[PlanItem] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return any(i.status is Status.ERROR for i in self.items)

    @property
    def to_rename(self) -> list[PlanItem]:
        return [i for i in self.items if i.will_rename]

    def count(self, status: Status) -> int:
        return sum(1 for i in self.items if i.status is status)

    def summary(self) -> dict[str, int]:
        return {s.value: self.count(s) for s in Status} | {"total": len(self.items)}

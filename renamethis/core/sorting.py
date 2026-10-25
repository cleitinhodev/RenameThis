"""Ordenação natural e por atributos."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from .models import FileEntry

_NUM = re.compile(r"(\d+)")


def natural_key(text: str) -> tuple:
    """Chave de ordenação natural: ``foto2`` vem antes de ``foto10``."""
    parts = _NUM.split(text.casefold())
    key: list[tuple[int, object]] = []
    for i, part in enumerate(parts):
        if i % 2:  # trecho numérico
            key.append((0, int(part)))
        elif part:
            key.append((1, part))
    return tuple(key)


class SortKey(str, Enum):
    NAME = "name"
    MODIFIED = "modified"
    CREATED = "created"
    SIZE = "size"
    TYPE = "type"
    NONE = "none"  # ordem da varredura (não recomendada)


@dataclass
class SortOptions:
    key: SortKey = SortKey.NAME
    descending: bool = False
    folders_first: bool = False

    def to_dict(self) -> dict:
        return {
            "key": self.key.value,
            "descending": self.descending,
            "folders_first": self.folders_first,
        }

    @classmethod
    def from_dict(cls, data: dict) -> SortOptions:
        return cls(
            key=SortKey(data.get("key", "name")),
            descending=bool(data.get("descending", False)),
            folders_first=bool(data.get("folders_first", False)),
        )


def sort_entries(entries: list[FileEntry], options: SortOptions | None = None) -> list[FileEntry]:
    """Retorna uma nova lista ordenada. Empates são desfeitos pelo nome natural,
    e depois pela pasta, garantindo um resultado sempre determinístico."""
    options = options or SortOptions()
    base = sorted(entries, key=lambda e: (natural_key(e.name), str(e.parent)))
    if options.key is SortKey.NONE:
        result = list(entries)
    elif options.key is SortKey.NAME:
        result = base
    else:
        getter = {
            SortKey.MODIFIED: lambda e: e.mtime,
            SortKey.CREATED: lambda e: e.ctime,
            SortKey.SIZE: lambda e: e.size,
            SortKey.TYPE: lambda e: natural_key(e.ext.lower()),
        }[options.key]
        result = sorted(base, key=getter)  # sort estável mantém o desempate por nome
    if options.descending:
        result.reverse()
    if options.folders_first:
        result.sort(key=lambda e: not e.is_dir)
    return result

"""Predefinições (regras + filtros + ordenação) salvas em JSON."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from .planner import ConflictPolicy
from .rules import Rule, rule_from_dict
from .scanner import ScanOptions
from .sorting import SortOptions

PRESET_VERSION = 1


@dataclass
class Preset:
    name: str = ""
    rules: list[Rule] = field(default_factory=list)
    scan: ScanOptions = field(default_factory=ScanOptions)
    sort: SortOptions = field(default_factory=SortOptions)
    conflict: ConflictPolicy = ConflictPolicy.SUFFIX

    def to_dict(self) -> dict:
        return {
            "app": "RenameThis",
            "version": PRESET_VERSION,
            "name": self.name,
            "rules": [r.to_dict() for r in self.rules],
            "scan": self.scan.to_dict(),
            "sort": self.sort.to_dict(),
            "conflict": ConflictPolicy(self.conflict).value,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Preset:
        if not isinstance(data, dict) or not isinstance(data.get("rules", []), list):
            raise ValueError("invalid preset")
        return cls(
            name=str(data.get("name", "")),
            rules=[rule_from_dict(r) for r in data.get("rules", [])],
            scan=ScanOptions.from_dict(data.get("scan", {})),
            sort=SortOptions.from_dict(data.get("sort", {})),
            conflict=ConflictPolicy(data.get("conflict", "suffix")),
        )


def save_preset(preset: Preset, path: str | os.PathLike[str]) -> None:
    path = Path(path)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(preset.to_dict(), fh, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def load_preset(path: str | os.PathLike[str]) -> Preset:
    with open(path, encoding="utf-8") as fh:
        return Preset.from_dict(json.load(fh))

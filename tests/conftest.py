from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

import pytest

from renamethis.core import Journal, ScanOptions, build_plan, scan, sort_entries
from renamethis.core.rules import Rule


@dataclass
class MapRule(Rule):
    """Regra de teste: mapeia nome completo antigo -> novo."""

    type: ClassVar[str] = "test_map"
    mapping: dict | None = None

    def transform(self, stem, ext, ctx):
        new = (self.mapping or {}).get(ctx.entry.name)
        if new is None:
            return stem, ext
        return new, ""


@pytest.fixture(autouse=True)
def _isolated_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("RENAMETHIS_DATA_DIR", str(tmp_path / "_data"))


@pytest.fixture
def journal(tmp_path) -> Journal:
    return Journal(tmp_path / "_journal")


@pytest.fixture
def folder(tmp_path) -> Path:
    d = tmp_path / "pasta"
    d.mkdir()
    return d


def make_files(folder: Path, names, content_from_name: bool = True) -> None:
    for n in names:
        p = folder / n
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(f"conteudo de {n}" if content_from_name else "", encoding="utf-8")


def snapshot(folder: Path) -> dict[str, str]:
    """{caminho relativo: conteúdo} de todos os arquivos (ignora pastas)."""
    return {
        str(p.relative_to(folder)).replace("\\", "/"): p.read_text(encoding="utf-8")
        for p in sorted(folder.rglob("*"))
        if p.is_file()
    }


def plan_for(folder: Path, rules, options: ScanOptions | None = None, sort=None, **kw):
    entries = sort_entries(scan(folder, options or ScanOptions()), sort)
    return build_plan(entries, rules, **kw)


def map_plan(folder: Path, mapping: dict, **kw):
    return plan_for(folder, [MapRule(mapping=mapping)], **kw)

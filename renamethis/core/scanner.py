"""Varredura de pastas com filtros."""

from __future__ import annotations

import os
import stat
import sys
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from .models import FileEntry

# Arquivos de sistema que nunca devem ser renomeados por padrão
SYSTEM_FILES = {
    "desktop.ini",
    "thumbs.db",
    "ehthumbs.db",
    ".ds_store",
    "icon\r",
    ".localized",
    "$recycle.bin",
    "system volume information",
}


class ScanError(Exception):
    """Pasta inválida ou inacessível."""

    def __init__(self, code: str, path: str = "") -> None:
        super().__init__(f"{code}: {path}")
        self.code = code
        self.path = path


def _norm_exts(exts: Iterable[str]) -> set[str]:
    out = set()
    for e in exts:
        e = e.strip().lower().lstrip("*").lstrip(".")
        if e:
            out.add("." + e)
    return out


def parse_ext_list(text: str) -> list[str]:
    """Converte ``"jpg, .png *.gif"`` em ``["jpg", "png", "gif"]``."""
    parts = text.replace(";", ",").replace(" ", ",").split(",")
    return [p.strip().lstrip("*").lstrip(".") for p in parts if p.strip().lstrip("*.")]


@dataclass
class ScanOptions:
    recursive: bool = False
    include_files: bool = True
    include_dirs: bool = False
    include_hidden: bool = False
    include_system: bool = False
    extensions: list[str] = field(default_factory=list)  # vazio = todas
    exclude_extensions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return dict(self.__dict__)

    @classmethod
    def from_dict(cls, data: dict) -> ScanOptions:
        known = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        return cls(**known)


def is_hidden(path: Path, st: os.stat_result | None = None) -> bool:
    if path.name.startswith("."):
        return True
    if sys.platform == "win32":
        try:
            st = st or path.stat()
            attrs = getattr(st, "st_file_attributes", 0)
            return bool(attrs & stat.FILE_ATTRIBUTE_HIDDEN)
        except OSError:
            return False
    if sys.platform == "darwin":
        try:
            st = st or path.stat()
            return bool(getattr(st, "st_flags", 0) & getattr(stat, "UF_HIDDEN", 0x8000))
        except OSError:
            return False
    return False


def is_system(path: Path, st: os.stat_result | None = None) -> bool:
    if path.name.lower() in SYSTEM_FILES:
        return True
    if sys.platform == "win32":
        try:
            st = st or path.stat()
            attrs = getattr(st, "st_file_attributes", 0)
            return bool(attrs & stat.FILE_ATTRIBUTE_SYSTEM)
        except OSError:
            return False
    return False


def scan(folder: str | os.PathLike[str], options: ScanOptions | None = None) -> list[FileEntry]:
    """Lista os itens da pasta aplicando os filtros. A ordem do retorno não é garantida;
    use :func:`renamethis.core.sorting.sort_entries`."""
    options = options or ScanOptions()
    if not folder or not str(folder).strip():
        raise ScanError("folder_empty")
    root = Path(folder).expanduser()
    if not root.exists():
        raise ScanError("folder_not_found", str(root))
    if not root.is_dir():
        raise ScanError("not_a_folder", str(root))
    try:
        root = root.resolve()
    except OSError as exc:  # pragma: no cover
        raise ScanError("folder_unreadable", str(root)) from exc

    include = _norm_exts(options.extensions)
    exclude = _norm_exts(options.exclude_extensions)
    entries: list[FileEntry] = []

    def walk(directory: Path, is_root: bool) -> None:
        try:
            with os.scandir(directory) as it:
                children = list(it)
        except OSError as exc:
            if is_root:
                raise ScanError("folder_unreadable", str(directory)) from exc
            return
        for de in children:
            p = Path(de.path)
            try:
                st = de.stat(follow_symlinks=False)
            except OSError:
                continue
            if not options.include_system and is_system(p, st):
                continue
            if not options.include_hidden and is_hidden(p, st):
                continue
            # Links simbólicos para pastas não são seguidos (evita loops)
            is_dir = de.is_dir(follow_symlinks=False)
            if is_dir:
                if options.recursive:
                    walk(p, False)
                if options.include_dirs:
                    entries.append(_entry(p, True, st))
                continue
            if not options.include_files:
                continue
            ext = os.path.splitext(de.name)[1].lower()
            if include and ext not in include:
                continue
            if exclude and ext in exclude:
                continue
            entries.append(_entry(p, False, st))

    walk(root, True)
    return entries


def _entry(p: Path, is_dir: bool, st: os.stat_result) -> FileEntry:
    ctime = getattr(st, "st_birthtime", None) or st.st_ctime
    return FileEntry(
        path=p,
        is_dir=is_dir,
        size=0 if is_dir else st.st_size,
        mtime=st.st_mtime,
        ctime=ctime,
    )

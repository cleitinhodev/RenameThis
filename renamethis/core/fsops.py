"""Operações de baixo nível: renomear SEM nunca sobrescrever."""

from __future__ import annotations

import ctypes
import errno
import os
import sys
from pathlib import Path

_AT_FDCWD = -100
_RENAME_NOREPLACE = 1  # Linux renameat2
_RENAME_EXCL = 0x4  # macOS renamex_np

_libc = None
_native = None
if sys.platform.startswith("linux") or sys.platform == "darwin":
    try:
        _libc = ctypes.CDLL(None, use_errno=True)
        if sys.platform == "darwin":
            _native = getattr(_libc, "renamex_np", None)
        else:
            _native = getattr(_libc, "renameat2", None)
    except OSError:  # pragma: no cover
        _native = None

_native_ok = _native is not None


def _native_rename(src: str, dst: str) -> bool:
    """Tenta a chamada nativa atômica "sem substituir". Retorna False se indisponível."""
    global _native_ok
    if not _native_ok:
        return False
    s, d = os.fsencode(src), os.fsencode(dst)
    if sys.platform == "darwin":
        res = _native(s, d, ctypes.c_uint(_RENAME_EXCL))
    else:
        res = _native(_AT_FDCWD, s, _AT_FDCWD, d, ctypes.c_uint(_RENAME_NOREPLACE))
    if res == 0:
        return True
    err = ctypes.get_errno()
    if err in (errno.ENOSYS, errno.EINVAL, errno.ENOTSUP, getattr(errno, "EOPNOTSUPP", -1)):
        # Sistema de arquivos não suporta (ex.: alguns FUSE/rede): usa o método portátil
        return False
    raise OSError(err, os.strerror(err), src, None, dst)


def safe_rename(src: str | os.PathLike[str], dst: str | os.PathLike[str]) -> None:
    """Renomeia ``src`` para ``dst`` e levanta ``FileExistsError`` se ``dst`` existir.

    No Windows ``os.rename`` já recusa sobrescrever. No Linux/macOS usamos
    ``renameat2(RENAME_NOREPLACE)`` / ``renamex_np(RENAME_EXCL)``, que são atômicos;
    se não houver suporte, verificamos a existência antes de renomear.
    """
    src, dst = os.fspath(src), os.fspath(dst)
    if os.path.dirname(os.path.abspath(src)) != os.path.dirname(os.path.abspath(dst)):
        raise ValueError("safe_rename só renomeia dentro da mesma pasta")
    if os.path.lexists(dst):
        raise FileExistsError(errno.EEXIST, "destino já existe", dst)
    if _native_rename(src, dst):
        return
    if os.path.lexists(dst):  # pragma: no cover - corrida improvável
        raise FileExistsError(errno.EEXIST, "destino já existe", dst)
    os.rename(src, dst)


def file_id(path: str | os.PathLike[str]) -> tuple[int, int] | None:
    try:
        st = os.lstat(path)
    except OSError:
        return None
    return st.st_dev, st.st_ino


def exists(path: Path) -> bool:
    return os.path.lexists(path)

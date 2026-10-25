"""Validação de nomes de arquivo — regras do Windows aplicadas em todos os sistemas.

Aplicar as regras mais restritas (Windows) em qualquer sistema garante que os
arquivos renomeados continuem válidos se forem copiados para outro computador,
pendrive ou serviço de nuvem.
"""

from __future__ import annotations

import os
import re
import unicodedata

from .models import Level

INVALID_CHARS = set('<>:"/\\|?*')
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
    "COM¹", "COM²", "COM³", "LPT¹", "LPT²", "LPT³",
}  # fmt: skip
MAX_NAME_BYTES = 255
MAX_WINDOWS_PATH = 260


def validate_name(name: str) -> list[tuple[str, Level, dict]]:
    """Retorna a lista de problemas (código, nível, parâmetros) do nome."""
    issues: list[tuple[str, Level, dict]] = []
    if not name or not name.strip():
        return [("empty_name", Level.ERROR, {})]
    if name in (".", ".."):
        return [("path_traversal", Level.ERROR, {})]
    if "/" in name or "\\" in name or (os.sep in name) or (os.altsep and os.altsep in name):
        issues.append(("path_separator", Level.ERROR, {}))
    bad = sorted({c for c in name if c in INVALID_CHARS and c not in "/\\"})
    if bad:
        issues.append(("invalid_chars", Level.ERROR, {"chars": " ".join(bad)}))
    if _CONTROL.search(name):
        issues.append(("control_chars", Level.ERROR, {}))
    base = name.split(".")[0].strip().upper()
    if base in RESERVED_NAMES:
        issues.append(("reserved_name", Level.ERROR, {"name": base}))
    if name[-1] in ". ":
        issues.append(("trailing_dot_space", Level.ERROR, {}))
    if name[0] == " ":
        issues.append(("leading_space", Level.WARNING, {}))
    if len(name.encode("utf-8")) > MAX_NAME_BYTES:
        issues.append(("name_too_long", Level.ERROR, {"max": MAX_NAME_BYTES}))
    return issues


def normalize_key(name: str, case_insensitive: bool) -> str:
    """Chave usada para detectar nomes iguais no mesmo diretório."""
    key = unicodedata.normalize("NFC", name)
    return key.casefold() if case_insensitive else key


_case_cache: dict[str, bool] = {}


def is_case_insensitive(folder: str | os.PathLike[str]) -> bool:
    """Descobre (sem escrever no disco) se o sistema de arquivos ignora maiúsculas."""
    folder = os.fspath(folder)
    if folder in _case_cache:
        return _case_cache[folder]
    result: bool | None = None
    try:
        for name in os.listdir(folder):
            swapped = name.swapcase()
            if swapped == name:
                continue
            if swapped in os.listdir(folder):
                # existem os dois: com certeza é sensível
                result = False
                break
            result = os.path.exists(os.path.join(folder, swapped))
            break
    except OSError:
        pass
    if result is None:
        import sys

        result = sys.platform in ("win32", "darwin")
    _case_cache[folder] = result
    return result

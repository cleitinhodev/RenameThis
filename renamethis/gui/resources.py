"""Localização de arquivos de recurso que funciona no código-fonte e no PyInstaller."""

from __future__ import annotations

import sys
from pathlib import Path


def resource_path(relative: str) -> Path | None:
    """Procura ``relative`` (ex.: ``Design/icone.ico``) nos locais possíveis.

    - executável do PyInstaller: ``sys._MEIPASS`` (pasta temporária do pacote)
    - ao lado do executável (PyInstaller --onedir)
    - raiz do repositório (execução a partir do código / ``pip install -e .``)
    Retorna ``None`` se não encontrar, para o app nunca deixar de abrir por isso.
    """
    candidates: list[Path] = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass))
    if getattr(sys, "frozen", False):
        candidates.append(Path(sys.executable).resolve().parent)
    here = Path(__file__).resolve()
    candidates += [here.parents[2], here.parents[1]]
    for base in candidates:
        path = base / relative
        if path.exists():
            return path
    return None

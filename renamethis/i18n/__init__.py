"""Traduções (pt_BR padrão + en).

Os textos ficam em arquivos JSON (``pt_BR.json``, ``en.json``) para facilitar
novas traduções: basta copiar um arquivo, traduzir e registrar em ``LANGUAGES``.
"""

from __future__ import annotations

import json
import locale
import os
from functools import cache
from importlib import resources
from typing import Any

DEFAULT_LANGUAGE = "pt_BR"
FALLBACK_LANGUAGE = "en"
LANGUAGES = {"pt_BR": "Português (Brasil)", "en": "English"}

_current = DEFAULT_LANGUAGE


@cache
def _load(lang: str) -> dict[str, str]:
    try:
        text = resources.files(__package__).joinpath(f"{lang}.json").read_text(encoding="utf-8")
    except (FileNotFoundError, OSError):
        return {}
    return json.loads(text)


def normalize_language(lang: str | None) -> str:
    if not lang:
        return DEFAULT_LANGUAGE
    lang = lang.replace("-", "_")
    if lang in LANGUAGES:
        return lang
    low = lang.lower()
    if low.startswith("pt"):
        return "pt_BR"
    if low.startswith("en"):
        return "en"
    return FALLBACK_LANGUAGE


def detect_language() -> str:
    env = os.environ.get("RENAMETHIS_LANG")
    if env:
        return normalize_language(env)
    try:
        loc = locale.getlocale()[0] or os.environ.get("LANG", "")
    except (ValueError, TypeError):  # pragma: no cover
        loc = ""
    if not loc:
        return DEFAULT_LANGUAGE
    return normalize_language(loc)


def set_language(lang: str) -> str:
    global _current
    _current = normalize_language(lang)
    return _current


def get_language() -> str:
    return _current


class _SafeDict(dict):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def tr(key: str, **params: Any) -> str:
    """Traduz ``key`` no idioma atual (cai para inglês e, por fim, para a própria chave)."""
    text = _load(_current).get(key)
    if text is None:
        text = _load(FALLBACK_LANGUAGE).get(key, key)
    if params:
        try:
            return text.format_map(_SafeDict(params))
        except (ValueError, IndexError):
            return text
    return text


def issue_text(issue: Any) -> str:
    return tr(f"issue.{issue.code}", **issue.params)


def error_text(code: str, **params: Any) -> str:
    return tr(f"err.{code}", **params)


def keys(lang: str) -> set[str]:
    return set(_load(lang))

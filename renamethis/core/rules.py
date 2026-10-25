"""Regras de renomeação combináveis.

Cada regra recebe o nome atual dividido em (nome, extensão) e devolve a versão
transformada. As regras são aplicadas em sequência, na ordem definida pelo
usuário. Todas são serializáveis para JSON (predefinições).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field, fields
from datetime import datetime
from typing import Any, ClassVar

from . import metadata
from .models import FileEntry, split_name
from .validation import INVALID_CHARS


class RuleError(Exception):
    """Erro ao aplicar uma regra a um arquivo (vira um erro na prévia)."""

    def __init__(self, code: str, **params: Any) -> None:
        super().__init__(code)
        self.code = code
        self.params = params


@dataclass
class RuleContext:
    entry: FileEntry
    index: int  # posição na lista ordenada (0 = primeiro)
    folder_index: int  # posição dentro da mesma pasta
    total: int
    warnings: list[tuple[str, dict]] = field(default_factory=list)

    def warn(self, code: str, **params: Any) -> None:
        if (code, params) not in self.warnings:
            self.warnings.append((code, params))


@dataclass(frozen=True)
class FieldSpec:
    """Descrição de um campo editável (a interface gera o formulário a partir disto)."""

    name: str
    kind: str  # text | int | bool | choice
    choices: tuple[str, ...] = ()
    minimum: int = -999999
    maximum: int = 999999


POSITIONS = ("prefix", "suffix", "replace")
SCOPES = ("name", "ext", "full")


def _place(stem: str, piece: str, position: str, sep: str) -> str:
    if position == "replace" or not stem:
        return piece
    if position == "prefix":
        return f"{piece}{sep}{stem}"
    return f"{stem}{sep}{piece}"


def index_to_letters(index: int) -> str:
    """0 -> A, 25 -> Z, 26 -> AA, 701 -> ZZ, 702 -> AAA (estilo colunas do Excel)."""
    if index < 0:
        raise ValueError("index must be >= 0")
    out = ""
    n = index + 1
    while n:
        n, rem = divmod(n - 1, 26)
        out = chr(65 + rem) + out
    return out


def strip_accents(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return unicodedata.normalize(
        "NFC", "".join(c for c in decomposed if not unicodedata.combining(c))
    )


def get_date(entry: FileEntry, source: str, ctx: RuleContext | None) -> datetime:
    if source == "created":
        return datetime.fromtimestamp(entry.ctime)
    if source == "exif":
        dt = metadata.exif_datetime(entry)
        if dt is not None:
            return dt
        if ctx is not None and entry.ext.lower() in metadata.IMAGE_EXTS:
            if not metadata.has_pillow():
                ctx.warn("pillow_missing")
            else:
                ctx.warn("exif_missing")
    return datetime.fromtimestamp(entry.mtime)


def _format_date(dt: datetime, fmt: str) -> str:
    try:
        return dt.strftime(fmt or "%Y-%m-%d")
    except ValueError as exc:
        raise RuleError("bad_date_format", format=fmt) from exc


@dataclass
class Rule:
    """Classe base. Subclasses definem ``type``, ``FIELDS`` e ``transform``."""

    type: ClassVar[str] = ""
    FIELDS: ClassVar[tuple[FieldSpec, ...]] = ()
    enabled: bool = True

    def transform(self, stem: str, ext: str, ctx: RuleContext) -> tuple[str, str]:
        raise NotImplementedError

    def apply(self, stem: str, ext: str, ctx: RuleContext) -> tuple[str, str]:
        if not self.enabled:
            return stem, ext
        return self.transform(stem, ext, ctx)

    def validate(self) -> list[tuple[str, dict]]:
        """Erros de configuração (ex.: regex inválida). Vazio = ok."""
        return []

    def to_dict(self) -> dict[str, Any]:
        data = {"type": self.type}
        for f in fields(self):
            data[f.name] = getattr(self, f.name)
        return data

    def summary(self) -> dict[str, Any]:
        """Parâmetros resumidos para exibir na lista de regras."""
        return {f.name: getattr(self, f.name) for f in fields(self) if f.name != "enabled"}


# --------------------------------------------------------------------------- regras


@dataclass
class PrefixSuffixRule(Rule):
    type: ClassVar[str] = "prefix_suffix"
    FIELDS: ClassVar = (FieldSpec("prefix", "text"), FieldSpec("suffix", "text"))
    prefix: str = ""
    suffix: str = ""

    def transform(self, stem, ext, ctx):
        return f"{self.prefix}{stem}{self.suffix}", ext


@dataclass
class ReplaceRule(Rule):
    type: ClassVar[str] = "replace"
    FIELDS: ClassVar = (
        FieldSpec("find", "text"),
        FieldSpec("replace", "text"),
        FieldSpec("regex", "bool"),
        FieldSpec("case_sensitive", "bool"),
        FieldSpec("scope", "choice", SCOPES),
    )
    find: str = ""
    replace: str = ""
    regex: bool = False
    case_sensitive: bool = False
    scope: str = "name"

    def _pattern(self) -> re.Pattern[str]:
        flags = 0 if self.case_sensitive else re.IGNORECASE
        src = self.find if self.regex else re.escape(self.find)
        return re.compile(src, flags)

    def validate(self):
        if not self.find:
            return []
        try:
            self._pattern()
        except re.error as exc:
            return [("bad_regex", {"error": str(exc)})]
        return []

    def transform(self, stem, ext, ctx):
        if not self.find:
            return stem, ext
        try:
            pat = self._pattern()
        except re.error as exc:
            raise RuleError("bad_regex", error=str(exc)) from exc
        repl = self.replace if self.regex else self.replace.replace("\\", "\\\\")

        def sub(text: str) -> str:
            try:
                return pat.sub(repl, text)
            except (re.error, IndexError) as exc:
                raise RuleError("bad_regex", error=str(exc)) from exc

        if self.scope == "ext":
            return stem, sub(ext)
        if self.scope == "full":
            return split_name(sub(stem + ext), ctx.entry.is_dir)
        return sub(stem), ext


@dataclass
class RemoveRule(Rule):
    type: ClassVar[str] = "remove"
    MODES: ClassVar = ("chars", "range", "first", "last", "digits", "brackets")
    FIELDS: ClassVar = (
        FieldSpec("mode", "choice", MODES),
        FieldSpec("chars", "text"),
        FieldSpec("start", "int", minimum=1),
        FieldSpec("count", "int", minimum=0),
    )
    mode: str = "chars"
    chars: str = ""
    start: int = 1  # 1 = primeiro caractere
    count: int = 1

    def transform(self, stem, ext, ctx):
        if self.mode == "chars":
            return "".join(c for c in stem if c not in self.chars), ext
        if self.mode == "range":
            i = max(self.start, 1) - 1
            return stem[:i] + stem[i + max(self.count, 0) :], ext
        if self.mode == "first":
            return stem[max(self.count, 0) :], ext
        if self.mode == "last":
            n = max(self.count, 0)
            return (stem[:-n] if n else stem), ext
        if self.mode == "digits":
            return re.sub(r"\d", "", stem), ext
        if self.mode == "brackets":
            out = re.sub(r"\s*(\([^)]*\)|\[[^\]]*\]|\{[^}]*\})", "", stem)
            return out.strip(), ext
        return stem, ext


@dataclass
class InsertRule(Rule):
    type: ClassVar[str] = "insert"
    FIELDS: ClassVar = (
        FieldSpec("text", "text"),
        FieldSpec("position", "int", minimum=0),
        FieldSpec("from_end", "bool"),
    )
    text: str = ""
    position: int = 0  # quantidade de caracteres antes do texto inserido
    from_end: bool = False

    def transform(self, stem, ext, ctx):
        pos = min(max(self.position, 0), len(stem))
        if self.from_end:
            pos = len(stem) - pos
        return stem[:pos] + self.text + stem[pos:], ext


@dataclass
class CounterRule(Rule):
    type: ClassVar[str] = "counter"
    FIELDS: ClassVar = (
        FieldSpec("start", "int"),
        FieldSpec("step", "int", minimum=1),
        FieldSpec("padding", "int", minimum=0, maximum=12),
        FieldSpec("position", "choice", POSITIONS),
        FieldSpec("separator", "text"),
        FieldSpec("reset_per_folder", "bool"),
    )
    start: int = 1
    step: int = 1
    padding: int = 0
    position: str = "suffix"
    separator: str = "_"
    reset_per_folder: bool = False

    def value(self, ctx: RuleContext) -> int:
        idx = ctx.folder_index if self.reset_per_folder else ctx.index
        return self.start + idx * self.step

    def transform(self, stem, ext, ctx):
        n = self.value(ctx)
        text = f"{n:0{self.padding}d}" if self.padding else str(n)
        return _place(stem, text, self.position, self.separator), ext


@dataclass
class LettersRule(Rule):
    type: ClassVar[str] = "letters"
    FIELDS: ClassVar = (
        FieldSpec("start", "int", minimum=1),
        FieldSpec("uppercase", "bool"),
        FieldSpec("position", "choice", POSITIONS),
        FieldSpec("separator", "text"),
        FieldSpec("reset_per_folder", "bool"),
    )
    start: int = 1  # 1 = A
    uppercase: bool = True
    position: str = "suffix"
    separator: str = "_"
    reset_per_folder: bool = False

    def transform(self, stem, ext, ctx):
        idx = ctx.folder_index if self.reset_per_folder else ctx.index
        text = index_to_letters(max(self.start, 1) - 1 + idx)
        if not self.uppercase:
            text = text.lower()
        return _place(stem, text, self.position, self.separator), ext


@dataclass
class DateRule(Rule):
    type: ClassVar[str] = "date"
    SOURCES: ClassVar = ("modified", "created", "exif")
    FIELDS: ClassVar = (
        FieldSpec("source", "choice", SOURCES),
        FieldSpec("format", "text"),
        FieldSpec("position", "choice", POSITIONS),
        FieldSpec("separator", "text"),
    )
    source: str = "modified"
    format: str = "%Y-%m-%d"
    position: str = "prefix"
    separator: str = "_"

    def validate(self):
        if not self.format.strip():
            return [("bad_date_format", {"format": self.format})]
        try:
            datetime(2024, 1, 2, 3, 4, 5).strftime(self.format)
        except ValueError:
            return [("bad_date_format", {"format": self.format})]
        return []

    def transform(self, stem, ext, ctx):
        dt = get_date(ctx.entry, self.source, ctx)
        return _place(stem, _format_date(dt, self.format), self.position, self.separator), ext


def _title(text: str) -> str:
    out, cap = [], True
    for ch in text.lower():
        out.append(ch.upper() if cap and ch.isalpha() else ch)
        if ch.isalpha() or ch.isdigit() or ch in "'’":
            cap = False
        else:
            cap = ch in " _-.()[]"
    return "".join(out)


def _sentence(text: str) -> str:
    low = text.lower()
    for i, ch in enumerate(low):
        if ch.isalpha():
            return low[:i] + ch.upper() + low[i + 1 :]
    return low


@dataclass
class CaseRule(Rule):
    type: ClassVar[str] = "case"
    MODES: ClassVar = ("lower", "upper", "title", "sentence", "invert")
    FIELDS: ClassVar = (FieldSpec("mode", "choice", MODES), FieldSpec("include_ext", "bool"))
    mode: str = "lower"
    include_ext: bool = False

    def _do(self, text: str) -> str:
        return {
            "lower": str.lower,
            "upper": str.upper,
            "title": _title,
            "sentence": _sentence,
            "invert": str.swapcase,
        }.get(self.mode, str)(text)

    def transform(self, stem, ext, ctx):
        return self._do(stem), (self._do(ext) if self.include_ext else ext)


@dataclass
class CleanupRule(Rule):
    type: ClassVar[str] = "cleanup"
    SPACES: ClassVar = ("keep", "underscore", "dash", "dot", "remove")
    FIELDS: ClassVar = (
        FieldSpec("spaces", "choice", SPACES),
        FieldSpec("separators_to_spaces", "bool"),
        FieldSpec("strip_accents", "bool"),
        FieldSpec("remove_invalid", "bool"),
        FieldSpec("collapse", "bool"),
        FieldSpec("trim", "bool"),
    )
    spaces: str = "keep"
    separators_to_spaces: bool = False
    strip_accents: bool = False
    remove_invalid: bool = True
    collapse: bool = True
    trim: bool = True

    def transform(self, stem, ext, ctx):
        s = stem
        if self.remove_invalid:
            s = "".join(c for c in s if c not in INVALID_CHARS and ord(c) >= 32)
        if self.strip_accents:
            s = strip_accents(s)
        if self.separators_to_spaces:
            s = re.sub(r"[_.\-]+", " ", s)
        rep = {"underscore": "_", "dash": "-", "dot": ".", "remove": ""}.get(self.spaces)
        if rep is not None:
            s = re.sub(r"\s", rep, s)
        if self.collapse:
            s = re.sub(r"\s{2,}", " ", s)
            s = re.sub(r"([_.\-])\1+", r"\1", s)
        if self.trim:
            s = s.strip(" _-.")
        return s, ext


@dataclass
class ExtensionRule(Rule):
    type: ClassVar[str] = "extension"
    MODES: ClassVar = ("keep", "lower", "upper", "change", "remove")
    FIELDS: ClassVar = (FieldSpec("mode", "choice", MODES), FieldSpec("new_ext", "text"))
    mode: str = "lower"
    new_ext: str = ""

    def transform(self, stem, ext, ctx):
        if ctx.entry.is_dir:
            return stem, ext
        if self.mode == "lower":
            return stem, ext.lower()
        if self.mode == "upper":
            return stem, ext.upper()
        if self.mode == "change":
            new = self.new_ext.strip().lstrip(".")
            new_ext = ("." + new) if new else ""
            if ext.lower() != new_ext.lower():
                ctx.warn("ext_changed")
            return stem, new_ext
        if self.mode == "remove":
            if ext:
                ctx.warn("ext_changed")
            return stem, ""
        return stem, ext


# ------------------------------------------------------------------ modelos (templates)

_TOKEN = re.compile(r"\{([a-zA-Z_]+)(?::([^{}]*))?\}")
DATE_TOKENS = {"date", "modified", "created", "exif", "now"}
MUSIC_TOKENS = {"artist", "title", "album", "track", "year", "genre"}
SIMPLE_TOKENS = {"name", "current", "ext", "parent", "size", "n", "letter", "letters"}
ALL_TOKENS = DATE_TOKENS | MUSIC_TOKENS | SIMPLE_TOKENS


def _check_template(template: str) -> list[tuple[str, dict]]:
    if not template.strip():
        return [("template_empty", {})]
    stripped = _TOKEN.sub("", template)
    if "{" in stripped or "}" in stripped:
        return [("template_braces", {})]
    errors = []
    for m in _TOKEN.finditer(template):
        token = m.group(1).lower()
        if token not in ALL_TOKENS:
            errors.append(("template_unknown_token", {"token": m.group(1)}))
        elif token in DATE_TOKENS and m.group(2):
            try:
                datetime(2024, 1, 2).strftime(m.group(2))
            except ValueError:
                errors.append(("bad_date_format", {"format": m.group(2)}))
    return errors


def _fmt_number(n: int, spec: str | None) -> str:
    if not spec:
        return str(n)
    if spec.isdigit():
        return f"{n:0{int(spec)}d}"
    try:
        return format(n, spec)
    except ValueError as exc:
        raise RuleError("bad_number_format", format=spec) from exc


@dataclass
class TemplateRule(Rule):
    """Monta o nome a partir de um modelo, ex.: ``Viagem_{n:03}_{exif:%Y-%m-%d}``."""

    type: ClassVar[str] = "template"
    FIELDS: ClassVar = (
        FieldSpec("template", "text"),
        FieldSpec("start", "int"),
        FieldSpec("step", "int", minimum=1),
        FieldSpec("reset_per_folder", "bool"),
    )
    template: str = "{name}"
    start: int = 1
    step: int = 1
    reset_per_folder: bool = False

    def validate(self):
        return _check_template(self.template)

    def transform(self, stem, ext, ctx):
        errs = _check_template(self.template)
        if errs:
            code, params = errs[0]
            raise RuleError(code, **params)
        entry = ctx.entry
        idx = ctx.folder_index if self.reset_per_folder else ctx.index
        tags: dict[str, str] | None = None

        def music(key: str) -> str:
            nonlocal tags
            if tags is None:
                tags = metadata.music_tags(entry) or {}
                if not tags:
                    ctx.warn("mutagen_missing" if not metadata.has_mutagen() else "tags_missing")
            value = tags.get(key, "")
            if not value and tags:
                ctx.warn("tag_missing", tag=key)
            return value

        def repl(m: re.Match[str]) -> str:
            token, spec = m.group(1).lower(), m.group(2)
            if token == "name":
                return entry.stem
            if token == "current":
                return stem
            if token == "ext":
                return entry.ext.lstrip(".")
            if token == "parent":
                return entry.parent.name
            if token == "size":
                return str(entry.size)
            if token == "n":
                return _fmt_number(self.start + idx * self.step, spec)
            if token in ("letter", "letters"):
                letters = index_to_letters(idx)
                return letters.lower() if spec == "lower" else letters
            if token in DATE_TOKENS:
                if token == "now":
                    dt = datetime.now()
                else:
                    src = {"date": "modified"}.get(token, token)
                    dt = get_date(entry, src, ctx)
                return _format_date(dt, spec or "%Y-%m-%d")
            if token in MUSIC_TOKENS:
                value = music(token)
                if token == "track" and value:
                    try:
                        return _fmt_number(int(value), spec)
                    except ValueError:
                        return value
                return value
            raise RuleError("template_unknown_token", token=token)  # pragma: no cover

        return _TOKEN.sub(repl, self.template), ext


@dataclass
class MusicRule(TemplateRule):
    """Renomeia músicas pelas tags (artista, título, faixa...)."""

    type: ClassVar[str] = "music"
    FIELDS: ClassVar = (FieldSpec("template", "text"),)
    template: str = "{track:02} - {artist} - {title}"


RULE_TYPES: dict[str, type[Rule]] = {
    cls.type: cls
    for cls in (
        PrefixSuffixRule,
        ReplaceRule,
        RemoveRule,
        InsertRule,
        CounterRule,
        LettersRule,
        DateRule,
        CaseRule,
        CleanupRule,
        ExtensionRule,
        TemplateRule,
        MusicRule,
    )
}


def rule_from_dict(data: dict[str, Any]) -> Rule:
    kind = data.get("type")
    cls = RULE_TYPES.get(str(kind))
    if cls is None:
        raise ValueError(f"unknown rule type: {kind!r}")
    allowed = {f.name: f for f in fields(cls)}
    kwargs: dict[str, Any] = {}
    for key, value in data.items():
        if key not in allowed:
            continue
        default = getattr(cls(), key)
        # Coerção de tipos defensiva (arquivos de predefinição editados à mão)
        if isinstance(default, bool):
            value = bool(value)
        elif isinstance(default, int):
            value = int(value)
        elif isinstance(default, str):
            value = str(value)
        kwargs[key] = value
    return cls(**kwargs)


def apply_rules(rules: list[Rule], entry: FileEntry, ctx: RuleContext) -> str:
    stem, ext = entry.stem, entry.ext
    for rule in rules:
        stem, ext = rule.apply(stem, ext, ctx)
    return stem + ext

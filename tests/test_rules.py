import os
from datetime import datetime
from pathlib import Path

import pytest

from renamethis.core import metadata
from renamethis.core.models import FileEntry
from renamethis.core.rules import (
    RULE_TYPES,
    CaseRule,
    CleanupRule,
    CounterRule,
    DateRule,
    ExtensionRule,
    InsertRule,
    LettersRule,
    MusicRule,
    PrefixSuffixRule,
    RemoveRule,
    ReplaceRule,
    RuleContext,
    RuleError,
    TemplateRule,
    apply_rules,
    index_to_letters,
    rule_from_dict,
    strip_accents,
)

MTIME = datetime(2023, 7, 14, 10, 30, 0).timestamp()


def entry(name="Foto Viagem.JPG", parent="/fotos/Ferias", is_dir=False, size=1234):
    return FileEntry(Path(parent) / name, is_dir, size, MTIME, MTIME)


def run(rules, name="Foto Viagem.JPG", index=0, folder_index=None, **kw):
    e = entry(name, **kw)
    ctx = RuleContext(e, index, index if folder_index is None else folder_index, 10)
    return apply_rules(rules if isinstance(rules, list) else [rules], e, ctx)


def run_ctx(rule, name="Foto Viagem.JPG", index=0):
    e = entry(name)
    ctx = RuleContext(e, index, index, 10)
    return apply_rules([rule], e, ctx), ctx


def test_prefix_suffix():
    assert run(PrefixSuffixRule(prefix="2024_", suffix="-final")) == "2024_Foto Viagem-final.JPG"


def test_disabled_rule_is_ignored():
    assert run(PrefixSuffixRule(prefix="X", enabled=False)) == "Foto Viagem.JPG"


def test_replace_plain_case_insensitive():
    assert run(ReplaceRule(find="viagem", replace="Trip")) == "Foto Trip.JPG"
    assert run(ReplaceRule(find="viagem", replace="Trip", case_sensitive=True)) == "Foto Viagem.JPG"


def test_replace_plain_treats_special_chars_literally():
    assert run(ReplaceRule(find=".", replace="_"), name="a.b.c.txt") == "a_b_c.txt"
    assert run(ReplaceRule(find="a", replace=r"\1"), name="a.txt") == r"\1.txt"


def test_replace_regex_groups():
    rule = ReplaceRule(find=r"IMG_(\d{4})(\d{2})(\d{2})", replace=r"\1-\2-\3", regex=True)
    assert run(rule, name="IMG_20240131.jpg") == "2024-01-31.jpg"


def test_replace_scopes():
    assert run(ReplaceRule(find="jpeg", replace="jpg", scope="ext"), name="a.jpeg") == "a.jpg"
    assert (
        run(ReplaceRule(find=".tar.gz", replace=".tgz", scope="full"), name="x.tar.gz") == "x.tgz"
    )


def test_replace_bad_regex():
    rule = ReplaceRule(find="(", regex=True)
    assert rule.validate()[0][0] == "bad_regex"
    with pytest.raises(RuleError):
        run(rule)


def test_replace_bad_group_reference():
    with pytest.raises(RuleError):
        run(ReplaceRule(find="a", replace=r"\5", regex=True), name="a.txt")


def test_remove_modes():
    assert run(RemoveRule(mode="chars", chars="aeiou"), name="banana.txt") == "bnn.txt"
    assert run(RemoveRule(mode="range", start=2, count=3), name="abcdef.txt") == "aef.txt"
    assert run(RemoveRule(mode="first", count=4), name="IMG_001.jpg") == "001.jpg"
    assert run(RemoveRule(mode="last", count=3), name="nome_old.txt") == "nome_.txt"
    assert run(RemoveRule(mode="last", count=0), name="nome.txt") == "nome.txt"
    assert run(RemoveRule(mode="digits"), name="a1b22c.txt") == "abc.txt"
    assert run(RemoveRule(mode="brackets"), name="Musica (Remix) [HD].mp3") == "Musica.mp3"


def test_insert():
    assert run(InsertRule(text="-", position=4), name="20240131.txt") == "2024-0131.txt"
    assert run(InsertRule(text="!", position=0, from_end=True), name="oi.txt") == "oi!.txt"
    assert run(InsertRule(text="X", position=99), name="ab.txt") == "abX.txt"


def test_counter_padding_step_position():
    rule = CounterRule(start=1, step=1, padding=3, position="suffix", separator="_")
    assert run(rule, name="foto.jpg", index=0) == "foto_001.jpg"
    assert run(rule, name="foto.jpg", index=41) == "foto_042.jpg"
    rule = CounterRule(start=10, step=5, position="prefix", separator=" - ")
    assert run(rule, name="foto.jpg", index=2) == "20 - foto.jpg"
    rule = CounterRule(start=1, position="replace")
    assert run(rule, name="foto.jpg", index=4) == "5.jpg"


def test_counter_reset_per_folder():
    rule = CounterRule(position="replace", reset_per_folder=True)
    assert run(rule, name="a.txt", index=7, folder_index=0) == "1.txt"


def test_index_to_letters():
    assert [index_to_letters(i) for i in (0, 1, 25, 26, 27, 51, 52, 701, 702)] == [
        "A", "B", "Z", "AA", "AB", "AZ", "BA", "ZZ", "AAA"]  # fmt: skip
    with pytest.raises(ValueError):
        index_to_letters(-1)


def test_letters_rule():
    assert run(LettersRule(position="replace"), name="x.txt", index=26) == "AA.txt"
    assert run(LettersRule(uppercase=False, separator="-"), name="x.txt", index=1) == "x-b.txt"
    assert run(LettersRule(start=3, position="prefix", separator=""), name="x.txt") == "Cx.txt"


def test_date_rule_modified():
    rule = DateRule(source="modified", format="%Y-%m-%d", position="prefix")
    assert run(rule, name="a.txt") == "2023-07-14_a.txt"
    rule = DateRule(format="%d.%m.%Y %Hh%M", position="replace")
    assert run(rule, name="a.txt") == "14.07.2023 10h30.txt"


def test_date_rule_validate():
    assert DateRule(format="").validate()
    assert not DateRule(format="%Y").validate()


def test_date_exif_falls_back_with_warning(tmp_path):
    p = tmp_path / "semexif.txt"
    p.write_text("x")
    os.utime(p, (MTIME, MTIME))
    e = FileEntry.from_path(p)
    ctx = RuleContext(e, 0, 0, 1)
    out = apply_rules([DateRule(source="exif", position="replace")], e, ctx)
    assert out == "2023-07-14.txt"
    assert ctx.warnings and ctx.warnings[0][0] in ("exif_missing", "pillow_missing")


def test_date_exif_real_photo(tmp_path):
    pil = pytest.importorskip("PIL.Image")
    img = pil.new("RGB", (4, 4))
    exif = img.getexif()
    exif[306] = "2001:01:01 00:00:00"
    exif.get_ifd(0x8769)[36867] = "2019:05:06 07:08:09"
    p = tmp_path / "IMG_1.jpg"
    img.save(p, exif=exif)
    e = FileEntry.from_path(p)
    assert metadata.exif_datetime(e) == datetime(2019, 5, 6, 7, 8, 9)
    ctx = RuleContext(e, 0, 0, 1)
    out = apply_rules([DateRule(source="exif", format="%Y%m%d_%H%M%S", position="replace")], e, ctx)
    assert out == "20190506_070809.jpg"
    assert not ctx.warnings


@pytest.mark.parametrize(
    "mode,expected",
    [
        ("lower", "foto viagem.JPG"),
        ("upper", "FOTO VIAGEM.JPG"),
        ("title", "Foto Viagem.JPG"),
        ("sentence", "Foto viagem.JPG"),
        ("invert", "fOTO vIAGEM.JPG"),
    ],
)
def test_case_rule(mode, expected):
    assert run(CaseRule(mode=mode)) == expected


def test_case_title_details():
    assert run(CaseRule(mode="title"), name="o_dia D d'água.txt") == "O_Dia D D'água.txt"
    assert run(CaseRule(mode="lower", include_ext=True)) == "foto viagem.jpg"


def test_cleanup():
    rule = CleanupRule(spaces="underscore", strip_accents=True)
    assert run(rule, name="  Relatório   Anual  ção .pdf") == "Relatorio_Anual_cao.pdf"
    rule = CleanupRule(separators_to_spaces=True)
    assert run(rule, name="meu_arquivo--final..v2.txt") == "meu arquivo final v2.txt"
    rule = CleanupRule(remove_invalid=True)
    assert run(rule, name="a:b?c.txt") == "abc.txt"
    assert strip_accents("ÁÉÍÓÚ ãõ ç ñ") == "AEIOU ao c n"


def test_extension_rule():
    assert run(ExtensionRule(mode="lower")) == "Foto Viagem.jpg"
    assert run(ExtensionRule(mode="upper"), name="a.png") == "a.PNG"
    out, ctx = run_ctx(ExtensionRule(mode="change", new_ext=".jpeg"))
    assert out == "Foto Viagem.jpeg" and ctx.warnings
    out, ctx = run_ctx(ExtensionRule(mode="change", new_ext="jpg"))
    assert out == "Foto Viagem.jpg" and not ctx.warnings
    out, ctx = run_ctx(ExtensionRule(mode="remove"))
    assert out == "Foto Viagem" and ctx.warnings
    assert run(ExtensionRule(mode="upper"), name="pasta.v2", is_dir=True) == "pasta.v2"


def test_template_tokens():
    rule = TemplateRule(template="{parent}_{n:03}_{date:%Y}_{name}_{ext}_{size}", start=5, step=2)
    assert run(rule, index=1) == "Ferias_007_2023_Foto Viagem_JPG_1234.JPG"
    assert run(TemplateRule(template="{letter}-{letter:lower}"), index=27) == "AB-ab.JPG"
    assert (
        run([PrefixSuffixRule(prefix="x"), TemplateRule(template="{current}!")])
        == "xFoto Viagem!.JPG"
    )


def test_template_validation():
    assert TemplateRule(template="{nada}").validate()[0][0] == "template_unknown_token"
    assert TemplateRule(template="{name").validate()[0][0] == "template_braces"
    assert TemplateRule(template="").validate()[0][0] == "template_empty"
    assert not TemplateRule(template="{name}_{n:04}").validate()
    with pytest.raises(RuleError):
        run(TemplateRule(template="{oops}"))


def test_music_rule_with_tags(monkeypatch):
    tags = {
        "artist": "Djavan",
        "title": "Oceano",
        "album": "",
        "track": "3",
        "year": "1989",
        "genre": "",
    }
    monkeypatch.setattr(metadata, "music_tags", lambda e: tags)
    assert run(MusicRule(), name="faixa.mp3") == "03 - Djavan - Oceano.mp3"
    out, ctx = run_ctx(TemplateRule(template="{album} {title}"), name="f.mp3")
    assert out == " Oceano.mp3"
    assert ("tag_missing", {"tag": "album"}) in ctx.warnings


def test_music_rule_without_tags_warns(monkeypatch):
    monkeypatch.setattr(metadata, "music_tags", lambda e: None)
    out, ctx = run_ctx(MusicRule(template="{artist}"), name="f.mp3")
    assert out == ".mp3"
    assert ctx.warnings[0][0] in ("tags_missing", "mutagen_missing")


def test_pipeline_order_matters():
    a = [ReplaceRule(find=" ", replace="_"), CaseRule(mode="upper")]
    b = [CaseRule(mode="upper"), ReplaceRule(find="_", replace=" ")]
    assert run(a) == "FOTO_VIAGEM.JPG"
    assert run(b) == "FOTO VIAGEM.JPG"


@pytest.mark.parametrize("kind", sorted(RULE_TYPES))
def test_every_rule_roundtrips(kind):
    rule = RULE_TYPES[kind]()
    data = rule.to_dict()
    assert data["type"] == kind
    clone = rule_from_dict(data)
    assert clone == rule
    # todos os campos editáveis existem na regra
    for spec in rule.FIELDS:
        assert hasattr(rule, spec.name)
        if spec.kind == "choice":
            assert getattr(rule, spec.name) in spec.choices


def test_rule_from_dict_coerces_and_rejects():
    r = rule_from_dict({"type": "counter", "start": "7", "padding": 2.0, "lixo": True})
    assert r.start == 7 and r.padding == 2
    with pytest.raises(ValueError):
        rule_from_dict({"type": "nao_existe"})

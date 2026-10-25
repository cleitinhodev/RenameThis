import re
from pathlib import Path

from renamethis.core.rules import RULE_TYPES
from renamethis.i18n import LANGUAGES, keys, normalize_language, set_language, tr

SRC = Path(__file__).resolve().parents[1] / "renamethis"


def test_all_languages_have_same_keys():
    base = keys("pt_BR")
    assert base
    for lang in LANGUAGES:
        assert keys(lang) == base, set(base) ^ keys(lang)


def test_every_issue_code_is_translated():
    code_re = re.compile(
        r'(?:add|warn)\(\s*"([a-z_]+)"'
        r'|RuleError\(\s*"([a-z_]+)"'
        r'|\("([a-z_]+)", Level\.'
    )
    found = set()
    for py in (SRC / "core").glob("*.py"):
        for m in code_re.finditer(py.read_text(encoding="utf-8")):
            found.add(next(g for g in m.groups() if g))
    assert found
    missing = {c for c in found if f"issue.{c}" not in keys("pt_BR")}
    assert not missing


def test_rules_and_fields_translated():
    k = keys("pt_BR")
    for kind, cls in RULE_TYPES.items():
        assert f"rule.{kind}" in k and f"desc.{kind}" in k
        for spec in cls.FIELDS:
            assert f"field.{spec.name}" in k
            for choice in spec.choices:
                assert f"choice.{choice}" in k


def test_tr_fallbacks_and_params():
    set_language("en")
    assert tr("button.apply") == "Rename"
    assert tr("nao.existe") == "nao.existe"
    assert tr("issue.reserved_name", name="CON") == "“CON” is a reserved name on Windows."
    assert "{name}" in tr("issue.reserved_name")  # sem parâmetros, não formata
    set_language("pt_BR")
    assert tr("button.apply") == "Renomear"


def test_normalize_language():
    assert normalize_language("pt-PT") == "pt_BR"
    assert normalize_language("en_US") == "en"
    assert normalize_language("de_DE") == "en"
    assert normalize_language(None) == "pt_BR"

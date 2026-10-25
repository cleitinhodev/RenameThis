import pytest

from renamethis.core.models import Level, split_name
from renamethis.core.validation import normalize_key, validate_name


def codes(name):
    return {c for c, _lvl, _p in validate_name(name)}


@pytest.mark.parametrize("name", ["foto.jpg", "Relatório 2024.pdf", "a", "ação_ç.txt"])
def test_valid_names(name):
    assert not [i for i in validate_name(name) if i[1] is Level.ERROR]


@pytest.mark.parametrize(
    "name,code",
    [
        ("", "empty_name"),
        ("   ", "empty_name"),
        ("..", "path_traversal"),
        (".", "path_traversal"),
        ("../fora.txt", "path_separator"),
        ("a/b.txt", "path_separator"),
        ("a\\b.txt", "path_separator"),
        ("a:b.txt", "invalid_chars"),
        ("a?.txt", "invalid_chars"),
        ('a"b', "invalid_chars"),
        ("a<b>|*", "invalid_chars"),
        ("tab\tname", "control_chars"),
        ("CON", "reserved_name"),
        ("con.txt", "reserved_name"),
        ("Nul.tar.gz", "reserved_name"),
        ("COM1.log", "reserved_name"),
        ("lpt9", "reserved_name"),
        ("arquivo.", "trailing_dot_space"),
        ("arquivo ", "trailing_dot_space"),
        ("a" * 256, "name_too_long"),
        ("ç" * 128 + ".txt", "name_too_long"),  # 255 bytes em UTF-8 estoura
    ],
)
def test_invalid_names(name, code):
    assert code in codes(name)


def test_reserved_lookalikes_are_ok():
    assert "reserved_name" not in codes("CONSOLE.txt")
    assert "reserved_name" not in codes("com10.txt")


def test_leading_space_is_warning():
    issues = validate_name(" nome.txt")
    assert ("leading_space", Level.WARNING, {}) in issues


def test_split_name():
    assert split_name("foto.jpg") == ("foto", ".jpg")
    assert split_name("arquivo.tar.gz") == ("arquivo.tar", ".gz")
    assert split_name(".bashrc") == (".bashrc", "")
    assert split_name("sem_ext") == ("sem_ext", "")
    assert split_name("termina.") == ("termina.", "")
    assert split_name("pasta.v2", is_dir=True) == ("pasta.v2", "")


def test_normalize_key():
    assert normalize_key("ABC.txt", True) == normalize_key("abc.TXT", True)
    assert normalize_key("ABC.txt", False) != normalize_key("abc.txt", False)
    # NFC x NFD
    assert normalize_key("ação", False) == normalize_key("ac\u0327a\u0303o", False)

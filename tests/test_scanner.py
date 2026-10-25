import pytest

from renamethis.core import ScanError, ScanOptions, scan
from renamethis.core.scanner import parse_ext_list
from tests.conftest import make_files


def names(entries):
    return sorted(e.name for e in entries)


def test_empty_path_raises():
    with pytest.raises(ScanError) as exc:
        scan("")
    assert exc.value.code == "folder_empty"


def test_missing_folder_raises(tmp_path):
    with pytest.raises(ScanError) as exc:
        scan(tmp_path / "nao_existe")
    assert exc.value.code == "folder_not_found"


def test_file_instead_of_folder(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("x")
    with pytest.raises(ScanError) as exc:
        scan(f)
    assert exc.value.code == "not_a_folder"


def test_hidden_and_system_ignored_by_default(folder):
    make_files(folder, ["a.txt", ".oculto", "desktop.ini", "Thumbs.db", ".DS_Store"])
    assert names(scan(folder)) == ["a.txt"]
    opts = ScanOptions(include_hidden=True)
    assert names(scan(folder, opts)) == [".oculto", "a.txt"]
    opts = ScanOptions(include_hidden=True, include_system=True)
    assert len(scan(folder, opts)) == 5


def test_extension_filters(folder):
    make_files(folder, ["a.JPG", "b.jpg", "c.png", "d.txt"])
    assert names(scan(folder, ScanOptions(extensions=["jpg", ".png"]))) == [
        "a.JPG",
        "b.jpg",
        "c.png",
    ]
    assert names(scan(folder, ScanOptions(exclude_extensions=["*.txt"]))) == [
        "a.JPG",
        "b.jpg",
        "c.png",
    ]


def test_recursive_and_dirs(folder):
    make_files(folder, ["a.txt", "sub/b.txt", "sub/deep/c.txt"])
    assert names(scan(folder)) == ["a.txt"]
    assert names(scan(folder, ScanOptions(recursive=True))) == ["a.txt", "b.txt", "c.txt"]
    assert names(scan(folder, ScanOptions(include_dirs=True))) == ["a.txt", "sub"]
    only_dirs = ScanOptions(include_files=False, include_dirs=True, recursive=True)
    assert names(scan(folder, only_dirs)) == ["deep", "sub"]


def test_parse_ext_list():
    assert parse_ext_list("jpg, .png *.gif;tiff") == ["jpg", "png", "gif", "tiff"]
    assert parse_ext_list("  ") == []


def test_options_roundtrip():
    o = ScanOptions(recursive=True, extensions=["jpg"])
    assert ScanOptions.from_dict(o.to_dict() | {"lixo": 1}) == o

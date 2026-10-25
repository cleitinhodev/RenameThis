from renamethis.core import SortKey, SortOptions, natural_key, scan, sort_entries
from tests.conftest import make_files


def test_natural_key_numbers():
    names = ["foto10.jpg", "foto2.jpg", "foto1.jpg", "Foto3.jpg"]
    assert sorted(names, key=natural_key) == ["foto1.jpg", "foto2.jpg", "Foto3.jpg", "foto10.jpg"]


def test_natural_key_mixed():
    names = ["10.txt", "1.txt", "2.txt", "a.txt", "1a.txt"]
    assert sorted(names, key=natural_key) == ["1.txt", "1a.txt", "2.txt", "10.txt", "a.txt"]


def test_sort_by_name_and_desc(folder):
    make_files(folder, ["b10.txt", "b2.txt", "a.txt"])
    entries = scan(folder)
    assert [e.name for e in sort_entries(entries)] == ["a.txt", "b2.txt", "b10.txt"]
    desc = sort_entries(entries, SortOptions(descending=True))
    assert [e.name for e in desc] == ["b10.txt", "b2.txt", "a.txt"]


def test_sort_by_size(folder):
    (folder / "grande.txt").write_text("x" * 100)
    (folder / "pequeno.txt").write_text("x")
    (folder / "medio.txt").write_text("x" * 10)
    out = sort_entries(scan(folder), SortOptions(SortKey.SIZE))
    assert [e.name for e in out] == ["pequeno.txt", "medio.txt", "grande.txt"]


def test_sort_by_modified(folder):
    import os

    make_files(folder, ["a.txt", "b.txt", "c.txt"])
    os.utime(folder / "a.txt", (3000, 3000))
    os.utime(folder / "b.txt", (1000, 1000))
    os.utime(folder / "c.txt", (2000, 2000))
    out = sort_entries(scan(folder), SortOptions(SortKey.MODIFIED))
    assert [e.name for e in out] == ["b.txt", "c.txt", "a.txt"]


def test_sort_by_type_tiebreak_by_name(folder):
    make_files(folder, ["z.b", "a.c", "b.a", "a.a"])
    out = sort_entries(scan(folder), SortOptions(SortKey.TYPE))
    assert [e.name for e in out] == ["a.a", "b.a", "z.b", "a.c"]


def test_sort_options_roundtrip():
    o = SortOptions(SortKey.SIZE, True, True)
    assert SortOptions.from_dict(o.to_dict()) == o

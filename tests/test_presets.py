import pytest

from renamethis.core import (
    ConflictPolicy,
    Preset,
    ScanOptions,
    SortKey,
    SortOptions,
    load_preset,
    save_preset,
)
from renamethis.core.rules import CounterRule, ReplaceRule


def test_preset_roundtrip(tmp_path):
    preset = Preset(
        name="Fotos da viagem",
        rules=[ReplaceRule(find="IMG", replace="Foto"), CounterRule(padding=3, enabled=False)],
        scan=ScanOptions(recursive=True, extensions=["jpg"]),
        sort=SortOptions(SortKey.MODIFIED, descending=True),
        conflict=ConflictPolicy.SKIP,
    )
    path = tmp_path / "p.json"
    save_preset(preset, path)
    loaded = load_preset(path)
    assert loaded == preset


def test_invalid_preset(tmp_path):
    p = tmp_path / "x.json"
    p.write_text('{"rules": "nope"}')
    with pytest.raises(ValueError):
        load_preset(p)

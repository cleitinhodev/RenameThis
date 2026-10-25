"""Núcleo do RenameThis (lógica pura, sem dependência de interface gráfica).

Fluxo típico::

    entries = scan(pasta, ScanOptions())
    entries = sort_entries(entries, SortOptions())
    plan = build_plan(entries, regras)
    if not plan.has_errors:
        result = apply_plan(plan)
"""

from .executor import ApplyResult, apply_plan
from .journal import Journal, JournalEntry, recover_incomplete, undo_last
from .models import FileEntry, Issue, Level, Plan, PlanItem, Status
from .planner import ConflictPolicy, build_plan
from .presets import Preset, load_preset, save_preset
from .rules import RULE_TYPES, Rule, rule_from_dict
from .scanner import ScanError, ScanOptions, scan
from .sorting import SortKey, SortOptions, natural_key, sort_entries

__all__ = [
    "ApplyResult",
    "ConflictPolicy",
    "FileEntry",
    "Issue",
    "Journal",
    "JournalEntry",
    "Level",
    "Plan",
    "PlanItem",
    "Preset",
    "RULE_TYPES",
    "Rule",
    "ScanError",
    "ScanOptions",
    "SortKey",
    "SortOptions",
    "Status",
    "apply_plan",
    "build_plan",
    "load_preset",
    "natural_key",
    "recover_incomplete",
    "rule_from_dict",
    "save_preset",
    "scan",
    "sort_entries",
    "undo_last",
]

"""Interface de linha de comando do RenameThis (usa o mesmo núcleo da interface gráfica)."""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

from . import __version__
from .core import (
    ConflictPolicy,
    Journal,
    Preset,
    ScanError,
    SortKey,
    SortOptions,
    Status,
    apply_plan,
    build_plan,
    load_preset,
    recover_incomplete,
    rule_from_dict,
    save_preset,
    scan,
    sort_entries,
    undo_last,
)
from .core.executor import ApplyResult
from .core.rules import RULE_TYPES, CaseRule, PrefixSuffixRule, ReplaceRule, Rule, TemplateRule
from .core.scanner import parse_ext_list
from .i18n import LANGUAGES, detect_language, error_text, issue_text, set_language, tr

TRUE = {"1", "true", "sim", "s", "yes", "y", "on", "verdadeiro"}
FALSE = {"0", "false", "nao", "não", "n", "no", "off", "falso"}

_COLORS = {
    Status.OK: "\033[32m",
    Status.WARNING: "\033[33m",
    Status.SKIPPED: "\033[90m",
    Status.ERROR: "\033[31m",
    Status.UNCHANGED: "\033[90m",
}
_RESET = "\033[0m"


class CliError(Exception):
    pass


def _use_color() -> bool:
    return sys.stdout.isatty() and os.environ.get("NO_COLOR") is None


def parse_rule_args(kind: str, pairs: Sequence[str]) -> Rule:
    """``counter padding=3 position=prefix`` -> CounterRule(padding=3, position="prefix")."""
    cls = RULE_TYPES.get(kind)
    if cls is None:
        raise CliError(tr("cli.bad_rule", error=kind))
    specs = {f.name: f for f in cls.FIELDS}
    data: dict[str, object] = {"type": kind}
    for pair in pairs:
        if "=" not in pair:
            raise CliError(tr("cli.bad_kv", arg=pair))
        key, value = pair.split("=", 1)
        key = key.strip().replace("-", "_")
        if key not in specs and key != "enabled":
            raise CliError(tr("cli.unknown_field", rule=kind, field=key))
        kindf = specs[key].kind if key in specs else "bool"
        if kindf == "bool":
            low = value.strip().lower()
            if low not in TRUE | FALSE:
                raise CliError(tr("cli.bad_kv", arg=pair))
            data[key] = low in TRUE
        elif kindf == "int":
            try:
                data[key] = int(value)
            except ValueError as exc:
                raise CliError(tr("cli.bad_kv", arg=pair)) from exc
        elif kindf == "choice":
            if value not in specs[key].choices:
                raise CliError(f"{key}: {value} ∉ {', '.join(specs[key].choices)}")
            data[key] = value
        else:
            data[key] = value
    return rule_from_dict(data)


class _RuleAction(argparse.Action):
    """Acumula as regras na ordem em que aparecem na linha de comando."""

    def __call__(self, parser, namespace, values, option_string=None):
        rules = list(getattr(namespace, "rules", None) or [])
        try:
            if self.dest == "add":
                kind, *pairs = values
                rules.append(parse_rule_args(kind, pairs))
            elif self.dest == "prefix":
                rules.append(PrefixSuffixRule(prefix=values))
            elif self.dest == "suffix":
                rules.append(PrefixSuffixRule(suffix=values))
            elif self.dest == "replace":
                rules.append(ReplaceRule(find=values[0], replace=values[1]))
            elif self.dest == "regex":
                rules.append(ReplaceRule(find=values[0], replace=values[1], regex=True))
            elif self.dest == "template":
                rules.append(TemplateRule(template=values))
            elif self.dest == "case":
                rules.append(CaseRule(mode=values))
        except CliError as exc:
            parser.error(str(exc))
        namespace.rules = rules


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="renamethis-cli", description=tr("cli.description"), epilog=tr("cli.epilog")
    )
    p.add_argument("--version", action="version", version=f"RenameThis {__version__}")
    p.add_argument("--lang", choices=sorted(LANGUAGES), help=tr("cli.help.lang"))
    sub = p.add_subparsers(dest="command", required=True)

    r = sub.add_parser("rename", help=tr("cli.help.rename"), epilog=tr("cli.epilog"))
    r.add_argument("folder", help=tr("cli.help.folder"))
    r.set_defaults(rules=[])
    r.add_argument("--add", nargs="+", metavar="ARG", action=_RuleAction, help=tr("cli.help.add"))
    r.add_argument("--prefix", metavar="TEXT", action=_RuleAction, help=tr("cli.help.prefix"))
    r.add_argument("--suffix", metavar="TEXT", action=_RuleAction, help=tr("cli.help.suffix"))
    r.add_argument(
        "--replace",
        nargs=2,
        metavar=("FIND", "REPL"),
        action=_RuleAction,
        help=tr("cli.help.replace"),
    )
    r.add_argument(
        "--regex",
        nargs=2,
        metavar=("PATTERN", "REPL"),
        action=_RuleAction,
        help=tr("cli.help.regex"),
    )
    r.add_argument(
        "--template", metavar="TEMPLATE", action=_RuleAction, help=tr("cli.help.template")
    )
    r.add_argument("--case", choices=CaseRule.MODES, action=_RuleAction, help=tr("cli.help.case"))
    r.add_argument("--preset", metavar="FILE", help=tr("cli.help.preset"))
    r.add_argument("--save-preset", metavar="FILE", help=tr("cli.help.save_preset"))
    r.add_argument("--sort", choices=[k.value for k in SortKey], help=tr("cli.help.sort"))
    r.add_argument("--desc", action="store_true", default=None, help=tr("cli.help.desc"))
    r.add_argument(
        "--recursive", "-r", action="store_true", default=None, help=tr("cli.help.recursive")
    )
    r.add_argument("--dirs", action="store_true", default=None, help=tr("cli.help.dirs"))
    r.add_argument("--no-files", action="store_true", default=None, help=tr("cli.help.no_files"))
    r.add_argument("--hidden", action="store_true", default=None, help=tr("cli.help.hidden"))
    r.add_argument("--system", action="store_true", default=None, help=tr("cli.help.system"))
    r.add_argument("--ext", metavar="LIST", help=tr("cli.help.ext"))
    r.add_argument("--exclude-ext", metavar="LIST", help=tr("cli.help.exclude_ext"))
    r.add_argument(
        "--on-conflict", choices=[c.value for c in ConflictPolicy], help=tr("cli.help.on_conflict")
    )
    r.add_argument("--dry-run", "-n", action="store_true", help=tr("cli.help.dry_run"))
    r.add_argument("--yes", "-y", action="store_true", help=tr("cli.help.yes"))
    r.add_argument("--all", action="store_true", help=tr("cli.help.all"))

    u = sub.add_parser("undo", help=tr("cli.help.undo"))
    u.add_argument("--yes", "-y", action="store_true", help=tr("cli.help.yes"))
    h = sub.add_parser("history", help=tr("cli.help.history"))
    h.add_argument("--limit", type=int, default=20, help=tr("cli.help.limit"))
    sub.add_parser("recover", help=tr("cli.help.recover"))
    sub.add_parser("rules", help=tr("cli.help.rules"))
    return p


def _preset_from_args(args: argparse.Namespace) -> Preset:
    preset = load_preset(args.preset) if args.preset else Preset()
    if args.rules:
        preset.rules = list(preset.rules) + list(args.rules)
    s = preset.scan
    if args.recursive is not None:
        s.recursive = True
    if args.dirs is not None:
        s.include_dirs = True
    if args.no_files is not None:
        s.include_files = False
    if args.hidden is not None:
        s.include_hidden = True
    if args.system is not None:
        s.include_system = True
    if args.ext is not None:
        s.extensions = parse_ext_list(args.ext)
    if args.exclude_ext is not None:
        s.exclude_extensions = parse_ext_list(args.exclude_ext)
    if args.sort:
        preset.sort = SortOptions(
            SortKey(args.sort), preset.sort.descending, preset.sort.folders_first
        )
    if args.desc is not None:
        preset.sort.descending = True
    if args.on_conflict:
        preset.conflict = ConflictPolicy(args.on_conflict)
    return preset


def _ask(prompt: str) -> bool:
    try:
        answer = input(prompt)
    except EOFError:
        return False
    return answer.strip().lower() in TRUE


def _print_result(result: ApplyResult) -> int:
    if result.ok:
        print(tr("result.ok", renamed=len(result.renamed)))
        if result.skipped:
            print(tr("result.skipped", skipped=result.skipped))
        if result.journal_path:
            print(tr("cli.journal", path=result.journal_path))
        return 0
    print(tr("result.failed"), file=sys.stderr)
    reason = error_text(
        result.error_code or "unexpected",
        path=result.error_path or "",
        detail=result.error_detail or "",
    )
    print(tr("result.reason", reason=reason), file=sys.stderr)
    if result.rollback_errors:
        print(tr("result.rollback_failed"), file=sys.stderr)
        for line in result.rollback_errors:
            print("  " + line, file=sys.stderr)
    return 1


def cmd_rename(args: argparse.Namespace) -> int:
    try:
        preset = _preset_from_args(args)
    except (OSError, ValueError) as exc:
        print(tr("preset.load_error", error=exc), file=sys.stderr)
        return 2
    if args.save_preset:
        save_preset(preset, args.save_preset)
        print(tr("cli.preset_saved", path=args.save_preset))
    if not preset.rules:
        print(tr("cli.no_rules"), file=sys.stderr)
        return 2
    try:
        entries = sort_entries(scan(args.folder, preset.scan), preset.sort)
    except ScanError as exc:
        print(error_text(exc.code, path=exc.path), file=sys.stderr)
        return 2
    plan = build_plan(entries, preset.rules, preset.conflict)
    root = Path(args.folder).expanduser().resolve()
    color = _use_color()
    hidden = 0
    for item in plan.items:
        if item.status is Status.UNCHANGED and not args.all:
            hidden += 1
            continue
        try:
            rel = item.source.relative_to(root)
        except ValueError:
            rel = item.source
        label = tr(f"status.{item.status.value}")
        line = f"{rel}  →  {item.new_name}   [{label}]"
        if color:
            line = f"{_COLORS[item.status]}{line}{_RESET}"
        print(line)
        for issue in item.issues:
            if issue.level.value != "info":
                print(f"      - {issue_text(issue)}")
    if hidden:
        print(tr("cli.hidden_unchanged", count=hidden))
    s = plan.summary()
    print()
    print(
        tr(
            "summary.counts",
            total=s["total"],
            rename=s["ok"] + s["warning"],
            skipped=s["skipped"],
            errors=s["error"],
        )
    )
    if plan.has_errors:
        print(tr("cli.has_errors"), file=sys.stderr)
        return 1
    if not plan.to_rename:
        print(tr("cli.nothing"))
        return 0
    if args.dry_run:
        print(tr("cli.dry_run"))
        return 0
    if not args.yes and not _ask(tr("cli.confirm", count=len(plan.to_rename))):
        print(tr("cli.aborted"))
        return 1
    return _print_result(apply_plan(plan, Journal()))


def cmd_undo(args: argparse.Namespace) -> int:
    journal = Journal()
    entry = journal.last_undoable()
    if entry is None:
        print(tr("undo.none"))
        return 0
    date = entry.created_dt.strftime("%Y-%m-%d %H:%M:%S")
    if not args.yes and not _ask(tr("cli.undo_confirm", count=entry.count, date=date)):
        print(tr("cli.aborted"))
        return 1
    result = undo_last(journal)
    if result is not None and result.ok:
        print(tr("undo.ok", count=len(result.renamed)))
        return 0
    return _print_result(result) if result else 1


def cmd_history(args: argparse.Namespace) -> int:
    entries = Journal().entries()[: max(args.limit, 1)]
    if not entries:
        print(tr("history.empty"))
        return 0
    for e in entries:
        status = "undone" if e.undone else e.status
        when = datetime.fromisoformat(e.created).strftime("%Y-%m-%d %H:%M:%S")
        folders = ", ".join(e.folders[:2]) + (" …" if len(e.folders) > 2 else "")
        print(
            f"{when}  {tr('kind.' + e.kind):<12} {e.count:>6}  "
            f"{tr('jstatus.' + status):<20} {folders}"
        )
    return 0


def cmd_recover(_args: argparse.Namespace) -> int:
    journal = Journal()
    if not journal.incomplete():
        print(tr("recover.none"))
        return 0
    restored, errors = recover_incomplete(journal)
    print(tr("recover.done", count=restored))
    if errors:
        print(tr("recover.errors"), file=sys.stderr)
        for e in errors:
            print("  " + e, file=sys.stderr)
        return 1
    return 0


def cmd_rules(_args: argparse.Namespace) -> int:
    for kind, cls in RULE_TYPES.items():
        print(f"{kind:<14} {tr('rule.' + kind)}")
        default = cls()
        for spec in cls.FIELDS:
            extra = f" ({'|'.join(spec.choices)})" if spec.choices else ""
            print(
                f"    {spec.name}={getattr(default, spec.name)!r}{extra}  — "
                f"{tr('field.' + spec.name)}"
            )
    return 0


def _prescan_lang(argv: Sequence[str]) -> str | None:
    for i, a in enumerate(argv):
        if a == "--lang" and i + 1 < len(argv):
            return argv[i + 1]
        if a.startswith("--lang="):
            return a.split("=", 1)[1]
    return None


def main(argv: Sequence[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    set_language(_prescan_lang(argv) or detect_language())
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(errors="replace")
        except (ValueError, OSError):  # pragma: no cover
            pass
    args = build_parser().parse_args(argv)
    handlers = {
        "rename": cmd_rename,
        "undo": cmd_undo,
        "history": cmd_history,
        "recover": cmd_recover,
        "rules": cmd_rules,
    }
    return handlers[args.command](args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

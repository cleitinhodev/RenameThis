"""Formulário gerado automaticamente a partir dos campos de cada regra."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QSpinBox,
    QWidget,
)

from ..core.rules import Rule
from ..i18n import tr

_TIPS = {
    ("replace", "find"): "tip.find",
    ("letters", "start"): "tip.start_letters",
    ("insert", "position"): "tip.position_insert",
    ("remove", "start"): "tip.start_remove",
}


def _hidden_fields(rule: Rule) -> set[str]:
    """Campos irrelevantes para o modo atual (ficam escondidos)."""
    t = rule.type
    if t == "remove":
        mode = rule.mode
        return {
            "chars": {"start", "count"},
            "range": {"chars"},
            "first": {"chars", "start"},
            "last": {"chars", "start"},
        }.get(mode, {"chars", "start", "count"})
    if t == "extension":
        return set() if rule.mode == "change" else {"new_ext"}
    if t in ("counter", "letters", "date"):
        return {"separator"} if rule.position == "replace" else set()
    return set()


class RuleEditor(QWidget):
    changed = Signal()

    def __init__(self, rule: Rule, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.rule = rule
        self._rows: dict[str, QWidget] = {}
        form = QFormLayout(self)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self._form = form
        title = QLabel(tr("rule." + rule.type))
        title.setObjectName("EditorTitle")
        form.addRow(title)

        for spec in rule.FIELDS:
            value = getattr(rule, spec.name)
            label = tr(f"field.{spec.name}")
            tip_key = _TIPS.get((rule.type, spec.name))
            if spec.kind == "bool":
                w = QCheckBox(label)
                w.setChecked(bool(value))
                w.toggled.connect(lambda v, n=spec.name: self._set(n, bool(v)))
                form.addRow(w)
            else:
                if spec.kind == "int":
                    w = QSpinBox()
                    w.setRange(spec.minimum, spec.maximum)
                    w.setValue(int(value))
                    w.valueChanged.connect(lambda v, n=spec.name: self._set(n, int(v)))
                elif spec.kind == "choice":
                    w = QComboBox()
                    for choice in spec.choices:
                        w.addItem(tr(f"choice.{choice}"), choice)
                    w.setCurrentIndex(max(0, list(spec.choices).index(value)))
                    w.currentIndexChanged.connect(
                        lambda _i, n=spec.name, box=w: self._set(n, box.currentData())
                    )
                else:
                    w = QLineEdit(str(value))
                    w.setClearButtonEnabled(True)
                    w.textChanged.connect(lambda v, n=spec.name: self._set(n, v))
                w.setObjectName(f"field_{spec.name}")
                form.addRow(label, w)
            if tip_key:
                w.setToolTip(tr(tip_key))
            self._rows[spec.name] = w

        if rule.type in ("template", "music"):
            self._add_help(tr("tokens.text"))
        if rule.type == "date":
            self._add_help(tr("date_format.help"))
        self._update_visibility()

    def _add_help(self, text: str) -> None:
        help_label = QLabel(text)
        help_label.setWordWrap(True)
        help_label.setTextFormat(Qt.TextFormat.RichText)
        help_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        font = help_label.font()
        font.setPointSizeF(max(font.pointSizeF() - 1, 7))
        help_label.setFont(font)
        help_label.setObjectName("HelpLabel")
        self._form.addRow(help_label)

    def _set(self, name: str, value) -> None:
        setattr(self.rule, name, value)
        self._update_visibility()
        self.changed.emit()

    def _update_visibility(self) -> None:
        hidden = _hidden_fields(self.rule)
        for name, widget in self._rows.items():
            self._form.setRowVisible(widget, name not in hidden)

    def field_widget(self, name: str) -> QWidget | None:
        return self._rows.get(name)

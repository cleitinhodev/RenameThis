"""Modelo da tabela de prévia."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPalette
from PySide6.QtWidgets import QApplication, QStyle

from ..core.models import Level, Plan, PlanItem, Status
from ..i18n import issue_text, tr

COLUMNS = ("index", "original", "new", "folder", "status")

# Cores com transparência funcionam bem tanto no tema claro quanto no escuro
_BACKGROUND = {
    Status.ERROR: QColor(220, 53, 69, 75),
    Status.WARNING: QColor(255, 165, 0, 60),
    Status.SKIPPED: QColor(128, 128, 128, 45),
}


class PreviewModel(QAbstractTableModel):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._plan: Plan | None = None
        self._root: Path | None = None
        self._rows: list[tuple[int, PlanItem]] = []
        self.only_changes = False

    # ------------------------------------------------------------------ dados
    def set_plan(self, plan: Plan | None, root: Path | None = None) -> None:
        self.beginResetModel()
        self._plan, self._root = plan, root
        self._rebuild()
        self.endResetModel()

    def set_only_changes(self, value: bool) -> None:
        self.beginResetModel()
        self.only_changes = value
        self._rebuild()
        self.endResetModel()

    def retranslate(self) -> None:
        self.headerDataChanged.emit(Qt.Orientation.Horizontal, 0, len(COLUMNS) - 1)
        if self._rows:
            self.dataChanged.emit(
                self.index(0, 0), self.index(len(self._rows) - 1, len(COLUMNS) - 1)
            )

    def _rebuild(self) -> None:
        if self._plan is None:
            self._rows = []
            return
        self._rows = [
            (i, item)
            for i, item in enumerate(self._plan.items)
            if not self.only_changes or item.status is not Status.UNCHANGED
        ]

    def item_at(self, row: int) -> PlanItem | None:
        return self._rows[row][1] if 0 <= row < len(self._rows) else None

    # ------------------------------------------------------------------ Qt API
    def rowCount(self, parent=QModelIndex()) -> int:  # noqa: B008, N802
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent=QModelIndex()) -> int:  # noqa: B008, N802
        return 0 if parent.isValid() else len(COLUMNS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):  # noqa: N802
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return tr(f"col.{COLUMNS[section]}")
        return None

    def _folder_text(self, item: PlanItem) -> str:
        if self._root is None:
            return str(item.entry.parent)
        try:
            rel = item.entry.parent.relative_to(self._root)
        except ValueError:
            return str(item.entry.parent)
        return "." if str(rel) == "." else str(rel)

    @staticmethod
    def status_text(item: PlanItem) -> str:
        label = tr(f"status.{item.status.value}")
        first = next((i for i in item.issues if i.level is not Level.INFO), None)
        return f"{label}: {issue_text(first)}" if first else label

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        pos, item = self._rows[index.row()]
        col = COLUMNS[index.column()]
        if role == Qt.ItemDataRole.DisplayRole:
            if col == "index":
                return str(pos + 1)
            if col == "original":
                return item.entry.name + ("/" if item.entry.is_dir else "")
            if col == "new":
                return item.new_name + ("/" if item.entry.is_dir else "")
            if col == "folder":
                return self._folder_text(item)
            return self.status_text(item)
        if role == Qt.ItemDataRole.ToolTipRole:
            lines = [str(item.target) if col == "new" else str(item.source)]
            lines += [f"• {issue_text(i)}" for i in item.issues]
            return "\n".join(lines)
        if role == Qt.ItemDataRole.BackgroundRole:
            return _BACKGROUND.get(item.status)
        if role == Qt.ItemDataRole.ForegroundRole and item.status is Status.UNCHANGED:
            return QGuiApplication.palette().color(QPalette.ColorRole.PlaceholderText)
        if role == Qt.ItemDataRole.FontRole and col == "new" and item.will_rename:
            font = QFont()
            font.setBold(True)
            return font
        if role == Qt.ItemDataRole.DecorationRole and col == "status":
            style = QApplication.style()
            icon = {
                Status.ERROR: QStyle.StandardPixmap.SP_MessageBoxCritical,
                Status.WARNING: QStyle.StandardPixmap.SP_MessageBoxWarning,
                Status.SKIPPED: QStyle.StandardPixmap.SP_DialogCancelButton,
                Status.OK: QStyle.StandardPixmap.SP_DialogApplyButton,
            }.get(item.status)
            return style.standardIcon(icon) if icon is not None and style else None
        return None

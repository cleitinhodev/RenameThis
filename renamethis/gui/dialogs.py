"""Diálogos auxiliares."""

from __future__ import annotations

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from ..core.journal import Journal
from ..i18n import tr


class HistoryDialog(QDialog):
    def __init__(self, journal: Journal, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("history.title"))
        self.resize(820, 420)
        layout = QVBoxLayout(self)
        entries = journal.entries()
        if not entries:
            layout.addWidget(QLabel(tr("history.empty")))
        cols = ["col_date", "col_kind", "col_count", "col_status", "col_folder"]
        table = QTableWidget(len(entries), len(cols))
        table.setHorizontalHeaderLabels([tr(f"history.{c}") for c in cols])
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.verticalHeader().setVisible(False)
        for row, e in enumerate(entries):
            status = "undone" if e.undone else e.status
            values = [
                e.created_dt.strftime("%Y-%m-%d %H:%M:%S"),
                tr(f"kind.{e.kind}"),
                str(e.count),
                tr(f"jstatus.{status}"),
                ", ".join(e.folders),
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setToolTip(value)
                table.setItem(row, col, item)
        table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        table.resizeColumnsToContents()
        layout.addWidget(table)
        self.table = table

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        open_dir = QPushButton(tr("history.open_dir"))
        buttons.addButton(open_dir, QDialogButtonBox.ButtonRole.ActionRole)
        open_dir.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(journal.directory)))
        )
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

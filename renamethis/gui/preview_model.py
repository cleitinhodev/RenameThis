"""Modelo da tabela de prévia."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import QStyle, QStyledItemDelegate, QStyleOptionViewItem

from ..core.models import Level, Plan, PlanItem, Status
from ..i18n import issue_text, tr
from . import theme

COLUMNS = ("index", "original", "new", "folder", "status")


def _status_colors(status: Status) -> tuple[str, str] | None:
    """(cor forte, cor suave) do status no tema atual."""
    p = theme.current()
    return {
        Status.OK: (p.ok, p.ok_soft),
        Status.WARNING: (p.warning, p.warning_soft),
        Status.ERROR: (p.error, p.error_soft),
        Status.SKIPPED: (p.skipped, p.skipped_soft),
    }.get(status)


_STATUS_ICON = {
    Status.OK: "ok",
    Status.WARNING: "warning",
    Status.ERROR: "error",
    Status.SKIPPED: "skip",
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
            if item.status in (Status.ERROR, Status.WARNING, Status.SKIPPED):
                color = QColor(_status_colors(item.status)[1])
                color.setAlpha(150 if theme.current().dark else 120)
                return color
            return None
        if role == Qt.ItemDataRole.ForegroundRole and item.status is Status.UNCHANGED:
            return QColor(theme.current().text_muted)
        if role == Qt.ItemDataRole.FontRole and col == "new" and item.will_rename:
            font = QFont()
            font.setBold(True)
            return font
        if role == Qt.ItemDataRole.ForegroundRole and col == "new" and item.will_rename:
            return QColor(theme.current().accent)
        if role == Qt.ItemDataRole.DecorationRole and col == "status":
            name = _STATUS_ICON.get(item.status)
            colors = _status_colors(item.status)
            return theme.icon(name, colors[0]) if name and colors else None
        return None


class PreviewDelegate(QStyledItemDelegate):
    """Desenha a coluna de situação como um "selo" colorido e uma faixa de cor no nº."""

    def __init__(self, model: PreviewModel, parent=None) -> None:
        super().__init__(parent)
        self._model = model

    def sizeHint(self, option, index):  # noqa: N802
        size = super().sizeHint(option, index)
        return QSize(size.width() + 16, max(size.height(), 30))

    def paint(self, painter: QPainter, option, index) -> None:
        item = self._model.item_at(index.row())
        col = COLUMNS[index.column()]
        if item is None or col not in ("status", "index"):
            super().paint(painter, option, index)
            return
        colors = _status_colors(item.status)
        if col == "index":
            super().paint(painter, option, index)
            if colors:
                painter.save()
                painter.setRenderHint(QPainter.RenderHint.Antialiasing)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(colors[0]))
                r = option.rect
                painter.drawRoundedRect(QRectF(r.left() + 2, r.top() + 5, 4, r.height() - 10), 2, 2)
                painter.restore()
            return

        # fundo/seleção padrão, sem texto e sem ícone
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        opt.text = ""
        opt.icon = type(opt.icon)()
        style = opt.widget.style() if opt.widget else None
        if style:
            style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, opt.widget)

        p = theme.current()
        label = tr(f"status.{item.status.value}")
        first = next((i for i in item.issues if i.level is not Level.INFO), None)
        detail = issue_text(first) if first else ""
        strong, soft = colors if colors else (p.text_muted, p.surface_alt)

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        font = QFont(option.font)
        font.setBold(True)
        font.setPointSizeF(max(font.pointSizeF() - 0.5, 7))
        fm = QFontMetrics(font)
        r = option.rect.adjusted(6, 0, -6, 0)
        icon_size = 14
        pill_h = min(r.height() - 8, fm.height() + 8)
        pill_w = fm.horizontalAdvance(label) + icon_size + 26
        pill = QRectF(r.left(), r.center().y() - pill_h / 2 + 0.5, pill_w, pill_h)
        if item.status is Status.UNCHANGED:
            # discreto: só um ponto e o texto, sem selo
            font.setBold(False)
            fm = QFontMetrics(font)
            pill_w = fm.horizontalAdvance(label) + icon_size + 14
            pill = QRectF(r.left() - 6, pill.top(), pill_w, pill_h)
        else:
            painter.setPen(QPen(QColor(strong), 1))
            painter.setBrush(QColor(soft))
            painter.drawRoundedRect(pill, pill_h / 2, pill_h / 2)
        name = _STATUS_ICON.get(item.status, "dot")
        pix = theme.icon(name, strong).pixmap(icon_size, icon_size)
        painter.drawPixmap(int(pill.left() + 8), int(pill.center().y() - icon_size / 2), pix)
        painter.setFont(font)
        painter.setPen(QColor(strong))
        text_rect = QRectF(pill.left() + 12 + icon_size, pill.top(), pill_w, pill.height())
        painter.drawText(text_rect, int(Qt.AlignmentFlag.AlignVCenter), label)
        if detail:
            painter.setFont(option.font)
            selected = bool(option.state & QStyle.StateFlag.State_Selected)
            painter.setPen(QColor(p.selection_text if selected else p.text_muted))
            rest = QRectF(pill.right() + 8, r.top(), r.right() - pill.right() - 8, r.height())
            elided = QFontMetrics(option.font).elidedText(
                detail, Qt.TextElideMode.ElideRight, int(rest.width())
            )
            painter.drawText(rest, int(Qt.AlignmentFlag.AlignVCenter), elided)
        painter.restore()

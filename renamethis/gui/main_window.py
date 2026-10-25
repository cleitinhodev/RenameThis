"""Janela principal do RenameThis."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from PySide6.QtCore import QSettings, Qt, QTimer, Slot
from PySide6.QtGui import QAction, QActionGroup, QGuiApplication, QIcon, QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSplitter,
    QStyle,
    QTableView,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .. import __version__
from ..core import (
    ConflictPolicy,
    Journal,
    Plan,
    Preset,
    ScanError,
    ScanOptions,
    SortKey,
    SortOptions,
    Status,
    apply_plan,
    build_plan,
    load_preset,
    metadata,
    recover_incomplete,
    save_preset,
    scan,
    sort_entries,
    undo_last,
)
from ..core.executor import ApplyResult
from ..core.journal import default_data_dir
from ..core.rules import RULE_TYPES, Rule
from ..core.scanner import parse_ext_list
from ..i18n import LANGUAGES, error_text, get_language, set_language, tr
from .dialogs import HistoryDialog
from .preview_model import COLUMNS, PreviewModel
from .resources import resource_path
from .rule_editor import RuleEditor
from .workers import start_worker

RULE_ROLE = Qt.ItemDataRole.UserRole + 1


def describe_rule(rule: Rule) -> str:
    params: dict[str, Any] = rule.to_dict()
    for spec in rule.FIELDS:
        if spec.kind == "choice":
            params[f"{spec.name}_label"] = tr(f"choice.{getattr(rule, spec.name)}")
    text = tr(f"desc.{rule.type}", **params).strip()
    return text if len(text) <= 60 else text[:57] + "…"


class MainWindow(QMainWindow):
    def __init__(
        self,
        settings: QSettings | None = None,
        journal: Journal | None = None,
        check_incomplete: bool = True,
    ) -> None:
        super().__init__()
        self.settings = settings or QSettings("CleitinhoDEV", "RenameThis")
        self.journal = journal or Journal()
        self.rules: list[Rule] = []
        self.scan_opts = ScanOptions()
        self.sort_opts = SortOptions()
        self.conflict = ConflictPolicy.SUFFIX
        self.folder = ""
        self.plan: Plan | None = None
        self._entries: list = []
        self._entries_key: tuple | None = None
        self._need_rescan = True
        self._running = False
        self._thread = None
        self._worker = None
        self._selected_rule = -1
        self._updating_list = False
        self._scan_error: str | None = None
        self._last_undoable = None
        self.last_result = None

        self.model = PreviewModel(self)
        self.preview_timer = QTimer(self, singleShot=True, interval=200)
        self.preview_timer.timeout.connect(self.refresh_preview)

        icon_path = resource_path("Design/icone.ico")
        if icon_path:
            self.setWindowIcon(QIcon(str(icon_path)))
        self.setAcceptDrops(True)
        self._restore_session()
        self._refresh_undo_state()
        self._build_ui()
        geometry = self.settings.value("geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)
        else:
            self.resize(1240, 780)
        hints = QGuiApplication.styleHints()
        if hasattr(hints, "colorSchemeChanged"):
            hints.colorSchemeChanged.connect(lambda *_: self.model.retranslate())
        self.refresh_preview()
        if check_incomplete:
            QTimer.singleShot(0, self._check_incomplete)

    # ================================================================ diálogos
    # Todas as caixas de diálogo passam por aqui (facilita testes automatizados)
    def ask(self, title: str, text: str, informative: str = "", ok_text: str = "") -> bool:
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle(title)
        box.setText(text)
        if informative:
            box.setInformativeText(informative)
        if ok_text:
            yes = box.addButton(ok_text, QMessageBox.ButtonRole.AcceptRole)
        else:
            yes = box.addButton(QMessageBox.StandardButton.Yes)
        cancel = box.addButton(QMessageBox.StandardButton.Cancel)
        box.setDefaultButton(cancel)  # segurança: Enter não confirma por engano
        box.exec()
        return box.clickedButton() is yes

    def notify(self, kind: str, title: str, text: str, details: str = "") -> None:
        icon = {
            "info": QMessageBox.Icon.Information,
            "warning": QMessageBox.Icon.Warning,
            "error": QMessageBox.Icon.Critical,
        }[kind]
        box = QMessageBox(icon, title, text, QMessageBox.StandardButton.Ok, self)
        if details:
            box.setDetailedText(details)
        box.exec()

    # ================================================================ estado
    def current_preset(self) -> Preset:
        return Preset(
            rules=copy.deepcopy(self.rules),
            scan=copy.deepcopy(self.scan_opts),
            sort=copy.deepcopy(self.sort_opts),
            conflict=self.conflict,
        )

    def apply_preset(self, preset: Preset) -> None:
        self.rules = list(preset.rules)
        self.scan_opts = preset.scan
        self.sort_opts = preset.sort
        self.conflict = ConflictPolicy(preset.conflict)
        self._selected_rule = 0 if self.rules else -1

    def _restore_session(self) -> None:
        self.folder = str(self.settings.value("folder", "") or "")
        raw = self.settings.value("session")
        if raw:
            try:
                self.apply_preset(Preset.from_dict(json.loads(raw)))
            except (ValueError, TypeError, KeyError):
                pass

    def _save_session(self) -> None:
        self.settings.setValue("folder", self.folder)
        self.settings.setValue("session", json.dumps(self.current_preset().to_dict()))
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("language", get_language())

    def closeEvent(self, event) -> None:  # noqa: N802
        if self._running:
            self.notify("warning", tr("app.title"), tr("busy"))
            event.ignore()
            return
        self._save_session()
        super().closeEvent(event)

    # ================================================================ interface
    def _build_ui(self) -> None:
        """(Re)constrói a interface a partir do estado — usado também ao trocar de idioma."""
        self.setWindowTitle(f"{tr('app.title')} — {tr('app.tagline')}")
        self._build_menus()
        old = self.centralWidget()
        central = QWidget()
        root = QVBoxLayout(central)

        # --- pasta
        top = QHBoxLayout()
        top.addWidget(QLabel(tr("folder.label")))
        self.folder_edit = QLineEdit(self.folder)
        self.folder_edit.setPlaceholderText(tr("folder.placeholder"))
        self.folder_edit.setClearButtonEnabled(True)
        self.folder_edit.setAcceptDrops(False)  # o drop vai para a janela
        self.folder_edit.textChanged.connect(self._on_folder_text)
        top.addWidget(self.folder_edit, 1)
        browse = QPushButton(tr("folder.browse"))
        browse.clicked.connect(self.browse_folder)
        top.addWidget(browse)
        refresh = QToolButton()
        refresh.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_BrowserReload))
        refresh.setToolTip(tr("folder.refresh"))
        refresh.clicked.connect(self.rescan)
        top.addWidget(refresh)
        self.top_bar = QWidget()
        self.top_bar.setLayout(top)
        top.setContentsMargins(0, 0, 0, 0)
        root.addWidget(self.top_bar)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.left_panel = self._build_left_panel()
        splitter.addWidget(self.left_panel)
        splitter.addWidget(self._build_preview_panel())
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([430, 810])
        root.addWidget(splitter, 1)

        # --- barra inferior
        bottom = QHBoxLayout()
        self.summary_label = QLabel()
        self.summary_label.setWordWrap(True)
        bottom.addWidget(self.summary_label, 1)
        self.progress = QProgressBar()
        self.progress.setMaximumWidth(220)
        self.progress.setVisible(False)
        bottom.addWidget(self.progress)
        self.undo_button = QPushButton(tr("button.undo"))
        self.undo_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowBack))
        self.undo_button.clicked.connect(self.undo)
        bottom.addWidget(self.undo_button)
        self.apply_button = QPushButton(tr("button.apply"))
        self.apply_button.setToolTip(tr("button.apply_tip"))
        self.apply_button.setMinimumHeight(34)
        self.apply_button.setMinimumWidth(140)
        font = self.apply_button.font()
        font.setBold(True)
        self.apply_button.setFont(font)
        self.apply_button.clicked.connect(lambda: self.start_apply())
        bottom.addWidget(self.apply_button)
        root.addLayout(bottom)

        self.setCentralWidget(central)
        if old is not None:
            old.deleteLater()
        self._refresh_rule_list(self._selected_rule)
        self.model.retranslate()
        self._update_summary()
        self._update_buttons()

    def _build_menus(self) -> None:
        bar = self.menuBar()
        bar.clear()
        m_file = bar.addMenu(tr("menu.file"))
        self.act_open = m_file.addAction(tr("menu.open_folder"), self.browse_folder)
        self.act_open.setShortcut(QKeySequence.StandardKey.Open)
        m_file.addSeparator()
        self.act_load = m_file.addAction(tr("menu.load_preset"), self.load_preset_dialog)
        self.act_save = m_file.addAction(tr("menu.save_preset"), self.save_preset_dialog)
        m_file.addSeparator()
        m_file.addAction(tr("menu.history"), self.show_history)
        m_file.addSeparator()
        act_quit = m_file.addAction(tr("menu.quit"), self.close)
        act_quit.setShortcut(QKeySequence.StandardKey.Quit)

        m_edit = bar.addMenu(tr("menu.edit"))
        self.act_undo = m_edit.addAction(tr("menu.undo"), self.undo)
        self.act_recover = m_edit.addAction(tr("menu.recover"), self.recover)

        m_lang = bar.addMenu(tr("menu.language"))
        group = QActionGroup(self)
        group.setExclusive(True)
        for code, name in LANGUAGES.items():
            act = QAction(name, self, checkable=True)
            act.setChecked(code == get_language())
            act.triggered.connect(lambda _c=False, c=code: self.change_language(c))
            group.addAction(act)
            m_lang.addAction(act)

        m_help = bar.addMenu(tr("menu.help"))
        m_help.addAction(tr("menu.tokens"), self.show_tokens)
        m_help.addAction(tr("menu.about"), self.show_about)

    def _build_left_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)

        # --- regras
        box = QGroupBox(tr("rules.group"))
        v = QVBoxLayout(box)
        self.rule_list = QListWidget()
        self.rule_list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.rule_list.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.rule_list.setToolTip(tr("rules.enabled_tip"))
        self.rule_list.setMinimumHeight(130)
        self.rule_list.currentRowChanged.connect(self._on_rule_selected)
        self.rule_list.itemChanged.connect(self._on_rule_item_changed)
        self.rule_list.model().rowsMoved.connect(self._on_rules_moved)
        self.rule_list.model().rowsInserted.connect(self._on_rules_moved)
        v.addWidget(self.rule_list)

        buttons = QHBoxLayout()
        add = QToolButton()
        add.setText("＋ " + tr("rules.add"))
        add.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        add.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(add)
        for kind in RULE_TYPES:
            menu.addAction(tr(f"rule.{kind}"), lambda k=kind: self.add_rule(k))
        add.setMenu(menu)
        self.add_rule_button = add
        buttons.addWidget(add)
        buttons.addStretch(1)
        sp = QStyle.StandardPixmap
        for icon, tip, slot in (
            (sp.SP_ArrowUp, "rules.up", lambda: self.move_rule(-1)),
            (sp.SP_ArrowDown, "rules.down", lambda: self.move_rule(1)),
            (sp.SP_FileDialogNewFolder, "rules.duplicate", self.duplicate_rule),
            (sp.SP_TrashIcon, "rules.remove", self.remove_rule),
            (sp.SP_DialogResetButton, "rules.clear", self.clear_rules),
        ):
            b = QToolButton()
            b.setIcon(self.style().standardIcon(icon))
            b.setToolTip(tr(tip))
            b.clicked.connect(slot)
            buttons.addWidget(b)
        v.addLayout(buttons)
        layout.addWidget(box, 2)

        # --- editor da regra
        ebox = QGroupBox(tr("editor.group"))
        ev = QVBoxLayout(ebox)
        self.editor_area = QScrollArea()
        self.editor_area.setWidgetResizable(True)
        self.editor_area.setFrameShape(QScrollArea.Shape.NoFrame)
        ev.addWidget(self.editor_area)
        layout.addWidget(ebox, 3)

        # --- opções
        obox = QGroupBox(tr("options.group"))
        form = QFormLayout(obox)
        self.sort_combo = QComboBox()
        for key in SortKey:
            self.sort_combo.addItem(tr(f"sort.{key.value}"), key.value)
        self.sort_combo.setCurrentIndex(list(SortKey).index(self.sort_opts.key))
        self.sort_combo.currentIndexChanged.connect(self._on_sort_changed)
        self.desc_check = QCheckBox(tr("options.desc"))
        self.desc_check.setChecked(self.sort_opts.descending)
        self.desc_check.toggled.connect(self._on_sort_changed)
        sort_row = QHBoxLayout()
        sort_row.addWidget(self.sort_combo, 1)
        sort_row.addWidget(self.desc_check)
        form.addRow(tr("options.sort"), sort_row)

        self.ext_edit = QLineEdit(", ".join(self.scan_opts.extensions))
        self.ext_edit.setPlaceholderText(tr("options.only_ext_ph"))
        self.ext_edit.textChanged.connect(self._on_scan_changed)
        form.addRow(tr("options.only_ext"), self.ext_edit)
        self.exclude_edit = QLineEdit(", ".join(self.scan_opts.exclude_extensions))
        self.exclude_edit.setPlaceholderText(tr("options.exclude_ext_ph"))
        self.exclude_edit.textChanged.connect(self._on_scan_changed)
        form.addRow(tr("options.exclude_ext"), self.exclude_edit)

        self.checks: dict[str, QCheckBox] = {}
        grid = QGridLayout()
        for n, (attr, key) in enumerate(
            (
                ("include_files", "options.files"),
                ("include_dirs", "options.dirs"),
                ("recursive", "options.recursive"),
                ("include_hidden", "options.hidden"),
                ("include_system", "options.system"),
            )
        ):
            cb = QCheckBox(tr(key))
            cb.setChecked(bool(getattr(self.scan_opts, attr)))
            cb.toggled.connect(self._on_scan_changed)
            self.checks[attr] = cb
            if attr == "include_system":
                grid.addWidget(cb, 2, 0, 1, 2)
            else:
                grid.addWidget(cb, n // 2, n % 2)
        form.addRow(grid)

        self.conflict_combo = QComboBox()
        for policy in ConflictPolicy:
            self.conflict_combo.addItem(tr(f"conflict.{policy.value}"), policy.value)
        self.conflict_combo.setCurrentIndex(list(ConflictPolicy).index(self.conflict))
        self.conflict_combo.currentIndexChanged.connect(self._on_conflict_changed)
        form.addRow(tr("options.conflict"), self.conflict_combo)
        layout.addWidget(obox, 0)
        return panel

    def _build_preview_panel(self) -> QWidget:
        panel = QGroupBox(tr("preview.group"))
        v = QVBoxLayout(panel)
        row = QHBoxLayout()
        self.only_changes_check = QCheckBox(tr("preview.only_changes"))
        self.only_changes_check.setChecked(self.model.only_changes)
        self.only_changes_check.toggled.connect(self.model.set_only_changes)
        row.addWidget(self.only_changes_check)
        row.addStretch(1)
        v.addLayout(row)
        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.setAlternatingRowColors(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setWordWrap(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(COLUMNS.index("index"), QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(COLUMNS.index("status"), QHeaderView.ResizeMode.Stretch)
        header.resizeSection(COLUMNS.index("original"), 240)
        header.resizeSection(COLUMNS.index("new"), 260)
        header.resizeSection(COLUMNS.index("folder"), 90)
        v.addWidget(self.table)
        return panel

    # ================================================================ regras
    def _refresh_rule_list(self, select: int = -1) -> None:
        self._updating_list = True
        self.rule_list.clear()
        for i, rule in enumerate(self.rules):
            item = QListWidgetItem(f"{i + 1}. {tr('rule.' + rule.type)} — {describe_rule(rule)}")
            item.setData(RULE_ROLE, i)  # índice (int sobrevive ao arrastar e soltar)
            item.setFlags(
                item.flags() | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsDragEnabled
            )
            item.setCheckState(Qt.CheckState.Checked if rule.enabled else Qt.CheckState.Unchecked)
            self.rule_list.addItem(item)
        self._updating_list = False
        if self.rules:
            select = min(max(select, 0), len(self.rules) - 1)
            self.rule_list.setCurrentRow(select)
        self._show_editor(select if self.rules else -1)

    def _show_editor(self, row: int) -> None:
        self._selected_rule = row
        if 0 <= row < len(self.rules):
            editor = RuleEditor(self.rules[row])
            editor.changed.connect(self._on_rule_edited)
            self.editor_area.setWidget(editor)
        else:
            label = QLabel(tr("editor.none") if self.rules else tr("rules.empty_hint"))
            label.setWordWrap(True)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.editor_area.setWidget(label)

    @Slot(int)
    def _on_rule_selected(self, row: int) -> None:
        if not self._updating_list and row != self._selected_rule:
            self._show_editor(row)

    def _on_rule_item_changed(self, item: QListWidgetItem) -> None:
        if self._updating_list:
            return
        idx = item.data(RULE_ROLE)
        rule = self.rules[idx] if isinstance(idx, int) and 0 <= idx < len(self.rules) else None
        if rule is not None:
            enabled = item.checkState() == Qt.CheckState.Checked
            if rule.enabled != enabled:
                rule.enabled = enabled
                self.schedule_preview()

    def _on_rules_moved(self, *_args) -> None:
        if not self._updating_list:
            QTimer.singleShot(0, self._sync_rules_from_list)

    def _sync_rules_from_list(self) -> None:
        """Lê a nova ordem depois de arrastar e soltar na lista."""
        order = [self.rule_list.item(i).data(RULE_ROLE) for i in range(self.rule_list.count())]
        if sorted(o for o in order if isinstance(o, int)) != list(range(len(self.rules))):
            self._refresh_rule_list(self._selected_rule)  # estado inesperado: restaura
            return
        if order == list(range(len(self.rules))):
            return
        current = self.rule_list.currentRow()
        self.rules = [self.rules[i] for i in order]
        self._refresh_rule_list(current)
        self.schedule_preview()

    def _on_rule_edited(self) -> None:
        row = self._selected_rule
        item = self.rule_list.item(row)
        if item is not None:
            self._updating_list = True
            rule = self.rules[row]
            item.setText(f"{row + 1}. {tr('rule.' + rule.type)} — {describe_rule(rule)}")
            self._updating_list = False
        self.schedule_preview()

    def add_rule(self, kind: str) -> None:
        self.rules.append(RULE_TYPES[kind]())
        self._refresh_rule_list(len(self.rules) - 1)
        self.schedule_preview()

    def remove_rule(self) -> None:
        row = self.rule_list.currentRow()
        if 0 <= row < len(self.rules):
            del self.rules[row]
            self._refresh_rule_list(row)
            self.schedule_preview()

    def duplicate_rule(self) -> None:
        row = self.rule_list.currentRow()
        if 0 <= row < len(self.rules):
            self.rules.insert(row + 1, copy.deepcopy(self.rules[row]))
            self._refresh_rule_list(row + 1)
            self.schedule_preview()

    def move_rule(self, delta: int) -> None:
        row = self.rule_list.currentRow()
        new = row + delta
        if 0 <= row < len(self.rules) and 0 <= new < len(self.rules):
            self.rules[row], self.rules[new] = self.rules[new], self.rules[row]
            self._refresh_rule_list(new)
            self.schedule_preview()

    def clear_rules(self) -> None:
        if self.rules and self.ask(tr("app.title"), tr("rules.clear_confirm")):
            self.rules = []
            self._refresh_rule_list(-1)
            self.schedule_preview()

    # ================================================================ opções
    def _on_folder_text(self, text: str) -> None:
        self.folder = text.strip()
        self._need_rescan = True
        self.preview_timer.start(400)

    def set_folder(self, folder: str) -> None:
        self.folder_edit.setText(folder)  # dispara _on_folder_text
        self.refresh_preview()

    def browse_folder(self) -> None:
        start = self.folder if Path(self.folder or ".").is_dir() else str(Path.home())
        folder = QFileDialog.getExistingDirectory(self, tr("folder.dialog"), start)
        if folder:
            self.set_folder(folder)

    def _on_sort_changed(self, *_args) -> None:
        self.sort_opts = SortOptions(
            SortKey(self.sort_combo.currentData()),
            self.desc_check.isChecked(),
            self.sort_opts.folders_first,
        )
        self.schedule_preview()

    def _on_scan_changed(self, *_args) -> None:
        values = {attr: cb.isChecked() for attr, cb in self.checks.items()}
        self.scan_opts = ScanOptions(
            **values,
            extensions=parse_ext_list(self.ext_edit.text()),
            exclude_extensions=parse_ext_list(self.exclude_edit.text()),
        )
        self.schedule_preview(rescan=True)

    def _on_conflict_changed(self, *_args) -> None:
        self.conflict = ConflictPolicy(self.conflict_combo.currentData())
        self.schedule_preview()

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        if not self._running and event.mimeData().hasUrls():
            if any(u.isLocalFile() for u in event.mimeData().urls()):
                event.acceptProposedAction()
                return
        event.ignore()

    def dropEvent(self, event) -> None:  # noqa: N802
        for url in event.mimeData().urls():
            if url.isLocalFile():
                path = Path(url.toLocalFile())
                self.set_folder(str(path if path.is_dir() else path.parent))
                event.acceptProposedAction()
                return

    # ================================================================ prévia
    def schedule_preview(self, rescan: bool = False) -> None:
        if rescan:
            self._need_rescan = True
        self.preview_timer.start(200)

    def rescan(self) -> None:
        self._need_rescan = True
        self.refresh_preview()

    @Slot()
    def refresh_preview(self) -> None:
        if self._running:
            return
        self.preview_timer.stop()
        self._scan_error = None
        folder = self.folder
        if not folder:
            self.plan = None
            self.model.set_plan(None)
            self._update_summary()
            self._update_buttons()
            return
        key = (folder, json.dumps(self.scan_opts.to_dict(), sort_keys=True))
        if self._need_rescan or key != self._entries_key:
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            try:
                self._entries = scan(folder, self.scan_opts)
                self._entries_key = key
                self._need_rescan = False
            except ScanError as exc:
                self._entries, self._entries_key = [], None
                self._scan_error = error_text(exc.code, path=exc.path)
            finally:
                QApplication.restoreOverrideCursor()
        if self._scan_error:
            self.plan = None
            self.model.set_plan(None)
        else:
            entries = sort_entries(self._entries, self.sort_opts)
            self.plan = build_plan(entries, self.rules, self.conflict)
            try:
                root = Path(folder).expanduser().resolve()
            except OSError:
                root = None
            self.model.set_plan(self.plan, root)
        self._update_summary()
        self._update_buttons()

    def _update_summary(self) -> None:
        if not hasattr(self, "summary_label"):
            return
        style = ""
        if self._running:
            text = tr("summary.running")
        elif getattr(self, "_scan_error", None):
            text, style = self._scan_error, "color: #d9534f;"
        elif not self.folder:
            text = tr("summary.no_folder")
        elif self.plan is None or not self.plan.items:
            text = tr("summary.empty")
        elif not any(r.enabled for r in self.rules):
            text = tr("summary.no_rules", total=len(self.plan.items))
        else:
            s = self.plan.summary()
            text = tr(
                "summary.counts",
                total=s["total"],
                rename=s["ok"] + s["warning"],
                skipped=s["skipped"],
                errors=s["error"],
            )
            if self.plan.has_errors:
                text += "  —  " + tr("summary.has_errors")
                style = "color: #d9534f; font-weight: bold;"
        self.summary_label.setText(text)
        self.summary_label.setStyleSheet(style)

    def _update_buttons(self) -> None:
        if not hasattr(self, "apply_button"):
            return
        can_apply = (
            not self._running
            and self.plan is not None
            and not self.plan.has_errors
            and bool(self.plan.to_rename)
        )
        self.apply_button.setEnabled(can_apply)
        last = None if self._running else self._last_undoable
        self.undo_button.setEnabled(last is not None)
        self.act_undo.setEnabled(last is not None)
        if last is not None:
            self.undo_button.setToolTip(
                tr(
                    "undo.tooltip",
                    count=last.count,
                    date=last.created_dt.strftime("%d/%m/%Y %H:%M"),
                )
            )
        else:
            self.undo_button.setToolTip(tr("undo.none"))
        for w in (self.left_panel, self.top_bar):
            w.setEnabled(not self._running)
        for act in (self.act_open, self.act_load, self.act_recover):
            act.setEnabled(not self._running)

    def _refresh_undo_state(self) -> None:
        self._last_undoable = self.journal.last_undoable()

    # ================================================================ execução
    def _set_running(self, running: bool) -> None:
        self._running = running
        self.progress.setVisible(running)
        self.progress.setValue(0)
        self._update_summary()
        self._update_buttons()

    def _start(self, fn, on_finished) -> None:
        self._set_running(True)
        self._thread, self._worker = start_worker(self, fn, self._on_progress, on_finished)

    @Slot(int, int)
    def _on_progress(self, done: int, total: int) -> None:
        self.progress.setMaximum(max(total, 1))
        self.progress.setValue(done)

    def start_apply(self, confirm: bool = True) -> None:
        if self._running:
            return
        if self.preview_timer.isActive():
            self.refresh_preview()
        plan = self.plan
        if plan is None or plan.has_errors or not plan.to_rename:
            self._update_buttons()
            return
        count = len(plan.to_rename)
        if confirm:
            info = [tr("confirm.folder", folder=self.folder)]
            if plan.count(Status.SKIPPED):
                info.append(tr("confirm.skipped", count=plan.count(Status.SKIPPED)))
            if plan.count(Status.WARNING):
                info.append(tr("confirm.warnings", count=plan.count(Status.WARNING)))
            info.append(tr("confirm.undo_hint"))
            if not self.ask(
                tr("confirm.title"),
                tr("confirm.text", count=count),
                "\n".join(info),
                tr("button.apply"),
            ):
                return
        journal = self.journal
        self._start(lambda progress: apply_plan(plan, journal, progress), self._on_apply_done)

    def _result_message(self, result: ApplyResult) -> tuple[str, str, str]:
        if result.ok:
            parts = [tr("result.ok", renamed=len(result.renamed))]
            if result.skipped:
                parts.append(tr("result.skipped", skipped=result.skipped))
            return "info", "\n".join(parts), ""
        reason = error_text(
            result.error_code or "unexpected",
            path=result.error_path or "",
            detail=result.error_detail or "",
        )
        text = tr("result.failed") + "\n\n" + tr("result.reason", reason=reason)
        if result.rollback_errors:
            text += "\n\n" + tr("result.rollback_failed")
            return "error", text, "\n".join(result.rollback_errors)
        return "warning", text, ""

    @Slot(object)
    def _on_apply_done(self, result) -> None:
        self._set_running(False)
        if isinstance(result, Exception):
            self.notify("error", tr("error.title"), error_text("unexpected", detail=repr(result)))
        else:
            kind, text, details = self._result_message(result)
            self.notify(kind, tr("result.title"), text, details)
        self.last_result = result
        self._refresh_undo_state()
        self.rescan()

    def undo(self) -> None:
        if self._running:
            return
        entry = self.journal.last_undoable()
        if entry is None:
            self.notify("info", tr("undo.confirm_title"), tr("undo.none"))
            return
        text = tr(
            "undo.confirm",
            count=entry.count,
            date=entry.created_dt.strftime("%d/%m/%Y %H:%M:%S"),
            folder=", ".join(entry.folders[:3]),
        )
        if not self.ask(tr("undo.confirm_title"), text, ok_text=tr("button.undo")):
            return
        journal = self.journal
        self._start(lambda progress: undo_last(journal, progress), self._on_undo_done)

    @Slot(object)
    def _on_undo_done(self, result) -> None:
        self._set_running(False)
        self.last_result = result
        if result is None:
            self.notify("info", tr("undo.confirm_title"), tr("undo.none"))
        elif isinstance(result, Exception):
            self.notify("error", tr("error.title"), error_text("unexpected", detail=repr(result)))
        elif result.ok:
            self.notify("info", tr("undo.confirm_title"), tr("undo.ok", count=len(result.renamed)))
        else:
            kind, text, details = self._result_message(result)
            self.notify(kind, tr("undo.confirm_title"), text, details)
        self._refresh_undo_state()
        self.rescan()

    def _check_incomplete(self) -> None:
        if self.journal.incomplete() and self.ask(tr("recover.title"), tr("recover.ask")):
            self.recover(confirm=False)

    def recover(self, confirm: bool = True) -> None:
        if self._running:
            return
        if not self.journal.incomplete():
            if confirm:
                self.notify("info", tr("recover.title"), tr("recover.none"))
            return
        restored, errors = recover_incomplete(self.journal)
        if errors:
            self.notify(
                "warning",
                tr("recover.title"),
                tr("recover.done", count=restored) + "\n" + tr("recover.errors"),
                "\n".join(errors),
            )
        else:
            self.notify("info", tr("recover.title"), tr("recover.done", count=restored))
        self._refresh_undo_state()
        self.rescan()

    # ================================================================ outros
    def change_language(self, code: str) -> None:
        if code == get_language():
            return
        set_language(code)
        self.settings.setValue("language", code)
        self._build_ui()
        self.refresh_preview()

    def _presets_dir(self) -> Path:
        d = default_data_dir() / "presets"
        try:
            d.mkdir(parents=True, exist_ok=True)
        except OSError:
            return Path.home()
        return d

    def save_preset_dialog(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            tr("menu.save_preset"),
            str(self._presets_dir() / "preset.json"),
            tr("preset.filter"),
        )
        if not path:
            return
        if not path.lower().endswith(".json"):
            path += ".json"
        preset = self.current_preset()
        preset.name = Path(path).stem
        try:
            save_preset(preset, path)
        except OSError as exc:
            self.notify("error", tr("error.title"), tr("preset.save_error", error=exc))

    def load_preset_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, tr("menu.load_preset"), str(self._presets_dir()), tr("preset.filter")
        )
        if path:
            self.load_preset_file(path)

    def load_preset_file(self, path: str) -> bool:
        try:
            preset = load_preset(path)
        except (OSError, ValueError, TypeError, KeyError) as exc:
            self.notify("error", tr("error.title"), tr("preset.load_error", error=exc))
            return False
        self.apply_preset(preset)
        self._build_ui()
        self.rescan()
        return True

    def show_history(self) -> None:
        HistoryDialog(self.journal, self).exec()

    def show_tokens(self) -> None:
        box = QMessageBox(
            QMessageBox.Icon.Information,
            tr("tokens.title"),
            tr("tokens.text"),
            QMessageBox.StandardButton.Ok,
            self,
        )
        box.setTextFormat(Qt.TextFormat.RichText)
        box.exec()

    def show_about(self) -> None:
        def avail(ok: bool) -> str:
            return tr("about.available") if ok else tr("about.missing")

        QMessageBox.about(
            self,
            tr("about.title"),
            tr(
                "about.text",
                version=__version__,
                pillow=avail(metadata.has_pillow()),
                mutagen=avail(metadata.has_mutagen()),
            ),
        )

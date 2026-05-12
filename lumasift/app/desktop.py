from __future__ import annotations

import html
import json
import logging
import os
import sys
import time
import traceback
from pathlib import Path
from typing import Any

from PySide6.QtCore import QAbstractListModel, QEasingCurve, QModelIndex, QObject, QPropertyAnimation, QSettings, QSize, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QGraphicsOpacityEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListView,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QSpinBox,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from lumasift.analysis.editing_advice import build_selected_editing_advice
from lumasift.core.config import Settings
from lumasift.core.harness import LumaSiftHarness
from lumasift.core.logging_setup import configure_logging
from lumasift.io.preview import create_jpeg_preview
from lumasift.reports.csv_report import write_csv_report
from lumasift.reports.json_report import write_json_report
from lumasift.reports.markdown_report import render_selected_editing_advice_markdown, write_markdown_report
from lumasift.storage.state_db import LumaSiftStateDb


UI_TEXT: dict[str, dict[str, str]] = {
    "zh": {
        "app_title": "LumaSift - 本地 AI 选片",
        "hero_title": "LumaSift",
        "hero_subtitle": "本地优先的 AI 选片工作台",
        "scanned": "已扫描",
        "shown": "已显示",
        "selected": "已选择",
        "mode": "模式",
        "local": "本地",
        "qwen": "Qwen",
        "step_import": "1. 导入",
        "step_import_caption": "选择本地照片文件夹",
        "step_local": "2. 初筛",
        "step_local_caption": "本地预览与快速评分",
        "step_qwen": "3. 深评",
        "step_qwen_caption": "只分析高价值候选",
        "step_edit": "4. 修图",
        "step_edit_caption": "多选生成参数方案",
        "photo_folder": "照片目录",
        "output_folder": "输出目录",
        "browse": "浏览",
        "scan": "扫描",
        "qwen_top": "Qwen",
        "advice_top": "修图",
        "show": "显示",
        "qwen_keys": "密钥",
        "api_placeholder": "可选：多个 Qwen key 用英文逗号分隔，留空则读取 .env",
        "save_keys": "本机保存密钥",
        "cache_note": "仅上传 Top-N 压缩预览，RAW 留在本机。",
        "analyze": "开始分析",
        "cancel": "取消",
        "ready": "就绪",
        "review_board": "选片板",
        "search": "搜索文件名/分类/风格",
        "all_categories": "全部分类",
        "all_labels": "全部标记",
        "unlabeled": "未标记",
        "sort_high": "高分优先",
        "sort_low": "低分优先",
        "sort_rank": "排名",
        "sort_name": "文件名",
        "no_results": "无结果",
        "review_cockpit": "评审",
        "detail_hint": "选中照片后查看评分、理由和修图参数。",
        "keep": "保留",
        "maybe": "待定",
        "reject": "淘汰",
        "editing_plan": "修图方案",
        "open_output": "打开输出",
        "open_contact": "联系表",
        "empty_grid": "选择目录后开始分析",
        "running_grid": "正在分析，结果会自动出现。",
        "empty_filtered": "没有匹配结果，调整筛选条件。",
        "done": "完成",
        "failed": "失败",
        "closing": "正在等待后台任务安全结束...",
        "missing_input_title": "目录不存在",
        "missing_key_title": "缺少 Qwen 密钥",
        "missing_key_body": "Qwen 模式需要 API key。请填入密钥或配置 .env。",
        "no_selection": "未选择照片",
        "select_first": "请先选择一张或多张照片。",
        "no_records": "没有结果",
        "run_first": "请先运行分析。",
    },
    "en": {
        "app_title": "LumaSift - Local AI Photo Curation",
        "hero_title": "LumaSift",
        "hero_subtitle": "Local-first AI photo curation workspace",
        "scanned": "Scanned",
        "shown": "Shown",
        "selected": "Selected",
        "mode": "Mode",
        "local": "Local",
        "qwen": "Qwen",
        "step_import": "1. Import",
        "step_import_caption": "Choose local photo folder",
        "step_local": "2. Pre-score",
        "step_local_caption": "Local preview and fast score",
        "step_qwen": "3. Deep review",
        "step_qwen_caption": "Only high-value candidates",
        "step_edit": "4. Edit",
        "step_edit_caption": "Multi-select tuning plan",
        "photo_folder": "Photo folder",
        "output_folder": "Output folder",
        "browse": "Browse",
        "scan": "Scan",
        "qwen_top": "Qwen",
        "advice_top": "Advice",
        "show": "Show",
        "qwen_keys": "Keys",
        "api_placeholder": "Optional: comma-separated Qwen keys. Leave empty to use .env.",
        "save_keys": "Save keys locally",
        "cache_note": "Only Top-N compressed previews are uploaded; RAW stays local.",
        "analyze": "Analyze",
        "cancel": "Cancel",
        "ready": "Ready",
        "review_board": "Review board",
        "search": "Search filename/category/style",
        "all_categories": "All categories",
        "all_labels": "All labels",
        "unlabeled": "unlabeled",
        "sort_high": "Score high to low",
        "sort_low": "Score low to high",
        "sort_rank": "Rank",
        "sort_name": "Filename A-Z",
        "no_results": "No results",
        "review_cockpit": "Review",
        "detail_hint": "Select photos to inspect scores, reasons, and editing parameters.",
        "keep": "Keep",
        "maybe": "Maybe",
        "reject": "Reject",
        "editing_plan": "Editing Plan",
        "open_output": "Open Output",
        "open_contact": "Contact Sheet",
        "empty_grid": "Choose a folder, then analyze",
        "running_grid": "Analysis is running. Results will appear here.",
        "empty_filtered": "No matches. Adjust filters.",
        "done": "Done",
        "failed": "Failed",
        "closing": "Waiting for background tasks to stop safely...",
        "missing_input_title": "Input folder missing",
        "missing_key_title": "Qwen API key missing",
        "missing_key_body": "Qwen mode requires API keys. Enter keys or configure .env.",
        "no_selection": "No selection",
        "select_first": "Select one or more photos first.",
        "no_records": "No records",
        "run_first": "Run an analysis first.",
    },
}


def crash_log_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    root = Path(base) if base else Path.home()
    path = root / "LumaSift" / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def install_crash_logging() -> None:
    log_path = crash_log_dir() / "crash.log"
    logging.basicConfig(
        filename=str(log_path),
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    def excepthook(exc_type: type[BaseException], exc: BaseException, tb: Any) -> None:
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write("\n--- unhandled exception ---\n")
            traceback.print_exception(exc_type, exc, tb, file=handle)
        sys.__excepthook__(exc_type, exc, tb)

    sys.excepthook = excepthook


class AnalysisWorker(QObject):
    finished = Signal(dict)
    failed = Signal(str)
    progress = Signal(str, int, int)

    def __init__(self, settings: Settings, run_id: str) -> None:
        super().__init__()
        self.settings = settings
        self.run_id = run_id

    def run(self) -> None:
        try:
            configure_logging(self.settings.output_dir)
            result = LumaSiftHarness(
                settings=self.settings,
                run_id=self.run_id,
                progress_callback=lambda stage, current, total: self.progress.emit(stage, current, total),
            ).run()
            report = json.loads(result.report_json.read_text(encoding="utf-8"))
            self.finished.emit({"summary": result.summary, "report": report, "output_dir": str(self.settings.output_dir)})
        except Exception as exc:  # noqa: BLE001 - GUI must show failures instead of crashing.
            logging.exception("Analysis failed")
            self.failed.emit(str(exc))


class ThumbnailWorker(QObject):
    thumbnail_ready = Signal(int, int, str)
    finished = Signal()

    def __init__(self, jobs: list[tuple[int, dict[str, Any]]], output_dir: Path, generation: int, max_side: int = 360) -> None:
        super().__init__()
        self.jobs = jobs
        self.output_dir = output_dir
        self.generation = generation
        self.max_side = max_side
        self.cancelled = False

    def stop(self) -> None:
        self.cancelled = True

    def run(self) -> None:
        preview_dir = self.output_dir / "gui_previews"
        for row, record in self.jobs:
            if self.cancelled:
                break
            try:
                preview_path = create_jpeg_preview(Path(record["path"]), preview_dir, max_side=self.max_side)
                self.thumbnail_ready.emit(self.generation, row, str(preview_path))
            except Exception:
                self.thumbnail_ready.emit(self.generation, row, "")
        self.finished.emit()


class PhotoListModel(QAbstractListModel):
    def __init__(self, placeholder_icon: QIcon) -> None:
        super().__init__()
        self.records: list[dict[str, Any]] = []
        self.icons: dict[int, QIcon] = {}
        self.placeholder_icon = placeholder_icon
        self.empty_message = "Drop into the workflow by choosing a folder, then run analysis."

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802 - Qt API
        if parent.isValid():
            return 0
        return len(self.records) if self.records else 1

    def data(self, index: QModelIndex, role: int = int(Qt.ItemDataRole.DisplayRole)) -> Any:
        if not index.isValid():
            return None
        row = index.row()
        if not self.records:
            if role == int(Qt.ItemDataRole.DisplayRole):
                return self.empty_message
            return None
        if row < 0 or row >= len(self.records):
            return None
        record = self.records[row]
        if role == int(Qt.ItemDataRole.UserRole):
            return record
        if role == int(Qt.ItemDataRole.DecorationRole):
            return self.icons.get(row, self.placeholder_icon)
        if role == int(Qt.ItemDataRole.DisplayRole):
            score = float(record.get("final_selection_score", 0) or 0)
            category = str(record.get("category", "")).replace("_", " ")
            style = str(record.get("recommended_style", "")).replace("_", " ")
            user_label = str(record.get("user_label", "") or "unlabeled")
            return f"#{record.get('rank')} | {score:.1f} | {user_label}\n{record.get('filename')}\n{category}\n{style}"
        if role == int(Qt.ItemDataRole.ToolTipRole):
            return str(record.get("path", ""))
        return None

    def flags(self, index: QModelIndex) -> Qt.ItemFlag:
        if not index.isValid() or not self.records:
            return Qt.ItemFlag.NoItemFlags
        return Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable

    def set_records(self, records: list[dict[str, Any]], empty_message: str | None = None) -> None:
        self.beginResetModel()
        self.records = records
        self.icons.clear()
        if empty_message:
            self.empty_message = empty_message
        self.endResetModel()

    def set_icon(self, row: int, icon: QIcon) -> None:
        if row < 0 or row >= len(self.records):
            return
        self.icons[row] = icon
        index = self.index(row, 0)
        self.dataChanged.emit(index, index, [int(Qt.ItemDataRole.DecorationRole)])

    def refresh_row(self, row: int) -> None:
        if row < 0 or row >= len(self.records):
            return
        index = self.index(row, 0)
        self.dataChanged.emit(index, index, [int(Qt.ItemDataRole.DisplayRole), int(Qt.ItemDataRole.UserRole)])


class LumaSiftWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.resize(1440, 900)
        self.records: list[dict[str, Any]] = []
        self.output_dir = Path("./outputs/gui")
        self.settings_store = QSettings("LumaSift", "LumaSift")
        self.language = str(self.settings_store.value("language", "zh"))
        if self.language not in UI_TEXT:
            self.language = "zh"
        self.worker_thread: QThread | None = None
        self.worker: AnalysisWorker | None = None
        self.thumbnail_thread: QThread | None = None
        self.thumbnail_worker: ThumbnailWorker | None = None
        self.visible_records: list[dict[str, Any]] = []
        self.photo_model: PhotoListModel | None = None
        self.thumbnail_generation = 0
        self.loaded_thumbnail_rows: set[int] = set()
        self.pending_thumbnail_rows: set[int] = set()
        self.workflow_steps: dict[str, QFrame] = {}
        self.stat_labels: dict[str, QLabel] = {}
        self.workflow_labels: dict[str, tuple[QLabel, QLabel]] = {}
        self.static_labels: dict[str, QLabel] = {}
        self._animations: list[QPropertyAnimation] = []
        self.state_db = LumaSiftStateDb()
        self.current_run_id = ""
        self.pending_close = False
        self.allow_close = False
        self._build_ui()
        self._load_preferences()
        self._apply_style()
        self._retranslate_ui()
        self._update_workflow("import")
        self._update_dashboard()

    def _t(self, key: str) -> str:
        return UI_TEXT.get(self.language, UI_TEXT["zh"]).get(key, key)

    def _change_language(self, label: str) -> None:
        self.language = "en" if label == "English" else "zh"
        self.settings_store.setValue("language", self.language)
        self._retranslate_ui()

    def _retranslate_ui(self) -> None:
        self.setWindowTitle(self._t("app_title"))
        if hasattr(self, "language_combo"):
            self.language_combo.blockSignals(True)
            self.language_combo.setCurrentText("English" if self.language == "en" else "中文")
            self.language_combo.blockSignals(False)
        if hasattr(self, "title_label"):
            self.title_label.setText(self._t("hero_title"))
        if hasattr(self, "subtitle_label"):
            self.subtitle_label.setText(self._t("hero_subtitle"))
        for key in ("scanned", "shown", "selected", "mode"):
            label = self.static_labels.get(f"stat_{key}")
            if label:
                label.setText(self._t(key))
        step_keys = {
            "import": ("step_import", "step_import_caption"),
            "local": ("step_local", "step_local_caption"),
            "qwen": ("step_qwen", "step_qwen_caption"),
            "edit": ("step_edit", "step_edit_caption"),
        }
        for step, (title_key, caption_key) in step_keys.items():
            labels = self.workflow_labels.get(step)
            if labels:
                labels[0].setText(self._t(title_key))
                labels[1].setText(self._t(caption_key))
        for key, label in [
            ("photo_folder", self.static_labels.get("photo_folder")),
            ("output_folder", self.static_labels.get("output_folder")),
            ("qwen_keys", self.static_labels.get("qwen_keys")),
            ("review_board", self.static_labels.get("review_board")),
            ("review_cockpit", self.static_labels.get("review_cockpit")),
        ]:
            if label:
                label.setText(self._t(key))
        if hasattr(self, "browse_input_button"):
            self.browse_input_button.setText(self._t("browse"))
            self.browse_output_button.setText(self._t("browse"))
        mini_map = {
            "mini_Mode": "mode",
            "mini_Scan": "scan",
            "mini_Qwen Top": "qwen_top",
            "mini_Advice Top": "advice_top",
            "mini_Show": "show",
        }
        for key, text_key in mini_map.items():
            if key in self.static_labels:
                self.static_labels[key].setText(self._t(text_key))
        if hasattr(self, "api_key_edit"):
            mode_value = self.mode_combo.currentData() or "local_only"
            self.mode_combo.blockSignals(True)
            self.mode_combo.clear()
            self.mode_combo.addItem(self._t("local"), "local_only")
            self.mode_combo.addItem(self._t("qwen"), "qwen_vision")
            mode_index = self.mode_combo.findData(mode_value)
            self.mode_combo.setCurrentIndex(mode_index if mode_index >= 0 else 0)
            self.mode_combo.blockSignals(False)
            self._sync_mode_controls()
            self.api_key_edit.setPlaceholderText(self._t("api_placeholder"))
            self.show_key_checkbox.setText(self._t("show"))
            self.save_keys_checkbox.setText(self._t("save_keys"))
            self.cache_note.setText(self._t("cache_note"))
            self.run_button.setText(self._t("analyze"))
            self.cancel_button.setText(self._t("cancel"))
            self.search_edit.setPlaceholderText(self._t("search"))
            self.detail_hint_label.setText(self._t("detail_hint"))
            self.keep_button.setText(self._t("keep"))
            self.maybe_button.setText(self._t("maybe"))
            self.reject_button.setText(self._t("reject"))
            self.generate_advice_button.setText(self._t("editing_plan"))
            self.open_output_button.setText(self._t("open_output"))
            self.open_contact_button.setText(self._t("open_contact"))
            if not self.records:
                self.result_count_label.setText(self._t("no_results"))
                self.status_label.setText(self._t("ready"))
                self._show_empty_grid(self._t("empty_grid"))
        self._reset_filter_combos()
        self._update_dashboard()

    def _reset_filter_combos(self) -> None:
        if not hasattr(self, "category_filter"):
            return
        category = self.category_filter.currentData() or self.category_filter.currentText()
        label_value = self.label_filter.currentData() or "all"
        sort_value = self.sort_combo.currentData() or "score_desc"
        self.category_filter.blockSignals(True)
        self.category_filter.clear()
        self.category_filter.addItem(self._t("all_categories"), "all")
        categories = sorted({str(record.get("category", "")) for record in self.records if record.get("category")})
        for item in categories:
            self.category_filter.addItem(item, item)
        category_index = self.category_filter.findData(category)
        self.category_filter.setCurrentIndex(category_index if category_index >= 0 else 0)
        self.category_filter.blockSignals(False)

        self.label_filter.blockSignals(True)
        self.label_filter.clear()
        for text_key, data in [
            ("all_labels", "all"),
            ("keep", "keep"),
            ("maybe", "maybe"),
            ("reject", "reject"),
            ("unlabeled", "unlabeled"),
        ]:
            self.label_filter.addItem(self._t(text_key), data)
        label_index = self.label_filter.findData(label_value)
        self.label_filter.setCurrentIndex(label_index if label_index >= 0 else 0)
        self.label_filter.blockSignals(False)

        self.sort_combo.blockSignals(True)
        self.sort_combo.clear()
        for text_key, data in [
            ("sort_high", "score_desc"),
            ("sort_low", "score_asc"),
            ("sort_rank", "rank"),
            ("sort_name", "filename"),
        ]:
            self.sort_combo.addItem(self._t(text_key), data)
        sort_index = self.sort_combo.findData(sort_value)
        self.sort_combo.setCurrentIndex(sort_index if sort_index >= 0 else 0)
        self.sort_combo.blockSignals(False)

    def _build_ui(self) -> None:
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(12)

        root.addWidget(self._build_header())
        root.addWidget(self._build_workflow())
        root.addWidget(self._build_controls())
        root.addWidget(self._build_result_toolbar())

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setObjectName("mainSplitter")
        self.photo_list = QListView()
        self.photo_list.setObjectName("photoGrid")
        self.photo_list.setViewMode(QListView.ViewMode.IconMode)
        self.photo_list.setResizeMode(QListView.ResizeMode.Adjust)
        self.photo_list.setMovement(QListView.Movement.Static)
        self.photo_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.photo_list.setIconSize(QSize(210, 148))
        self.photo_list.setSpacing(12)
        self.photo_list.setUniformItemSizes(True)
        self.photo_list.setLayoutMode(QListView.LayoutMode.Batched)
        self.photo_list.setBatchSize(96)
        self.photo_model = PhotoListModel(self._placeholder_icon())
        self.photo_list.setModel(self.photo_model)
        self.photo_list.selectionModel().selectionChanged.connect(lambda *_: self._show_selected_detail())
        self.photo_list.verticalScrollBar().valueChanged.connect(lambda *_: self._queue_visible_thumbnails())
        self._show_empty_grid("Drop into the workflow by choosing a folder, then run analysis.")
        splitter.addWidget(self.photo_list)

        detail_panel = QFrame()
        detail_panel.setObjectName("detailPanel")
        self._apply_shadow(detail_panel, blur=22, y=8, alpha=24)
        detail_layout = QVBoxLayout(detail_panel)
        detail_layout.setContentsMargins(14, 14, 14, 14)
        detail_layout.setSpacing(10)
        detail_title = QLabel("")
        detail_title.setObjectName("sectionTitle")
        self.static_labels["review_cockpit"] = detail_title
        detail_hint = QLabel("")
        detail_hint.setObjectName("muted")
        detail_hint.setWordWrap(True)
        self.detail_hint_label = detail_hint
        detail_layout.addWidget(detail_title)
        detail_layout.addWidget(detail_hint)
        self.detail_text = QTextEdit()
        self.detail_text.setObjectName("detailText")
        self.detail_text.setReadOnly(True)
        self.detail_text.setHtml(self._empty_detail_html())
        detail_layout.addWidget(self.detail_text)

        advice_buttons = QHBoxLayout()
        self.keep_button = QPushButton("")
        self.keep_button.setObjectName("markKeepButton")
        self.keep_button.clicked.connect(lambda: self._mark_selected("keep"))
        advice_buttons.addWidget(self.keep_button)
        self.maybe_button = QPushButton("")
        self.maybe_button.setObjectName("markMaybeButton")
        self.maybe_button.clicked.connect(lambda: self._mark_selected("maybe"))
        advice_buttons.addWidget(self.maybe_button)
        self.reject_button = QPushButton("")
        self.reject_button.setObjectName("markRejectButton")
        self.reject_button.clicked.connect(lambda: self._mark_selected("reject"))
        advice_buttons.addWidget(self.reject_button)
        self.generate_advice_button = QPushButton("")
        self.generate_advice_button.setObjectName("primaryButton")
        self.generate_advice_button.clicked.connect(self._generate_selected_advice)
        advice_buttons.addWidget(self.generate_advice_button)
        self.open_output_button = QPushButton("")
        self.open_output_button.setObjectName("secondaryButton")
        self.open_output_button.clicked.connect(lambda: self._open_path(self.output_dir))
        advice_buttons.addWidget(self.open_output_button)
        self.open_contact_button = QPushButton("")
        self.open_contact_button.setObjectName("secondaryButton")
        self.open_contact_button.clicked.connect(lambda: self._open_path(self.output_dir / "contact_sheet_top50.jpg"))
        advice_buttons.addWidget(self.open_contact_button)
        detail_layout.addLayout(advice_buttons)
        splitter.addWidget(detail_panel)
        splitter.setSizes([930, 430])
        root.addWidget(splitter, stretch=1)

        self.setCentralWidget(central)

    def _build_header(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("hero")
        self._apply_shadow(frame, blur=24, y=8, alpha=18)
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)

        copy = QVBoxLayout()
        title = QLabel("LumaSift")
        title.setObjectName("title")
        self.title_label = title
        subtitle = QLabel("")
        subtitle.setObjectName("subtitle")
        self.subtitle_label = subtitle
        copy.addWidget(title)
        copy.addWidget(subtitle)
        layout.addLayout(copy, stretch=1)

        self.language_combo = QComboBox()
        self.language_combo.addItems(["中文", "English"])
        self.language_combo.setFixedWidth(110)
        self.language_combo.currentTextChanged.connect(self._change_language)
        layout.addWidget(self.language_combo)

        for key, label in [
            ("scanned", "Scanned"),
            ("shown", "Shown"),
            ("selected", "Selected"),
            ("mode", "Mode"),
        ]:
            card = QFrame()
            card.setObjectName("statCard")
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(12, 9, 12, 9)
            value = QLabel("0" if key != "mode" else "Local")
            value.setObjectName("statValue")
            caption = QLabel(label)
            caption.setObjectName("statCaption")
            card_layout.addWidget(value)
            card_layout.addWidget(caption)
            self.stat_labels[key] = value
            self.static_labels[f"stat_{key}"] = caption
            layout.addWidget(card)
        return frame

    def _build_workflow(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("workflow")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        for key, title, caption in [
            ("import", "1. Import", "Choose local RAW/JPG folder"),
            ("local", "2. Pre-score", "Fast local CV and preview cache"),
            ("qwen", "3. Deep review", "Qwen only for high-value candidates"),
            ("edit", "4. Edit plan", "Multi-select concrete tuning guidance"),
        ]:
            step = QFrame()
            step.setObjectName("stepCard")
            step.setProperty("state", "idle")
            step_layout = QVBoxLayout(step)
            step_layout.setContentsMargins(14, 11, 14, 11)
            step_layout.setSpacing(4)
            heading = QLabel(title)
            heading.setObjectName("stepTitle")
            body = QLabel(caption)
            body.setObjectName("stepCaption")
            body.setWordWrap(True)
            step_layout.addWidget(heading)
            step_layout.addWidget(body)
            self.workflow_steps[key] = step
            self.workflow_labels[key] = (heading, body)
            layout.addWidget(step, stretch=1)
        return frame

    def _build_controls(self) -> QFrame:
        group = QFrame()
        group.setObjectName("controlCard")
        self._apply_shadow(group, blur=24, y=8, alpha=20)
        layout = QGridLayout(group)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setHorizontalSpacing(10)
        layout.setVerticalSpacing(9)

        self.input_edit = QLineEdit("D:/DCIM")
        self.input_edit.setObjectName("pathEdit")
        browse_input = QPushButton("Browse")
        self.browse_input_button = browse_input
        browse_input.setObjectName("secondaryButton")
        browse_input.clicked.connect(self._choose_input)
        source_label = QLabel("Photo folder")
        source_label.setObjectName("fieldLabel")
        self.static_labels["photo_folder"] = source_label
        layout.addWidget(source_label, 0, 0)
        layout.addWidget(self.input_edit, 0, 1)
        layout.addWidget(browse_input, 0, 2)

        self.output_edit = QLineEdit(str(self.output_dir))
        self.output_edit.setObjectName("pathEdit")
        browse_output = QPushButton("Browse")
        self.browse_output_button = browse_output
        browse_output.setObjectName("secondaryButton")
        browse_output.clicked.connect(self._choose_output)
        output_label = QLabel("Output folder")
        output_label.setObjectName("fieldLabel")
        self.static_labels["output_folder"] = output_label
        layout.addWidget(output_label, 1, 0)
        layout.addWidget(self.output_edit, 1, 1)
        layout.addWidget(browse_output, 1, 2)

        self.mode_combo = QComboBox()
        self.mode_combo.addItem("local_only", "local_only")
        self.mode_combo.addItem("qwen_vision", "qwen_vision")
        self.mode_combo.currentTextChanged.connect(self._sync_mode_controls)
        self.mode_combo.setFixedWidth(160)
        self.limit_spin = QSpinBox()
        self.limit_spin.setRange(1, 100000)
        self.limit_spin.setValue(50)
        self.limit_spin.setFixedWidth(96)
        self.top_n_spin = QSpinBox()
        self.top_n_spin.setRange(1, 500)
        self.top_n_spin.setValue(5)
        self.top_n_spin.setFixedWidth(88)
        self.selected_top_spin = QSpinBox()
        self.selected_top_spin.setRange(1, 100)
        self.selected_top_spin.setValue(10)
        self.selected_top_spin.setFixedWidth(88)
        self.display_limit_spin = QSpinBox()
        self.display_limit_spin.setRange(20, 2000)
        self.display_limit_spin.setValue(300)
        self.display_limit_spin.setFixedWidth(96)

        option_bar = QFrame()
        option_bar.setObjectName("optionBar")
        option_layout = QHBoxLayout(option_bar)
        option_layout.setContentsMargins(0, 0, 0, 0)
        option_layout.setSpacing(10)
        for label, control in [
            ("Mode", self.mode_combo),
            ("Scan", self.limit_spin),
            ("Qwen Top", self.top_n_spin),
            ("Advice Top", self.selected_top_spin),
            ("Show", self.display_limit_spin),
        ]:
            mini = QFrame()
            mini.setObjectName("miniControl")
            mini_layout = QVBoxLayout(mini)
            mini_layout.setContentsMargins(10, 8, 10, 8)
            mini_layout.setSpacing(3)
            mini_label = QLabel(label)
            mini_label.setObjectName("miniLabel")
            self.static_labels[f"mini_{label}"] = mini_label
            mini_layout.addWidget(mini_label)
            mini_layout.addWidget(control)
            option_layout.addWidget(mini)
        option_layout.addStretch(1)
        layout.addWidget(option_bar, 2, 0, 1, 3)

        self.api_key_edit = QLineEdit()
        self.api_key_edit.setPlaceholderText("Optional: comma-separated Qwen keys. Leave empty to use .env.")
        self.api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.show_key_checkbox = QCheckBox("Show")
        self.show_key_checkbox.toggled.connect(self._toggle_key_visibility)
        key_row = QWidget()
        key_layout = QHBoxLayout(key_row)
        key_layout.setContentsMargins(0, 0, 0, 0)
        key_layout.addWidget(self.api_key_edit, stretch=1)
        key_layout.addWidget(self.show_key_checkbox)
        self.save_keys_checkbox = QCheckBox("Save API keys locally")
        self.cache_note = QLabel("Qwen mode uploads only Top-N compressed JPEG previews; RAW files stay local.")
        self.cache_note.setObjectName("muted")
        api_label = QLabel("Qwen keys")
        api_label.setObjectName("fieldLabel")
        self.static_labels["qwen_keys"] = api_label
        layout.addWidget(api_label, 3, 0)
        layout.addWidget(key_row, 3, 1, 1, 2)
        layout.addWidget(self.save_keys_checkbox, 4, 1)
        layout.addWidget(self.cache_note, 4, 2)

        self.run_button = QPushButton("Analyze Folder")
        self.run_button.setObjectName("primaryButton")
        self.run_button.clicked.connect(self._start_analysis)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setObjectName("secondaryButton")
        self.cancel_button.clicked.connect(self._cancel_analysis)
        self.cancel_button.setEnabled(False)
        self.progress = QProgressBar()
        self.progress.setObjectName("runProgress")
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.status_label = QLabel("Ready")
        self.status_label.setObjectName("muted")
        layout.addWidget(self.run_button, 5, 0)
        layout.addWidget(self.cancel_button, 5, 1)
        layout.addWidget(self.progress, 5, 2)
        layout.addWidget(self.status_label, 6, 0, 1, 3)
        return group

    def _build_result_toolbar(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("toolbar")
        self._apply_shadow(frame, blur=18, y=6, alpha=14)
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("")
        self.search_edit.textChanged.connect(self._populate_records)
        self.category_filter = QComboBox()
        self.category_filter.addItems(
            [
                "All categories",
                "portfolio_candidate",
                "strong_edit_candidate",
                "story_candidate",
                "technically_weak_but_interesting",
                "ordinary_record",
                "reject_candidate",
                "failed",
            ]
        )
        self.category_filter.currentTextChanged.connect(self._populate_records)
        self.label_filter = QComboBox()
        self.label_filter.addItems(["All labels", "keep", "maybe", "reject", "unlabeled"])
        self.label_filter.currentTextChanged.connect(self._populate_records)
        self.sort_combo = QComboBox()
        self.sort_combo.addItems(["Score high to low", "Score low to high", "Rank", "Filename A-Z"])
        self.sort_combo.currentTextChanged.connect(self._populate_records)
        self.result_count_label = QLabel("")
        self.result_count_label.setObjectName("resultCount")

        filter_label = QLabel("")
        filter_label.setObjectName("sectionTitle")
        self.static_labels["review_board"] = filter_label
        layout.addWidget(filter_label)
        layout.addWidget(self.search_edit, stretch=1)
        layout.addWidget(self.category_filter)
        layout.addWidget(self.label_filter)
        layout.addWidget(self.sort_combo)
        layout.addWidget(self.result_count_label)
        return frame

    def _choose_input(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, self._t("photo_folder"), self.input_edit.text())
        if folder:
            self.input_edit.setText(folder)
            self._save_preferences()
            self._update_workflow("import")

    def _choose_output(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, self._t("output_folder"), self.output_edit.text())
        if folder:
            self.output_edit.setText(folder)
            self.output_dir = Path(folder)
            self._save_preferences()

    def _start_analysis(self) -> None:
        input_dir = Path(self.input_edit.text()).expanduser()
        output_dir = Path(self.output_edit.text()).expanduser()
        if not input_dir.exists():
            QMessageBox.warning(self, self._t("missing_input_title"), str(input_dir))
            return

        self.output_dir = output_dir
        self.current_run_id = f"gui-{time.strftime('%Y%m%d-%H%M%S')}"
        settings = Settings.from_env()
        settings.input_dir = input_dir
        settings.output_dir = output_dir
        settings.ai_mode = str(self.mode_combo.currentData() or "local_only")
        settings.limit = self.limit_spin.value()
        settings.top_n_api_analysis = self.top_n_spin.value()
        settings.selected_ranks = f"1-{self.selected_top_spin.value()}"
        keys_text = self.api_key_edit.text().strip()
        if keys_text:
            settings.vision_api_keys = [key.strip() for key in keys_text.split(",") if key.strip()]
        if settings.ai_mode == "qwen_vision" and not settings.vision_api_keys:
            QMessageBox.warning(
                self,
                self._t("missing_key_title"),
                self._t("missing_key_body"),
            )
            return

        self._save_preferences()
        stop_file = output_dir / "STOP_LUMASIFT"
        stop_file.unlink(missing_ok=True)

        self.run_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.status_label.setText(self._t("step_local"))
        self._set_grid_records([], self._t("running_grid"))
        self.detail_text.setHtml(self._empty_detail_html())
        self._update_workflow("local")
        self._update_dashboard()

        self.worker_thread = QThread()
        self.worker = AnalysisWorker(settings=settings, run_id=self.current_run_id)
        self.worker.moveToThread(self.worker_thread)
        self.worker_thread.started.connect(self.worker.run)
        self.worker.finished.connect(self._analysis_finished)
        self.worker.failed.connect(self._analysis_failed)
        self.worker.progress.connect(self._analysis_progress)
        self.worker.finished.connect(self.worker_thread.quit)
        self.worker.failed.connect(self.worker_thread.quit)
        self.worker_thread.finished.connect(self._analysis_thread_finished)
        self.worker_thread.finished.connect(self.worker_thread.deleteLater)
        self.worker_thread.start()

    def _analysis_thread_finished(self) -> None:
        self.worker_thread = None
        self.worker = None
        self._finish_pending_close_if_ready()

    def _analysis_finished(self, payload: dict) -> None:
        self.records = list(payload["report"].get("records", []))
        self._merge_user_labels()
        self.state_db.record_run(
            run_id=str(payload["summary"].get("run_id", self.current_run_id)),
            input_dir=self.input_edit.text(),
            output_dir=str(self.output_dir),
            ai_mode=str(self.mode_combo.currentData() or "local_only"),
            summary=payload["summary"],
        )
        self._write_current_reports()
        self.status_label.setText(f"{self._t('done')}: {payload['summary']['processed']} / {payload['summary']['failed']}")
        self.progress.setRange(0, 100)
        self.progress.setValue(100)
        self.run_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self._refresh_filter_options()
        self._populate_records()
        self._update_workflow("edit")
        self._update_dashboard(payload["summary"])
        self._fade_in(self.photo_list)

    def _analysis_failed(self, message: str) -> None:
        self.status_label.setText(self._t("failed"))
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.run_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self._update_workflow("import")
        QMessageBox.critical(self, "Analysis failed", message)

    def _analysis_progress(self, stage: str, current: int, total: int) -> None:
        self._update_workflow("qwen" if stage == "qwen" else "local")
        if total <= 0:
            self.progress.setValue(0)
            self.status_label.setText(f"{stage}: preparing...")
            return
        value = int((current / total) * 100)
        self.progress.setValue(max(0, min(100, value)))
        label = {
            "manifest": "Scanning files",
            "local": "Local RAW/preview analysis",
            "qwen": "Qwen vision review",
            "done": "Done",
        }.get(stage, stage)
        self.status_label.setText(f"{label}: {current}/{total}")

    def _populate_records(self) -> None:
        if not hasattr(self, "photo_list"):
            return
        self._stop_thumbnail_worker()
        self.thumbnail_generation += 1
        self.loaded_thumbnail_rows.clear()
        self.pending_thumbnail_rows.clear()
        self.visible_records = self._filtered_records()[: self.display_limit_spin.value()]
        if not self.visible_records:
            self.result_count_label.setText(f"Showing 0/{len(self.records)}")
            self.status_label.setText(self._t("no_results"))
            self._update_dashboard()
            self._show_empty_grid(self._t("empty_filtered"))
            return
        self._set_grid_records(self.visible_records)
        self.result_count_label.setText(f"{len(self.visible_records)}/{len(self.records)}")
        self.status_label.setText(f"{len(self.visible_records)}/{len(self.records)}")
        self._update_dashboard()
        self._queue_visible_thumbnails()

    def _show_empty_grid(self, message: str) -> None:
        self._set_grid_records([], message)

    def _set_grid_records(self, records: list[dict[str, Any]], empty_message: str | None = None) -> None:
        if self.photo_model is not None:
            self.photo_model.set_records(records, empty_message)

    def _filtered_records(self) -> list[dict[str, Any]]:
        records = list(self.records)
        query = self.search_edit.text().strip().lower() if hasattr(self, "search_edit") else ""
        category = self.category_filter.currentData() if hasattr(self, "category_filter") else "all"
        label_filter = self.label_filter.currentData() if hasattr(self, "label_filter") else "all"
        if category and category != "all":
            records = [record for record in records if str(record.get("category", "")) == category]
        if label_filter and label_filter != "all":
            if label_filter == "unlabeled":
                records = [record for record in records if not record.get("user_label")]
            else:
                records = [record for record in records if str(record.get("user_label", "")) == label_filter]
        if query:
            records = [
                record
                for record in records
                if query
                in " ".join(
                    [
                        str(record.get("filename", "")),
                        str(record.get("path", "")),
                        str(record.get("category", "")),
                        str(record.get("user_label", "")),
                        str(record.get("recommended_style", "")),
                    ]
                ).lower()
            ]

        sort_key = self.sort_combo.currentData() if hasattr(self, "sort_combo") else "score_desc"
        if sort_key == "score_asc":
            records.sort(key=lambda item: float(item.get("final_selection_score", 0) or 0))
        elif sort_key == "filename":
            records.sort(key=lambda item: str(item.get("filename", "")).lower())
        elif sort_key == "rank":
            records.sort(key=lambda item: int(item.get("rank", 999999) or 999999))
        else:
            records.sort(key=lambda item: float(item.get("final_selection_score", 0) or 0), reverse=True)
        return records

    def _refresh_filter_options(self) -> None:
        self._reset_filter_combos()

    def _placeholder_icon(self) -> QIcon:
        pixmap = QPixmap(210, 148)
        pixmap.fill(QColor("#e8edf3"))
        return QIcon(pixmap)

    def _start_thumbnail_worker(self) -> None:
        if not self.visible_records or self.thumbnail_thread is not None:
            return
        rows = sorted(self.pending_thumbnail_rows)[:96]
        if not rows:
            return
        for row in rows:
            self.pending_thumbnail_rows.discard(row)
        jobs = [(row, self.visible_records[row]) for row in rows if 0 <= row < len(self.visible_records)]
        if not jobs:
            return
        self.thumbnail_thread = QThread()
        self.thumbnail_worker = ThumbnailWorker(jobs, self.output_dir, self.thumbnail_generation, max_side=360)
        self.thumbnail_worker.moveToThread(self.thumbnail_thread)
        self.thumbnail_thread.started.connect(self.thumbnail_worker.run)
        self.thumbnail_worker.thumbnail_ready.connect(self._thumbnail_ready)
        self.thumbnail_worker.finished.connect(self.thumbnail_thread.quit)
        self.thumbnail_thread.finished.connect(self._thumbnail_thread_finished)
        self.thumbnail_thread.finished.connect(self.thumbnail_thread.deleteLater)
        self.thumbnail_thread.start()

    def _queue_visible_thumbnails(self) -> None:
        if not self.visible_records or self.photo_model is None:
            return
        viewport = self.photo_list.viewport().rect().adjusted(-260, -260, 260, 520)
        rows: list[int] = []
        row_count = self.photo_model.rowCount()
        for row in range(row_count):
            index = self.photo_model.index(row, 0)
            rect = self.photo_list.visualRect(index)
            if rect.isValid() and rect.intersects(viewport):
                rows.append(row)
        if not rows:
            rows = list(range(min(36, len(self.visible_records))))
        for row in rows[:120]:
            if row not in self.loaded_thumbnail_rows:
                self.pending_thumbnail_rows.add(row)
        self._start_thumbnail_worker()

    def _thumbnail_thread_finished(self) -> None:
        self.thumbnail_worker = None
        self.thumbnail_thread = None
        if self.pending_close:
            self._finish_pending_close_if_ready()
            return
        if self.pending_thumbnail_rows:
            self._start_thumbnail_worker()

    def _stop_thumbnail_worker(self) -> None:
        if self.thumbnail_worker is not None:
            self.thumbnail_worker.stop()
        if self.thumbnail_thread is not None and self.thumbnail_thread.isRunning():
            self.thumbnail_thread.quit()
            if not self.thumbnail_thread.wait(2500):
                return
        self.thumbnail_worker = None
        self.thumbnail_thread = None

    def _thumbnail_ready(self, generation: int, row: int, preview_path: str) -> None:
        if generation != self.thumbnail_generation or not preview_path or self.photo_model is None:
            return
        if row < 0 or row >= len(self.visible_records):
            return
        pixmap = QPixmap(preview_path)
        if not pixmap.isNull():
            self.loaded_thumbnail_rows.add(row)
            self.photo_model.set_icon(row, QIcon(pixmap))

    def _show_selected_detail(self) -> None:
        selected = self._selected_record_indexes()
        if not selected:
            self.detail_text.setHtml(self._empty_detail_html())
            self._update_dashboard()
            return
        record = selected[0].data(Qt.ItemDataRole.UserRole)
        self.detail_text.setHtml(self._format_record_detail_html(record, len(selected)))
        self._update_dashboard()
        self._fade_in(self.detail_text, duration=180)

    def _format_record_detail_html(self, record: dict[str, Any], selected_count: int) -> str:
        score = float(record.get("final_selection_score", 0) or 0)
        category = self._escape(str(record.get("category", ""))).replace("_", " ")
        style = self._escape(str(record.get("recommended_style", ""))).replace("_", " ")
        user_label = self._escape(str(record.get("user_label", "") or "unlabeled"))
        filename = self._escape(str(record.get("filename", "")))
        story = self._escape(str(record.get("story_interpretation", "") or "Qwen review has not been run yet."))
        direction = self._escape(str(record.get("best_editing_direction", "") or "Use the selected-photo editing plan for detailed parameters."))
        crop = self._escape(str(record.get("crop_strategy", "") or "No crop instruction recorded."))
        positives = self._html_list(record.get("positive_reasons", [])[:5], "pending vision review")
        negatives = self._html_list(record.get("negative_reasons", [])[:5], "none recorded")
        params = record.get("specific_edit_parameters", {}) or {}
        params_rows = "".join(
            f"<tr><td>{self._escape(str(key)).replace('_', ' ')}</td><td>{self._escape(str(value))}</td></tr>"
            for key, value in params.items()
        )
        if not params_rows:
            params_rows = f"<tr><td>{'参数' if self.language == 'zh' else 'Parameters'}</td><td>{'点击修图方案生成' if self.language == 'zh' else 'Generate an editing plan.'}</td></tr>"
        labels = {
            "selected": "已选" if self.language == "zh" else "Selected",
            "user_label": "标记" if self.language == "zh" else "user label",
            "final": "总分" if self.language == "zh" else "Final selection",
            "story": "故事/纪实" if self.language == "zh" else "Story / documentary",
            "composition": "构图" if self.language == "zh" else "Composition",
            "editability": "可修度" if self.language == "zh" else "Editability",
            "story_read": "画面判断" if self.language == "zh" else "Story read",
            "why": "保留理由" if self.language == "zh" else "Why it can work",
            "risks": "风险" if self.language == "zh" else "Risks to control",
            "direction": "修图方向" if self.language == "zh" else "Editing direction",
            "crop": "裁切" if self.language == "zh" else "Crop",
            "params": "参数" if self.language == "zh" else "Concrete parameters",
        }
        return f"""
        <html><head>{self._detail_html_style()}</head><body>
        <div class="detail-shell">
          <div class="hero-line">
            <span class="rank">Rank #{self._escape(str(record.get("rank", "-")))}</span>
            <span class="score">{score:.1f}</span>
          </div>
          <h2>{filename}</h2>
          <p class="meta">{labels["selected"]} {selected_count} | {category} | {style} | {labels["user_label"]}: {user_label}</p>
          {self._score_bar(labels["final"], score)}
          {self._score_bar(labels["story"], record.get("street_documentary_potential_score", 0))}
          {self._score_bar(labels["composition"], record.get("composition_score", 0))}
          {self._score_bar(labels["editability"], record.get("editability_score", 0))}
          <h3>{labels["story_read"]}</h3>
          <p>{story}</p>
          <h3>{labels["why"]}</h3>
          {positives}
          <h3>{labels["risks"]}</h3>
          {negatives}
          <h3>{labels["direction"]}</h3>
          <p>{direction}</p>
          <h3>{labels["crop"]}</h3>
          <p>{crop}</p>
          <h3>{labels["params"]}</h3>
          <table>{params_rows}</table>
        </div>
        </body></html>
        """

    def _generate_selected_advice(self) -> None:
        selected_indexes = self._selected_record_indexes()
        if selected_indexes:
            selected_ranks = [index.data(Qt.ItemDataRole.UserRole).get("rank") for index in selected_indexes]
        else:
            selected_ranks = list(range(1, min(self.selected_top_spin.value(), len(self.records)) + 1))

        if not self.records:
            QMessageBox.information(self, self._t("no_records"), self._t("run_first"))
            return
        payload = build_selected_editing_advice(self.records, selected_ranks=selected_ranks)
        json_path = self.output_dir / "selected_editing_advice.json"
        md_path = self.output_dir / "selected_editing_advice.md"
        write_json_report(json_path, payload)
        write_markdown_report(md_path, render_selected_editing_advice_markdown(payload))
        self.detail_text.setHtml(self._format_advice_html(payload))
        self.status_label.setText(str(md_path))
        self._update_workflow("edit")
        self._fade_in(self.detail_text)

    def _mark_selected(self, label: str) -> None:
        selected_indexes = self._selected_record_indexes()
        if not selected_indexes:
            QMessageBox.information(self, self._t("no_selection"), self._t("select_first"))
            return
        changed = 0
        changed_rows: list[int] = []
        for index in selected_indexes:
            record = index.data(Qt.ItemDataRole.UserRole)
            if not isinstance(record, dict) or not record.get("path"):
                continue
            record["user_label"] = label
            self.state_db.set_user_label(
                path=record["path"],
                label=label,
                run_id=self.current_run_id or None,
                rank=int(record.get("rank", 0) or 0),
                score=float(record.get("final_selection_score", 0) or 0),
                category=str(record.get("category", "")),
            )
            changed += 1
            changed_rows.append(index.row())
        self._write_current_reports()
        if self.photo_model is not None:
            for row in changed_rows:
                self.photo_model.refresh_row(row)
        self.status_label.setText(f"{changed} -> {self._t(label)}")

    def _cancel_analysis(self) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        (self.output_dir / "STOP_LUMASIFT").write_text("stop", encoding="utf-8")
        self.status_label.setText(self._t("closing") if self.pending_close else self._t("cancel"))
        self.cancel_button.setEnabled(False)

    def _toggle_key_visibility(self, enabled: bool) -> None:
        self.api_key_edit.setEchoMode(QLineEdit.EchoMode.Normal if enabled else QLineEdit.EchoMode.Password)

    def _sync_mode_controls(self) -> None:
        qwen_enabled = (self.mode_combo.currentData() or self.mode_combo.currentText()) == "qwen_vision"
        self.top_n_spin.setEnabled(qwen_enabled)
        self.api_key_edit.setEnabled(qwen_enabled)
        self.show_key_checkbox.setEnabled(qwen_enabled)
        self.save_keys_checkbox.setEnabled(qwen_enabled)
        self.stat_labels.get("mode", QLabel()).setText(self._t("qwen") if qwen_enabled else self._t("local"))
        self._update_workflow("qwen" if qwen_enabled else "import")

    def _load_preferences(self) -> None:
        self.input_edit.setText(str(self.settings_store.value("input_dir", "D:/DCIM")))
        self.output_edit.setText(str(self.settings_store.value("output_dir", "./outputs/gui")))
        self.output_dir = Path(self.output_edit.text())
        self.limit_spin.setValue(int(self.settings_store.value("limit", 50)))
        self.top_n_spin.setValue(int(self.settings_store.value("top_n", 5)))
        self.selected_top_spin.setValue(int(self.settings_store.value("selected_top", 10)))
        self.display_limit_spin.setValue(int(self.settings_store.value("display_limit", 300)))
        mode = str(self.settings_store.value("mode", "local_only"))
        mode_index = self.mode_combo.findData(mode if mode in {"local_only", "qwen_vision"} else "local_only")
        self.mode_combo.setCurrentIndex(mode_index if mode_index >= 0 else 0)
        saved_keys = str(self.settings_store.value("api_keys", ""))
        self.api_key_edit.setText(saved_keys)
        self.save_keys_checkbox.setChecked(bool(saved_keys))
        self._sync_mode_controls()

    def _save_preferences(self) -> None:
        self.settings_store.setValue("input_dir", self.input_edit.text())
        self.settings_store.setValue("output_dir", self.output_edit.text())
        self.settings_store.setValue("limit", self.limit_spin.value())
        self.settings_store.setValue("top_n", self.top_n_spin.value())
        self.settings_store.setValue("selected_top", self.selected_top_spin.value())
        self.settings_store.setValue("display_limit", self.display_limit_spin.value())
        self.settings_store.setValue("mode", self.mode_combo.currentData() or "local_only")
        if self.save_keys_checkbox.isChecked():
            self.settings_store.setValue("api_keys", self.api_key_edit.text())
        else:
            self.settings_store.remove("api_keys")

    def _merge_user_labels(self) -> None:
        labels = self.state_db.load_labels(str(record.get("path", "")) for record in self.records if record.get("path"))
        for record in self.records:
            path = str(record.get("path", ""))
            normalized = str(Path(path).expanduser().resolve()) if path else ""
            if normalized in labels:
                record["user_label"] = labels[normalized]

    def _write_current_reports(self) -> None:
        if not self.records:
            return
        self.output_dir.mkdir(parents=True, exist_ok=True)
        write_csv_report(self.output_dir / "report.csv", self.records)
        write_json_report(
            self.output_dir / "report.json",
            {
                "run_id": self.current_run_id,
                "ai_mode": str(self.mode_combo.currentData() or "local_only") if hasattr(self, "mode_combo") else "",
                "input_dir": self.input_edit.text() if hasattr(self, "input_edit") else "",
                "records": self.records,
                "user_label_source": str(self.state_db.path),
            },
        )
        write_json_report(self.output_dir / "user_labels.json", {"records": self.state_db.export_labeled_records()})

    def _selected_record_indexes(self) -> list[QModelIndex]:
        if not hasattr(self, "photo_list") or self.photo_list.selectionModel() is None:
            return []
        indexes = self.photo_list.selectionModel().selectedIndexes()
        return [index for index in indexes if index.isValid() and index.data(Qt.ItemDataRole.UserRole)]

    def _open_path(self, path: Path) -> None:
        try:
            if not path.exists():
                QMessageBox.information(self, self._t("no_results"), str(path))
                return
            os.startfile(path)  # type: ignore[attr-defined]
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, self._t("failed"), str(exc))

    def _apply_shadow(self, widget: QWidget, *, blur: int, y: int, alpha: int) -> None:
        shadow = QGraphicsDropShadowEffect(widget)
        shadow.setBlurRadius(blur)
        shadow.setOffset(0, y)
        shadow.setColor(QColor(15, 23, 42, alpha))
        widget.setGraphicsEffect(shadow)

    def _fade_in(self, widget: QWidget, *, duration: int = 260) -> None:
        effect = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(effect)
        animation = QPropertyAnimation(effect, b"opacity", self)
        animation.setDuration(duration)
        animation.setStartValue(0.35)
        animation.setEndValue(1.0)
        animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        animation.finished.connect(lambda: self._animations.remove(animation) if animation in self._animations else None)
        self._animations.append(animation)
        animation.start()

    def _update_workflow(self, active: str) -> None:
        order = ["import", "local", "qwen", "edit"]
        active_index = order.index(active) if active in order else 0
        for index, key in enumerate(order):
            step = self.workflow_steps.get(key)
            if step is None:
                continue
            if index < active_index:
                state = "done"
            elif index == active_index:
                state = "active"
            else:
                state = "idle"
            step.setProperty("state", state)
            step.style().unpolish(step)
            step.style().polish(step)

    def _update_dashboard(self, summary: dict[str, Any] | None = None) -> None:
        if not self.stat_labels:
            return
        scanned = summary.get("scanned", len(self.records)) if summary else len(self.records)
        selected = self._selected_record_indexes() if hasattr(self, "photo_list") else []
        mode = self._t("qwen") if hasattr(self, "mode_combo") and (self.mode_combo.currentData() or self.mode_combo.currentText()) == "qwen_vision" else self._t("local")
        self.stat_labels["scanned"].setText(str(scanned))
        self.stat_labels["shown"].setText(str(len(self.visible_records)))
        self.stat_labels["selected"].setText(str(len(selected)))
        self.stat_labels["mode"].setText(mode)

    def _empty_detail_html(self) -> str:
        return """
        <html><head>{style}</head><body>
        <div class="empty-state">
          <h2>{title}</h2>
          <p>{body}</p>
          <table>
            <tr><td>1</td><td>{step1}</td></tr>
            <tr><td>2</td><td>{step2}</td></tr>
            <tr><td>3</td><td>{step3}</td></tr>
          </table>
        </div>
        </body></html>
        """.format(
            style=self._detail_html_style(),
            title="从本地目录开始" if self.language == "zh" else "Start with a local folder",
            body="选目录、跑分析、再多选生成修图方案。" if self.language == "zh" else "Choose a folder, run analysis, then multi-select photos for editing plans.",
            step1="选择照片目录" if self.language == "zh" else "Choose a photo folder",
            step2="本地快速初筛" if self.language == "zh" else "Run local pre-score",
            step3="高价值候选再交给 Qwen" if self.language == "zh" else "Use Qwen for high-value candidates",
        )

    def _escape(self, value: str) -> str:
        return html.escape(value, quote=True)

    def _html_list(self, values: list[Any], fallback: str) -> str:
        items = [str(item) for item in values if str(item).strip()]
        if not items:
            items = [fallback]
        return "<ul>" + "".join(f"<li>{self._escape(item)}</li>" for item in items) + "</ul>"

    def _score_bar(self, label: str, value: Any) -> str:
        try:
            score = max(0.0, min(100.0, float(value or 0)))
        except (TypeError, ValueError):
            score = 0.0
        return (
            "<div class='score-row'>"
            f"<span>{self._escape(label)}</span><b>{score:.0f}</b>"
            f"<div class='bar'><div style='width:{score:.0f}%;'></div></div>"
            "</div>"
        )

    def _format_advice_html(self, payload: dict[str, Any]) -> str:
        markdown = render_selected_editing_advice_markdown(payload)
        escaped = self._escape(markdown)
        count = int(payload.get("selected_count", 0) or 0)
        title = f"{count} 张照片的修图方案" if self.language == "zh" else f"Editing plan for {count} selected photos"
        note = "已写入 selected_editing_advice.md / .json" if self.language == "zh" else "Written to selected_editing_advice.md and selected_editing_advice.json."
        return f"""
        <html><head>{self._detail_html_style()}</head><body>
        <h2>{title}</h2>
        <p class="meta">{note}</p>
        <pre>{escaped}</pre>
        </body></html>
        """

    def _detail_html_style(self) -> str:
        return """
        <style>
        body { color: #162033; font-family: Segoe UI, Microsoft YaHei; font-size: 12px; }
        h2 { margin: 0 0 4px 0; font-size: 20px; color: #0f172a; }
        h3 { margin: 16px 0 6px 0; font-size: 13px; color: #0f172a; }
        p { line-height: 1.45; margin: 4px 0 8px 0; color: #334155; }
        ul { margin: 4px 0 8px 18px; padding: 0; }
        li { margin-bottom: 5px; }
        table { border-collapse: collapse; width: 100%; margin-top: 8px; }
        td { border-bottom: 1px solid #e2e8f0; padding: 6px; vertical-align: top; }
        pre { white-space: pre-wrap; background: #f8fafc; border: 1px solid #d8e0ea; border-radius: 8px; padding: 10px; }
        .hero-line { margin-bottom: 8px; }
        .rank { color: #2563eb; font-weight: 800; }
        .score { float: right; color: #0f172a; font-size: 28px; font-weight: 900; }
        .meta { color: #64748b; }
        .score-row { margin: 8px 0 10px 0; }
        .score-row span { font-weight: 700; color: #334155; }
        .score-row b { float: right; color: #0f172a; }
        .bar { margin-top: 4px; height: 8px; background: #e2e8f0; border-radius: 4px; }
        .bar div { height: 8px; background: #2563eb; border-radius: 4px; }
        </style>
        """

    def _apply_style(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow, QWidget {
                background: #eef2f6;
                color: #17202a;
                font-family: Segoe UI, Microsoft YaHei;
                font-size: 12px;
            }
            QLabel { background: transparent; }
            QLabel#title { font-size: 34px; font-weight: 800; color: #0f172a; letter-spacing: 0px; }
            QLabel#subtitle { color: #425466; font-size: 13px; }
            QLabel#muted, QLabel#statCaption, QLabel#stepCaption { color: #64748b; }
            QLabel#sectionTitle { font-size: 14px; font-weight: 800; color: #0f172a; }
            QLabel#fieldLabel { color: #334155; font-weight: 700; }
            QLabel#miniLabel { color: #64748b; font-weight: 700; }
            QFrame#hero, QFrame#controlCard, QFrame#toolbar, QFrame#detailPanel {
                background: #ffffff;
                border: 1px solid #d8e0ea;
                border-radius: 8px;
            }
            QFrame#statCard {
                background: #f6f9fc;
                border: 1px solid #dce5ef;
                border-radius: 8px;
                min-width: 92px;
            }
            QFrame#optionBar { background: transparent; border: none; }
            QFrame#miniControl {
                background: #f8fafc;
                border: 1px solid #dbe5ee;
                border-radius: 8px;
            }
            QLabel#statValue { font-size: 20px; font-weight: 800; color: #0b5cab; }
            QFrame#workflow { background: transparent; }
            QFrame#stepCard {
                background: #ffffff;
                border: 1px solid #d8e0ea;
                border-radius: 8px;
            }
            QFrame#stepCard[state="active"] {
                background: #eff6ff;
                border: 2px solid #2563eb;
            }
            QFrame#stepCard[state="done"] {
                background: #ecfdf5;
                border: 1px solid #34d399;
            }
            QLabel#stepTitle { font-weight: 800; color: #0f172a; }
            QLineEdit, QSpinBox, QComboBox, QTextEdit, QListView {
                background: #ffffff;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                padding: 7px;
                selection-background-color: #bfdbfe;
            }
            QLineEdit:focus, QSpinBox:focus, QComboBox:focus, QTextEdit:focus {
                border: 2px solid #2563eb;
            }
            QPushButton {
                border: none;
                border-radius: 6px;
                padding: 9px 13px;
                font-weight: 800;
            }
            QPushButton#primaryButton { background: #2563eb; color: #ffffff; }
            QPushButton#primaryButton:hover { background: #1d4ed8; }
            QPushButton#secondaryButton { background: #e8eef6; color: #0f172a; }
            QPushButton#secondaryButton:hover { background: #dbe7f3; }
            QPushButton#markKeepButton { background: #dcfce7; color: #166534; }
            QPushButton#markKeepButton:hover { background: #bbf7d0; }
            QPushButton#markMaybeButton { background: #fef3c7; color: #92400e; }
            QPushButton#markMaybeButton:hover { background: #fde68a; }
            QPushButton#markRejectButton { background: #fee2e2; color: #991b1b; }
            QPushButton#markRejectButton:hover { background: #fecaca; }
            QPushButton:disabled { background: #cbd5e1; color: #64748b; }
            QListView#photoGrid {
                background: #f8fafc;
                border: 1px solid #d8e0ea;
                border-radius: 8px;
                padding: 10px;
            }
            QListView#photoGrid::item {
                background: #ffffff;
                border: 1px solid #d9e2ec;
                border-radius: 8px;
                padding: 8px;
                color: #1e293b;
            }
            QListView#photoGrid::item:hover {
                border: 1px solid #60a5fa;
                background: #f8fbff;
            }
            QListView#photoGrid::item:selected {
                border: 2px solid #2563eb;
                background: #eff6ff;
            }
            QLabel#resultCount {
                background: #eef2ff;
                color: #1e40af;
                border-radius: 6px;
                padding: 6px 10px;
                font-weight: 800;
            }
            QTextEdit#detailText {
                background: #fbfdff;
                border: 1px solid #d8e0ea;
                border-radius: 8px;
                padding: 10px;
            }
            QProgressBar {
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                text-align: center;
                background: #f8fafc;
                height: 18px;
                font-weight: 700;
            }
            QProgressBar::chunk { background: #2563eb; border-radius: 5px; }
            """
        )

    def closeEvent(self, event: Any) -> None:
        if self.allow_close:
            super().closeEvent(event)
            return
        if self._background_tasks_running():
            event.ignore()
            self.pending_close = True
            self.status_label.setText(self._t("closing"))
            self._request_background_stop()
            return
        super().closeEvent(event)

    def _background_tasks_running(self) -> bool:
        analysis_running = self.worker_thread is not None and self.worker_thread.isRunning()
        thumbnail_running = self.thumbnail_thread is not None and self.thumbnail_thread.isRunning()
        return bool(analysis_running or thumbnail_running)

    def _request_background_stop(self) -> None:
        self._cancel_analysis()
        if self.thumbnail_worker is not None:
            self.thumbnail_worker.stop()
        if self.thumbnail_thread is not None and self.thumbnail_thread.isRunning():
            self.thumbnail_thread.quit()
        if not self._background_tasks_running():
            self._finish_pending_close_if_ready()

    def _finish_pending_close_if_ready(self) -> None:
        if self.pending_close and not self._background_tasks_running():
            self.allow_close = True
            QTimer.singleShot(0, self.close)


def main() -> int:
    install_crash_logging()
    app = QApplication(sys.argv)
    app.setApplicationName("LumaSift")
    window = LumaSiftWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

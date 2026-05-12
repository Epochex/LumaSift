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

from PySide6.QtCore import QAbstractListModel, QEasingCurve, QItemSelectionModel, QModelIndex, QObject, QPropertyAnimation, QSettings, QSize, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontDatabase, QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QAbstractSpinBox,
    QCheckBox,
    QComboBox,
    QDialog,
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
    QSizePolicy,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QStyle,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from lumasift.analysis.editing_advice import build_selected_editing_advice
from lumasift.analysis.user_feedback import apply_user_feedback_fields, normalized_user_label
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
        "sort_user": "标记优先",
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
        "grid_tooltip": "双击照片打开大图预览",
        "advanced_settings": "高级设置",
        "hide_advanced": "收起设置",
        "review_mode": "筛片模式",
        "show_setup": "展开设置",
        "new_scan": "重新分析",
        "run_history": "历史",
        "load_run": "载入",
        "missing_run": "输出不可用",
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
        "sort_user": "Label priority",
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
        "grid_tooltip": "Double-click a photo to open the large preview",
        "advanced_settings": "Advanced",
        "hide_advanced": "Hide Settings",
        "review_mode": "Review Mode",
        "show_setup": "Show Setup",
        "new_scan": "Analyze Again",
        "run_history": "History",
        "load_run": "Load",
        "missing_run": "Output unavailable",
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


PREFERRED_UI_FONTS = [
    "Microsoft YaHei UI",
    "Microsoft YaHei",
    "Noto Sans CJK SC",
    "Source Han Sans SC",
    "SimHei",
    "PingFang SC",
    "Arial Unicode MS",
    "Segoe UI",
]

WINDOWS_UI_FONT_FILES = [
    Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "msyh.ttc",
    Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "msyhbd.ttc",
    Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "simhei.ttf",
]


def preferred_ui_font_family() -> str:
    for font_file in WINDOWS_UI_FONT_FILES:
        if font_file.exists():
            QFontDatabase.addApplicationFont(str(font_file))
    available = set(QFontDatabase.families())
    for family in PREFERRED_UI_FONTS:
        if family in available:
            return family
    return QApplication.font().family()


def apply_application_font(app: QApplication) -> str:
    family = preferred_ui_font_family()
    font = QFont(family, 10)
    font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    app.setFont(font)
    return family


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
    qwen_event = Signal(dict)

    def __init__(self, settings: Settings, run_id: str, state_db_path: Path | None = None) -> None:
        super().__init__()
        self.settings = settings
        self.run_id = run_id
        self.state_db_path = state_db_path

    def run(self) -> None:
        try:
            configure_logging(self.settings.output_dir)
            result = LumaSiftHarness(
                settings=self.settings,
                run_id=self.run_id,
                progress_callback=lambda stage, current, total: self.progress.emit(stage, current, total),
                event_callback=lambda event: self.qwen_event.emit(event),
                state_db=LumaSiftStateDb(self.state_db_path) if self.state_db_path else None,
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


class LargePreviewWorker(QObject):
    finished = Signal(str)
    failed = Signal(str)

    def __init__(self, path: Path, output_dir: Path, max_side: int = 2400) -> None:
        super().__init__()
        self.path = path
        self.output_dir = output_dir
        self.max_side = max_side

    def run(self) -> None:
        try:
            preview_dir = self.output_dir / "large_previews"
            preview_path = create_jpeg_preview(self.path, preview_dir, max_side=self.max_side)
            self.finished.emit(str(preview_path))
        except Exception as exc:  # noqa: BLE001 - preview failure should stay inside the dialog.
            logging.exception("Large preview failed for %s", self.path)
            self.failed.emit(str(exc))


class LargePreviewDialog(QDialog):
    def __init__(self, record: dict[str, Any], output_dir: Path, language: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.record = record
        self.output_dir = output_dir
        self.language = language if language in {"zh", "en"} else "zh"
        self.preview_thread: QThread | None = None
        self.preview_worker: LargePreviewWorker | None = None
        self.original_pixmap: QPixmap | None = None
        self.fit_to_window = True
        self.pending_close = False

        filename = str(record.get("filename") or Path(str(record.get("path", ""))).name)
        title = f"大图预览 - {filename}" if self.language == "zh" else f"Large Preview - {filename}"
        self.setWindowTitle(title)
        self.setObjectName("largePreviewDialog")
        self.resize(1280, 860)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        header = QFrame()
        header.setObjectName("previewHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(12, 10, 12, 10)
        header_layout.setSpacing(8)
        title_label = QLabel(filename)
        title_label.setObjectName("sectionTitle")
        self.status_label = QLabel("正在生成 RAW 预览..." if self.language == "zh" else "Generating RAW preview...")
        self.status_label.setObjectName("muted")
        self.fit_button = QPushButton("适应窗口" if self.language == "zh" else "Fit")
        self.fit_button.setObjectName("secondaryButton")
        self.fit_button.clicked.connect(self._fit)
        self.actual_button = QPushButton("100%")
        self.actual_button.setObjectName("secondaryButton")
        self.actual_button.clicked.connect(self._actual_size)
        header_layout.addWidget(title_label, stretch=1)
        header_layout.addWidget(self.status_label)
        header_layout.addWidget(self.fit_button)
        header_layout.addWidget(self.actual_button)
        layout.addWidget(header)

        self.image_label = QLabel("加载中..." if self.language == "zh" else "Loading...")
        self.image_label.setObjectName("previewImage")
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setMinimumSize(640, 420)
        self.image_label.setScaledContents(False)

        self.scroll_area = QScrollArea()
        self.scroll_area.setObjectName("previewScrollArea")
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.scroll_area.setWidget(self.image_label)
        layout.addWidget(self.scroll_area, stretch=1)

        self.setStyleSheet(
            """
            QDialog#largePreviewDialog { background: #0f172a; color: #e5edf7; }
            QFrame#previewHeader {
                background: #111827;
                border: 1px solid #263244;
                border-radius: 8px;
            }
            QLabel#sectionTitle { font-size: 14px; font-weight: 800; color: #f8fafc; }
            QLabel#muted { color: #94a3b8; }
            QLabel#previewImage {
                background: #020617;
                color: #94a3b8;
                border: 1px solid #1e293b;
                border-radius: 8px;
            }
            QScrollArea#previewScrollArea {
                background: #020617;
                border: none;
            }
            QPushButton {
                border: none;
                border-radius: 6px;
                padding: 8px 12px;
                font-weight: 800;
            }
            QPushButton#secondaryButton { background: #233044; color: #f8fafc; }
            QPushButton#secondaryButton:hover { background: #334155; }
            """
        )

    def showEvent(self, event: Any) -> None:  # noqa: N802 - Qt API
        super().showEvent(event)
        if self.preview_thread is None and self.original_pixmap is None:
            QTimer.singleShot(0, self._start_load)

    def resizeEvent(self, event: Any) -> None:  # noqa: N802 - Qt API
        super().resizeEvent(event)
        if self.fit_to_window:
            self._apply_fit()

    def closeEvent(self, event: Any) -> None:  # noqa: N802 - Qt API
        if self.preview_thread is not None and self.preview_thread.isRunning():
            event.ignore()
            self.pending_close = True
            self.status_label.setText("预览生成中，完成后关闭..." if self.language == "zh" else "Preview is loading. Closing after it finishes...")
            return
        super().closeEvent(event)

    def _start_load(self) -> None:
        path = Path(str(self.record.get("path", "")))
        self.preview_thread = QThread()
        self.preview_worker = LargePreviewWorker(path, self.output_dir, max_side=2400)
        self.preview_worker.moveToThread(self.preview_thread)
        self.preview_thread.started.connect(self.preview_worker.run)
        self.preview_worker.finished.connect(self._load_finished)
        self.preview_worker.failed.connect(self._load_failed)
        self.preview_worker.finished.connect(self.preview_thread.quit)
        self.preview_worker.failed.connect(self.preview_thread.quit)
        self.preview_thread.finished.connect(self._thread_finished)
        self.preview_thread.finished.connect(self.preview_thread.deleteLater)
        self.preview_thread.start()

    def _load_finished(self, preview_path: str) -> None:
        pixmap = QPixmap(preview_path)
        if pixmap.isNull():
            self._load_failed("Cannot decode generated preview.")
            return
        self.original_pixmap = pixmap
        size_text = f"{pixmap.width()} x {pixmap.height()}"
        self.status_label.setText(size_text)
        self._fit()

    def _load_failed(self, message: str) -> None:
        text = f"预览失败：{message}" if self.language == "zh" else f"Preview failed: {message}"
        self.status_label.setText(text)
        self.image_label.setText(text)

    def _thread_finished(self) -> None:
        self.preview_worker = None
        self.preview_thread = None
        if self.pending_close:
            QTimer.singleShot(0, self.close)

    def _fit(self) -> None:
        self.fit_to_window = True
        self._apply_fit()

    def _actual_size(self) -> None:
        if self.original_pixmap is None:
            return
        self.fit_to_window = False
        self.image_label.setPixmap(self.original_pixmap)
        self.image_label.resize(self.original_pixmap.size())
        self.scroll_area.setWidgetResizable(False)

    def _apply_fit(self) -> None:
        if self.original_pixmap is None:
            return
        self.scroll_area.setWidgetResizable(True)
        available = self.scroll_area.viewport().size() - QSize(24, 24)
        if available.width() <= 0 or available.height() <= 0:
            return
        scaled = self.original_pixmap.scaled(
            available,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.image_label.setPixmap(scaled)


class RunHistoryDialog(QDialog):
    def __init__(self, runs: list[dict[str, Any]], language: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.runs = runs
        self.language = language if language in {"zh", "en"} else "zh"
        self.selected_run: dict[str, Any] | None = None
        self.setWindowTitle("运行历史" if self.language == "zh" else "Run History")
        self.resize(920, 420)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        self.table = QTableWidget(0, 7)
        self.table.setObjectName("historyTable")
        headers = (
            ["时间", "模式", "照片", "成功", "失败", "输出", "状态"]
            if self.language == "zh"
            else ["Time", "Mode", "Photos", "Done", "Failed", "Output", "State"]
        )
        self.table.setHorizontalHeaderLabels(headers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._populate()
        layout.addWidget(self.table, stretch=1)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.open_button = QPushButton("打开输出" if self.language == "zh" else "Open Output")
        self.open_button.setObjectName("secondaryButton")
        self.open_button.clicked.connect(self._open_selected_output)
        self.load_button = QPushButton("载入结果" if self.language == "zh" else "Load Run")
        self.load_button.setObjectName("primaryButton")
        self.load_button.clicked.connect(self._load_selected)
        close_button = QPushButton("关闭" if self.language == "zh" else "Close")
        close_button.setObjectName("secondaryButton")
        close_button.clicked.connect(self.reject)
        buttons.addWidget(self.open_button)
        buttons.addWidget(self.load_button)
        buttons.addWidget(close_button)
        layout.addLayout(buttons)

        self.setStyleSheet(
            """
            QDialog { background: #090d12; color: #dbe7f3; font-family: Microsoft YaHei UI, Microsoft YaHei, Segoe UI; }
            QTableWidget {
                background: #0c1117;
                alternate-background-color: #101820;
                border: 1px solid #26313d;
                border-radius: 8px;
                color: #dbe7f3;
                gridline-color: #26313d;
            }
            QHeaderView::section {
                background: #111820;
                color: #9fb0c2;
                border: none;
                padding: 7px;
                font-weight: 800;
            }
            QPushButton {
                border: none;
                border-radius: 6px;
                padding: 9px 13px;
                font-weight: 800;
            }
            QPushButton#primaryButton { background: #00a6ff; color: #061019; }
            QPushButton#secondaryButton { background: #233044; color: #f8fafc; }
            """
        )

    def _populate(self) -> None:
        self.table.setRowCount(len(self.runs))
        for row, run in enumerate(self.runs):
            output_dir = Path(str(run.get("output_dir", "")))
            report_path = output_dir / "report.json"
            available = output_dir.exists() and report_path.exists()
            values = [
                time.strftime("%Y-%m-%d %H:%M", time.localtime(int(run.get("created_at", 0) or 0))),
                str(run.get("ai_mode", "")),
                str(run.get("scanned", 0)),
                str(run.get("processed", 0)),
                str(run.get("failed", 0)),
                str(output_dir),
                ("可载入" if self.language == "zh" else "Ready") if available else ("缺失" if self.language == "zh" else "Missing"),
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, run)
                if not available:
                    item.setForeground(QColor("#ff9f1c"))
                self.table.setItem(row, column, item)
        self.table.resizeColumnsToContents()
        if self.runs:
            self.table.selectRow(0)

    def _current_run(self) -> dict[str, Any] | None:
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        run = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
        return run if isinstance(run, dict) else None

    def _load_selected(self) -> None:
        run = self._current_run()
        if not run:
            return
        output_dir = Path(str(run.get("output_dir", "")))
        if not (output_dir / "report.json").exists():
            QMessageBox.information(self, self.windowTitle(), "输出不可用" if self.language == "zh" else "Output unavailable")
            return
        self.selected_run = run
        self.accept()

    def _open_selected_output(self) -> None:
        run = self._current_run()
        if not run:
            return
        output_dir = Path(str(run.get("output_dir", "")))
        if not output_dir.exists():
            QMessageBox.information(self, self.windowTitle(), "输出不可用" if self.language == "zh" else "Output unavailable")
            return
        os.startfile(output_dir)  # type: ignore[attr-defined]


class PhotoListModel(QAbstractListModel):
    def __init__(self, placeholder_icon: QIcon) -> None:
        super().__init__()
        self.records: list[dict[str, Any]] = []
        self.icons: dict[int, QIcon] = {}
        self.placeholder_icon = placeholder_icon
        self.empty_message = "Drop into the workflow by choosing a folder, then run analysis."
        self.language = "zh"
        self.category_labels = {
            "zh": {
                "portfolio_candidate": "作品候选",
                "strong_edit_candidate": "强修图候选",
                "story_candidate": "故事候选",
                "technically_weak_but_interesting": "技术弱但有趣",
                "ordinary_record": "普通记录",
                "reject_candidate": "淘汰候选",
                "failed": "失败",
            },
            "en": {},
        }
        self.user_label_labels = {
            "zh": {"keep": "保留", "maybe": "待定", "reject": "淘汰", "unlabeled": "未标记"},
            "en": {},
        }
        self.style_labels = {
            "zh": {
                "high_contrast_bw": "高反差黑白",
                "soft_documentary_color": "柔和纪实彩色",
                "cinematic_warm": "电影暖调",
                "cold_urban": "冷调城市",
                "low_key_noir": "低调暗黑",
                "natural_editorial": "自然纪实",
                "do_not_overedit": "克制修图",
            },
            "en": {},
        }

    def set_language(self, language: str) -> None:
        self.language = language if language in {"zh", "en"} else "zh"
        if self.records:
            top_left = self.index(0, 0)
            bottom_right = self.index(len(self.records) - 1, 0)
            self.dataChanged.emit(top_left, bottom_right, [int(Qt.ItemDataRole.DisplayRole)])

    def _display_value(self, value: Any, mapping: dict[str, dict[str, str]]) -> str:
        raw = str(value or "")
        if not raw:
            return ""
        translated = mapping.get(self.language, {}).get(raw)
        if translated:
            return translated
        return raw.replace("_", " ")

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
            category = self._display_value(record.get("category", ""), self.category_labels)
            user_label = self._display_value(record.get("user_label", "") or "unlabeled", self.user_label_labels)
            return f"#{record.get('rank')}  {score:.1f}  {user_label}\n{record.get('filename')}\n{category}"
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
        self.ui_font_family = apply_application_font(QApplication.instance() or QApplication([]))
        self.setProperty("lumasift_ui_font_family", self.ui_font_family)
        self.resize(1440, 900)
        self.setMinimumSize(1220, 800)
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
        self.review_mode = False
        self.qwen_queue_state: dict[str, Any] = {}
        self.preview_dialogs: list[LargePreviewDialog] = []
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
        if self.photo_model is not None:
            self.photo_model.set_language(self.language)
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
            ("review_mode", self.static_labels.get("review_mode")),
        ]:
            if label:
                label.setText(self._t(key))
        if hasattr(self, "browse_input_button"):
            self.browse_input_button.setText(self._t("browse"))
            self.browse_output_button.setText(self._t("browse"))
        if hasattr(self, "history_button"):
            self.history_button.setText(self._t("run_history"))
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
            self.advanced_button.setText(self._t("hide_advanced") if self.advanced_panel.isVisible() else self._t("advanced_settings"))
            self.review_setup_button.setText(self._t("show_setup"))
            self.review_history_button.setText(self._t("run_history"))
            self.review_new_scan_button.setText(self._t("new_scan"))
            self.search_edit.setPlaceholderText(self._t("search"))
            self.photo_list.setToolTip(self._t("grid_tooltip"))
            self.detail_hint_label.setText(self._t("detail_hint"))
            self.keep_button.setText("√")
            self.keep_button.setToolTip(self._t("keep"))
            self.maybe_button.setText("◇")
            self.maybe_button.setToolTip(self._t("maybe"))
            self.reject_button.setText("×")
            self.reject_button.setToolTip(self._t("reject"))
            self.generate_advice_button.setText(("◆ " + self._t("editing_plan")) if self.language == "zh" else "◆ Edit")
            self.generate_advice_button.setToolTip(self._t("editing_plan"))
            self.open_output_button.setText("")
            self.open_output_button.setToolTip(self._t("open_output"))
            self.open_contact_button.setText("")
            self.open_contact_button.setToolTip(self._t("open_contact"))
            if not self.records:
                self.result_count_label.setText(self._t("no_results"))
                self.status_label.setText(self._t("ready"))
                self._show_empty_grid(self._t("empty_grid"))
                self.detail_text.setHtml(self._empty_detail_html())
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
            ("sort_user", "user_priority"),
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

        self.header_frame = self._build_header()
        self.workflow_frame = self._build_workflow()
        self.controls_frame = self._build_controls()
        self.review_bar = self._build_review_bar()
        root.addWidget(self.header_frame)
        root.addWidget(self.workflow_frame)
        root.addWidget(self.controls_frame)
        root.addWidget(self.review_bar)
        self.review_bar.setVisible(False)
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
        self.photo_model.set_language(self.language)
        self.photo_list.setModel(self.photo_model)
        self.photo_list.selectionModel().selectionChanged.connect(lambda *_: self._show_selected_detail())
        self.photo_list.doubleClicked.connect(self._open_large_preview)
        self.photo_list.verticalScrollBar().valueChanged.connect(lambda *_: self._queue_visible_thumbnails())
        self._show_empty_grid("Drop into the workflow by choosing a folder, then run analysis.")
        splitter.addWidget(self.photo_list)

        self.detail_panel = QFrame()
        self.detail_panel.setObjectName("detailPanel")
        self.detail_panel.setMinimumWidth(620)
        self._apply_shadow(self.detail_panel, blur=22, y=8, alpha=24)
        detail_layout = QVBoxLayout(self.detail_panel)
        detail_layout.setContentsMargins(10, 10, 10, 10)
        detail_layout.setSpacing(7)
        guide_strip = QFrame()
        guide_strip.setObjectName("constructGuide")
        guide_layout = QHBoxLayout(guide_strip)
        guide_layout.setContentsMargins(0, 0, 0, 0)
        guide_layout.setSpacing(6)
        for name, width in [("guideCyan", 90), ("guideYellow", 46), ("guideRed", 28)]:
            segment = QFrame()
            segment.setObjectName(name)
            segment.setFixedSize(width, 6)
            guide_layout.addWidget(segment)
        guide_layout.addStretch(1)
        detail_layout.addWidget(guide_strip)
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
        self.detail_text.setMinimumHeight(80)
        self.detail_text.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.detail_text.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self.detail_text.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.detail_text.document().setDocumentMargin(0)
        self.detail_text.setHtml(self._empty_detail_html())
        detail_layout.addWidget(self.detail_text, stretch=1)

        action_bar = QFrame()
        action_bar.setObjectName("actionBar")
        action_grid = QGridLayout(action_bar)
        action_grid.setContentsMargins(8, 8, 8, 8)
        action_grid.setHorizontalSpacing(8)
        action_grid.setVerticalSpacing(8)
        self.keep_button = QPushButton("")
        self.keep_button.setObjectName("markKeepButton")
        self.keep_button.setMinimumHeight(38)
        self.keep_button.setMinimumWidth(64)
        self.keep_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.keep_button.clicked.connect(lambda: self._mark_selected("keep"))
        action_grid.addWidget(self.keep_button, 0, 0)
        self.maybe_button = QPushButton("")
        self.maybe_button.setObjectName("markMaybeButton")
        self.maybe_button.setMinimumHeight(38)
        self.maybe_button.setMinimumWidth(64)
        self.maybe_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.maybe_button.clicked.connect(lambda: self._mark_selected("maybe"))
        action_grid.addWidget(self.maybe_button, 0, 1)
        self.reject_button = QPushButton("")
        self.reject_button.setObjectName("markRejectButton")
        self.reject_button.setMinimumHeight(38)
        self.reject_button.setMinimumWidth(64)
        self.reject_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.reject_button.clicked.connect(lambda: self._mark_selected("reject"))
        action_grid.addWidget(self.reject_button, 0, 2)
        self.generate_advice_button = QPushButton("")
        self.generate_advice_button.setObjectName("primaryButton")
        self.generate_advice_button.setMinimumHeight(38)
        self.generate_advice_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.generate_advice_button.clicked.connect(self._generate_selected_advice)
        action_grid.addWidget(self.generate_advice_button, 1, 0)
        self.open_output_button = QPushButton("")
        self.open_output_button.setObjectName("secondaryButton")
        self.open_output_button.setMinimumHeight(38)
        self.open_output_button.setMinimumWidth(52)
        self.open_output_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon))
        self.open_output_button.setIconSize(QSize(18, 18))
        self.open_output_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.open_output_button.clicked.connect(lambda: self._open_path(self.output_dir))
        action_grid.addWidget(self.open_output_button, 1, 1)
        self.open_contact_button = QPushButton("")
        self.open_contact_button.setObjectName("secondaryButton")
        self.open_contact_button.setMinimumHeight(38)
        self.open_contact_button.setMinimumWidth(52)
        self.open_contact_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogDetailedView))
        self.open_contact_button.setIconSize(QSize(18, 18))
        self.open_contact_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.open_contact_button.clicked.connect(lambda: self._open_path(self.output_dir / "contact_sheet_top50.jpg"))
        action_grid.addWidget(self.open_contact_button, 1, 2)
        detail_layout.addWidget(action_bar, stretch=0)
        splitter.addWidget(self.detail_panel)
        splitter.setSizes([760, 700])
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

        self.history_button = QPushButton("")
        self.history_button.setObjectName("secondaryButton")
        self.history_button.clicked.connect(self._open_run_history)
        layout.addWidget(self.history_button)

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
            step.setCursor(Qt.CursorShape.PointingHandCursor)
            step.mousePressEvent = lambda event, step_key=key: self._focus_workflow_step(step_key)  # type: ignore[method-assign]
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

    def _build_review_bar(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("reviewBar")
        self._apply_shadow(frame, blur=18, y=6, alpha=18)
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(12, 9, 12, 9)
        layout.setSpacing(10)

        mode_label = QLabel("")
        mode_label.setObjectName("sectionTitle")
        self.static_labels["review_mode"] = mode_label
        self.review_summary_label = QLabel("")
        self.review_summary_label.setObjectName("muted")
        self.review_setup_button = QPushButton("")
        self.review_setup_button.setObjectName("ghostButton")
        self.review_setup_button.clicked.connect(lambda: self._exit_review_mode(show_advanced=True))
        self.review_history_button = QPushButton("")
        self.review_history_button.setObjectName("secondaryButton")
        self.review_history_button.clicked.connect(self._open_run_history)
        self.review_new_scan_button = QPushButton("")
        self.review_new_scan_button.setObjectName("secondaryButton")
        self.review_new_scan_button.clicked.connect(lambda: self._exit_review_mode(show_advanced=False))

        layout.addWidget(mode_label)
        layout.addWidget(self.review_summary_label, stretch=1)
        layout.addWidget(self.review_history_button)
        layout.addWidget(self.review_setup_button)
        layout.addWidget(self.review_new_scan_button)
        return frame

    def _build_controls(self) -> QFrame:
        group = QFrame()
        group.setObjectName("controlCard")
        self._apply_shadow(group, blur=24, y=8, alpha=20)
        layout = QVBoxLayout(group)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        main_row = QGridLayout()
        main_row.setHorizontalSpacing(10)
        main_row.setVerticalSpacing(8)

        self.input_edit = QLineEdit("D:/DCIM")
        self.input_edit.setObjectName("pathEdit")
        browse_input = QPushButton("Browse")
        self.browse_input_button = browse_input
        browse_input.setObjectName("secondaryButton")
        browse_input.clicked.connect(self._choose_input)
        source_label = QLabel("Photo folder")
        source_label.setObjectName("fieldLabel")
        self.static_labels["photo_folder"] = source_label
        main_row.addWidget(source_label, 0, 0)
        main_row.addWidget(self.input_edit, 0, 1)
        main_row.addWidget(browse_input, 0, 2)

        self.output_edit = QLineEdit(str(self.output_dir))
        self.output_edit.setObjectName("pathEdit")
        browse_output = QPushButton("Browse")
        self.browse_output_button = browse_output
        browse_output.setObjectName("secondaryButton")
        browse_output.clicked.connect(self._choose_output)
        output_label = QLabel("Output folder")
        output_label.setObjectName("fieldLabel")
        self.static_labels["output_folder"] = output_label
        main_row.addWidget(output_label, 1, 0)
        main_row.addWidget(self.output_edit, 1, 1)
        main_row.addWidget(browse_output, 1, 2)

        self.run_button = QPushButton("Analyze Folder")
        self.run_button.setObjectName("primaryButton")
        self.run_button.setMinimumHeight(48)
        self.run_button.setMinimumWidth(104)
        self.run_button.clicked.connect(self._start_analysis)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setObjectName("secondaryButton")
        self.cancel_button.setMinimumHeight(48)
        self.cancel_button.setMinimumWidth(74)
        self.cancel_button.clicked.connect(self._cancel_analysis)
        self.cancel_button.setEnabled(False)
        main_row.addWidget(self.run_button, 0, 3, 2, 1)
        main_row.addWidget(self.cancel_button, 0, 4, 2, 1)
        main_row.setColumnStretch(1, 1)
        layout.addLayout(main_row)

        progress_row = QHBoxLayout()
        progress_row.setContentsMargins(0, 0, 0, 0)
        progress_row.setSpacing(10)
        self.progress = QProgressBar()
        self.progress.setObjectName("runProgress")
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.status_label = QLabel("Ready")
        self.status_label.setObjectName("muted")
        self.advanced_button = QPushButton("")
        self.advanced_button.setObjectName("ghostButton")
        self.advanced_button.clicked.connect(self._toggle_advanced_panel)
        progress_row.addWidget(self.progress, stretch=1)
        progress_row.addWidget(self.status_label, stretch=0)
        progress_row.addWidget(self.advanced_button, stretch=0)
        layout.addLayout(progress_row)
        self.qwen_queue_label = QLabel("")
        self.qwen_queue_label.setObjectName("qwenQueueLabel")
        self.qwen_queue_label.setTextFormat(Qt.TextFormat.RichText)
        self.qwen_queue_label.setMinimumHeight(36)
        self.qwen_queue_label.setWordWrap(False)
        self.qwen_queue_label.setVisible(False)
        layout.addWidget(self.qwen_queue_label)

        self.mode_combo = QComboBox()
        self.mode_combo.addItem("local_only", "local_only")
        self.mode_combo.addItem("qwen_vision", "qwen_vision")
        self.mode_combo.currentTextChanged.connect(self._sync_mode_controls)
        self.mode_combo.setObjectName("settingInput")
        self.mode_combo.setFixedSize(174, 36)
        self.limit_spin = QSpinBox()
        self.limit_spin.setRange(1, 100000)
        self.limit_spin.setValue(50)
        self.limit_spin.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.limit_spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.limit_spin.setObjectName("settingInput")
        self.limit_spin.setFixedSize(128, 36)
        self.top_n_spin = QSpinBox()
        self.top_n_spin.setRange(1, 500)
        self.top_n_spin.setValue(5)
        self.top_n_spin.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.top_n_spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.top_n_spin.setObjectName("settingInput")
        self.top_n_spin.setFixedSize(128, 36)
        self.selected_top_spin = QSpinBox()
        self.selected_top_spin.setRange(1, 100)
        self.selected_top_spin.setValue(10)
        self.selected_top_spin.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.selected_top_spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.selected_top_spin.setObjectName("settingInput")
        self.selected_top_spin.setFixedSize(128, 36)
        self.display_limit_spin = QSpinBox()
        self.display_limit_spin.setRange(20, 2000)
        self.display_limit_spin.setValue(300)
        self.display_limit_spin.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.display_limit_spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.display_limit_spin.setObjectName("settingInput")
        self.display_limit_spin.setFixedSize(128, 36)

        self.advanced_panel = QFrame()
        self.advanced_panel.setObjectName("advancedPanel")
        self.advanced_panel.setFixedHeight(188)
        self.advanced_panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        advanced_layout = QVBoxLayout(self.advanced_panel)
        advanced_layout.setContentsMargins(10, 10, 10, 10)
        advanced_layout.setSpacing(10)

        settings_grid = QGridLayout()
        settings_grid.setContentsMargins(0, 0, 0, 0)
        settings_grid.setHorizontalSpacing(18)
        settings_grid.setVerticalSpacing(6)
        for col, (label, control) in enumerate([
            ("Mode", self.mode_combo),
            ("Scan", self.limit_spin),
            ("Qwen Top", self.top_n_spin),
            ("Advice Top", self.selected_top_spin),
            ("Show", self.display_limit_spin),
        ]):
            mini_label = QLabel(label)
            mini_label.setObjectName("miniLabel")
            self.static_labels[f"mini_{label}"] = mini_label
            mini_label.setMinimumHeight(18)
            settings_grid.addWidget(mini_label, 0, col)
            settings_grid.addWidget(control, 1, col)
            settings_grid.setColumnMinimumWidth(col, 136 if label != "Mode" else 180)
        settings_grid.setColumnStretch(5, 1)
        advanced_layout.addLayout(settings_grid)

        self.api_key_edit = QLineEdit()
        self.api_key_edit.setPlaceholderText("Optional: comma-separated Qwen keys. Leave empty to use .env.")
        self.api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key_edit.setMinimumHeight(34)
        self.show_key_checkbox = QCheckBox("Show")
        self.show_key_checkbox.setMinimumHeight(24)
        self.show_key_checkbox.toggled.connect(self._toggle_key_visibility)
        key_row = QWidget()
        key_layout = QHBoxLayout(key_row)
        key_layout.setContentsMargins(0, 0, 0, 0)
        key_layout.addWidget(self.api_key_edit, stretch=1)
        key_layout.addWidget(self.show_key_checkbox)
        self.save_keys_checkbox = QCheckBox("Save API keys locally")
        self.save_keys_checkbox.setMinimumHeight(24)
        self.cache_note = QLabel("Qwen mode uploads only Top-N compressed JPEG previews; RAW files stay local.")
        self.cache_note.setObjectName("muted")
        self.cache_note.setMinimumHeight(20)
        api_label = QLabel("Qwen keys")
        api_label.setObjectName("fieldLabel")
        self.static_labels["qwen_keys"] = api_label
        key_grid = QGridLayout()
        key_grid.setHorizontalSpacing(10)
        key_grid.setVerticalSpacing(6)
        key_grid.addWidget(api_label, 0, 0)
        key_grid.addWidget(key_row, 0, 1)
        key_grid.addWidget(self.save_keys_checkbox, 1, 1)
        key_grid.addWidget(self.cache_note, 2, 1)
        key_grid.setRowMinimumHeight(0, 34)
        key_grid.setRowMinimumHeight(1, 24)
        key_grid.setRowMinimumHeight(2, 20)
        key_grid.setColumnStretch(1, 1)
        advanced_layout.addLayout(key_grid)
        self.advanced_panel.setVisible(False)
        layout.addWidget(self.advanced_panel)
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
        self.sort_combo.addItems(["Score high to low", "Label priority", "Score low to high", "Rank", "Filename A-Z"])
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

    def _toggle_advanced_panel(self) -> None:
        if self.review_mode:
            self._exit_review_mode(show_advanced=True)
            return
        self.advanced_panel.setVisible(not self.advanced_panel.isVisible())
        self.advanced_button.setText(self._t("hide_advanced") if self.advanced_panel.isVisible() else self._t("advanced_settings"))

    def _focus_workflow_step(self, step: str) -> None:
        if self.review_mode:
            self._exit_review_mode(show_advanced=step in {"local", "qwen"})
        self._update_workflow(step)
        if step == "import":
            self.input_edit.setFocus()
        elif step == "local":
            self.limit_spin.setFocus()
            if not self.advanced_panel.isVisible():
                self._toggle_advanced_panel()
        elif step == "qwen":
            mode_index = self.mode_combo.findData("qwen_vision")
            if mode_index >= 0:
                self.mode_combo.setCurrentIndex(mode_index)
            if not self.advanced_panel.isVisible():
                self._toggle_advanced_panel()
            self.api_key_edit.setFocus()
        elif step == "edit":
            self.generate_advice_button.setFocus()

    def _enter_review_mode(self, summary: dict[str, Any] | None = None) -> None:
        self.review_mode = True
        self.header_frame.setVisible(False)
        self.workflow_frame.setVisible(False)
        self.controls_frame.setVisible(False)
        self.advanced_panel.setVisible(False)
        self.review_bar.setVisible(True)
        processed = summary.get("processed", len(self.records)) if summary else len(self.records)
        failed = summary.get("failed", 0) if summary else 0
        visible = len(self.visible_records)
        self.review_summary_label.setText(f"{processed} / {failed} | {visible}")
        self._update_dashboard(summary)

    def _exit_review_mode(self, *, show_advanced: bool) -> None:
        self.review_mode = False
        self.header_frame.setVisible(True)
        self.workflow_frame.setVisible(True)
        self.controls_frame.setVisible(True)
        self.review_bar.setVisible(False)
        self.advanced_panel.setVisible(show_advanced)
        self.advanced_button.setText(self._t("hide_advanced") if show_advanced else self._t("advanced_settings"))

    def _start_analysis(self) -> None:
        if self.review_mode:
            self._exit_review_mode(show_advanced=False)
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
        self.advanced_panel.setVisible(False)
        self.advanced_button.setText(self._t("advanced_settings"))
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.status_label.setText(self._t("step_local"))
        self._reset_qwen_queue_state(settings)
        self._set_grid_records([], self._t("running_grid"))
        self.detail_text.setHtml(self._empty_detail_html())
        self._update_workflow("local")
        self._update_dashboard()

        self.worker_thread = QThread()
        self.worker = AnalysisWorker(settings=settings, run_id=self.current_run_id, state_db_path=self.state_db.path)
        self.worker.moveToThread(self.worker_thread)
        self.worker_thread.started.connect(self.worker.run)
        self.worker.finished.connect(self._analysis_finished)
        self.worker.failed.connect(self._analysis_failed)
        self.worker.progress.connect(self._analysis_progress)
        self.worker.qwen_event.connect(self._analysis_qwen_event)
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
        self._enter_review_mode(payload["summary"])

    def _analysis_failed(self, message: str) -> None:
        if self.review_mode:
            self._exit_review_mode(show_advanced=True)
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

    def _reset_qwen_queue_state(self, settings: Settings) -> None:
        enabled = settings.ai_mode == "qwen_vision"
        self.qwen_queue_state = {
            "enabled": enabled,
            "model": settings.vision_model,
            "total": settings.top_n_api_analysis if enabled else 0,
            "queued": settings.top_n_api_analysis if enabled else 0,
            "running": "",
            "done": 0,
            "cache": 0,
            "failed": 0,
            "retrying": 0,
            "cancelled": 0,
            "cancelling": False,
        }
        self._render_qwen_queue_state()

    def _analysis_qwen_event(self, event: dict[str, Any]) -> None:
        event_type = str(event.get("type", ""))
        if event_type == "qwen_queue_prepared":
            total = int(event.get("total", 0) or 0)
            self.qwen_queue_state.update(
                {
                    "enabled": True,
                    "model": str(event.get("model", self.qwen_queue_state.get("model", "Qwen"))),
                    "total": total,
                    "queued": total,
                    "running": "",
                    "done": 0,
                    "cache": 0,
                    "failed": 0,
                    "retrying": 0,
                    "cancelled": 0,
                    "cancelling": False,
                }
            )
        elif event_type == "qwen_candidate_running":
            self.qwen_queue_state["queued"] = max(0, int(self.qwen_queue_state.get("queued", 0) or 0) - 1)
            self.qwen_queue_state["running"] = str(event.get("filename") or Path(str(event.get("path", ""))).name)
        elif event_type == "qwen_candidate_finished":
            status = str(event.get("status", "done"))
            if status == "cache-hit":
                self.qwen_queue_state["cache"] = int(self.qwen_queue_state.get("cache", 0) or 0) + 1
            else:
                self.qwen_queue_state["done"] = int(self.qwen_queue_state.get("done", 0) or 0) + 1
            self.qwen_queue_state["running"] = ""
        elif event_type == "qwen_candidate_failed":
            self.qwen_queue_state["failed"] = int(self.qwen_queue_state.get("failed", 0) or 0) + 1
            self.qwen_queue_state["running"] = ""
        elif event_type == "qwen_candidate_cancelled":
            self.qwen_queue_state["queued"] = max(0, int(self.qwen_queue_state.get("queued", 0) or 0) - 1)
            self.qwen_queue_state["cancelled"] = int(self.qwen_queue_state.get("cancelled", 0) or 0) + 1
            self.qwen_queue_state["running"] = ""
            self.qwen_queue_state["cancelling"] = True
        elif event_type == "qwen_queue_cancelled":
            self.qwen_queue_state["queued"] = 0
            self.qwen_queue_state["cancelling"] = False
        elif event_type == "qwen_client_event":
            client_event = event.get("client_event", {})
            if isinstance(client_event, dict) and str(client_event.get("type", "")) == "retrying":
                self.qwen_queue_state["retrying"] = int(self.qwen_queue_state.get("retrying", 0) or 0) + 1
        self._render_qwen_queue_state()

    def _render_qwen_queue_state(self) -> None:
        if not hasattr(self, "qwen_queue_label"):
            return
        if not self.qwen_queue_state.get("enabled"):
            self.qwen_queue_label.setVisible(False)
            self.qwen_queue_label.setText("")
            return
        model = self.qwen_queue_state.get("model", "Qwen")
        running = str(self.qwen_queue_state.get("running", "") or "")
        if len(running) > 32:
            running = f"{running[:29]}..."
        labels = {
            "queued": "排队" if self.language == "zh" else "Queued",
            "running": "运行" if self.language == "zh" else "Running",
            "done": "完成" if self.language == "zh" else "Done",
            "cache": "缓存" if self.language == "zh" else "Cache",
            "failed": "失败" if self.language == "zh" else "Failed",
            "retry": "重试" if self.language == "zh" else "Retry",
            "cancelled": "取消" if self.language == "zh" else "Cancelled",
        }
        queued = self.qwen_queue_state.get("queued", 0)
        done = self.qwen_queue_state.get("done", 0)
        cache = self.qwen_queue_state.get("cache", 0)
        failed = self.qwen_queue_state.get("failed", 0)
        retrying = self.qwen_queue_state.get("retrying", 0)
        cancelled = self.qwen_queue_state.get("cancelled", 0)
        cancelling = bool(self.qwen_queue_state.get("cancelling"))
        text = (
            "<span style='font-weight:900; color:#f8fafc;'>Qwen</span>"
            f"&nbsp;&nbsp;<span style='color:#9fb0c2;'>{self._escape(str(model))}</span>"
            f"&nbsp;&nbsp;&nbsp;<span title='{labels['queued']}' style='color:#9fb0c2;'>● <b>{queued}</b></span>"
            f"&nbsp;&nbsp;<span title='{labels['running']}' style='color:#ffd400;'>▶ <b>{self._escape(running or '0')}</b></span>"
            f"&nbsp;&nbsp;<span title='{labels['done']}' style='color:#00a6ff;'>√ <b>{done}</b></span>"
            f"&nbsp;&nbsp;<span title='{labels['cache']}' style='color:#61d394;'>⚡ <b>{cache}</b></span>"
            f"&nbsp;&nbsp;<span title='{labels['failed']}' style='color:#ff3b30;'>! <b>{failed}</b></span>"
            f"&nbsp;&nbsp;<span title='{labels['retry']}' style='color:#ff9f1c;'>↻ <b>{retrying}</b></span>"
            f"&nbsp;&nbsp;<span title='{labels['cancelled']}' style='color:#a78bfa;'>- <b>{cancelled}</b></span>"
        )
        if cancelling:
            text += "&nbsp;&nbsp;<span style='color:#a78bfa;'>...</span>"
        self.qwen_queue_label.setToolTip(
            f"Qwen {model}: {labels['queued']} {queued}, {labels['running']} {running or '0'}, "
            f"{labels['done']} {done}, {labels['cache']} {cache}, {labels['failed']} {failed}, "
            f"{labels['retry']} {retrying}, {labels['cancelled']} {cancelled}"
        )
        self.qwen_queue_label.setText(text)
        self.qwen_queue_label.setVisible(True)

    def _populate_records(self) -> None:
        if not hasattr(self, "photo_list"):
            return
        selected_keys = self._selected_record_keys()
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
        self._restore_selection_by_keys(selected_keys)
        self.result_count_label.setText(f"{len(self.visible_records)}/{len(self.records)}")
        self.status_label.setText(f"{len(self.visible_records)}/{len(self.records)}")
        self._update_dashboard()
        self._queue_visible_thumbnails()

    def _show_empty_grid(self, message: str) -> None:
        self._set_grid_records([], message)

    def _set_grid_records(self, records: list[dict[str, Any]], empty_message: str | None = None) -> None:
        if self.photo_model is not None:
            self.photo_model.set_records(records, empty_message)

    def _record_key(self, record: dict[str, Any]) -> str:
        path = str(record.get("path", "") or "")
        if not path:
            return str(record.get("filename", "") or "")
        try:
            return str(Path(path).expanduser().resolve())
        except OSError:
            return str(Path(path).expanduser())

    def _canonical_record(self, record: dict[str, Any]) -> dict[str, Any]:
        key = self._record_key(record)
        for candidate in self.records:
            if self._record_key(candidate) == key:
                return candidate
        return record

    def _normalized_user_label(self, record: dict[str, Any]) -> str:
        return normalized_user_label(record.get("user_label"))

    def _selected_record_keys(self) -> set[str]:
        keys: set[str] = set()
        for index in self._selected_record_indexes():
            record = index.data(Qt.ItemDataRole.UserRole)
            if isinstance(record, dict):
                keys.add(self._record_key(record))
        return keys

    def _restore_selection_by_keys(self, selected_keys: set[str]) -> None:
        if not selected_keys or self.photo_model is None or self.photo_list.selectionModel() is None:
            return
        selection_model = self.photo_list.selectionModel()
        selection_model.clearSelection()
        first_selected: QModelIndex | None = None
        for row, record in enumerate(self.photo_model.records):
            if self._record_key(record) not in selected_keys:
                continue
            index = self.photo_model.index(row, 0)
            selection_model.select(
                index,
                QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows,
            )
            if first_selected is None:
                first_selected = index
        if first_selected is not None:
            self.photo_list.scrollTo(first_selected, QAbstractItemView.ScrollHint.PositionAtCenter)
            self.photo_list.setCurrentIndex(first_selected)

    def _filtered_records(self) -> list[dict[str, Any]]:
        records = list(self.records)
        query = self.search_edit.text().strip().lower() if hasattr(self, "search_edit") else ""
        category = self.category_filter.currentData() if hasattr(self, "category_filter") else "all"
        label_filter = self.label_filter.currentData() if hasattr(self, "label_filter") else "all"
        if category and category != "all":
            records = [record for record in records if str(record.get("category", "")) == category]
        if label_filter and label_filter != "all":
            if label_filter == "unlabeled":
                records = [record for record in records if not self._normalized_user_label(record)]
            else:
                records = [record for record in records if self._normalized_user_label(record) == label_filter]
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
        elif sort_key == "user_priority":
            records.sort(
                key=lambda item: (
                    int(item.get("user_feedback_priority", 0) or 0),
                    float(item.get("final_selection_score", 0) or 0),
                ),
                reverse=True,
            )
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

    def _open_large_preview(self, index: QModelIndex) -> None:
        if not index.isValid():
            return
        record = index.data(Qt.ItemDataRole.UserRole)
        if not record:
            return
        path = Path(str(record.get("path", "")))
        if not path.exists():
            QMessageBox.information(self, self._t("no_results"), str(path))
            return
        dialog = LargePreviewDialog(record, self.output_dir, self.language, self)
        dialog.destroyed.connect(lambda *_: self.preview_dialogs.remove(dialog) if dialog in self.preview_dialogs else None)
        self.preview_dialogs.append(dialog)
        screen = QApplication.primaryScreen()
        if screen is not None:
            geometry = screen.availableGeometry()
            dialog.resize(int(geometry.width() * 0.92), int(geometry.height() * 0.9))
            dialog.move(
                geometry.x() + int((geometry.width() - dialog.width()) / 2),
                geometry.y() + int((geometry.height() - dialog.height()) / 2),
            )
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

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

    def _first_score(self, record: dict[str, Any], *keys: str) -> float:
        for key in keys:
            try:
                value = float(record.get(key, 0) or 0)
            except (TypeError, ValueError):
                value = 0.0
            if value:
                return value
        return 0.0

    def _display_category(self, value: Any) -> str:
        raw = str(value or "")
        if self.language != "zh":
            return raw.replace("_", " ")
        return {
            "portfolio_candidate": "作品候选",
            "strong_edit_candidate": "强修图候选",
            "story_candidate": "故事候选",
            "technically_weak_but_interesting": "技术弱但有趣",
            "ordinary_record": "普通记录",
            "reject_candidate": "淘汰候选",
            "failed": "处理失败",
        }.get(raw, raw.replace("_", " "))

    def _display_style(self, value: Any) -> str:
        raw = str(value or "")
        if self.language != "zh":
            return raw.replace("_", " ")
        return {
            "pending_vision_review": "等待深评",
            "high_contrast_bw_documentary": "高反差黑白纪实",
            "low_key_noir_street": "低调黑色街头",
            "cinematic_urban_color": "电影感城市彩色",
            "muted_humanistic_color": "克制人文彩色",
            "gritty_flash_street": "粗粝闪光街头",
            "soft_editorial_documentary": "柔和编辑纪实",
            "cold_metropolitan": "冷调都市",
            "warm_memory_tone": "暖调记忆感",
            "do_not_overedit": "克制轻修",
        }.get(raw, raw.replace("_", " "))

    def _display_user_label(self, value: Any) -> str:
        raw = str(value or "unlabeled")
        if self.language != "zh":
            return raw.replace("_", " ")
        return {"keep": "保留", "maybe": "待定", "reject": "淘汰", "unlabeled": "未标记"}.get(raw, raw)

    def _display_story(self, record: dict[str, Any]) -> str:
        raw = str(record.get("story_interpretation", "") or "").strip()
        if self.language == "zh" and (not raw or raw == "Not available in local_only mode."):
            return "本地模式已完成技术与可修潜力预筛；故事性、人物关系和决定性瞬间建议对 Top-N 启用 Qwen 深评。"
        return raw or ("Qwen review has not been run yet." if self.language != "zh" else "等待深度评审。")

    def _display_direction(self, record: dict[str, Any]) -> str:
        raw = str(record.get("best_editing_direction", "") or "").strip()
        if self.language == "zh" and (not raw or raw == "Run qwen_vision mode for concrete artistic editing guidance."):
            return "先点击「修图方案」生成中文参数建议；如果要判断主体关系、街拍瞬间和画面故事，再启用 Qwen 深评。"
        return raw or ("Use the selected-photo editing plan for detailed parameters." if self.language != "zh" else "生成修图方案后查看具体参数。")

    def _localized_reasons(self, values: list[Any], *, positive: bool) -> list[str]:
        result: list[str] = []
        for item in values:
            text = str(item)
            if self.language == "zh":
                replacements = {
                    "Local proxy detected workable tonal/detail structure.": "本地指标显示画面仍有可用的明暗和细节结构。",
                    "Semantic story and human-documentary value require Qwen vision review.": "故事感、人物关系和人文价值需要 Qwen 视觉深评确认。",
                    "pending vision review": "等待视觉深评",
                }
                text = replacements.get(text, text)
            result.append(text)
        if not result and self.language == "zh":
            result.append("本地指标显示仍有可修空间。" if positive else "暂无明显风险。")
        return result

    def _format_record_detail_html(self, record: dict[str, Any], selected_count: int) -> str:
        score = float(record.get("final_selection_score", 0) or 0)
        category = self._escape(self._display_category(record.get("category", "")))
        style = self._escape(self._display_style(record.get("recommended_style", "")))
        user_label = self._escape(self._display_user_label(record.get("user_label", "") or "unlabeled"))
        filename = self._escape(str(record.get("filename", "")))
        story = self._escape(self._display_story(record))
        direction = self._escape(self._display_direction(record))
        crop = self._escape(str(record.get("crop_strategy", "") or ("先不裁切；进入修图方案后再给具体比例。" if self.language == "zh" else "No crop instruction recorded.")))
        positives = self._html_list(self._localized_reasons(record.get("positive_reasons", [])[:4], positive=True), "本地指标显示仍有可修空间" if self.language == "zh" else "pending vision review")
        negatives = self._html_list(self._localized_reasons(record.get("negative_reasons", [])[:4], positive=False), "暂无明显风险" if self.language == "zh" else "none recorded")
        params = record.get("specific_edit_parameters", {}) or {}
        params_rows = "".join(
            f"<tr><td>{self._escape(str(key)).replace('_', ' ')}</td><td>{self._escape(str(value))}</td></tr>"
            for key, value in params.items()
        )
        if not params_rows:
            params_rows = f"<tr><td>{'参数' if self.language == 'zh' else 'Parameters'}</td><td>{'点击「修图方案」生成具体参数' if self.language == 'zh' else 'Generate an editing plan.'}</td></tr>"
        labels = {
            "selected": "已选" if self.language == "zh" else "Selected",
            "user_label": "标记" if self.language == "zh" else "Mark",
            "story": "故事" if self.language == "zh" else "Story",
            "human": "人文" if self.language == "zh" else "Human",
            "editability": "可修" if self.language == "zh" else "Edit",
            "story_read": "判断" if self.language == "zh" else "Read",
            "why": "亮点" if self.language == "zh" else "Signals",
            "risks": "风险" if self.language == "zh" else "Risks",
            "direction": "方向" if self.language == "zh" else "Direction",
            "crop": "裁切" if self.language == "zh" else "Crop",
            "params": "参数" if self.language == "zh" else "Parameters",
        }
        story_score = self._first_score(record, "street_documentary_potential_score", "storytelling_score")
        human_score = self._first_score(record, "human_documentary_value_score", "decisive_moment_score", "composition_score")
        editability_score = self._first_score(record, "editability_score", "editing_potential_score")
        return f"""
        <html><head>{self._detail_html_style()}</head><body>
        <div class="detail-shell">
          <div class="summary-card">
            <span class="rank">#{self._escape(str(record.get("rank", "-")))}</span>
            <span class="score">{score:.1f}</span>
            <h2>{filename}</h2>
            <p class="meta">{labels["selected"]} {selected_count} | {category} | {style} | {labels["user_label"]}: {user_label}</p>
            <div class="metrics">
              <div><b>{story_score:.0f}</b><span>{labels["story"]}</span></div>
              <div><b>{human_score:.0f}</b><span>{labels["human"]}</span></div>
              <div><b>{editability_score:.0f}</b><span>{labels["editability"]}</span></div>
            </div>
          </div>
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
        payload = build_selected_editing_advice(self.records, selected_ranks=selected_ranks, language=self.language)
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
        changed_keys: set[str] = set()
        for index in selected_indexes:
            display_record = index.data(Qt.ItemDataRole.UserRole)
            if not isinstance(display_record, dict) or not display_record.get("path"):
                continue
            record = self._canonical_record(display_record)
            record["user_label"] = label
            display_record["user_label"] = label
            apply_user_feedback_fields(record)
            apply_user_feedback_fields(display_record)
            changed_keys.add(self._record_key(record))
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
        active_label_filter = self.label_filter.currentData() if hasattr(self, "label_filter") else "all"
        if active_label_filter and active_label_filter != "all":
            self._populate_records()
            self._restore_selection_by_keys(changed_keys)
        elif self.photo_model is not None:
            for row in changed_rows:
                self.photo_model.refresh_row(row)
        self._show_selected_detail()
        self._update_dashboard()
        self.status_label.setText(f"{changed} -> {self._t(label)}")

    def _cancel_analysis(self) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        (self.output_dir / "STOP_LUMASIFT").write_text("stop", encoding="utf-8")
        if self.qwen_queue_state.get("enabled"):
            self.qwen_queue_state["cancelling"] = True
            self._render_qwen_queue_state()
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
            apply_user_feedback_fields(record)

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

    def _open_run_history(self) -> None:
        dialog = RunHistoryDialog(self.state_db.list_runs(limit=30), self.language, self)
        if dialog.exec() != QDialog.DialogCode.Accepted or not dialog.selected_run:
            return
        self._restore_history_run(dialog.selected_run)

    def _restore_history_run(self, run: dict[str, Any]) -> None:
        output_dir = Path(str(run.get("output_dir", "")))
        report_path = output_dir / "report.json"
        if not report_path.exists():
            QMessageBox.information(self, self._t("run_history"), self._t("missing_run"))
            return
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001 - broken historical reports should not crash the GUI.
            QMessageBox.warning(self, self._t("failed"), str(exc))
            return
        self.output_dir = output_dir
        self.output_edit.setText(str(output_dir))
        self.input_edit.setText(str(run.get("input_dir", "")))
        mode_index = self.mode_combo.findData(str(run.get("ai_mode", "local_only")))
        if mode_index >= 0:
            self.mode_combo.setCurrentIndex(mode_index)
        self.current_run_id = str(run.get("run_id", ""))
        self.records = list(report.get("records", []))
        self._merge_user_labels()
        self._refresh_filter_options()
        self._populate_records()
        self._enter_review_mode(
            {
                "processed": int(run.get("processed", len(self.records)) or len(self.records)),
                "failed": int(run.get("failed", 0) or 0),
            }
        )
        self.status_label.setText(self._t("done"))
        self._fade_in(self.photo_list)

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

    def _format_advice_markdown_legacy_html(self, payload: dict[str, Any]) -> str:
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

    def _format_advice_html(self, payload: dict[str, Any]) -> str:
        items = payload.get("selected_editing_advice", []) or []
        count = int(payload.get("selected_count", 0) or 0)
        title = f"{count} 张照片的修图方案" if self.language == "zh" else f"Editing plan for {count} selected photos"
        note = "已写入 selected_editing_advice.md / .json" if self.language == "zh" else "Written to selected_editing_advice.md and selected_editing_advice.json."
        blocks = "".join(self._format_advice_item_html(item) for item in items)
        return f"""
        <html><head>{self._detail_html_style()}</head><body>
        <div class="detail-shell">
          <div class="summary-card">
            <span class="rank">{self._escape(str(count))}</span>
            <h2>{title}</h2>
            <p class="meta">{note}</p>
          </div>
          {blocks}
        </div>
        </body></html>
        """

    def _format_advice_item_html(self, item: dict[str, Any]) -> str:
        rank = self._escape(str(item.get("rank", "?")))
        filename = self._escape(str(item.get("filename", "")))
        score = float(item.get("final_selection_score", 0) or 0)
        style = self._escape(str(item.get("recommended_style_label") or item.get("recommended_style", "")).replace("_", " "))
        category = self._escape(str(item.get("category_label") or item.get("category", "")).replace("_", " "))
        tone = item.get("tone_recommendation") if isinstance(item.get("tone_recommendation"), dict) else {}
        tone_text = self._escape(str(tone.get("label") or tone.get("recommendation", "")).replace("_", " "))
        tone_reason = self._escape(str(tone.get("rationale", "")))
        labels = item.get("lightroom_parameter_labels", {})
        params = item.get("lightroom_parameters", {}) or {}
        parameter_order = [
            "exposure",
            "contrast",
            "highlights",
            "shadows",
            "whites",
            "blacks",
            "texture",
            "clarity",
            "dehaze",
            "vibrance",
            "saturation",
            "temperature",
            "tint",
        ]
        rows = ""
        if isinstance(params, dict):
            for key in parameter_order:
                label = labels.get(key, key.replace("_", " ").title()) if isinstance(labels, dict) else key
                rows += f"<tr><td>{self._escape(str(label))}</td><td><b>{self._escape(str(params.get(key, '')))}</b></td></tr>"
        local_adjustments = self._html_list(
            item.get("local_adjustments", [])[:8],
            "暂无局部调整建议" if self.language == "zh" else "No local adjustments.",
        )
        handling = item.get("grain_sharpness_motion_blur", {}) or {}
        handling_rows = ""
        if isinstance(handling, dict):
            handling_labels = {
                "grain": "颗粒" if self.language == "zh" else "Grain",
                "sharpness": "锐化" if self.language == "zh" else "Sharpness",
                "motion_blur": "运动模糊" if self.language == "zh" else "Motion blur",
            }
            for key, label in handling_labels.items():
                handling_rows += f"<tr><td>{label}</td><td>{self._escape(str(handling.get(key, '')))}</td></tr>"
        text = {
            "rank": "第" if self.language == "zh" else "Rank",
            "style": "风格" if self.language == "zh" else "Style",
            "tone": "色彩方向" if self.language == "zh" else "Tone",
            "direction": "总体方向" if self.language == "zh" else "Direction",
            "params": "Lightroom 参数" if self.language == "zh" else "Lightroom Parameters",
            "crop": "裁切" if self.language == "zh" else "Crop",
            "local": "局部调整" if self.language == "zh" else "Local Adjustments",
            "detail": "质感处理" if self.language == "zh" else "Texture Handling",
        }
        return f"""
        <div class="advice-card">
          <div class="advice-head">
            <span class="rank">{text["rank"]} {rank}</span>
            <span class="pill">{category}</span>
            <span class="score small-score">{score:.1f}</span>
            <h2>{filename}</h2>
            <p class="meta">{text["style"]}: {style} | {text["tone"]}: {tone_text} - {tone_reason}</p>
          </div>
          <h3>{text["direction"]}</h3>
          <p>{self._escape(str(item.get("editing_direction", "")))}</p>
          <h3>{text["params"]}</h3>
          <table class="param-table">{rows}</table>
          <h3>{text["crop"]}</h3>
          <p>{self._escape(str(item.get("crop_strategy", "")))}</p>
          <h3>{text["local"]}</h3>
          {local_adjustments}
          <h3>{text["detail"]}</h3>
          <table>{handling_rows}</table>
        </div>
        """

    def _detail_html_style(self) -> str:
        return """
        <style>
        body { color: #dbe7f3; font-family: Microsoft YaHei UI, Microsoft YaHei, Segoe UI; font-size: 12px; background: #090d12; margin: 0; }
        h2 { margin: 0 0 4px 0; font-size: 19px; color: #f8fafc; }
        h3 { margin: 12px 0 6px 0; font-size: 12px; color: #00a6ff; text-transform: uppercase; letter-spacing: 0px; border-left: 5px solid #ffd400; padding-left: 7px; }
        p { line-height: 1.45; margin: 4px 0 8px 0; color: #c8d4e0; }
        ul { margin: 4px 0 8px 18px; padding: 0; }
        li { margin-bottom: 5px; }
        table { border-collapse: collapse; width: 100%; margin-top: 8px; }
        td { border-bottom: 1px solid #26313d; padding: 6px; vertical-align: top; color: #dbe7f3; }
        pre { white-space: pre-wrap; background: #0b0f14; border: 1px solid #26313d; border-radius: 8px; padding: 10px; color: #dbe7f3; }
        .summary-card { background: #101820; border: 1px solid #293646; border-left: 6px solid #ff3b30; border-radius: 8px; padding: 10px; margin-bottom: 10px; }
        .advice-card { background: #0d131a; border: 1px solid #293646; border-left: 6px solid #00a6ff; border-radius: 8px; padding: 10px; margin: 8px 0 12px 0; }
        .advice-head h2 { margin-top: 5px; }
        .pill { display: inline-block; margin-left: 8px; padding: 2px 8px; border-radius: 8px; background: #17324a; color: #8fd3ff; font-weight: 800; }
        .rank { color: #ffd400; font-weight: 900; }
        .score { float: right; color: #f8fafc; font-size: 32px; font-weight: 900; }
        .small-score { font-size: 24px; }
        .meta { color: #93a4b8; }
        .metrics { display: table; width: 100%; margin-top: 10px; border-spacing: 6px 0; }
        .metrics div { display: table-cell; background: #0c1117; border: 1px solid #26313d; border-radius: 8px; padding: 8px; text-align: center; }
        .metrics b { display: block; color: #ffd400; font-size: 18px; }
        .metrics span { color: #9fb0c2; font-size: 11px; }
        .score-row { margin: 8px 0 10px 0; }
        .score-row span { font-weight: 700; color: #c8d4e0; }
        .score-row b { float: right; color: #f8fafc; }
        .bar { margin-top: 4px; height: 8px; background: #26313d; border-radius: 4px; }
        .bar div { height: 8px; background: #00a6ff; border-radius: 4px; }
        .param-table td:nth-child(1) { width: 42%; color: #9fb0c2; }
        .param-table td:nth-child(2) { width: 58%; color: #f8fafc; }
        </style>
        """

    def _apply_style(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow, QWidget {
                background: #090d12;
                color: #dbe7f3;
                font-family: Microsoft YaHei UI, Microsoft YaHei, Segoe UI;
                font-size: 12px;
            }
            QLabel { background: transparent; }
            QLabel#title { font-size: 34px; font-weight: 900; color: #f8fafc; letter-spacing: 0px; }
            QLabel#subtitle { color: #9fb0c2; font-size: 13px; }
            QLabel#muted, QLabel#statCaption, QLabel#stepCaption { color: #93a4b8; }
            QLabel#sectionTitle { font-size: 14px; font-weight: 900; color: #f8fafc; }
            QLabel#fieldLabel { color: #c8d4e0; font-weight: 800; }
            QLabel#miniLabel { color: #9fb0c2; font-weight: 800; }
            QLabel#qwenQueueLabel {
                color: #dbe7f3;
                background: #101820;
                border: 1px solid #26384a;
                border-left: 6px solid #ffd400;
                border-radius: 6px;
                padding: 6px 10px;
                font-weight: 700;
            }
            QFrame#hero, QFrame#controlCard, QFrame#toolbar, QFrame#reviewBar {
                background: #111820;
                border: 1px solid #26313d;
                border-radius: 8px;
            }
            QFrame#detailPanel {
                background: #0d1218;
                border: 2px solid #26313d;
                border-left: 6px solid #ff3b30;
                border-radius: 8px;
            }
            QFrame#constructGuide { background: transparent; border: none; }
            QFrame#guideCyan { background: #00a6ff; border: none; }
            QFrame#guideYellow { background: #ffd400; border: none; }
            QFrame#guideRed { background: #ff3b30; border: none; }
            QFrame#actionBar {
                background: #0a0f15;
                border: 1px solid #26313d;
                border-radius: 8px;
            }
            QFrame#statCard {
                background: #101820;
                border: 1px solid #293646;
                border-radius: 8px;
                min-width: 92px;
            }
            QFrame#optionBar { background: transparent; border: none; }
            QFrame#advancedPanel {
                background: #101419;
                border: 1px solid #26313d;
                border-radius: 8px;
            }
            QFrame#miniControl {
                background: #151b22;
                border: 1px solid #293646;
                border-radius: 8px;
                min-width: 132px;
            }
            QLabel#statValue { font-size: 20px; font-weight: 900; color: #8fd3ff; }
            QFrame#workflow { background: transparent; }
            QFrame#stepCard {
                background: #151b22;
                border: 1px solid #26313d;
                border-radius: 8px;
            }
            QFrame#stepCard[state="active"] {
                background: #172232;
                border: 2px solid #ffd400;
            }
            QFrame#stepCard[state="done"] {
                background: #14231e;
                border: 1px solid #00a6ff;
            }
            QLabel#stepTitle { font-weight: 900; color: #f8fafc; }
            QLineEdit, QSpinBox, QComboBox, QTextEdit, QListView {
                background: #0c1117;
                border: 1px solid #2a3645;
                border-radius: 6px;
                padding: 7px;
                color: #dbe7f3;
                selection-background-color: #245d82;
            }
            QLineEdit:focus, QSpinBox:focus, QComboBox:focus, QTextEdit:focus {
                border: 2px solid #ffd400;
            }
            QSpinBox {
                font-size: 14px;
                font-weight: 900;
                padding: 0px 10px;
                min-height: 32px;
                max-height: 32px;
            }
            QComboBox#settingInput, QSpinBox#settingInput {
                min-height: 34px;
                max-height: 34px;
                padding: 0px 10px;
            }
            QSpinBox::up-button, QSpinBox::down-button {
                width: 0px;
                border: none;
            }
            QPushButton {
                border: none;
                border-radius: 6px;
                padding: 9px 13px;
                font-weight: 800;
            }
            QPushButton#primaryButton { background: #00a6ff; color: #061019; }
            QPushButton#primaryButton:hover { background: #45c0ff; }
            QPushButton#secondaryButton { background: #233044; color: #f8fafc; }
            QPushButton#secondaryButton:hover { background: #334155; }
            QPushButton#ghostButton { background: transparent; color: #ffd400; border: 1px solid #334155; }
            QPushButton#ghostButton:hover { background: #172232; }
            QPushButton#markKeepButton { background: #00a6ff; color: #061019; }
            QPushButton#markKeepButton:hover { background: #45c0ff; }
            QPushButton#markMaybeButton { background: #ffd400; color: #111827; }
            QPushButton#markMaybeButton:hover { background: #ffe45c; }
            QPushButton#markRejectButton { background: #ff3b30; color: #ffffff; }
            QPushButton#markRejectButton:hover { background: #ff625a; }
            QPushButton#markKeepButton, QPushButton#markMaybeButton, QPushButton#markRejectButton {
                font-size: 21px;
                font-weight: 900;
                padding: 4px 10px;
            }
            QPushButton:disabled { background: #26313d; color: #66778a; }
            QListView#photoGrid {
                background: #0c1117;
                border: 1px solid #26313d;
                border-radius: 8px;
                padding: 10px;
            }
            QListView#photoGrid::item {
                background: #151b22;
                border: 1px solid #293646;
                border-radius: 8px;
                padding: 8px;
                color: #dbe7f3;
            }
            QListView#photoGrid::item:hover {
                border: 1px solid #8fd3ff;
                background: #172232;
            }
            QListView#photoGrid::item:selected {
                border: 2px solid #2ea8ff;
                background: #172232;
            }
            QLabel#resultCount {
                background: #172232;
                color: #8fd3ff;
                border-radius: 6px;
                padding: 6px 10px;
                font-weight: 800;
            }
            QTextEdit#detailText {
                background: #090d12;
                border: 1px solid #26313d;
                border-radius: 8px;
                padding: 8px;
                color: #dbe7f3;
            }
            QProgressBar {
                border: 1px solid #2a3645;
                border-radius: 6px;
                text-align: center;
                background: #0c1117;
                color: #dbe7f3;
                height: 18px;
                font-weight: 700;
            }
            QProgressBar::chunk { background: #00a6ff; border-radius: 5px; }
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
    apply_application_font(app)
    app.setApplicationName("LumaSift")
    window = LumaSiftWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

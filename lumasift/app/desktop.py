from __future__ import annotations

import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QSettings, QSize, Qt, QThread, Signal
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
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
from lumasift.reports.json_report import write_json_report
from lumasift.reports.markdown_report import render_selected_editing_advice_markdown, write_markdown_report


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
    thumbnail_ready = Signal(int, str)
    finished = Signal()

    def __init__(self, records: list[dict[str, Any]], output_dir: Path, max_side: int = 360) -> None:
        super().__init__()
        self.records = records
        self.output_dir = output_dir
        self.max_side = max_side
        self.cancelled = False

    def stop(self) -> None:
        self.cancelled = True

    def run(self) -> None:
        preview_dir = self.output_dir / "gui_previews"
        for index, record in enumerate(self.records):
            if self.cancelled:
                break
            try:
                preview_path = create_jpeg_preview(Path(record["path"]), preview_dir, max_side=self.max_side)
                self.thumbnail_ready.emit(index, str(preview_path))
            except Exception:
                self.thumbnail_ready.emit(index, "")
        self.finished.emit()


class LumaSiftWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("LumaSift - Local AI Photo Curation")
        self.resize(1280, 820)
        self.records: list[dict[str, Any]] = []
        self.output_dir = Path("./outputs/gui")
        self.settings_store = QSettings("LumaSift", "LumaSift")
        self.worker_thread: QThread | None = None
        self.worker: AnalysisWorker | None = None
        self.thumbnail_thread: QThread | None = None
        self.thumbnail_worker: ThumbnailWorker | None = None
        self.visible_records: list[dict[str, Any]] = []
        self._build_ui()
        self._load_preferences()
        self._apply_style()

    def _build_ui(self) -> None:
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        title = QLabel("LumaSift")
        title.setObjectName("title")
        subtitle = QLabel("Local-first AI culling for story-driven street and documentary photography")
        subtitle.setObjectName("subtitle")
        root.addWidget(title)
        root.addWidget(subtitle)

        controls = self._build_controls()
        root.addWidget(controls)
        root.addWidget(self._build_result_toolbar())

        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.photo_list = QListWidget()
        self.photo_list.setViewMode(QListWidget.ViewMode.IconMode)
        self.photo_list.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.photo_list.setMovement(QListWidget.Movement.Static)
        self.photo_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.photo_list.setIconSize(QSize(180, 130))
        self.photo_list.setSpacing(10)
        self.photo_list.itemSelectionChanged.connect(self._show_selected_detail)
        splitter.addWidget(self.photo_list)

        detail_panel = QWidget()
        detail_layout = QVBoxLayout(detail_panel)
        detail_layout.setContentsMargins(10, 0, 0, 0)
        self.detail_text = QTextEdit()
        self.detail_text.setReadOnly(True)
        self.detail_text.setPlaceholderText("Run an analysis, then select photos to inspect story scores and editing guidance.")
        detail_layout.addWidget(self.detail_text)

        advice_buttons = QHBoxLayout()
        self.generate_advice_button = QPushButton("Generate Editing Advice for Selection")
        self.generate_advice_button.clicked.connect(self._generate_selected_advice)
        advice_buttons.addWidget(self.generate_advice_button)
        self.open_output_button = QPushButton("Open Output")
        self.open_output_button.clicked.connect(lambda: self._open_path(self.output_dir))
        advice_buttons.addWidget(self.open_output_button)
        self.open_contact_button = QPushButton("Open Contact Sheet")
        self.open_contact_button.clicked.connect(lambda: self._open_path(self.output_dir / "contact_sheet_top50.jpg"))
        advice_buttons.addWidget(self.open_contact_button)
        detail_layout.addLayout(advice_buttons)
        splitter.addWidget(detail_panel)
        splitter.setSizes([820, 420])
        root.addWidget(splitter, stretch=1)

        self.setCentralWidget(central)

    def _build_controls(self) -> QGroupBox:
        group = QGroupBox("Run")
        layout = QGridLayout(group)

        self.input_edit = QLineEdit("D:/DCIM")
        browse_input = QPushButton("Browse")
        browse_input.clicked.connect(self._choose_input)
        layout.addWidget(QLabel("Photo folder"), 0, 0)
        layout.addWidget(self.input_edit, 0, 1)
        layout.addWidget(browse_input, 0, 2)

        self.output_edit = QLineEdit(str(self.output_dir))
        browse_output = QPushButton("Browse")
        browse_output.clicked.connect(self._choose_output)
        layout.addWidget(QLabel("Output folder"), 1, 0)
        layout.addWidget(self.output_edit, 1, 1)
        layout.addWidget(browse_output, 1, 2)

        options = QWidget()
        options_layout = QFormLayout(options)
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["local_only", "qwen_vision"])
        self.mode_combo.currentTextChanged.connect(self._sync_mode_controls)
        self.limit_spin = QSpinBox()
        self.limit_spin.setRange(1, 100000)
        self.limit_spin.setValue(50)
        self.top_n_spin = QSpinBox()
        self.top_n_spin.setRange(1, 500)
        self.top_n_spin.setValue(5)
        self.selected_top_spin = QSpinBox()
        self.selected_top_spin.setRange(1, 100)
        self.selected_top_spin.setValue(10)
        self.display_limit_spin = QSpinBox()
        self.display_limit_spin.setRange(20, 2000)
        self.display_limit_spin.setValue(300)
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
        self.cache_note = QLabel("Qwen mode sends only Top-N JPEG previews and uses response cache.")
        self.cache_note.setObjectName("muted")
        options_layout.addRow("Mode", self.mode_combo)
        options_layout.addRow("Scan limit", self.limit_spin)
        options_layout.addRow("Qwen Top-N", self.top_n_spin)
        options_layout.addRow("Auto advice Top-N", self.selected_top_spin)
        options_layout.addRow("Display Top-N", self.display_limit_spin)
        options_layout.addRow("Qwen API keys", key_row)
        options_layout.addRow("", self.save_keys_checkbox)
        options_layout.addRow("", self.cache_note)
        layout.addWidget(options, 2, 0, 1, 3)

        self.run_button = QPushButton("Analyze Folder")
        self.run_button.clicked.connect(self._start_analysis)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self._cancel_analysis)
        self.cancel_button.setEnabled(False)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.status_label = QLabel("Ready")
        self.status_label.setObjectName("muted")
        layout.addWidget(self.run_button, 3, 0)
        layout.addWidget(self.cancel_button, 3, 1)
        layout.addWidget(self.progress, 3, 2)
        layout.addWidget(self.status_label, 4, 0, 1, 3)
        return group

    def _build_result_toolbar(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("toolbar")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search filename, path, category, style...")
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
        self.sort_combo = QComboBox()
        self.sort_combo.addItems(["Score high to low", "Score low to high", "Rank", "Filename A-Z"])
        self.sort_combo.currentTextChanged.connect(self._populate_records)
        self.result_count_label = QLabel("No results")
        self.result_count_label.setObjectName("muted")

        layout.addWidget(QLabel("Filter"))
        layout.addWidget(self.search_edit, stretch=1)
        layout.addWidget(self.category_filter)
        layout.addWidget(self.sort_combo)
        layout.addWidget(self.result_count_label)
        return frame

    def _choose_input(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Choose photo folder", self.input_edit.text())
        if folder:
            self.input_edit.setText(folder)
            self._save_preferences()

    def _choose_output(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Choose output folder", self.output_edit.text())
        if folder:
            self.output_edit.setText(folder)
            self.output_dir = Path(folder)
            self._save_preferences()

    def _start_analysis(self) -> None:
        input_dir = Path(self.input_edit.text()).expanduser()
        output_dir = Path(self.output_edit.text()).expanduser()
        if not input_dir.exists():
            QMessageBox.warning(self, "Input folder missing", f"Folder does not exist:\n{input_dir}")
            return

        self.output_dir = output_dir
        settings = Settings.from_env()
        settings.input_dir = input_dir
        settings.output_dir = output_dir
        settings.ai_mode = self.mode_combo.currentText()
        settings.limit = self.limit_spin.value()
        settings.top_n_api_analysis = self.top_n_spin.value()
        settings.selected_ranks = f"1-{self.selected_top_spin.value()}"
        keys_text = self.api_key_edit.text().strip()
        if keys_text:
            settings.vision_api_keys = [key.strip() for key in keys_text.split(",") if key.strip()]
        if settings.ai_mode == "qwen_vision" and not settings.vision_api_keys:
            QMessageBox.warning(
                self,
                "Qwen API key missing",
                "qwen_vision requires API keys. Enter keys in the Qwen API keys field or configure .env.",
            )
            return

        self._save_preferences()
        stop_file = output_dir / "STOP_LUMASIFT"
        stop_file.unlink(missing_ok=True)

        self.run_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.status_label.setText("Analyzing...")
        self.photo_list.clear()
        self.detail_text.clear()

        self.worker_thread = QThread()
        self.worker = AnalysisWorker(settings=settings, run_id="gui-run")
        self.worker.moveToThread(self.worker_thread)
        self.worker_thread.started.connect(self.worker.run)
        self.worker.finished.connect(self._analysis_finished)
        self.worker.failed.connect(self._analysis_failed)
        self.worker.progress.connect(self._analysis_progress)
        self.worker.finished.connect(self.worker_thread.quit)
        self.worker.failed.connect(self.worker_thread.quit)
        self.worker_thread.finished.connect(self.worker_thread.deleteLater)
        self.worker_thread.start()

    def _analysis_finished(self, payload: dict) -> None:
        self.records = list(payload["report"].get("records", []))
        self.status_label.setText(
            f"Done: {payload['summary']['processed']} processed, {payload['summary']['failed']} failed"
        )
        self.progress.setRange(0, 100)
        self.progress.setValue(100)
        self.run_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self._refresh_filter_options()
        self._populate_records()

    def _analysis_failed(self, message: str) -> None:
        self.status_label.setText("Failed")
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.run_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        QMessageBox.critical(self, "Analysis failed", message)

    def _analysis_progress(self, stage: str, current: int, total: int) -> None:
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
        self.photo_list.clear()
        self.visible_records = self._filtered_records()[: self.display_limit_spin.value()]
        placeholder = self._placeholder_icon()
        for record in self.visible_records:
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, record)
            score = float(record.get("final_selection_score", 0) or 0)
            title = f"#{record.get('rank')}  {score:.1f}\n{record.get('filename')}\n{record.get('category')}"
            item.setText(title)
            item.setToolTip(str(record.get("path", "")))
            item.setIcon(placeholder)
            item.setSizeHint(QSize(210, 210))
            self.photo_list.addItem(item)
        self.result_count_label.setText(f"Showing {len(self.visible_records)}/{len(self.records)}")
        self.status_label.setText(f"Loaded {len(self.visible_records)}/{len(self.records)} ranked photos")
        self._start_thumbnail_worker()

    def _filtered_records(self) -> list[dict[str, Any]]:
        records = list(self.records)
        query = self.search_edit.text().strip().lower() if hasattr(self, "search_edit") else ""
        category = self.category_filter.currentText() if hasattr(self, "category_filter") else "All categories"
        if category and category != "All categories":
            records = [record for record in records if str(record.get("category", "")) == category]
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
                        str(record.get("recommended_style", "")),
                    ]
                ).lower()
            ]

        sort_key = self.sort_combo.currentText() if hasattr(self, "sort_combo") else "Score high to low"
        if sort_key == "Score low to high":
            records.sort(key=lambda item: float(item.get("final_selection_score", 0) or 0))
        elif sort_key == "Filename A-Z":
            records.sort(key=lambda item: str(item.get("filename", "")).lower())
        elif sort_key == "Rank":
            records.sort(key=lambda item: int(item.get("rank", 999999) or 999999))
        else:
            records.sort(key=lambda item: float(item.get("final_selection_score", 0) or 0), reverse=True)
        return records

    def _refresh_filter_options(self) -> None:
        current = self.category_filter.currentText()
        categories = sorted({str(record.get("category", "")) for record in self.records if record.get("category")})
        self.category_filter.blockSignals(True)
        self.category_filter.clear()
        self.category_filter.addItem("All categories")
        self.category_filter.addItems(categories)
        if current in categories:
            self.category_filter.setCurrentText(current)
        self.category_filter.blockSignals(False)

    def _record_icon(self, record: dict[str, Any]) -> QIcon:
        try:
            preview_path = create_jpeg_preview(Path(record["path"]), self.output_dir / "gui_previews", max_side=360)
            pixmap = QPixmap(str(preview_path))
            return QIcon(pixmap)
        except Exception:
            pixmap = QPixmap(180, 130)
            pixmap.fill(Qt.GlobalColor.lightGray)
            return QIcon(pixmap)

    def _placeholder_icon(self) -> QIcon:
        pixmap = QPixmap(180, 130)
        pixmap.fill(Qt.GlobalColor.lightGray)
        return QIcon(pixmap)

    def _start_thumbnail_worker(self) -> None:
        if not self.visible_records:
            return
        self.thumbnail_thread = QThread()
        self.thumbnail_worker = ThumbnailWorker(self.visible_records, self.output_dir, max_side=360)
        self.thumbnail_worker.moveToThread(self.thumbnail_thread)
        self.thumbnail_thread.started.connect(self.thumbnail_worker.run)
        self.thumbnail_worker.thumbnail_ready.connect(self._thumbnail_ready)
        self.thumbnail_worker.finished.connect(self.thumbnail_thread.quit)
        self.thumbnail_thread.finished.connect(self.thumbnail_thread.deleteLater)
        self.thumbnail_thread.start()

    def _stop_thumbnail_worker(self) -> None:
        if self.thumbnail_worker is not None:
            self.thumbnail_worker.stop()
        if self.thumbnail_thread is not None and self.thumbnail_thread.isRunning():
            self.thumbnail_thread.quit()
            self.thumbnail_thread.wait(1500)
        self.thumbnail_worker = None
        self.thumbnail_thread = None

    def _thumbnail_ready(self, index: int, preview_path: str) -> None:
        if not preview_path or index >= self.photo_list.count():
            return
        item = self.photo_list.item(index)
        if item is None:
            return
        pixmap = QPixmap(preview_path)
        if not pixmap.isNull():
            item.setIcon(QIcon(pixmap))

    def _show_selected_detail(self) -> None:
        selected = self.photo_list.selectedItems()
        if not selected:
            self.detail_text.clear()
            return
        record = selected[0].data(Qt.ItemDataRole.UserRole)
        self.detail_text.setPlainText(self._format_record_detail(record, len(selected)))

    def _format_record_detail(self, record: dict[str, Any], selected_count: int) -> str:
        reasons = "\n".join(f"- {item}" for item in record.get("positive_reasons", [])[:4])
        negatives = "\n".join(f"- {item}" for item in record.get("negative_reasons", [])[:4])
        params = json.dumps(record.get("specific_edit_parameters", {}), ensure_ascii=False, indent=2)
        return (
            f"Selected: {selected_count}\n\n"
            f"Rank #{record.get('rank')}  Score {record.get('final_selection_score')}\n"
            f"File: {record.get('filename')}\n"
            f"Category: {record.get('category')}\n"
            f"Style: {record.get('recommended_style')}\n\n"
            f"Story interpretation:\n{record.get('story_interpretation', '')}\n\n"
            f"Why keep:\n{reasons or '- pending vision review'}\n\n"
            f"Risks:\n{negatives or '- none recorded'}\n\n"
            f"Editing direction:\n{record.get('best_editing_direction', '')}\n\n"
            f"Crop:\n{record.get('crop_strategy', '')}\n\n"
            f"Parameters:\n{params}"
        )

    def _generate_selected_advice(self) -> None:
        selected_items = self.photo_list.selectedItems()
        if selected_items:
            selected_ranks = [item.data(Qt.ItemDataRole.UserRole).get("rank") for item in selected_items]
        else:
            selected_ranks = list(range(1, min(self.selected_top_spin.value(), len(self.records)) + 1))

        if not self.records:
            QMessageBox.information(self, "No records", "Run an analysis first.")
            return
        payload = build_selected_editing_advice(self.records, selected_ranks=selected_ranks)
        json_path = self.output_dir / "selected_editing_advice.json"
        md_path = self.output_dir / "selected_editing_advice.md"
        write_json_report(json_path, payload)
        write_markdown_report(md_path, render_selected_editing_advice_markdown(payload))
        self.detail_text.setPlainText(render_selected_editing_advice_markdown(payload))
        self.status_label.setText(f"Editing advice written: {md_path}")

    def _cancel_analysis(self) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        (self.output_dir / "STOP_LUMASIFT").write_text("stop", encoding="utf-8")
        self.status_label.setText("Cancel requested. Finishing current photo...")
        self.cancel_button.setEnabled(False)

    def _toggle_key_visibility(self, enabled: bool) -> None:
        self.api_key_edit.setEchoMode(QLineEdit.EchoMode.Normal if enabled else QLineEdit.EchoMode.Password)

    def _sync_mode_controls(self) -> None:
        qwen_enabled = self.mode_combo.currentText() == "qwen_vision"
        self.top_n_spin.setEnabled(qwen_enabled)
        self.api_key_edit.setEnabled(qwen_enabled)
        self.show_key_checkbox.setEnabled(qwen_enabled)
        self.save_keys_checkbox.setEnabled(qwen_enabled)

    def _load_preferences(self) -> None:
        self.input_edit.setText(str(self.settings_store.value("input_dir", "D:/DCIM")))
        self.output_edit.setText(str(self.settings_store.value("output_dir", "./outputs/gui")))
        self.output_dir = Path(self.output_edit.text())
        self.limit_spin.setValue(int(self.settings_store.value("limit", 50)))
        self.top_n_spin.setValue(int(self.settings_store.value("top_n", 5)))
        self.selected_top_spin.setValue(int(self.settings_store.value("selected_top", 10)))
        self.display_limit_spin.setValue(int(self.settings_store.value("display_limit", 300)))
        mode = str(self.settings_store.value("mode", "local_only"))
        self.mode_combo.setCurrentText(mode if mode in {"local_only", "qwen_vision"} else "local_only")
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
        self.settings_store.setValue("mode", self.mode_combo.currentText())
        if self.save_keys_checkbox.isChecked():
            self.settings_store.setValue("api_keys", self.api_key_edit.text())
        else:
            self.settings_store.remove("api_keys")

    def _open_path(self, path: Path) -> None:
        try:
            if not path.exists():
                QMessageBox.information(self, "Not found", f"Path does not exist yet:\n{path}")
                return
            os.startfile(path)  # type: ignore[attr-defined]
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Open failed", str(exc))

    def _apply_style(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow, QWidget { background: #f3f3f3; color: #202020; font-family: Segoe UI, Microsoft YaHei; }
            QLabel#title { font-size: 30px; font-weight: 700; color: #111; }
            QLabel#subtitle, QLabel#muted { color: #666; }
            QGroupBox { border: 1px solid #d0d0d0; border-radius: 4px; margin-top: 10px; padding: 12px; background: #fbfbfb; }
            QFrame#toolbar { background: #f3f3f3; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }
            QLineEdit, QSpinBox, QComboBox, QTextEdit, QListWidget { background: #ffffff; border: 1px solid #c8c8c8; border-radius: 3px; padding: 5px; }
            QPushButton { background: #0078d4; color: white; border: none; border-radius: 3px; padding: 8px 12px; font-weight: 600; }
            QPushButton:hover { background: #106ebe; }
            QPushButton:disabled { background: #a0a0a0; }
            QListWidget::item { background: #ffffff; border: 1px solid #dddddd; border-radius: 4px; padding: 6px; }
            QListWidget::item:selected { border: 2px solid #0078d4; background: #e8f2fb; }
            QProgressBar { border: 1px solid #c8c8c8; border-radius: 3px; text-align: center; background: #ffffff; }
            QProgressBar::chunk { background: #0078d4; }
            """
        )

    def closeEvent(self, event: Any) -> None:
        self._stop_thumbnail_worker()
        if self.worker_thread is not None and self.worker_thread.isRunning():
            self._cancel_analysis()
            self.worker_thread.quit()
            self.worker_thread.wait(1500)
        super().closeEvent(event)


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("LumaSift")
    window = LumaSiftWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

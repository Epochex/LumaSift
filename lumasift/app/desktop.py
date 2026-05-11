from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QSize, Qt, QThread, Signal
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

    def __init__(self, settings: Settings, run_id: str) -> None:
        super().__init__()
        self.settings = settings
        self.run_id = run_id

    def run(self) -> None:
        try:
            configure_logging(self.settings.output_dir)
            result = LumaSiftHarness(settings=self.settings, run_id=self.run_id).run()
            report = json.loads(result.report_json.read_text(encoding="utf-8"))
            self.finished.emit({"summary": result.summary, "report": report, "output_dir": str(self.settings.output_dir)})
        except Exception as exc:  # noqa: BLE001 - GUI must show failures instead of crashing.
            logging.exception("Analysis failed")
            self.failed.emit(str(exc))


class LumaSiftWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("LumaSift - Local AI Photo Curation")
        self.resize(1280, 820)
        self.records: list[dict[str, Any]] = []
        self.output_dir = Path("./outputs/gui")
        self.worker_thread: QThread | None = None
        self.worker: AnalysisWorker | None = None
        self._build_ui()
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
        self.open_output_button = QPushButton("Choose Output Folder")
        self.open_output_button.clicked.connect(self._choose_output)
        advice_buttons.addWidget(self.open_output_button)
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
        self.limit_spin = QSpinBox()
        self.limit_spin.setRange(1, 100000)
        self.limit_spin.setValue(50)
        self.top_n_spin = QSpinBox()
        self.top_n_spin.setRange(1, 500)
        self.top_n_spin.setValue(5)
        self.selected_top_spin = QSpinBox()
        self.selected_top_spin.setRange(1, 100)
        self.selected_top_spin.setValue(10)
        self.cache_note = QLabel("Qwen mode sends only Top-N JPEG previews and uses response cache.")
        self.cache_note.setObjectName("muted")
        options_layout.addRow("Mode", self.mode_combo)
        options_layout.addRow("Scan limit", self.limit_spin)
        options_layout.addRow("Qwen Top-N", self.top_n_spin)
        options_layout.addRow("Auto advice Top-N", self.selected_top_spin)
        options_layout.addRow("", self.cache_note)
        layout.addWidget(options, 2, 0, 1, 3)

        self.run_button = QPushButton("Analyze Folder")
        self.run_button.clicked.connect(self._start_analysis)
        self.progress = QProgressBar()
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.status_label = QLabel("Ready")
        self.status_label.setObjectName("muted")
        layout.addWidget(self.run_button, 3, 0)
        layout.addWidget(self.progress, 3, 1)
        layout.addWidget(self.status_label, 3, 2)
        return group

    def _choose_input(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Choose photo folder", self.input_edit.text())
        if folder:
            self.input_edit.setText(folder)

    def _choose_output(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Choose output folder", self.output_edit.text())
        if folder:
            self.output_edit.setText(folder)
            self.output_dir = Path(folder)

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

        self.run_button.setEnabled(False)
        self.progress.setRange(0, 0)
        self.status_label.setText("Analyzing...")
        self.photo_list.clear()
        self.detail_text.clear()

        self.worker_thread = QThread()
        self.worker = AnalysisWorker(settings=settings, run_id="gui-run")
        self.worker.moveToThread(self.worker_thread)
        self.worker_thread.started.connect(self.worker.run)
        self.worker.finished.connect(self._analysis_finished)
        self.worker.failed.connect(self._analysis_failed)
        self.worker.finished.connect(self.worker_thread.quit)
        self.worker.failed.connect(self.worker_thread.quit)
        self.worker_thread.finished.connect(self.worker_thread.deleteLater)
        self.worker_thread.start()

    def _analysis_finished(self, payload: dict) -> None:
        self.records = list(payload["report"].get("records", []))
        self.status_label.setText(
            f"Done: {payload['summary']['processed']} processed, {payload['summary']['failed']} failed"
        )
        self.progress.setRange(0, 1)
        self.progress.setValue(1)
        self.run_button.setEnabled(True)
        self._populate_records()

    def _analysis_failed(self, message: str) -> None:
        self.status_label.setText("Failed")
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.run_button.setEnabled(True)
        QMessageBox.critical(self, "Analysis failed", message)

    def _populate_records(self) -> None:
        self.photo_list.clear()
        for record in self.records[:500]:
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, record)
            score = float(record.get("final_selection_score", 0) or 0)
            title = f"#{record.get('rank')}  {score:.1f}\n{record.get('filename')}\n{record.get('category')}"
            item.setText(title)
            item.setToolTip(str(record.get("path", "")))
            item.setIcon(self._record_icon(record))
            item.setSizeHint(QSize(210, 210))
            self.photo_list.addItem(item)

    def _record_icon(self, record: dict[str, Any]) -> QIcon:
        try:
            preview_path = create_jpeg_preview(Path(record["path"]), self.output_dir / "gui_previews", max_side=360)
            pixmap = QPixmap(str(preview_path))
            return QIcon(pixmap)
        except Exception:
            pixmap = QPixmap(180, 130)
            pixmap.fill(Qt.GlobalColor.lightGray)
            return QIcon(pixmap)

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

    def _apply_style(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow, QWidget { background: #f3f3f3; color: #202020; font-family: Segoe UI, Microsoft YaHei; }
            QLabel#title { font-size: 30px; font-weight: 700; color: #111; }
            QLabel#subtitle, QLabel#muted { color: #666; }
            QGroupBox { border: 1px solid #d0d0d0; border-radius: 4px; margin-top: 10px; padding: 12px; background: #fbfbfb; }
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


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("LumaSift")
    window = LumaSiftWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

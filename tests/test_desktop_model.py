from __future__ import annotations

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QIcon
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from PIL import Image

from lumasift.app.desktop import LargePreviewWorker, LumaSiftWindow, PhotoListModel


def test_photo_list_model_handles_large_record_sets() -> None:
    app = QApplication.instance() or QApplication([])
    _ = app
    model = PhotoListModel(QIcon())
    records = [
        {
            "rank": index + 1,
            "path": f"C:/tmp/{index}.jpg",
            "filename": f"{index}.jpg",
            "final_selection_score": 90.0,
            "category": "story_candidate",
            "recommended_style": "test_style",
            "user_label": "keep" if index == 0 else "",
        }
        for index in range(2000)
    ]

    model.set_records(records)

    assert model.rowCount() == 2000
    first = model.index(0, 0)
    assert "保留" in model.data(first, int(Qt.ItemDataRole.DisplayRole))
    model.set_language("en")
    assert "keep" in model.data(first, int(Qt.ItemDataRole.DisplayRole))
    assert model.data(first, int(Qt.ItemDataRole.UserRole))["filename"] == "0.jpg"


def test_large_preview_worker_creates_cached_preview(tmp_path) -> None:
    source = tmp_path / "source.jpg"
    Image.new("RGB", (120, 80), (20, 30, 40)).save(source)
    worker = LargePreviewWorker(source, tmp_path / "out", max_side=64)
    emitted: list[str] = []
    worker.finished.connect(emitted.append)

    worker.run()

    assert emitted
    assert emitted[0].endswith(".preview.jpg")


def test_window_starts_in_chinese_even_after_saved_english() -> None:
    app = QApplication.instance() or QApplication([])
    _ = app
    settings = QSettings("LumaSift", "LumaSift")
    settings.setValue("language", "en")

    window = LumaSiftWindow()

    assert window.language == "zh"
    assert window.language_combo.currentText() == "中文"


def test_detail_html_renders_qwen_story_evidence() -> None:
    app = QApplication.instance() or QApplication([])
    _ = app
    window = LumaSiftWindow()
    window.language = "zh"
    html = window._format_record_detail_html(
        {
            "rank": 1,
            "filename": "candidate.arw",
            "final_selection_score": 88.5,
            "category": "story_candidate",
            "recommended_style": "muted_humanistic_color",
            "user_label": "keep",
            "story_interpretation": "行人、车辆和街角标识形成城市压迫感。",
            "visible_evidence": ["行人正穿过车辆之间的空隙", "KFC 招牌提供地点线索"],
            "subject_relationship": "人物被车流和商业标识包围。",
            "decisive_moment_read": "动作尚未被遮挡，是可读的街头瞬间。",
            "why_this_frame": "这一帧的人车间距比相邻帧更完整。",
            "avoid_overediting": "不要抹掉街道颗粒和招牌信息。",
            "positive_reasons": ["人和环境关系具体"],
            "negative_reasons": ["边缘车辆略抢眼"],
            "specific_edit_parameters": {"contrast": "+12"},
        },
        1,
    )

    assert "可见证据" in html
    assert "行人正穿过车辆之间的空隙" in html
    assert "为什么是这张" in html
    assert "这一帧的人车间距" in html
    assert "float:" not in html
    window.close()


def test_api_key_entry_switches_to_qwen_review_mode() -> None:
    app = QApplication.instance() or QApplication([])
    _ = app
    window = LumaSiftWindow()
    window.language = "en"
    local_index = window.mode_combo.findData("local_only")
    window.mode_combo.setCurrentIndex(local_index)

    window._api_key_text_edited("sk-test")

    assert window.mode_combo.currentData() == "qwen_vision"
    assert window.top_n_spin.isEnabled()
    assert "Qwen" in window.status_label.text()
    window.close()


def test_local_mode_with_configured_qwen_key_shows_deep_review_hint() -> None:
    app = QApplication.instance() or QApplication([])
    _ = app
    window = LumaSiftWindow()
    window.language = "en"
    window._retranslate_ui()
    local_index = window.mode_combo.findData("local_only")
    window.mode_combo.setCurrentIndex(local_index)
    window.api_key_edit.setText("sk-test")
    window.qwen_queue_state = {"enabled": False}

    window._render_qwen_queue_state()

    assert not window.qwen_queue_label.isHidden()
    assert "Local" in window.qwen_queue_label.toolTip()
    assert "deep-review" in window.qwen_queue_label.toolTip()
    window.close()


def test_top_nav_settings_button_toggles_setup_panel_like_user_click() -> None:
    app = QApplication.instance() or QApplication([])
    _ = app
    window = LumaSiftWindow()
    window.show()
    app.processEvents()

    assert window.main_page.isVisible()
    assert not window.controls_frame.isVisible()
    assert window.title_label.text() != "LumaSift"
    QTest.mouseClick(window.settings_nav_button, Qt.MouseButton.LeftButton)
    app.processEvents()

    assert window.settings_page.isVisible()
    assert window.controls_frame.isVisible()
    assert window.advanced_panel.isVisible()
    QTest.mouseClick(window.nav_buttons["main"], Qt.MouseButton.LeftButton)
    app.processEvents()

    assert window.main_page.isVisible()
    assert not window.controls_frame.isVisible()
    window.close()


def test_review_mode_keeps_top_navigation_visible() -> None:
    app = QApplication.instance() or QApplication([])
    _ = app
    window = LumaSiftWindow()
    window.show()
    app.processEvents()

    window._enter_review_mode({"processed": 1, "failed": 0})
    app.processEvents()

    assert window.header_frame.isVisible()
    assert not window.workflow_frame.isVisible()
    assert not window.controls_frame.isVisible()
    window.close()


def test_cancel_button_does_not_mark_window_for_close(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    _ = app
    window = LumaSiftWindow()
    window.output_dir = tmp_path
    window.pending_close = True
    window.cancel_button.setEnabled(True)
    window.main_cancel_button.setEnabled(True)

    window._cancel_analysis()

    assert (tmp_path / "STOP_LUMASIFT").exists()
    assert not window.pending_close
    assert not window.allow_close
    assert not window.cancel_button.isEnabled()
    assert not window.main_cancel_button.isEnabled()
    window.close()


def test_qwen_progress_panel_tracks_deep_review_events() -> None:
    app = QApplication.instance() or QApplication([])
    _ = app
    window = LumaSiftWindow()
    window.language = "zh"
    window._analysis_qwen_event({"type": "qwen_queue_prepared", "total": 3, "model": "qwen3.6-plus"})
    window._analysis_qwen_event({"type": "qwen_candidate_running", "filename": "frame_001.jpg"})
    window._analysis_qwen_event({"type": "qwen_candidate_finished", "status": "done"})

    assert not window.qwen_status_frame.isHidden()
    assert window.qwen_progress.maximum() == 3
    assert window.qwen_progress.value() == 1
    assert "qwen3.6-plus" in window.qwen_queue_label.text()
    assert window.qwen_stage_label.text()
    window.close()


def test_review_status_filter_shows_qwen_reviewed_records() -> None:
    app = QApplication.instance() or QApplication([])
    _ = app
    window = LumaSiftWindow()
    window.language = "en"
    window.records = [
        {"rank": 1, "filename": "local.jpg", "path": "C:/tmp/local.jpg", "analysis_source": "local_proxy", "final_selection_score": 92},
        {
            "rank": 2,
            "filename": "reviewed.jpg",
            "path": "C:/tmp/reviewed.jpg",
            "analysis_source": "qwen_vision",
            "analysis_quality": "concrete",
            "qwen_status": "done",
            "final_selection_score": 88,
        },
        {"rank": 3, "filename": "failed.jpg", "path": "C:/tmp/failed.jpg", "qwen_status": "failed", "final_selection_score": 80},
    ]
    window._refresh_filter_options()

    window.review_filter.setCurrentIndex(window.review_filter.findData("reviewed"))
    reviewed = window._filtered_records()
    assert [record["filename"] for record in reviewed] == ["reviewed.jpg"]

    window.review_filter.setCurrentIndex(window.review_filter.findData("failed"))
    failed = window._filtered_records()
    assert [record["filename"] for record in failed] == ["failed.jpg"]
    window.close()


def test_default_advice_prefers_qwen_reviewed_records_over_local_top_rank() -> None:
    app = QApplication.instance() or QApplication([])
    _ = app
    window = LumaSiftWindow()
    window.records = [
        {"rank": 1, "filename": "local-top.jpg", "path": "C:/tmp/local-top.jpg", "analysis_source": "local_proxy", "final_selection_score": 98},
        {
            "rank": 2,
            "filename": "qwen-concrete.jpg",
            "path": "C:/tmp/qwen-concrete.jpg",
            "analysis_source": "qwen_vision",
            "analysis_quality": "concrete",
            "qwen_status": "done",
            "final_selection_score": 87,
        },
        {
            "rank": 3,
            "filename": "qwen-partial.jpg",
            "path": "C:/tmp/qwen-partial.jpg",
            "analysis_source": "qwen_vision",
            "analysis_quality": "weak",
            "qwen_status": "cache-hit",
            "final_selection_score": 93,
        },
    ]
    window.selected_top_spin.setValue(2)
    window._refresh_filter_options()

    assert window._default_advice_ranks(window._filtered_records()) == [2, 3]
    window.close()

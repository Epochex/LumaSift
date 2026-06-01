from __future__ import annotations

from types import SimpleNamespace

from PySide6.QtCore import QItemSelectionModel, QSettings, Qt
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from PIL import Image

from lumasift.analysis.qwen_story import QWEN_STORY_PROMPT_VERSION
from lumasift.app.desktop import LargePreviewDialog, LargePreviewWorker, LumaSiftWindow, PhotoListModel


def reset_shortcut_settings() -> None:
    settings = QSettings("LumaSift", "LumaSift")
    settings.remove("shortcuts_version")
    for action in ("keep", "reject", "toggle_mark", "maybe", "select_all", "invert_selection"):
        settings.remove(f"shortcut_{action}")


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


def test_large_preview_dialog_draws_llm_crop_overlay(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    _ = app
    record = {
        "path": str(tmp_path / "source.jpg"),
        "filename": "source.jpg",
        "analysis_source": "qwen_vision",
        "editing_plan": {
            "crop_plan": {
                "crop_box": {
                    "x": 0.25,
                    "y": 0.20,
                    "width": 0.50,
                    "height": 0.60,
                    "reason": "keep the pedestrian relationship readable",
                }
            }
        },
    }
    dialog = LargePreviewDialog(record, tmp_path, "en")
    pixmap = QPixmap(200, 100)
    pixmap.fill(QColor(80, 90, 100))

    rendered = dialog._pixmap_with_crop_overlay(pixmap).toImage()

    border = rendered.pixelColor(50, 20)
    outside = rendered.pixelColor(10, 10)
    inside = rendered.pixelColor(90, 50)
    assert border.red() > 200 and border.green() > 170
    assert outside.value() < inside.value()
    assert "pedestrian relationship" in dialog.crop_note_label.text()
    dialog.close()


def test_large_preview_dialog_supports_zoom_controls(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    _ = app
    record = {"path": str(tmp_path / "source.jpg"), "filename": "source.jpg"}
    dialog = LargePreviewDialog(record, tmp_path, "en")
    pixmap = QPixmap(200, 100)
    pixmap.fill(QColor(80, 90, 100))
    dialog.original_pixmap = pixmap

    dialog._set_zoom_factor(1.5)

    assert dialog.fit_to_window is False
    assert dialog.image_label.pixmap().width() == 300
    assert dialog.zoom_label.text() == "150%"
    dialog.close()


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
            "analysis_source": "qwen_vision",
            "analysis_quality": "concrete",
            "qwen_status": "done",
            "qwen_prompt_version": QWEN_STORY_PROMPT_VERSION,
            "story_interpretation": "行人、车辆和街角标识形成城市压迫感。",
            "professional_review": {
                "editorial_summary": "行人被车流和街角标识夹在一起，城市压力比普通街景更具体，适合作为候选。",
                "story_read": "人物穿过车辆之间的空隙，动作尚未被遮挡破坏，环境线索支撑人文阅读。",
                "composition_read": "边缘车辆略抢眼，但人物和街角标识仍形成可读的前后关系。",
                "selection_logic": "如果相邻帧有更清楚的人车间距再比较，否则这一帧值得保留。",
                "editing_logic": "后期应压低边缘车辆，保留街道颗粒和招牌信息。",
                "final_recommendation": "保留候选。",
            },
            "visible_evidence": ["行人正穿过车辆之间的空隙", "KFC 招牌提供地点线索"],
            "subject_relationship": "人物被车流和商业标识包围。",
            "decisive_moment_read": "动作尚未被遮挡，是可读的街头瞬间。",
            "why_this_frame": "这一帧的人车间距比相邻帧更完整。",
            "avoid_overediting": "不要抹掉街道颗粒和招牌信息。",
            "positive_reasons": ["人和环境关系具体"],
            "negative_reasons": ["边缘车辆略抢眼"],
            "editing_plan": {
                "crop_plan": {
                    "crop_box": {
                        "x": 0.08,
                        "y": 0.05,
                        "width": 0.84,
                        "height": 0.90,
                        "reason": "收掉边缘空白并保留人车关系",
                    }
                }
            },
            "specific_edit_parameters": {"contrast": "+12"},
        },
        1,
    )

    assert "可见证据" in html
    assert "专业深评" in html
    assert "城市压力比普通街景更具体" in html
    assert "行人正穿过车辆之间的空隙" in html
    assert "为什么是这张" in html
    assert "这一帧的人车间距" in html
    assert "预览裁切框" in html
    assert "收掉边缘空白" in html
    assert "float:" not in html
    window.close()


def test_detail_html_flags_failed_or_local_reviews_as_not_professional() -> None:
    app = QApplication.instance() or QApplication([])
    _ = app
    window = LumaSiftWindow()
    window.language = "zh"

    failed_html = window._format_record_detail_html(
        {
            "rank": 1,
            "filename": "failed.arw",
            "final_selection_score": 70,
            "category": "story_candidate",
            "analysis_source": "local_proxy",
            "qwen_status": "failed",
            "errors": ["qwen_vision_failed: Read timed out"],
            "local_metrics": {"brightness": 118, "contrast": 42},
        },
        1,
    )
    local_html = window._format_record_detail_html(
        {
            "rank": 2,
            "filename": "local.arw",
            "final_selection_score": 64,
            "category": "story_candidate",
            "analysis_source": "local_proxy",
            "local_metrics": {"brightness": 100, "contrast": 35},
        },
        1,
    )

    assert "深评失败：当前不是专业摄影判断" in failed_html
    assert "Read timed out" in failed_html
    assert "仅本地预筛：请先深评选中照片" in local_html
    assert "不是专业深评" in local_html
    window.close()


def test_detail_html_hides_stale_qwen_story_text() -> None:
    app = QApplication.instance() or QApplication([])
    _ = app
    window = LumaSiftWindow()
    window.language = "en"

    html = window._format_record_detail_html(
        {
            "rank": 1,
            "filename": "stale.arw",
            "final_selection_score": 70,
            "category": "story_candidate",
            "analysis_source": "qwen_vision",
            "analysis_quality": "concrete",
            "qwen_status": "done",
            "qwen_prompt_version": "qwen-story-v8",
            "story_interpretation": "old qwen story must not be displayed",
            "local_metrics": {"brightness": 118, "contrast": 42},
        },
        1,
    )

    assert "Stale deep review" in html
    assert "old qwen story must not be displayed" not in html
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
    assert "LLM Deep Analysis" in window.status_label.text()
    window.close()


def test_mode_labels_explain_token_cost_and_missing_api_is_highlighted(monkeypatch) -> None:
    monkeypatch.setattr("lumasift.app.desktop.Settings.from_env", staticmethod(lambda: SimpleNamespace(vision_api_keys=[])))
    app = QApplication.instance() or QApplication([])
    _ = app
    window = LumaSiftWindow()
    window.language = "zh"
    window._retranslate_ui()

    assert window.mode_combo.itemText(window.mode_combo.findData("local_only")) == "本地模式(不消耗token)"
    assert window.mode_combo.itemText(window.mode_combo.findData("qwen_vision")) == "LLM深度分析(需要填入API，消耗token)"

    window.mode_combo.setCurrentIndex(window.mode_combo.findData("qwen_vision"))
    window.api_key_edit.clear()
    window._sync_mode_controls()

    assert window.api_key_edit.property("attention") == "true"
    assert "需要 API key" in window.cache_note.text()
    window.close()


def test_startup_setup_message_confirms_paths_and_local_no_api(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("lumasift.app.desktop.Settings.from_env", staticmethod(lambda: SimpleNamespace(vision_api_keys=[])))
    app = QApplication.instance() or QApplication([])
    _ = app
    window = LumaSiftWindow()
    window.language = "zh"
    window.input_edit.setText(str(tmp_path))
    window.output_edit.setText(str(tmp_path / "out"))
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("local_only"))
    window.api_key_edit.clear()

    message = window._startup_setup_message()

    assert "读取照片目录" in message
    assert str(tmp_path) in message
    assert "保存结果目录" in message
    assert "没有导入 API key" in message
    assert "不会调用 API" in message
    window.close()


def test_startup_setup_message_warns_when_deep_analysis_has_no_key(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("lumasift.app.desktop.Settings.from_env", staticmethod(lambda: SimpleNamespace(vision_api_keys=[])))
    app = QApplication.instance() or QApplication([])
    _ = app
    window = LumaSiftWindow()
    window.language = "zh"
    window.input_edit.setText(str(tmp_path))
    window.output_edit.setText(str(tmp_path / "out"))
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("qwen_vision"))
    window.api_key_edit.clear()

    message = window._startup_setup_message()

    assert "LLM 深度分析" in message or "LLM深度分析" in message
    assert "还没有 API key" in message
    assert "配置 key" in message
    window.close()


def test_vision_llm_endpoint_and_model_are_saved_in_preferences(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    _ = app
    window = LumaSiftWindow()
    window.input_edit.setText(str(tmp_path))
    window.output_edit.setText(str(tmp_path / "out"))
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("qwen_vision"))
    window.vision_base_url_edit.setText("https://api.custom.local/v1")
    window.vision_model_edit.setText("custom-model-vl")
    window.api_key_edit.setText("sk-test")

    window._save_preferences()

    assert str(window.settings_store.value("vision_base_url")) == "https://api.custom.local/v1"
    assert str(window.settings_store.value("vision_model")) == "custom-model-vl"
    window.close()


def test_light_theme_uses_linear_style_and_is_saved() -> None:
    app = QApplication.instance() or QApplication([])
    _ = app
    settings = QSettings("LumaSift", "LumaSift")
    settings.remove("theme")
    window = LumaSiftWindow()

    window.theme_combo.setCurrentIndex(window.theme_combo.findData("light"))
    window._save_preferences()

    assert window.theme == "light"
    assert "#5e6ad2" in window.styleSheet().lower()
    assert "#f6f8fb" in window.styleSheet().lower()
    assert "#5e6ad2" in window._detail_html_style().lower()
    assert str(window.settings_store.value("theme")) == "light"
    window.close()

    second = LumaSiftWindow()
    assert second.theme == "light"
    second.close()
    settings.remove("theme")


def test_stale_example_vision_preferences_are_treated_as_auto_defaults() -> None:
    app = QApplication.instance() or QApplication([])
    _ = app
    window = LumaSiftWindow()
    window.settings_store.setValue("vision_base_url", "https://example.test/v1")
    window.settings_store.setValue("vision_model", "custom-vision-model")

    window._load_preferences()
    window._save_preferences()

    assert window.vision_base_url_edit.text() == ""
    assert window.vision_model_edit.text() == ""
    assert str(window.settings_store.value("vision_base_url")) == "https://api.newcoin.top/v1"
    assert str(window.settings_store.value("vision_model")) == "qwen3.6-plus"
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
            "qwen_prompt_version": QWEN_STORY_PROMPT_VERSION,
            "final_selection_score": 88,
        },
        {
            "rank": 4,
            "filename": "stale.jpg",
            "path": "C:/tmp/stale.jpg",
            "analysis_source": "qwen_vision",
            "analysis_quality": "concrete",
            "qwen_status": "done",
            "qwen_prompt_version": "qwen-story-v8",
            "final_selection_score": 84,
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


def test_pair_filter_shows_raw_jpeg_pair_records() -> None:
    app = QApplication.instance() or QApplication([])
    _ = app
    window = LumaSiftWindow()
    window.records = [
        {"rank": 1, "filename": "DSC0001.RAF", "path": "C:/tmp/DSC0001.RAF", "pair_status": "raw_jpeg_pair", "final_selection_score": 90},
        {"rank": 2, "filename": "DSC0002.NEF", "path": "C:/tmp/DSC0002.NEF", "pair_status": "raw_only", "final_selection_score": 80},
    ]
    window._refresh_filter_options()

    window.pair_filter.setCurrentIndex(window.pair_filter.findData("raw_jpeg_pair"))

    assert [record["filename"] for record in window._filtered_records()] == ["DSC0001.RAF"]
    window.close()


def test_tone_filter_shows_matching_records() -> None:
    app = QApplication.instance() or QApplication([])
    _ = app
    window = LumaSiftWindow()
    window.language = "zh"
    window.records = [
        {"rank": 1, "filename": "warm.jpg", "path": "C:/tmp/warm.jpg", "tone_category": "warm_tone", "final_selection_score": 90},
        {"rank": 2, "filename": "cool.jpg", "path": "C:/tmp/cool.jpg", "tone_category": "cool_tone", "final_selection_score": 80},
    ]
    window._refresh_filter_options()

    assert window.tone_filter.findData("warm_tone") >= 0
    window.tone_filter.setCurrentIndex(window.tone_filter.findData("warm_tone"))

    assert [record["filename"] for record in window._filtered_records()] == ["warm.jpg"]
    assert "暖" in window.tone_filter.currentText()
    window.close()


def test_group_filter_splits_time_and_visual_groups() -> None:
    app = QApplication.instance() or QApplication([])
    _ = app
    window = LumaSiftWindow()
    window.records = [
        {"rank": 1, "filename": "time-a.jpg", "path": "C:/tmp/time-a.jpg", "group_size": 2, "group_basis": "time", "final_selection_score": 90},
        {"rank": 2, "filename": "visual-a.jpg", "path": "C:/tmp/visual-a.jpg", "group_size": 2, "group_basis": "visual", "final_selection_score": 88},
        {"rank": 3, "filename": "single.jpg", "path": "C:/tmp/single.jpg", "group_size": 1, "final_selection_score": 80},
    ]
    window._refresh_filter_options()

    assert window.group_filter.findData("time") >= 0
    assert window.group_filter.findData("visual") >= 0
    window.group_filter.setCurrentIndex(window.group_filter.findData("time"))
    assert [record["filename"] for record in window._filtered_records()] == ["time-a.jpg"]
    window.group_filter.setCurrentIndex(window.group_filter.findData("visual"))
    assert [record["filename"] for record in window._filtered_records()] == ["visual-a.jpg"]
    window.close()


def test_keyboard_shortcuts_mark_and_unmark_current_record(tmp_path) -> None:
    reset_shortcut_settings()
    app = QApplication.instance() or QApplication([])
    _ = app
    window = LumaSiftWindow()
    window.output_dir = tmp_path
    window.records = [
        {"rank": 1, "filename": "street.jpg", "path": str(tmp_path / "street.jpg"), "final_selection_score": 90},
    ]
    window._populate_records()
    window.show()
    window.photo_list.setFocus()
    app.processEvents()

    QTest.keyClick(window, Qt.Key.Key_Up)
    assert window.records[0]["user_label"] == "keep"

    QTest.keyClick(window, Qt.Key.Key_S)
    assert window.records[0]["user_label"] == ""

    QTest.keyClick(window, Qt.Key.Key_D)
    assert window.records[0]["user_label"] == "maybe"

    QTest.keyClick(window, Qt.Key.Key_Down)
    assert window.records[0]["user_label"] == "reject"
    window.close()
    reset_shortcut_settings()


def test_review_action_buttons_are_labeled_and_crop_preview_tracks_selection(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    _ = app
    photo = tmp_path / "street.jpg"
    Image.new("RGB", (120, 80), (20, 30, 40)).save(photo)
    window = LumaSiftWindow()
    window.language = "zh"
    window.output_dir = tmp_path
    window.records = [
        {
            "rank": 1,
            "filename": "street.jpg",
            "path": str(photo),
            "final_selection_score": 90,
            "editing_plan": {
                "crop_plan": {
                    "crop_box": {"x": 0.1, "y": 0.1, "width": 0.8, "height": 0.8, "reason": "保留人物关系"}
                }
            },
        },
    ]
    window._retranslate_ui()
    window._populate_records()
    index = window.photo_model.index(0, 0)
    window.photo_list.selectionModel().select(index, QItemSelectionModel.SelectionFlag.Select)
    window._show_selected_detail()

    assert "保留" in window.keep_button.text()
    assert "深评选中照片" in window.deep_review_selected_button.text()
    assert "修图方案" in window.generate_advice_button.text()
    assert "裁切预览" in window.crop_preview_button.text()
    assert window.crop_preview_button.isEnabled()
    assert window.deep_review_selected_button.isEnabled()
    window.close()


def test_keyboard_shortcuts_select_all_and_invert_selection(tmp_path) -> None:
    reset_shortcut_settings()
    app = QApplication.instance() or QApplication([])
    _ = app
    window = LumaSiftWindow()
    window.output_dir = tmp_path
    window.records = [
        {"rank": 1, "filename": "one.jpg", "path": str(tmp_path / "one.jpg"), "final_selection_score": 90},
        {"rank": 2, "filename": "two.jpg", "path": str(tmp_path / "two.jpg"), "final_selection_score": 80},
        {"rank": 3, "filename": "three.jpg", "path": str(tmp_path / "three.jpg"), "final_selection_score": 70},
    ]
    window._populate_records()
    window.show()
    window.photo_list.setFocus()
    app.processEvents()

    QTest.keyClick(window.photo_list, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
    assert len(window._selected_record_indexes()) == 3

    first = window.photo_model.index(0, 0)
    window.photo_list.selectionModel().select(
        first,
        QItemSelectionModel.SelectionFlag.Deselect | QItemSelectionModel.SelectionFlag.Rows,
    )
    QTest.keyClick(window.photo_list, Qt.Key.Key_I, Qt.KeyboardModifier.ControlModifier)
    selected_names = [index.data(Qt.ItemDataRole.UserRole)["filename"] for index in window._selected_record_indexes()]
    assert selected_names == ["one.jpg"]
    window.close()
    reset_shortcut_settings()


def test_shortcuts_page_customizes_keep_key(tmp_path) -> None:
    reset_shortcut_settings()
    app = QApplication.instance() or QApplication([])
    _ = app
    window = LumaSiftWindow()
    window.output_dir = tmp_path
    window.records = [
        {"rank": 1, "filename": "street.jpg", "path": str(tmp_path / "street.jpg"), "final_selection_score": 90},
    ]
    window._populate_records()
    window._show_nav_page("shortcuts")
    assert not window.shortcuts_page.isHidden()

    combo = window.shortcut_combos["keep"]
    combo.setCurrentIndex(combo.findData(int(Qt.Key.Key_A)))

    assert int(window.settings_store.value("shortcut_keep")) == int(Qt.Key.Key_A)

    window.show()
    app.processEvents()
    QTest.keyClick(window, Qt.Key.Key_A)
    assert window.records[0]["user_label"] == "keep"
    window.close()
    reset_shortcut_settings()


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
            "qwen_prompt_version": QWEN_STORY_PROMPT_VERSION,
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

    assert window._default_advice_ranks(window._filtered_records()) == [2]
    window.close()


def test_help_page_documents_full_workflow_and_troubleshooting() -> None:
    app = QApplication.instance() or QApplication([])
    _ = app
    window = LumaSiftWindow()
    window.language = "zh"
    html = window._help_page_html()

    assert "LumaSift 使用说明" in html
    assert "导入照片目录" in html
    assert "LLM深度分析 Top-N" in html
    assert "深评状态筛选" in html
    assert "selected_editing_advice.md" in html
    assert "常见问题排查" in html
    window.close()

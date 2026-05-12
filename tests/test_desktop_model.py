from __future__ import annotations

from PySide6.QtCore import Qt
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

    assert window.controls_frame.isVisible()
    QTest.mouseClick(window.settings_nav_button, Qt.MouseButton.LeftButton)
    app.processEvents()

    assert not window.controls_frame.isVisible()
    QTest.mouseClick(window.settings_nav_button, Qt.MouseButton.LeftButton)
    app.processEvents()

    assert window.controls_frame.isVisible()
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

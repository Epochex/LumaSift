from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication
from PIL import Image

from lumasift.app.desktop import LargePreviewWorker, PhotoListModel


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

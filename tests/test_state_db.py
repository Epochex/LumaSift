from __future__ import annotations

from pathlib import Path

import pytest

from lumasift.storage.state_db import LumaSiftStateDb


def test_state_db_persists_user_labels(tmp_path: Path) -> None:
    db = LumaSiftStateDb(tmp_path / "state.sqlite")
    photo = tmp_path / "photo.jpg"
    photo.write_bytes(b"fake")

    db.set_user_label(path=photo, label="keep", run_id="run-1", rank=3, score=88.5, category="story_candidate")

    labels = db.load_labels([photo])
    assert labels[str(photo.resolve())] == "keep"
    exported = db.export_labeled_records()
    assert exported[0]["path"] == str(photo.resolve())
    assert exported[0]["user_label"] == "keep"
    assert exported[0]["rank"] == 3


def test_state_db_rejects_unknown_labels(tmp_path: Path) -> None:
    db = LumaSiftStateDb(tmp_path / "state.sqlite")
    photo = tmp_path / "photo.jpg"
    photo.write_bytes(b"fake")

    with pytest.raises(ValueError):
        db.set_user_label(path=photo, label="great")  # type: ignore[arg-type]


def test_state_db_records_run_history(tmp_path: Path) -> None:
    db = LumaSiftStateDb(tmp_path / "state.sqlite")

    db.record_run(
        run_id="run-1",
        input_dir="D:/DCIM",
        output_dir="./outputs/gui",
        ai_mode="local_only",
        summary={"scanned": 10, "processed": 9, "failed": 1},
    )

    rows = db.path.read_bytes()
    assert rows
    db.record_run(
        run_id="newer-run",
        input_dir="D:/DCIM2",
        output_dir="./outputs/gui2",
        ai_mode="qwen_vision",
        summary={"scanned": 3, "processed": 3, "failed": 0},
    )
    runs = db.list_runs(limit=2)
    assert [run["run_id"] for run in runs] == ["newer-run", "run-1"]
    assert runs[0]["processed"] == 3


def test_state_db_loads_labels_in_chunks(tmp_path: Path) -> None:
    db = LumaSiftStateDb(tmp_path / "state.sqlite")
    photos = []
    for index in range(1100):
        photo = tmp_path / f"{index}.jpg"
        photo.write_bytes(b"fake")
        photos.append(photo)
    db.set_user_label(path=photos[0], label="keep")
    db.set_user_label(path=photos[-1], label="reject")

    labels = db.load_labels(photos)

    assert labels[str(photos[0].resolve())] == "keep"
    assert labels[str(photos[-1].resolve())] == "reject"


def test_state_db_persists_manifest_without_overwriting_label(tmp_path: Path) -> None:
    db = LumaSiftStateDb(tmp_path / "state.sqlite")
    photo = tmp_path / "photo.jpg"
    photo.write_bytes(b"manifest bytes")
    stat = photo.stat()

    db.set_user_label(path=photo, label="keep")
    db.upsert_photo_manifest(
        path=photo,
        size_bytes=stat.st_size,
        mtime_ns=stat.st_mtime_ns,
        identity_hash="identity-1",
        preview_path=tmp_path / "preview.jpg",
        last_run_id="run-2",
        rank=1,
        score=92.5,
        category="portfolio_candidate",
        technical_quality_score=71.0,
        qwen_cache_key="qwen-key",
        visual_hash="abcd",
        visual_color="1,2,3",
        visual_scene_signature="001122",
        group_id="g0001",
        group_size=2,
        group_rank=1,
        is_group_best=True,
        group_best_path=photo,
        group_score_delta=0.0,
        scores={"final_selection_score": 92.5},
        record={"path": str(photo.resolve()), "filename": photo.name, "final_selection_score": 92.5, "group_id": "g0001"},
    )

    manifest = db.load_manifest_record(photo)
    assert manifest is not None
    assert manifest["user_label"] == "keep"
    assert manifest["last_run_id"] == "run-2"
    assert manifest["size_bytes"] == stat.st_size
    assert manifest["qwen_cache_key"] == "qwen-key"
    assert manifest["visual_hash"] == "abcd"
    assert manifest["visual_color"] == "1,2,3"
    assert manifest["visual_scene_signature"] == "001122"
    assert manifest["group_id"] == "g0001"
    assert manifest["is_group_best"] == 1

    reusable = db.reusable_record_for_file(photo)
    assert reusable is not None
    assert reusable["filename"] == "photo.jpg"
    assert reusable["user_label"] == "keep"

    photo.write_bytes(b"changed bytes")
    assert db.reusable_record_for_file(photo) is None

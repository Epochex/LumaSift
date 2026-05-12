import json
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication
from PIL import Image

from lumasift.core.config import Settings
from lumasift.core.harness import LumaSiftHarness
from lumasift.storage.state_db import LumaSiftStateDb


def test_harness_runs_local_only(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    Image.new("RGB", (32, 32), color=(200, 40, 40)).save(input_dir / "red.jpg")

    settings = Settings(input_dir=input_dir, output_dir=output_dir, ai_mode="local_only")
    result = LumaSiftHarness(settings=settings, run_id="test-run").run()

    assert result.summary["scanned"] == 1
    assert result.report_csv.exists()
    assert result.report_json.exists()
    assert (output_dir / "runs" / "test-run" / "events.jsonl").exists()
    record = json.loads(result.report_json.read_text(encoding="utf-8"))["records"][0]
    assert "Local pre-screen only" in record["story_interpretation"]
    assert record["positive_reasons"] != ["Local proxy detected workable tonal/detail structure."]


def test_local_fallback_reasons_vary_by_image_metrics(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    Image.new("RGB", (48, 48), color=(8, 8, 8)).save(input_dir / "dark.jpg")
    Image.new("RGB", (48, 48), color=(235, 235, 235)).save(input_dir / "bright.jpg")

    settings = Settings(input_dir=input_dir, output_dir=output_dir, ai_mode="local_only")
    result = LumaSiftHarness(settings=settings, run_id="local-varied").run()
    records = json.loads(result.report_json.read_text(encoding="utf-8"))["records"]
    reasons = {record["filename"]: " ".join(record["negative_reasons"]) for record in records}

    assert "dark" in reasons["dark.jpg"].lower()
    assert "bright" in reasons["bright.jpg"].lower()
    assert reasons["dark.jpg"] != reasons["bright.jpg"]


def test_harness_persists_and_reuses_sqlite_manifest(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    photo = input_dir / "red.jpg"
    Image.new("RGB", (32, 32), color=(200, 40, 40)).save(photo)
    db = LumaSiftStateDb(tmp_path / "state.sqlite")

    first_settings = Settings(input_dir=input_dir, output_dir=output_dir, ai_mode="local_only")
    LumaSiftHarness(settings=first_settings, run_id="manifest-first", state_db=db).run()

    row = db.load_manifest_record(photo)
    assert row is not None
    assert row["last_run_id"] == "manifest-first"
    assert row["preview_path"]

    second_settings = Settings(input_dir=input_dir, output_dir=output_dir, ai_mode="local_only")
    LumaSiftHarness(settings=second_settings, run_id="manifest-second", state_db=db).run()
    report = json.loads((output_dir / "report.json").read_text(encoding="utf-8"))

    assert report["records"][0]["manifest_status"] == "reused"
    assert db.load_manifest_record(photo)["last_run_id"] == "manifest-second"


def test_harness_does_not_reuse_qwen_record_for_local_only_run(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    photo = input_dir / "red.jpg"
    Image.new("RGB", (32, 32), color=(200, 40, 40)).save(photo)
    stat = photo.stat()
    db = LumaSiftStateDb(tmp_path / "state.sqlite")
    db.upsert_photo_manifest(
        path=photo,
        size_bytes=stat.st_size,
        mtime_ns=stat.st_mtime_ns,
        identity_hash="identity-qwen",
        last_run_id="qwen-run",
        rank=1,
        score=99.0,
        category="portfolio_candidate",
        record={
            "path": str(photo.resolve()),
            "filename": photo.name,
            "final_selection_score": 99.0,
            "category": "portfolio_candidate",
            "qwen_status": "done",
            "qwen_model": "qwen-test",
        },
    )

    settings = Settings(input_dir=input_dir, output_dir=output_dir, ai_mode="local_only")
    LumaSiftHarness(settings=settings, run_id="local-after-qwen", state_db=db).run()
    report = json.loads((output_dir / "report.json").read_text(encoding="utf-8"))

    assert report["records"][0].get("manifest_status") is None
    assert report["records"][0].get("qwen_model") is None


def test_harness_applies_user_feedback_without_changing_model_score(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    keep_photo = input_dir / "keep.jpg"
    reject_photo = input_dir / "reject.jpg"
    Image.new("RGB", (32, 32), color=(220, 40, 40)).save(keep_photo)
    Image.new("RGB", (32, 32), color=(40, 40, 40)).save(reject_photo)
    db = LumaSiftStateDb(tmp_path / "state.sqlite")
    db.set_user_label(path=keep_photo, label="keep")
    db.set_user_label(path=reject_photo, label="reject")

    settings = Settings(input_dir=input_dir, output_dir=output_dir, ai_mode="local_only")
    LumaSiftHarness(settings=settings, run_id="feedback-run", state_db=db).run()
    report = json.loads((output_dir / "report.json").read_text(encoding="utf-8"))

    by_name = {record["filename"]: record for record in report["records"]}
    assert by_name["keep.jpg"]["user_label"] == "keep"
    assert by_name["keep.jpg"]["user_feedback_priority"] == 2
    assert by_name["keep.jpg"]["user_feedback_action"] == "surface"
    assert by_name["keep.jpg"]["model_final_selection_score"] == by_name["keep.jpg"]["final_selection_score"]
    assert by_name["keep.jpg"]["model_category"] == by_name["keep.jpg"]["category"]
    assert by_name["reject.jpg"]["user_feedback_action"] == "skip_qwen"
    assert "user_feedback_priority" in (output_dir / "report.csv").read_text(encoding="utf-8-sig").splitlines()[0]


def test_harness_groups_similar_photos_and_marks_best(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    for name in ("a.jpg", "b.jpg"):
        Image.new("RGB", (64, 64), color=(200, 40, 40)).save(input_dir / name)
    Image.new("RGB", (64, 64), color=(40, 40, 200)).save(input_dir / "c.jpg")
    db = LumaSiftStateDb(tmp_path / "state.sqlite")

    settings = Settings(input_dir=input_dir, output_dir=output_dir, ai_mode="local_only")
    LumaSiftHarness(settings=settings, run_id="group-run", state_db=db).run()
    report = json.loads((output_dir / "report.json").read_text(encoding="utf-8"))

    grouped = [record for record in report["records"] if int(record.get("group_size", 1)) > 1]
    assert len(grouped) == 2
    assert sum(1 for record in grouped if record["is_group_best"]) == 1
    assert all(record["group_best_path"] for record in grouped)
    assert db.load_manifest_record(input_dir / "a.jpg")["visual_hash"]


def test_harness_respects_limit(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    for index in range(3):
        Image.new("RGB", (32, 32), color=(200, 40 + index, 40)).save(input_dir / f"{index}.jpg")

    settings = Settings(input_dir=input_dir, output_dir=output_dir, ai_mode="local_only", limit=2)
    result = LumaSiftHarness(settings=settings, run_id="limit-run").run()
    report = json.loads(result.report_json.read_text(encoding="utf-8"))

    assert result.summary["scanned"] == 2
    assert result.summary["processed"] == 2
    assert len(report["records"]) == 2


def test_harness_resume_skips_checkpointed_prefix(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    for index in range(3):
        Image.new("RGB", (32, 32), color=(200, 40 + index, 40)).save(input_dir / f"{index}.jpg")

    first_settings = Settings(input_dir=input_dir, output_dir=output_dir, ai_mode="local_only", limit=1)
    LumaSiftHarness(settings=first_settings, run_id="resume-run").run()

    resume_settings = Settings(input_dir=input_dir, output_dir=output_dir, ai_mode="local_only", limit=3, resume=True)
    result = LumaSiftHarness(settings=resume_settings, run_id="resume-run").run()
    report = json.loads(result.report_json.read_text(encoding="utf-8"))

    assert result.summary["scanned"] == 3
    assert result.summary["processed"] == 2
    assert sorted(record["filename"] for record in report["records"]) == ["1.jpg", "2.jpg"]


def test_harness_writes_selected_editing_advice(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    Image.new("RGB", (32, 32), color=(200, 40, 40)).save(input_dir / "red.jpg")

    settings = Settings(
        input_dir=input_dir,
        output_dir=output_dir,
        ai_mode="local_only",
        selected_ranks="1",
    )
    LumaSiftHarness(settings=settings, run_id="selected-run").run()

    assert (output_dir / "selected_editing_advice.json").exists()
    assert "第 1 张" in (output_dir / "selected_editing_advice.md").read_text(encoding="utf-8")


def test_qwen_stage_cancels_pending_candidates_without_network(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    events: list[dict] = []
    settings = Settings(
        input_dir=input_dir,
        output_dir=output_dir,
        ai_mode="qwen_vision",
        vision_api_keys=["test-key"],
        top_n_api_analysis=3,
    )
    harness = LumaSiftHarness(settings=settings, run_id="cancel-qwen", event_callback=events.append)
    (output_dir / "STOP_LUMASIFT").write_text("stop", encoding="utf-8")
    ranked = [
        {"filename": f"{index}.jpg", "path": str(input_dir / f"{index}.jpg"), "category": "story_candidate", "final_selection_score": 90 - index}
        for index in range(3)
    ]

    result = harness._apply_qwen_vision(ranked)

    assert [record["qwen_status"] for record in result] == ["cancelled", "cancelled", "cancelled"]
    assert all("qwen_vision_cancelled" in record["errors"] for record in result)
    assert any(event["type"] == "qwen_queue_cancelled" and event["cancelled"] == 3 for event in events)


def test_qwen_stage_skips_rejected_user_labels_by_default(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    events: list[dict] = []
    settings = Settings(
        input_dir=input_dir,
        output_dir=output_dir,
        ai_mode="qwen_vision",
        vision_api_keys=["test-key"],
        top_n_api_analysis=3,
    )
    harness = LumaSiftHarness(settings=settings, run_id="skip-reject", event_callback=events.append)
    ranked = [
        {
            "filename": "reject.jpg",
            "path": str(input_dir / "reject.jpg"),
            "category": "story_candidate",
            "final_selection_score": 90,
            "user_label": "reject",
        }
    ]

    result = harness._apply_qwen_vision(ranked)

    assert result[0]["qwen_status"] == "skipped_user_reject"
    assert result[0]["qwen_skip_reason"] == "user_label_reject"
    assert any(event["type"] == "qwen_queue_prepared" and event["total"] == 0 for event in events)


def test_qwen_stage_skips_non_winning_group_members_by_default(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    events: list[dict] = []
    settings = Settings(
        input_dir=input_dir,
        output_dir=output_dir,
        ai_mode="qwen_vision",
        vision_api_keys=["test-key"],
        top_n_api_analysis=3,
    )
    harness = LumaSiftHarness(settings=settings, run_id="skip-group", event_callback=events.append)
    ranked = [
        {
            "filename": "best.jpg",
            "path": str(input_dir / "best.jpg"),
            "category": "story_candidate",
            "final_selection_score": 90,
            "group_id": "g0001",
            "group_size": 2,
            "is_group_best": True,
        },
        {
            "filename": "other.jpg",
            "path": str(input_dir / "other.jpg"),
            "category": "story_candidate",
            "final_selection_score": 80,
            "group_id": "g0001",
            "group_size": 2,
            "is_group_best": False,
        },
    ]
    (output_dir / "STOP_LUMASIFT").write_text("stop", encoding="utf-8")

    result = harness._apply_qwen_vision(ranked)

    by_name = {record["filename"]: record for record in result}
    assert by_name["other.jpg"]["qwen_status"] == "skipped_similar_group"
    assert by_name["other.jpg"]["qwen_skip_reason"] == "similar_group_non_winner"
    assert by_name["best.jpg"]["qwen_status"] == "cancelled"


def test_qwen_stage_writes_prompt_version_and_cache_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    photo = input_dir / "candidate.jpg"
    Image.new("RGB", (32, 32), color=(200, 40, 40)).save(photo)

    class FakeQwenClient:
        last_cache_hit = False
        last_cache_key_digest = "cache-digest"

        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        def analyze_image(self, *args: object, **kwargs: object) -> dict:
            assert "visible_evidence" in str(args[1])
            return {
                "model": "qwen-test",
                "choices": [{"message": {"content": '{"final_selection_score": 91, "category": "strong_edit_candidate"}'}}],
            }

    monkeypatch.setattr("lumasift.core.harness.QwenVisionClient", FakeQwenClient)
    settings = Settings(input_dir=input_dir, output_dir=output_dir, ai_mode="qwen_vision", vision_api_keys=["test-key"])
    harness = LumaSiftHarness(settings=settings, run_id="prompt-version")

    result = harness._apply_qwen_vision(
        [
            {
                "filename": "candidate.jpg",
                "path": str(photo),
                "category": "story_candidate",
                "final_selection_score": 80,
            }
        ]
    )

    assert result[0]["qwen_prompt_version"] == "qwen-story-v2"
    assert result[0]["qwen_cache_key"] == "cache-digest"


def test_desktop_app_module_imports() -> None:
    from lumasift.app.desktop import LumaSiftWindow

    app = QApplication.instance() or QApplication([])
    window = LumaSiftWindow()
    assert window.windowTitle().startswith("LumaSift")
    window.language_combo.setCurrentText("中文")
    assert "本地" in window.windowTitle()
    window.language_combo.setCurrentText("English")
    assert "Local" in window.windowTitle()
    window.close()


def test_desktop_restores_history_run(tmp_path: Path) -> None:
    from lumasift.app.desktop import LumaSiftWindow

    app = QApplication.instance() or QApplication([])
    output_dir = tmp_path / "run-output"
    output_dir.mkdir()
    (output_dir / "report.json").write_text(
        json.dumps(
            {
                "records": [
                    {
                        "rank": 1,
                        "path": str(tmp_path / "photo.jpg"),
                        "filename": "photo.jpg",
                        "category": "story_candidate",
                        "final_selection_score": 88.0,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    window = LumaSiftWindow()
    window.state_db = LumaSiftStateDb(tmp_path / "state.sqlite")
    window.state_db.record_run(
        run_id="history-run",
        input_dir=str(tmp_path),
        output_dir=str(output_dir),
        ai_mode="local_only",
        summary={"scanned": 1, "processed": 1, "failed": 0},
    )

    window._restore_history_run(window.state_db.list_runs(limit=1)[0])

    assert window.review_mode
    assert len(window.records) == 1
    assert window.output_dir == output_dir
    window.close()

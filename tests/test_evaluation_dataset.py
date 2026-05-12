from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

from lumasift.evaluation.dataset import EVAL_DATASET_SCHEMA, build_eval_dataset, write_eval_dataset_csv, write_eval_dataset_json
from lumasift.storage.state_db import LumaSiftStateDb


def test_eval_dataset_exports_labeled_metadata_without_photos(tmp_path: Path) -> None:
    db = LumaSiftStateDb(tmp_path / "state.sqlite")
    photo = tmp_path / "private.jpg"
    photo.write_bytes(b"private image bytes")
    db.set_user_label(path=photo, label="keep", run_id="run-1", rank=4, score=82.5, category="story_candidate")

    dataset = build_eval_dataset(db, prompt_version="qwen-story-v1", split="dev", notes="first pass")

    assert dataset["schema"] == EVAL_DATASET_SCHEMA
    assert dataset["contains_original_photos"] is False
    assert dataset["photo_count"] == 1
    record = dataset["records"][0]
    assert record["photo_id"]
    assert record["path"] == str(photo.resolve())
    assert record["user_label"] == "keep"
    assert record["gold_label"] == "keep"
    assert record["prompt_version"] == "qwen-story-v1"
    assert record["split"] == "dev"
    assert record["notes"] == "first pass"

    json_path = tmp_path / "eval.json"
    csv_path = tmp_path / "eval.csv"
    write_eval_dataset_json(json_path, dataset)
    write_eval_dataset_csv(csv_path, dataset)

    assert json.loads(json_path.read_text(encoding="utf-8"))["records"][0]["photo_id"] == record["photo_id"]
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["gold_label"] == "keep"


def test_export_eval_dataset_script(tmp_path: Path) -> None:
    db_path = tmp_path / "state.sqlite"
    db = LumaSiftStateDb(db_path)
    photo = tmp_path / "private.jpg"
    photo.write_bytes(b"private image bytes")
    db.set_user_label(path=photo, label="reject")
    output = tmp_path / "labels.json"

    result = subprocess.run(
        [
            sys.executable,
            "scripts/export_eval_dataset.py",
            "--db",
            str(db_path),
            "--output",
            str(output),
            "--prompt-version",
            "qwen-story-v1",
            "--split",
            "test",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert "Exported 1 labeled records" in result.stdout
    assert payload["records"][0]["user_label"] == "reject"
    assert payload["records"][0]["split"] == "test"

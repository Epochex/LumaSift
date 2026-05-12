from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any

from lumasift.storage.state_db import LumaSiftStateDb


EVAL_DATASET_SCHEMA = "lumasift.eval_dataset.v1"
EVAL_FIELDS = [
    "photo_id",
    "path",
    "user_label",
    "gold_label",
    "story_rank",
    "notes",
    "split",
    "prompt_version",
    "run_id",
    "rank",
    "score",
    "category",
    "updated_at",
]


def build_eval_dataset(
    db: LumaSiftStateDb,
    *,
    prompt_version: str = "",
    split: str = "unassigned",
    notes: str = "",
) -> dict[str, Any]:
    records = [_eval_record(row, prompt_version=prompt_version, split=split, notes=notes) for row in db.export_labeled_records()]
    return {
        "schema": EVAL_DATASET_SCHEMA,
        "photo_count": len(records),
        "contains_original_photos": False,
        "fields": EVAL_FIELDS,
        "records": records,
    }


def write_eval_dataset_json(path: Path, dataset: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dataset, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_eval_dataset_csv(path: Path, dataset: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=EVAL_FIELDS)
        writer.writeheader()
        for record in dataset.get("records", []):
            writer.writerow({field: record.get(field, "") for field in EVAL_FIELDS})


def _eval_record(row: dict[str, Any], *, prompt_version: str, split: str, notes: str) -> dict[str, Any]:
    user_label = str(row.get("user_label") or "")
    return {
        "photo_id": stable_photo_id(str(row.get("path") or "")),
        "path": row.get("path") or "",
        "user_label": user_label,
        "gold_label": user_label,
        "story_rank": "",
        "notes": notes,
        "split": split,
        "prompt_version": prompt_version,
        "run_id": row.get("run_id") or "",
        "rank": row.get("rank") or "",
        "score": row.get("score") or "",
        "category": row.get("category") or "",
        "updated_at": row.get("updated_at") or "",
    }


def stable_photo_id(path: str) -> str:
    return hashlib.sha256(path.encode("utf-8", errors="ignore")).hexdigest()[:16]

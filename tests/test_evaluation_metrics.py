from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from lumasift.evaluation.dataset import stable_photo_id
from lumasift.evaluation.metrics import METRICS_SCHEMA, evaluate_reports, write_metrics_json, write_metrics_markdown


def test_ranking_metrics_compute_precision_recall_ndcg_mrr(tmp_path: Path) -> None:
    eval_dataset = {
        "schema": "lumasift.eval_dataset.v1",
        "photo_count": 3,
        "records": [
            {"photo_id": stable_photo_id("a.jpg"), "path": "a.jpg", "gold_label": "keep", "prompt_version": "qwen-story-v1"},
            {"photo_id": stable_photo_id("b.jpg"), "path": "b.jpg", "gold_label": "reject", "prompt_version": "qwen-story-v1"},
            {"photo_id": stable_photo_id("c.jpg"), "path": "c.jpg", "gold_label": "maybe", "prompt_version": "qwen-story-v1"},
        ],
    }
    report = {
        "ai_mode": "qwen_vision",
        "records": [
            {"rank": 1, "path": "b.jpg", "qwen_model": "qwen-test"},
            {"rank": 2, "path": "a.jpg", "qwen_model": "qwen-test"},
            {
                "rank": 3,
                "path": "c.jpg",
                "qwen_model": "qwen-test",
                "filename": "c.jpg",
                "technical_quality_score": 40,
                "category": "technically_weak_but_interesting",
            },
        ],
    }

    payload = evaluate_reports(eval_dataset, [("report.json", report)], k=2)
    result = payload["results"][0]

    assert payload["schema"] == METRICS_SCHEMA
    assert result["label_distribution"] == {"reject": 1, "keep": 1, "maybe": 1}
    assert result["metrics"]["precision@2"] == 0.5
    assert result["metrics"]["recall@2"] == 0.5
    assert result["metrics"]["mrr"] == 0.5
    assert result["metrics"]["ndcg@2"] > 0
    assert result["prompt_version"] == "qwen-story-v1"
    assert result["model_versions"] == ["qwen-test"]
    assert result["false_negatives"][0]["filename"] == "c.jpg"

    json_path = tmp_path / "metrics.json"
    md_path = tmp_path / "metrics.md"
    write_metrics_json(json_path, payload)
    write_metrics_markdown(md_path, payload)
    assert json.loads(json_path.read_text(encoding="utf-8"))["schema"] == METRICS_SCHEMA
    md_text = md_path.read_text(encoding="utf-8")
    assert "precision@2" in md_text
    assert "False negatives" in md_text


def test_evaluate_ranking_script(tmp_path: Path) -> None:
    eval_path = tmp_path / "eval.json"
    report_path = tmp_path / "report.json"
    out_json = tmp_path / "metrics.json"
    out_md = tmp_path / "metrics.md"
    eval_path.write_text(
        json.dumps(
            {
                "schema": "lumasift.eval_dataset.v1",
                "photo_count": 1,
                "records": [{"photo_id": stable_photo_id("a.jpg"), "path": "a.jpg", "gold_label": "keep"}],
            }
        ),
        encoding="utf-8",
    )
    report_path.write_text(json.dumps({"records": [{"rank": 1, "path": "a.jpg"}]}), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "scripts/evaluate_ranking.py",
            "--eval",
            str(eval_path),
            "--report",
            str(report_path),
            "--k",
            "1",
            "--output-json",
            str(out_json),
            "--output-md",
            str(out_md),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "Evaluated 1 report" in result.stdout
    assert json.loads(out_json.read_text(encoding="utf-8"))["results"][0]["metrics"]["precision@1"] == 1.0
    assert out_md.exists()

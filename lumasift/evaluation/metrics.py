from __future__ import annotations

import json
import math
from collections import Counter
from pathlib import Path
from typing import Any

from lumasift.evaluation.dataset import stable_photo_id


METRICS_SCHEMA = "lumasift.ranking_metrics.v1"
RELEVANCE = {
    "keep": 2,
    "maybe": 1,
    "reject": 0,
}


def evaluate_report(eval_dataset: dict[str, Any], report: dict[str, Any], *, k: int = 10, report_path: str = "") -> dict[str, Any]:
    labels = _label_map(eval_dataset)
    ranked = _ranked_records(report)
    judged = [_record_with_label(record, labels) for record in ranked if _record_label(record, labels) is not None]
    top_k = judged[:k]
    relevant_total = sum(1 for item in judged if item["relevance"] > 0)
    relevant_at_k = sum(1 for item in top_k if item["relevance"] > 0)
    dcg = _dcg([item["relevance"] for item in top_k])
    ideal = sorted((item["relevance"] for item in judged), reverse=True)[:k]
    idcg = _dcg(ideal)
    first_relevant_rank = next((index for index, item in enumerate(judged, start=1) if item["relevance"] > 0), None)
    model_versions = sorted({str(record.get("qwen_model")) for record in ranked if record.get("qwen_model")})
    return {
        "report_path": report_path,
        "ai_mode": report.get("ai_mode", ""),
        "prompt_version": _prompt_version(eval_dataset, ranked),
        "model_versions": model_versions,
        "k": k,
        "ranked_count": len(ranked),
        "judged_count": len(judged),
        "relevant_count": relevant_total,
        "label_distribution": dict(Counter(item["gold_label"] for item in judged)),
        "false_negatives": _false_negatives(judged, k=k),
        "metrics": {
            f"precision@{k}": round(relevant_at_k / k, 6) if k else 0.0,
            f"recall@{k}": round(relevant_at_k / relevant_total, 6) if relevant_total else 0.0,
            f"ndcg@{k}": round(dcg / idcg, 6) if idcg else 0.0,
            "mrr": round(1 / first_relevant_rank, 6) if first_relevant_rank else 0.0,
        },
    }


def evaluate_reports(eval_dataset: dict[str, Any], reports: list[tuple[str, dict[str, Any]]], *, k: int = 10) -> dict[str, Any]:
    return {
        "schema": METRICS_SCHEMA,
        "eval_schema": eval_dataset.get("schema", ""),
        "eval_photo_count": eval_dataset.get("photo_count", len(eval_dataset.get("records", []))),
        "results": [evaluate_report(eval_dataset, report, k=k, report_path=path) for path, report in reports],
    }


def write_metrics_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_metrics_markdown(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# LumaSift Ranking Metrics", ""]
    for result in payload.get("results", []):
        metrics = result.get("metrics", {})
        lines.extend(
            [
                f"## {result.get('report_path') or 'report'}",
                "",
                f"- AI mode: `{result.get('ai_mode', '')}`",
                f"- Prompt version: `{result.get('prompt_version', '')}`",
                f"- Model versions: `{', '.join(result.get('model_versions', [])) or 'none'}`",
                f"- Judged photos: {result.get('judged_count', 0)} / {result.get('ranked_count', 0)}",
                f"- Label distribution: `{json.dumps(result.get('label_distribution', {}), ensure_ascii=False, sort_keys=True)}`",
                "",
                "| Metric | Value |",
                "| --- | ---: |",
            ]
        )
        for key, value in metrics.items():
            lines.append(f"| {key} | {value:.6f} |")
        false_negatives = result.get("false_negatives", [])
        if false_negatives:
            lines.extend(["", "### False negatives", ""])
            for item in false_negatives[:10]:
                lines.append(
                    f"- rank {item.get('rank')}: `{item.get('filename') or item.get('path')}` "
                    f"gold=`{item.get('gold_label')}` score={item.get('score')} "
                    f"technical={item.get('technical_quality_score')} category=`{item.get('category')}`"
                )
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def _label_map(eval_dataset: dict[str, Any]) -> dict[str, dict[str, Any]]:
    labels: dict[str, dict[str, Any]] = {}
    for row in eval_dataset.get("records", []):
        if not isinstance(row, dict):
            continue
        photo_id = str(row.get("photo_id") or "")
        path = str(row.get("path") or "")
        if photo_id:
            labels[photo_id] = row
        if path:
            labels[stable_photo_id(path)] = row
    return labels


def _ranked_records(report: dict[str, Any]) -> list[dict[str, Any]]:
    records = [record for record in report.get("records", []) if isinstance(record, dict)]
    return sorted(records, key=lambda item: int(item.get("rank", 999999) or 999999))


def _record_label(record: dict[str, Any], labels: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    photo_id = str(record.get("photo_id") or "")
    if photo_id and photo_id in labels:
        return labels[photo_id]
    path = str(record.get("path") or "")
    if path:
        return labels.get(stable_photo_id(path))
    return None


def _record_with_label(record: dict[str, Any], labels: dict[str, dict[str, Any]]) -> dict[str, Any]:
    row = _record_label(record, labels) or {}
    gold_label = str(row.get("gold_label") or row.get("user_label") or "")
    return {
        "record": record,
        "gold_label": gold_label,
        "relevance": RELEVANCE.get(gold_label, 0),
    }


def _dcg(relevances: list[int]) -> float:
    return sum((2**rel - 1) / math.log2(index + 1) for index, rel in enumerate(relevances, start=1))


def _prompt_version(eval_dataset: dict[str, Any], ranked: list[dict[str, Any]]) -> str:
    versions = {str(row.get("prompt_version")) for row in eval_dataset.get("records", []) if isinstance(row, dict) and row.get("prompt_version")}
    versions.update(str(record.get("qwen_prompt_version")) for record in ranked if record.get("qwen_prompt_version"))
    return ",".join(sorted(versions))


def _false_negatives(judged: list[dict[str, Any]], *, k: int) -> list[dict[str, Any]]:
    misses: list[dict[str, Any]] = []
    for index, item in enumerate(judged, start=1):
        if item["relevance"] <= 0 or index <= k:
            continue
        record = item["record"]
        technical = _float(record.get("technical_quality_score"))
        category = str(record.get("category") or "")
        story_strong_technical_weak = technical < 55.0 or category == "technically_weak_but_interesting"
        if not story_strong_technical_weak:
            continue
        misses.append(
            {
                "rank": record.get("rank", index),
                "path": record.get("path", ""),
                "filename": record.get("filename", ""),
                "gold_label": item["gold_label"],
                "score": record.get("final_selection_score", ""),
                "technical_quality_score": record.get("technical_quality_score", ""),
                "category": category,
            }
        )
    return misses


def _float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0

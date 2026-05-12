from __future__ import annotations

import csv
import json
from pathlib import Path


CSV_FIELDS = [
    "rank",
    "path",
    "filename",
    "extension",
    "width",
    "height",
    "technical_quality_score",
    "storytelling_score",
    "human_documentary_value_score",
    "decisive_moment_score",
    "emotional_impact_score",
    "visual_tension_score",
    "editing_potential_score",
    "final_selection_score",
    "category",
    "model_final_selection_score",
    "model_category",
    "user_label",
    "user_feedback_priority",
    "user_feedback_action",
    "qwen_skip_reason",
    "qwen_prompt_version",
    "qwen_model",
    "visual_hash",
    "visual_color",
    "visual_scene_signature",
    "group_id",
    "group_size",
    "group_rank",
    "is_group_best",
    "group_best_path",
    "group_score_delta",
    "group_review_role",
    "group_moment_risk",
    "analysis_source",
    "analysis_quality",
    "needs_qwen_review",
    "editorial_verdict",
    "visible_inventory",
    "visible_evidence",
    "score_rationales",
    "subject_relationship",
    "decisive_moment_read",
    "moment_status",
    "why_this_frame",
    "frame_failure_reasons",
    "story_interpretation",
    "editing_plan",
    "recommended_style",
    "positive_reasons",
    "negative_reasons",
    "best_editing_direction",
    "crop_strategy",
    "local_adjustments",
    "avoid_overediting",
    "specific_edit_parameters",
]


def _cell(value: object) -> object:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return value


def write_csv_report(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for record in records:
            writer.writerow({field: _cell(record.get(field, "")) for field in CSV_FIELDS})

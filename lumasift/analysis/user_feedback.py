from __future__ import annotations

from typing import Any


USER_LABEL_PRIORITY = {
    "keep": 2,
    "maybe": 1,
    "reject": -2,
}


def normalized_user_label(value: Any) -> str:
    label = str(value or "").strip().lower()
    return "" if label in {"", "unlabeled", "none", "null"} else label


def apply_user_feedback_fields(record: dict[str, Any]) -> None:
    label = normalized_user_label(record.get("user_label"))
    record["model_final_selection_score"] = record.get("final_selection_score")
    record["model_category"] = record.get("category")
    record["user_feedback_priority"] = USER_LABEL_PRIORITY.get(label, 0)
    if label == "keep":
        record["user_feedback_action"] = "surface"
    elif label == "maybe":
        record["user_feedback_action"] = "review"
    elif label == "reject":
        record["user_feedback_action"] = "skip_qwen"
    else:
        record["user_feedback_action"] = "none"

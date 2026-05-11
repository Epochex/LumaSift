from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from typing import Any


QWEN_STORY_PROMPT_VERSION = "qwen-story-v1"
QWEN_STORY_PROMPT = """
Act as a strict street/documentary photo editor. Rank selection value by story, human presence,
decisive moment, emotional impact, visual tension, and editing potential. Technical flaws are
secondary unless they destroy readability.

Return compact valid JSON only:
{
  "storytelling_score": 0-100,
  "human_documentary_value_score": 0-100,
  "decisive_moment_score": 0-100,
  "emotional_impact_score": 0-100,
  "visual_tension_score": 0-100,
  "editing_potential_score": 0-100,
  "technical_quality_score": 0-100,
  "final_selection_score": 0-100,
  "category": "portfolio_candidate|strong_edit_candidate|story_candidate|technically_weak_but_interesting|ordinary_record|reject_candidate",
  "why_keep": ["short reason"],
  "why_deprioritize": ["short reason"],
  "story_interpretation": "one short paragraph",
  "recommended_style": "high_contrast_bw_documentary|low_key_noir_street|cinematic_urban_color|muted_humanistic_color|gritty_flash_street|soft_editorial_documentary|cold_metropolitan|warm_memory_tone|do_not_overedit",
  "best_editing_direction": "one short paragraph",
  "specific_edit_parameters": {
    "exposure": "-0.20",
    "contrast": "+25",
    "highlights": "-40",
    "shadows": "+20",
    "whites": "+5",
    "blacks": "-30",
    "texture": "+10",
    "clarity": "+15",
    "dehaze": "+6",
    "vibrance": "-8",
    "saturation": "-5",
    "temperature": "-300K",
    "tint": "+4"
  },
  "crop_strategy": "short crop guidance",
  "local_adjustments": ["short dodge/burn/masking action"]
}
""".strip()


def extract_qwen_response_text(response: Mapping[str, Any]) -> str:
    candidates: list[Any] = [response.get("output_text")]
    choices = response.get("choices")
    if isinstance(choices, Sequence) and not isinstance(choices, (str, bytes, bytearray)):
        for choice in choices:
            if not isinstance(choice, Mapping):
                continue
            message = choice.get("message")
            if isinstance(message, Mapping):
                candidates.extend([message.get("content"), message.get("reasoning_content")])
            candidates.extend([choice.get("text"), choice.get("content")])

    for candidate in candidates:
        text = _content_to_text(candidate).strip()
        if text:
            return text
    raise ValueError("Qwen response did not contain text content")


def _content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, Mapping):
        for key in ("text", "content", "reasoning_content"):
            value = content.get(key)
            if isinstance(value, str):
                return value
        return ""
    if isinstance(content, Sequence) and not isinstance(content, (str, bytes, bytearray)):
        parts = [_content_to_text(item) for item in content]
        return "\n".join(part for part in parts if part)
    return ""


def _extract_message(response: dict[str, Any]) -> str:
    return extract_qwen_response_text(response)


def _parse_json_object(text: str) -> dict[str, Any]:
    text = text.strip()
    if not text:
        raise ValueError("Qwen response did not contain parseable text")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(0))


def merge_qwen_story_analysis(record: dict[str, Any], response: dict[str, Any]) -> None:
    text = _extract_message(response)
    data = _parse_json_object(text)
    for key in [
        "storytelling_score",
        "human_documentary_value_score",
        "decisive_moment_score",
        "emotional_impact_score",
        "visual_tension_score",
        "editing_potential_score",
        "technical_quality_score",
        "final_selection_score",
        "category",
        "story_interpretation",
        "recommended_style",
        "best_editing_direction",
        "specific_edit_parameters",
        "crop_strategy",
        "local_adjustments",
    ]:
        if key in data:
            record[key] = data[key]
    if "why_keep" in data:
        record["positive_reasons"] = data["why_keep"]
    if "why_deprioritize" in data:
        record["negative_reasons"] = data["why_deprioritize"]
    record["qwen_model"] = response.get("model", "unknown")

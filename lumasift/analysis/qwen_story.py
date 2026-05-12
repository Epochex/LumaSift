from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from typing import Any


QWEN_STORY_PROMPT_VERSION = "qwen-story-v2"
QWEN_STORY_PROMPT = """
你是严格但有摄影判断力的街拍/纪实/人文/旅行摄影选片编辑。

先看照片里真实可见的内容，再打分。不要写“画面有故事感”“主体关系清晰”这类空泛句子；
每个判断都必须指向可见证据：人物、手势、表情、动作方向、空间关系、招牌/车辆/街道环境、
光线、遮挡、边缘干扰、颜色或明暗结构。技术缺陷只有在破坏可读性时才降权；运动模糊、
颗粒、阴影、偏色如果增强现场感，可以成为保留理由。

如果照片属于连拍/相似组，要判断这一张是否有更好的身体动作、视线、遮挡关系、街头瞬间或
环境线索。不要因为“更清楚”就自动胜出；优先决定性瞬间和人文信息。

文字字段用中文，枚举值和 JSON key 保持英文。只返回一个合法 JSON 对象，不要 Markdown。
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
  "visible_evidence": ["3-6条具体可见证据，不要泛泛而谈"],
  "subject_relationship": "主体、人物/物件、环境之间的关系；如果看不清就明确说不确定",
  "decisive_moment_read": "这个瞬间是否成立，以及成立/不成立的原因",
  "why_this_frame": "为什么这张值得保留、待定或淘汰；相似组里要说明和邻近帧相比的判断依据",
  "story_interpretation": "2-4句具体照片阅读：发生了什么、张力在哪里、观者为什么会停留",
  "why_keep": ["具体保留理由"],
  "why_deprioritize": ["具体风险或淘汰理由"],
  "recommended_style": "high_contrast_bw_documentary|low_key_noir_street|cinematic_urban_color|muted_humanistic_color|gritty_flash_street|soft_editorial_documentary|cold_metropolitan|warm_memory_tone|do_not_overedit",
  "best_editing_direction": "围绕内容的修图意图，不只是参数说明",
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
  "crop_strategy": "裁切策略必须说明保留/去掉什么视觉信息",
  "local_adjustments": ["具体蒙版/局部加减光动作"],
  "avoid_overediting": "哪些质感、颜色或模糊不应该被修掉"
}
""".strip()


def build_qwen_story_prompt(record: Mapping[str, Any] | None = None) -> str:
    if not record:
        return QWEN_STORY_PROMPT
    context = {
        "filename": record.get("filename"),
        "local_final_selection_score": record.get("final_selection_score"),
        "local_category": record.get("category"),
        "group_id": record.get("group_id"),
        "group_size": record.get("group_size"),
        "group_rank": record.get("group_rank"),
        "is_group_best": record.get("is_group_best"),
        "local_metrics": record.get("local_metrics"),
    }
    compact = json.dumps({key: value for key, value in context.items() if value not in (None, "", {})}, ensure_ascii=False, sort_keys=True)
    return f"{QWEN_STORY_PROMPT}\n\n本地预筛上下文，仅作参考，不能替代你对图像内容的判断：\n{compact}"


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
        "visible_evidence",
        "subject_relationship",
        "decisive_moment_read",
        "why_this_frame",
        "story_interpretation",
        "recommended_style",
        "best_editing_direction",
        "specific_edit_parameters",
        "crop_strategy",
        "local_adjustments",
        "avoid_overediting",
    ]:
        if key in data:
            record[key] = data[key]
    if "why_keep" in data:
        record["positive_reasons"] = data["why_keep"]
    if "why_deprioritize" in data:
        record["negative_reasons"] = data["why_deprioritize"]
    record["qwen_model"] = response.get("model", "unknown")

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from typing import Any


QWEN_STORY_PROMPT_VERSION = "qwen-story-v5"
QWEN_STORY_PROMPT = """
你是严格但有摄影判断力的街拍/纪实/人文/旅行摄影选片编辑。

先看照片里真实可见的内容，再打分。不要写“画面有故事感”“主体关系清晰”这类空泛句子。
每个判断必须指向可见证据：人物、手势、表情、动作方向、空间关系、招牌/车辆/街道环境、
光线、遮挡、边缘干扰、颜色或明暗结构。技术缺陷只有在破坏可读性时才降权。

如果照片属于连拍/相似组，要判断这一张是否有更好的身体动作、视线、遮挡关系、街头瞬间或
环境线索。不要因为“更清楚”就自动胜出；优先决定性瞬间和人文信息。

每条修图动作必须能追溯到可见证据；如果看不清人、手势、表情或空间关系，必须写“不确定/看不清”，不能脑补。
文字字段用中文，枚举值和 JSON key 保持英文。只返回一个合法 JSON 对象，不要 Markdown。

输出必须短：字符串尽量少于 28 个汉字；数组最多 3 项；不要解释 JSON；不要输出空字段。
Lightroom 参数只给关键可执行值，不要展开所有颜色通道；`advanced_lightroom_parameters` 只写最相关的 3-5 个小节。
{
  "analysis_source": "qwen_vision",
  "analysis_quality": "concrete|weak|generic|missing",
  "analysis_quality_self_check": "是否具体",
  "editorial_verdict": {"action": "keep|maybe|reject", "confidence": 0-100, "one_line_reason": "具体对象+理由"},
  "visible_inventory": {"main_subject": "主对象", "setting_context": ["环境"], "gesture_expression_motion": ["动作/看不清"]},
  "storytelling_score": 0-100,
  "human_documentary_value_score": 0-100,
  "decisive_moment_score": 0-100,
  "emotional_impact_score": 0-100,
  "visual_tension_score": 0-100,
  "editing_potential_score": 0-100,
  "technical_quality_score": 0-100,
  "final_selection_score": 0-100,
  "category": "portfolio_candidate|strong_edit_candidate|story_candidate|technically_weak_but_interesting|ordinary_record|reject_candidate",
  "visible_evidence": ["3条具体可见证据"],
  "score_rationales": {
    "storytelling_score": {"reason": "短理由", "evidence_ids": [0]},
    "human_documentary_value_score": {"reason": "短理由", "evidence_ids": [0]},
    "decisive_moment_score": {"reason": "短理由", "evidence_ids": [0]},
    "editing_potential_score": {"reason": "短理由", "evidence_ids": [0]}
  },
  "subject_relationship": "主体与环境关系",
  "decisive_moment_read": "瞬间是否成立",
  "moment_status": "strong|weak|missed|ambiguous",
  "sequence_comparison": "相似组胜负/不确定",
  "decisive_moment_factors": ["动作", "视线", "遮挡"],
  "subject_identity_uncertainty": "看不清处",
  "selection_risk": "最大选择风险",
  "edit_vs_select_warning": "不能靠修图解决的问题",
  "reject_only_if": "淘汰条件",
  "why_this_frame": "为什么留/待定/淘汰",
  "frame_failure_reasons": ["失败点"],
  "story_interpretation": "1-2句照片阅读",
  "why_keep": ["保留理由"],
  "why_deprioritize": ["风险"],
  "recommended_style": "high_contrast_bw_documentary|low_key_noir_street|cinematic_urban_color|muted_humanistic_color|gritty_flash_street|soft_editorial_documentary|cold_metropolitan|warm_memory_tone|do_not_overedit",
  "best_editing_direction": "修图意图",
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
  "advanced_lightroom_parameters": {
    "tone_curve": {"point_curve": "medium_contrast", "shadows": "+4", "darks": "-6"},
    "hsl_color_mixer": {"orange": {"saturation": "+2", "luminance": "+4"}, "blue": {"saturation": "-10"}},
    "color_grading": {"shadows": {"hue": "220", "saturation": "8"}, "highlights": {"hue": "46", "saturation": "4"}},
    "detail": {"sharpening_amount": "28", "masking": "80"},
    "effects_grain_vignette": {"grain_amount": "8", "post_crop_vignette": "-6"}
  },
  "crop_strategy": "保留/去掉什么",
  "local_adjustments": ["局部动作"],
  "avoid_overediting": "别修掉什么",
  "editing_plan": {
    "edit_intent": "强化的对象",
    "color_mode": {"choice": "color|bw", "reason": "为什么"},
    "crop_plan": {"aspect_ratio": "original|3:2|4:5|16:9|custom", "keep": ["保留"], "remove_or_reduce": ["压弱"]},
    "local_masks": [{"target": "对象", "operation": "曝光/阴影/饱和度", "settings": {"exposure": "+0.20"}, "reason": "目的"}],
    "do_not_overedit": ["现场感"]
  }
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
        "group_review_role": record.get("group_review_role"),
        "group_moment_risk": record.get("group_moment_risk"),
        "group_score_delta": record.get("group_score_delta"),
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


def parse_qwen_story_response(response: Mapping[str, Any]) -> dict[str, Any]:
    return _parse_json_object(extract_qwen_response_text(response))


def _parse_json_object(text: str) -> dict[str, Any]:
    text = _strip_code_fence(text.strip())
    if not text:
        raise ValueError("Qwen response did not contain parseable text")
    candidates = [text]
    extracted = _extract_json_object_text(text)
    if extracted and extracted not in candidates:
        candidates.append(extracted)
    errors: list[str] = []
    for candidate in candidates:
        for repaired in _json_repair_candidates(candidate):
            try:
                data = json.loads(repaired)
            except json.JSONDecodeError as exc:
                errors.append(f"{exc.msg}: line {exc.lineno} column {exc.colno}")
                continue
            if isinstance(data, dict):
                return data
            errors.append(f"parsed JSON root was {type(data).__name__}, not object")
    detail = "; ".join(dict.fromkeys(errors[-3:])) or "unknown parse error"
    raise ValueError(f"Qwen response JSON was malformed after repair attempts: {detail}")


def _strip_code_fence(text: str) -> str:
    match = re.fullmatch(r"\s*```(?:json)?\s*(.*?)\s*```\s*", text, flags=re.DOTALL | re.IGNORECASE)
    return match.group(1).strip() if match else text


def _extract_json_object_text(text: str) -> str | None:
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = in_string
            continue
        if char == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return text[start:].strip()


def _json_repair_candidates(text: str) -> list[str]:
    normalized = text.strip()
    without_trailing_commas = re.sub(r",(\s*[}\]])", r"\1", normalized)
    with_member_commas = _insert_missing_member_commas(without_trailing_commas)
    candidates = [normalized, without_trailing_commas, with_member_commas]
    unique: list[str] = []
    for candidate in candidates:
        if candidate not in unique:
            unique.append(candidate)
    return unique


def _insert_missing_member_commas(text: str) -> str:
    value_end = r'(?P<value>(?:"(?:[^"\\]|\\.)*"|[}\]\d]|true|false|null))'
    next_key = r'(?P<space>\s*\n\s*)(?P<key>"[^"\n\r]+?"\s*:)'
    pattern = re.compile(value_end + next_key)
    previous = None
    repaired = text
    while repaired != previous:
        previous = repaired
        repaired = pattern.sub(r"\g<value>,\g<space>\g<key>", repaired)
    return repaired


def merge_qwen_story_analysis(record: dict[str, Any], response: dict[str, Any]) -> None:
    data = parse_qwen_story_response(response)
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
        "analysis_source",
        "analysis_quality",
        "analysis_quality_self_check",
        "editorial_verdict",
        "visible_inventory",
        "visible_evidence",
        "score_rationales",
        "subject_relationship",
        "decisive_moment_read",
        "moment_status",
        "sequence_comparison",
        "decisive_moment_factors",
        "subject_identity_uncertainty",
        "selection_risk",
        "edit_vs_select_warning",
        "reject_only_if",
        "why_this_frame",
        "frame_failure_reasons",
        "story_interpretation",
        "recommended_style",
        "best_editing_direction",
        "specific_edit_parameters",
        "advanced_lightroom_parameters",
        "crop_strategy",
        "local_adjustments",
        "avoid_overediting",
        "editing_plan",
    ]:
        if key in data:
            record[key] = data[key]
    if "why_keep" in data:
        record["positive_reasons"] = data["why_keep"]
    if "why_deprioritize" in data:
        record["negative_reasons"] = data["why_deprioritize"]
    record["analysis_source"] = "qwen_vision"
    record["analysis_quality"] = _analysis_quality(data)
    record["qwen_model"] = response.get("model", "unknown")


def _analysis_quality(data: Mapping[str, Any]) -> str:
    evidence = data.get("visible_evidence")
    if not isinstance(evidence, Sequence) or isinstance(evidence, (str, bytes, bytearray)):
        return "missing"
    concrete = [str(item) for item in evidence if _looks_concrete(str(item))]
    if (
        len(concrete) >= 3
        and data.get("subject_relationship")
        and data.get("decisive_moment_read")
        and _valid_editorial_verdict(data.get("editorial_verdict"))
        and _valid_score_rationales(data.get("score_rationales"), len(evidence))
        and _valid_editing_plan(data.get("editing_plan"))
    ):
        return "concrete"
    if concrete:
        return "weak"
    return "generic"


def _looks_concrete(text: str) -> bool:
    generic_terms = ("故事感", "人文感", "主体关系", "瞬间感", "氛围", "张力", "构图", "现场感", "画面成立")
    has_specific_anchor = any(char.isdigit() for char in text) or any(
        token in text
        for token in ("左", "右", "上", "下", "前景", "中景", "背景", "人物", "行人", "车辆", "招牌", "标识", "街道", "手", "脸", "背影", "窗口", "路口")
    )
    if not has_specific_anchor:
        return False
    stripped = text.strip()
    return not any(stripped == term for term in generic_terms)


def _valid_editorial_verdict(value: Any) -> bool:
    if not isinstance(value, Mapping):
        return False
    action = str(value.get("action") or "")
    reason = str(value.get("one_line_reason") or "")
    return action in {"keep", "maybe", "reject"} and _looks_concrete(reason)


def _valid_score_rationales(value: Any, evidence_count: int) -> bool:
    if not isinstance(value, Mapping):
        return False
    checked = 0
    for key in ("storytelling_score", "human_documentary_value_score", "decisive_moment_score", "editing_potential_score"):
        entry = value.get(key)
        if not isinstance(entry, Mapping):
            continue
        reason = str(entry.get("reason") or "")
        ids = entry.get("evidence_ids")
        if not _looks_concrete(reason) or not isinstance(ids, Sequence) or isinstance(ids, (str, bytes, bytearray)):
            continue
        valid_ids = []
        for item in ids:
            try:
                index = int(item)
            except (TypeError, ValueError):
                continue
            if 0 <= index < evidence_count:
                valid_ids.append(index)
        if valid_ids:
            checked += 1
    return checked >= 3


def _valid_editing_plan(value: Any) -> bool:
    if not isinstance(value, Mapping):
        return False
    intent = str(value.get("edit_intent") or "")
    crop_plan = value.get("crop_plan")
    masks = value.get("local_masks")
    if not _looks_concrete(intent):
        return False
    if not isinstance(crop_plan, Mapping):
        return False
    keep = crop_plan.get("keep")
    reduce = crop_plan.get("remove_or_reduce")
    if not isinstance(keep, Sequence) or isinstance(keep, (str, bytes, bytearray)) or not list(keep):
        return False
    if not isinstance(reduce, Sequence) or isinstance(reduce, (str, bytes, bytearray)) or not list(reduce):
        return False
    if not isinstance(masks, Sequence) or isinstance(masks, (str, bytes, bytearray)):
        return False
    for mask in masks:
        if not isinstance(mask, Mapping):
            continue
        if str(mask.get("target") or "").strip() and str(mask.get("operation") or "").strip() and _looks_concrete(str(mask.get("reason") or "")):
            return True
    return False

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from typing import Any


QWEN_STORY_PROMPT_VERSION = "qwen-story-v4"
QWEN_STORY_PROMPT = """
你是严格但有摄影判断力的街拍/纪实/人文/旅行摄影选片编辑。

先看照片里真实可见的内容，再打分。不要写“画面有故事感”“主体关系清晰”这类空泛句子；
每个判断都必须指向可见证据：人物、手势、表情、动作方向、空间关系、招牌/车辆/街道环境、
光线、遮挡、边缘干扰、颜色或明暗结构。技术缺陷只有在破坏可读性时才降权；运动模糊、
颗粒、阴影、偏色如果增强现场感，可以成为保留理由。

如果照片属于连拍/相似组，要判断这一张是否有更好的身体动作、视线、遮挡关系、街头瞬间或
环境线索。不要因为“更清楚”就自动胜出；优先决定性瞬间和人文信息。

每条修图动作必须能追溯到可见证据；如果看不清人、手势、表情或空间关系，必须写“不确定/看不清”，不能脑补。
文字字段用中文，枚举值和 JSON key 保持英文。只返回一个合法 JSON 对象，不要 Markdown。
{
  "analysis_source": "qwen_vision",
  "analysis_quality": "concrete|weak|generic|missing",
  "analysis_quality_self_check": "一句话说明这次阅读是否具体，如果不具体说明原因",
  "editorial_verdict": {
    "action": "keep|maybe|reject",
    "confidence": 0-100,
    "one_line_reason": "必须包含具体画面对象"
  },
  "visible_inventory": {
    "main_subject": "主对象；不确定就写不确定",
    "secondary_subjects": ["次要对象"],
    "setting_context": ["地点、招牌、车辆、街道、室内空间等"],
    "gesture_expression_motion": ["动作、表情、视线、运动方向；看不清就写看不清"],
    "light_color_structure": ["光线、颜色、明暗结构"],
    "edge_obstructions": ["边缘干扰、遮挡、裁切风险"]
  },
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
  "score_rationales": {
    "storytelling_score": {"reason": "具体理由", "evidence_ids": [0]},
    "human_documentary_value_score": {"reason": "具体理由", "evidence_ids": [0]},
    "decisive_moment_score": {"reason": "具体理由", "evidence_ids": [0]},
    "editing_potential_score": {"reason": "具体理由", "evidence_ids": [0]}
  },
  "subject_relationship": "主体、人物/物件、环境之间的关系；如果看不清就明确说不确定",
  "decisive_moment_read": "这个瞬间是否成立，以及成立/不成立的原因",
  "moment_status": "strong|weak|missed|ambiguous",
  "sequence_comparison": "如果这张来自相似组，说明它相对邻近帧在人、动作、遮挡、空间线索和情绪上的胜负；如果看不到邻近帧，只根据本帧写不确定",
  "decisive_moment_factors": ["人物动作", "视线/姿态", "遮挡关系", "空间张力", "环境信息"],
  "subject_identity_uncertainty": "主体、人物身份或动作看不清时必须明确写不确定，不能补故事",
  "selection_risk": "保留/待定/淘汰这张的最大风险，尤其说明是否可能误伤决定性瞬间",
  "edit_vs_select_warning": "哪些问题只能靠选择更好一帧解决，不能靠修图解决",
  "reject_only_if": "只有在画面内容、瞬间和可修空间都不足时才建议淘汰；不要因为轻微模糊/偏色/噪点直接淘汰",
  "why_this_frame": "为什么这张值得保留、待定或淘汰；相似组里要说明和邻近帧相比的判断依据",
  "frame_failure_reasons": ["具体失败点；没有就空数组"],
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
  "advanced_lightroom_parameters": {
    "tone_curve": {"point_curve": "medium_contrast", "highlights": "-6", "lights": "+4", "darks": "-6", "shadows": "+4"},
    "hsl_color_mixer": {"red": {"hue": "-4", "saturation": "-8", "luminance": "+2"}, "orange": {"hue": "-2", "saturation": "+2", "luminance": "+4"}, "yellow": {"hue": "-10", "saturation": "-16", "luminance": "-4"}, "green": {"hue": "+8", "saturation": "-20", "luminance": "-6"}, "aqua": {"hue": "-6", "saturation": "-14", "luminance": "0"}, "blue": {"hue": "-8", "saturation": "-10", "luminance": "-8"}, "purple": {"hue": "0", "saturation": "-10", "luminance": "0"}, "magenta": {"hue": "0", "saturation": "-10", "luminance": "0"}},
    "color_grading": {"shadows": {"hue": "220", "saturation": "8", "luminance": "-2"}, "midtones": {"hue": "34", "saturation": "5", "luminance": "0"}, "highlights": {"hue": "46", "saturation": "4", "luminance": "+2"}, "blending": "45", "balance": "-10"},
    "calibration": {"shadow_tint": "+3", "red_primary_hue": "+5", "red_primary_saturation": "-4", "green_primary_hue": "0", "green_primary_saturation": "-2", "blue_primary_hue": "-6", "blue_primary_saturation": "+8"},
    "detail": {"sharpening_amount": "28", "radius": "0.9", "detail": "15", "masking": "80"},
    "noise_reduction": {"luminance": "8", "detail": "40", "contrast": "0", "color": "15", "color_detail": "50"},
    "lens_corrections": {"remove_chromatic_aberration": "on", "enable_profile_corrections": "on"},
    "effects_grain_vignette": {"grain_amount": "8", "grain_size": "22", "grain_roughness": "35", "post_crop_vignette": "-6"}
  },
  "crop_strategy": "裁切策略必须说明保留/去掉什么视觉信息",
  "local_adjustments": ["具体蒙版/局部加减光动作"],
  "avoid_overediting": "哪些质感、颜色或模糊不应该被修掉",
  "editing_plan": {
    "edit_intent": "修图要强化的摄影内容，必须引用可见对象",
    "color_mode": {"choice": "color|bw", "reason": "为什么"},
    "crop_plan": {
      "aspect_ratio": "original|3:2|4:5|16:9|custom",
      "keep": ["必须保留的画面信息"],
      "remove_or_reduce": ["要裁掉或压弱的干扰"]
    },
    "local_masks": [
      {
        "target": "具体区域或对象",
        "operation": "曝光/阴影/饱和度/清晰度等",
        "settings": {"exposure": "+0.20"},
        "reason": "为了强化或压弱哪条内容"
      }
    ],
    "do_not_overedit": ["不要修掉的现场感、模糊、颜色或颗粒"]
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

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from typing import Any


QWEN_STORY_PROMPT_VERSION = "qwen-story-v13"


def is_current_concrete_qwen_review(record: Mapping[str, Any]) -> bool:
    return (
        str(record.get("qwen_status") or "").lower() in {"done", "cache-hit"}
        and str(record.get("analysis_source") or "") == "qwen_vision"
        and str(record.get("analysis_quality") or "") == "concrete"
        and str(record.get("qwen_prompt_version") or "") == QWEN_STORY_PROMPT_VERSION
    )


QWEN_STORY_PROMPT = """
你是严格但有摄影判断力的街拍/纪实/人文/旅行摄影选片编辑。

先看照片里真实可见的内容，再打分。不要写“画面有故事感”“主体关系清晰”这类空泛句子。
每个判断必须指向可见证据：人物、手势、表情、动作方向、空间关系、招牌/车辆/街道环境、
光线、遮挡、边缘干扰、颜色或明暗结构。技术缺陷只有在破坏可读性时才降权。

你必须像图片编辑一样有主见。不要把报告写成“需确认、可能、建议人工确认”的避责文本。
除非主体确实被遮挡或看不清，否则必须给出明确结论：保留、待定或淘汰，并说明哪一个可见对象决定了这个结论。
不要为了显得友好而把普通记录照夸成作品。地标合影、车站环境照、通勤路人、普通街景都要区分“作品候选”“组照过渡素材”“普通记录”“淘汰”。
保留结论也必须写清楚缺点。任何 keep/maybe 都要包含至少 2 条不能靠修图解决的 `critical_flaws`，例如：人物面部不可读、没有视线/手势、主体关系弱、只是形式结构、边缘遮挡、情节不成立。
不要清一色夸奖。`professional_review` 每段都要有取舍：先说成立点，再说限制；如果限制比成立点重要，必须降级为 maybe 或 reject。
禁止用“非常成功、优秀、没有明显问题、最平衡、最能体现、强烈作品候选”这类单向夸奖，除非同段同时写出具体失败点。
形式感不是故事。建筑线条、钢梁、冷调、纹理只能支撑视觉结构，不能自动等于人文价值；如果人物不可读、没有动作关系，故事/人文/瞬间分数必须保守。
只评价它作为街头/纪实/人文/旅行摄影照片或组照素材的价值；禁止写“适合社交媒体、政策文本、数据图表、宣传材料、传播”等用途化话术来抬高照片。
本地预筛分数、亮度、对比度、clipping、category、rank 只能作为背景信息，不能替代看图判断；
不要在专业深评里复述 brightness/contrast/highlight_clipping_ratio/local_final_selection_score 等指标。
`visible_evidence` 只能写照片里看得见的物体和关系。每条证据必须包含区域、对象、可见程度和它造成的选择影响；不要沿用提示词里的对象示例，也不要凭类似结构脑补人物。
禁止把亮度、对比度、分数、group_rank、category、clipping、预筛结论写进 `visible_evidence` 或 `professional_review`。
如果画面内容不成立，就直接写淘汰或降级，不要用“有潜力”包装。

你的输出要像一位资深图片编辑在复盘一张候选片：先给完整的编辑判断，再拆分证据、风险和后期方案。
不要把分析写成互不相连的短标签。必须回答：
1. 这张照片到底在讲什么，是否有街头/纪实/人文价值。
2. 主体、环境、动作、遮挡、边缘元素之间的关系是否成立。
3. 这是应该保留、待定还是淘汰；如果待定，需要补看什么。
4. 修图和裁切能强化什么，不能挽救什么。

如果照片属于连拍/相似组，要判断这一张是否有更好的身体动作、视线、遮挡关系、街头瞬间或
环境线索。不要因为“更清楚”就自动胜出；优先决定性瞬间和人文信息。

每条修图动作必须能追溯到可见证据；如果看不清人、手势、表情或空间关系，必须写“不确定/看不清”，不能脑补。
对“人”的判断要保守：只有清楚可见头部/躯干/肢体或明确人体姿态时才能写人物、行人、站立、行走。若只是模糊人形、雕塑、反光、遮挡后的轮廓，必须写“疑似人形/看不清/可能是雕塑或遮挡物”，不能当成确定人物。
不要写“下方人物、底部行人、画面下方有人”这类空间判断，除非该人物确实位于画面下 1/3 且在 `visible_evidence` 里明确描述。位于高处平台但低于另一个主体时，应写“中部平台上的疑似人形/人物”，不要写“下方人物”。
对标牌、外语、地名、制服、宗教、职业和文化含义要谨慎：只能先引用看见的文字/符号，再说明它在画面中的视觉作用。
不要把不确定的文字解释成“拼写错误、讽刺、艺术装置、文化错位”等事实；除非照片里有直接证据，否则写“文字提供地点/语境/语气”，不要做知识性断言。
文字字段用中文，枚举值和 JSON key 保持英文。只返回一个合法 JSON 对象，不要 Markdown。

输出要专业、连贯、可执行：`professional_review` 每段 45-90 个汉字；其他短字段可简洁但不能只写标签。
不要把 `analysis_quality` 写成 weak。只有当你能列出具体可见对象、位置、动作/关系、遮挡/边缘风险和后期目标时才输出 concrete；否则直接给 reject/maybe，但仍必须基于看见的内容。
`score_rationales.reason` 必须写出具体可见对象，不能只写“关系成立/故事成立/可修空间”。
`editing_plan.local_masks[].reason` 必须说明对哪个可见对象做什么，不能只写“突出主体”。
`professional_review` 的每段必须至少引用一个具体可见对象，例如人物、标牌、建筑、车辆、手势、视线、边缘遮挡或颜色/文字信息。
数组通常 3-5 项；每项必须有对象和理由。不要解释 JSON；不要输出空字段。
Lightroom 参数只给关键可执行值；`advanced_lightroom_parameters` 只写最相关的 3-5 个小节。
构图裁切必须给出归一化 crop_box：x/y/width/height 都是 0-1，基于原图左上角，不能写像素；不建议裁切时输出 x=0,y=0,width=1,height=1，并说明保留原构图的理由。
{
  "analysis_source": "qwen_vision",
  "analysis_quality": "concrete|weak|generic|missing",
  "analysis_quality_self_check": "是否具体",
  "review_depth_self_check": "是否形成完整编辑判断，而不是零碎描述",
  "editorial_decision_level": "decisive|cautious|reject_directly",
  "editorial_verdict": {"action": "keep|maybe|reject", "confidence": 0-100, "one_line_reason": "具体对象+理由"},
  "professional_review": {
    "editorial_summary": "完整总评：这张照片的核心内容和成立/不成立原因",
    "story_read": "故事与人文价值：人物、动作、环境如何产生意义",
    "composition_read": "构图判断：空间层次、边缘、遮挡、视线/动作方向",
    "selection_logic": "选片逻辑：为什么保留/待定/淘汰，和相邻帧比较时看什么",
    "editing_logic": "后期逻辑：裁切、影调、颜色和局部调整服务于什么",
    "final_recommendation": "最终建议：保留/待定/淘汰及下一步"
  },
  "visible_inventory": {
    "main_subject": "主对象；如果主体只是结构/建筑而非人，必须直说",
    "people": [
      {"id": "p1", "region": "画面上/中/下与左/中/右", "visibility": "clear|partial|uncertain", "pose_or_motion": "站立/行走/看不清/疑似人形", "confidence": 0-100}
    ],
    "setting_context": ["环境"],
    "gesture_expression_motion": ["动作/看不清"]
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
  "tone_category": "monochrome_or_near_bw|high_contrast|low_key|high_key|warm_tone|cool_tone|vivid_color|muted_color",
  "visible_evidence": ["3-5条具体可见证据"],
  "evidence_chain": [
    {"evidence": "可见对象/位置", "editorial_meaning": "它为什么影响故事或选择", "selection_effect": "加分/减分/不确定"}
  ],
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
  "critical_flaws": ["至少2条不能靠修图解决的缺点；keep/maybe也必须写"],
  "hallucination_checks": {
    "unsupported_claims": ["如果你发现自己写了照片中看不清或没有证据的对象/动作，列在这里；没有则空数组"],
    "uncertain_objects": ["看不清的人形/雕塑/反光/遮挡对象"],
    "spatial_sanity_check": "确认人物是否真的在上/中/下位置；避免把中部平台写成下方人物"
  },
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
    "crop_plan": {"aspect_ratio": "original|3:2|4:5|16:9|custom", "keep": ["保留"], "remove_or_reduce": ["压弱"], "crop_box": {"x": 0.08, "y": 0.05, "width": 0.84, "height": 0.90, "reason": "为什么这样裁", "composition_goal": "强化什么关系"}},
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
        "group_id": record.get("group_id"),
        "group_size": record.get("group_size"),
        "group_rank": record.get("group_rank"),
        "is_group_best": record.get("is_group_best"),
        "group_review_role": record.get("group_review_role"),
        "group_moment_risk": record.get("group_moment_risk"),
        "group_basis": record.get("group_basis"),
        "group_time_span_seconds": record.get("group_time_span_seconds"),
    }
    compact = json.dumps({key: value for key, value in context.items() if value not in (None, "", {})}, ensure_ascii=False, sort_keys=True)
    return f"{QWEN_STORY_PROMPT}\n\n连拍/分组上下文，仅用于比较相邻帧，不能替代你对图像内容的判断，也不能写入可见证据：\n{compact}"


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


def validate_qwen_story_response(response: Mapping[str, Any]) -> None:
    data = parse_qwen_story_response(response)
    quality = _analysis_quality(data)
    if quality != "concrete":
        raise ValueError(f"LLM Deep Analysis response was too generic for professional review: {quality}")
    if not _valid_critical_flaws(data):
        raise ValueError("LLM Deep Analysis response did not include concrete critical flaws")
    if _too_praise_heavy_review(data):
        raise ValueError("LLM Deep Analysis response was too praise-heavy for professional review")
    if _unsupported_person_or_motion_claims(data):
        raise ValueError("LLM Deep Analysis response contains unsupported person or motion claims")
    if _overstated_story_or_human_value(data):
        raise ValueError("LLM Deep Analysis response overstated story or human value without readable human evidence")
    if _metric_driven_or_indecisive_review(data):
        raise ValueError("LLM Deep Analysis response was metric-driven or too indecisive for professional review")
    if not _valid_professional_review(data.get("professional_review")):
        raise ValueError("LLM Deep Analysis response did not include a coherent professional_review")


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
        "tone_category",
        "tone_profile",
        "analysis_source",
        "analysis_quality",
        "analysis_quality_self_check",
        "review_depth_self_check",
        "editorial_decision_level",
        "editorial_verdict",
        "professional_review",
        "visible_inventory",
        "visible_evidence",
        "evidence_chain",
        "score_rationales",
        "subject_relationship",
        "decisive_moment_read",
        "moment_status",
        "sequence_comparison",
        "decisive_moment_factors",
        "subject_identity_uncertainty",
        "critical_flaws",
        "hallucination_checks",
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


QWEN_REVIEW_FIELDS = (
    "professional_review",
    "visible_inventory",
    "visible_evidence",
    "evidence_chain",
    "score_rationales",
    "subject_relationship",
    "decisive_moment_read",
    "moment_status",
    "sequence_comparison",
    "decisive_moment_factors",
    "subject_identity_uncertainty",
    "critical_flaws",
    "hallucination_checks",
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
    "advanced_lightroom_parameter_labels",
    "crop_strategy",
    "crop_plan",
    "local_adjustments",
    "avoid_overediting",
    "editing_plan",
    "positive_reasons",
    "negative_reasons",
    "editorial_decision_level",
    "editorial_verdict",
)


def clear_qwen_review_fields(record: dict[str, Any], *, status: str = "failed", reason: str = "") -> None:
    for key in QWEN_REVIEW_FIELDS:
        record.pop(key, None)
    record["analysis_source"] = "local_proxy"
    record["analysis_quality"] = "missing_semantic_read"
    record["qwen_status"] = status
    record["qwen_prompt_version"] = QWEN_STORY_PROMPT_VERSION
    if reason:
        record.setdefault("errors", []).append(f"qwen_vision_failed: {reason}")


def _analysis_quality(data: Mapping[str, Any]) -> str:
    evidence = data.get("visible_evidence")
    if not isinstance(evidence, Sequence) or isinstance(evidence, (str, bytes, bytearray)):
        return "missing"
    concrete = [str(item) for item in evidence if _looks_concrete(str(item))]
    has_verdict = _valid_editorial_verdict(data.get("editorial_verdict"))
    has_review = _valid_professional_review(data.get("professional_review"))
    has_relationship = _valid_relationship_read(str(data.get("subject_relationship") or ""))
    has_moment = _valid_moment_read(str(data.get("decisive_moment_read") or ""))
    if len(concrete) >= 4 and has_relationship and has_moment and has_verdict and has_review:
        return "concrete"
    if len(concrete) >= 3 and has_verdict and has_review:
        return "concrete"
    if has_verdict and has_review:
        return "concrete"
    if concrete:
        return "weak"
    return "generic"


def _looks_concrete(text: str) -> bool:
    if _mostly_metadata_claim(text):
        return False
    stripped = text.strip()
    generic_terms = ("故事感", "人文感", "主体关系", "瞬间感", "氛围", "张力", "构图", "现场感", "画面成立")
    return (
        _has_visual_anchor(stripped)
        and _has_specific_visual_detail(stripped)
        and not _is_template_visual_claim(stripped)
        and not any(stripped == term for term in generic_terms)
    )


def _has_specific_visual_detail(text: str) -> bool:
    lower = text.lower()
    if re.search(r"\b(?:db|kfc|u-?bahn|s-?bahn|airpods)\b|[A-Z]{2,}|\b[A-Z]?\d+[A-Z]?\b", text):
        return True
    chinese_terms = (
        "红色",
        "黄色",
        "绿色",
        "蓝色",
        "白色",
        "黑色",
        "灰色",
        "米色",
        "橙色",
        "粉色",
        "背包",
        "帽子",
        "耳机",
        "眼镜",
        "外套",
        "夹克",
        "头发",
        "短发",
        "背影",
        "面部",
        "男性",
        "后脑",
        "脸",
        "手",
        "微笑",
        "标牌",
        "标识",
        "标语",
        "招牌",
        "文字",
        "和平符号",
        "玻璃",
        "栏杆",
        "立柱",
        "柱子",
        "钢梁",
        "车站",
        "站台",
        "售票机",
        "路口",
        "斑马线",
        "树丛",
        "树",
        "天空",
        "灰白色",
        "砖墙",
        "塔楼",
        "教堂",
        "脚手架",
        "垃圾桶",
        "军装",
        "海报",
        "拱门",
        "楼梯",
        "雕像",
        "雕塑",
        "模型",
        "人形",
        "四马战车",
        "地标",
        "勃兰登堡",
        "建筑",
        "网格",
        "顶棚",
        "玻璃顶棚",
        "窗户",
        "门",
        "车辆边缘",
        "面包车",
        "公交",
        "自行车",
        "奔驰",
        "摩托",
        "裁切",
        "遮挡",
        "反光",
        "倒影",
        "高光",
        "阴影",
        "边缘",
    )
    english_terms = (
        "red",
        "yellow",
        "green",
        "blue",
        "white",
        "black",
        "gray",
        "grey",
        "beige",
        "orange",
        "pink",
        "backpack",
        "bag",
        "hat",
        "cap",
        "earphone",
        "earbud",
        "glasses",
        "jacket",
        "hair",
        "head",
        "face",
        "hand",
        "smile",
        "sign",
        "storefront",
        "letter",
        "text",
        "glass",
        "railing",
        "pillar",
        "column",
        "station",
        "platform",
        "crosswalk",
        "tree",
        "sky",
        "statue",
        "landmark",
        "building",
        "window",
        "gate",
        "van",
        "bus",
        "bicycle",
        "cyclist",
        "crop",
        "cropped",
        "occlud",
        "reflection",
        "highlight",
        "shadow",
        "edge",
    )
    return any(term in text for term in chinese_terms) or any(term in lower for term in english_terms)


def _is_template_visual_claim(text: str) -> bool:
    if _has_specific_visual_detail(text):
        return False
    lower = text.lower()
    vague_terms = (
        "形成关系",
        "形成层次",
        "关系清晰",
        "空间关系",
        "主体关系",
        "故事感",
        "现场感",
        "画面成立",
        "值得保留",
        "human relationship",
        "subject relationship",
        "street relationship",
        "visual layer",
        "layered context",
        "story signal",
        "worth keeping",
    )
    generic_objects = (
        "人物",
        "主体",
        "前景",
        "背景",
        "街道",
        "环境",
        "车辆",
        "person",
        "subject",
        "foreground",
        "background",
        "street",
        "environment",
        "vehicle",
    )
    object_hits = sum(1 for term in generic_objects if term in text or term in lower)
    return object_hits >= 2 and any(term in text or term in lower for term in vague_terms)


def _valid_relationship_read(text: str) -> bool:
    if _looks_concrete(text):
        return True
    lower = text.lower()
    negative_terms = ("割裂", "无互动", "没有互动", "缺乏互动", "无法形成", "未形成", "no interaction", "disconnected", "no usable relationship")
    relation_terms = ("关系", "互动", "连接", "环境", "主体", "relationship", "interaction", "connection", "environment")
    return any(term in text or term in lower for term in negative_terms) and any(
        term in text or term in lower for term in relation_terms
    )


def _valid_moment_read(text: str) -> bool:
    if _looks_concrete(text):
        return True
    lower = text.lower()
    negative_terms = ("瞬间未成立", "未捕捉", "没有", "无", "缺乏", "静止", "no readable", "no decisive", "does not survive")
    moment_terms = ("瞬间", "动作", "手势", "戏剧性", "互动", "moment", "gesture", "timing", "action")
    return any(term in text or term in lower for term in negative_terms) and any(term in text or term in lower for term in moment_terms)


def _has_visual_anchor(text: str) -> bool:
    position_terms = (
            "左",
            "右",
            "上",
            "下",
            "前景",
            "中景",
            "背景",
            "顶部",
            "底部",
            "边缘",
            "中心",
            "画面",
    )
    subject_terms = (
            "人物",
            "游客",
            "旅人",
            "行人",
            "男子",
            "女性",
            "老人",
            "孩子",
            "人群",
            "面部",
            "表情",
            "微笑",
            "耳机",
            "AirPods",
            "手势",
            "手",
            "脸",
            "背影",
            "姿态",
    )
    environment_terms = (
            "车辆",
            "车流",
            "招牌",
            "标识",
            "标牌",
            "标语",
            "文字",
            "字",
            "DB",
            "Juten",
            "Tach",
            "Bahnhof",
            "街道",
            "站台",
            "玻璃门",
            "地标",
            "雕塑",
            "柱廊",
            "天空",
            "窗口",
            "路口",
            "树",
            "树丛",
            "门",
            "窗",
            "栏杆",
            "工人",
            "背心",
            "标志牌",
            "反光标志",
            "建筑",
            "钢梁",
            "楼梯",
            "平台",
            "背包",
            "帽子",
            "衣服",
            "蓝衣",
            "红色",
            "黄色",
            "绿色",
            "蓝色",
            "白色",
            "灰白",
            "深蓝",
            "光线",
            "阴影",
            "高光",
    )
    relation_terms = (
            "遮挡",
            "视线",
            "动作",
            "行走",
            "经过",
            "互动",
            "合影",
            "直视",
            "看向",
            "压过",
            "入画",
            "反射",
            "形成",
            "突出",
            "强化",
            "弱化",
            "提亮",
            "压暗",
            "裁剪",
            "聚焦",
            "恢复",
            "醒目",
            "对比",
            "关系",
            "层次",
            "引导线",
            "完整",
            "清晰",
            "模糊",
            "可见",
    )
    categories = [
        any(token in text for token in position_terms),
        any(token in text for token in subject_terms),
        any(token in text for token in environment_terms),
        any(token in text for token in relation_terms),
    ]
    return sum(1 for item in categories if item) >= 2 or (
        any(token in text for token in subject_terms) and any(token in text for token in environment_terms)
    )


def _metadata_terms() -> tuple[str, ...]:
    return (
        "brightness",
        "contrast",
        "highlight_clipping",
        "shadow_clipping",
        "technical_quality_score",
        "local_final_selection_score",
        "final_selection_score",
        "story_candidate",
        "portfolio_candidate",
        "strong_edit_candidate",
        "local_category",
        "group_rank",
        "group_size",
        "group_id",
        "rank=1",
        "rank1",
        "moment_risk",
        "delta=",
        "clipping",
        "category",
        "预筛",
        "技术参数",
        "参数",
        "分数",
        "组内",
        "裁切比",
        "评分",
    )


def _mostly_metadata_claim(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return True
    hits = sum(1 for term in _metadata_terms() if term in stripped)
    if hits >= 1 and not _has_visual_anchor(stripped):
        return True
    if hits >= 2:
        return True
    if re.search(r"\b(?:brightness|contrast|rank|score|category|clipping|delta)\b\s*[=:]?\s*\d", stripped, flags=re.IGNORECASE):
        return True
    if re.search(r"(亮度|对比度|高光裁切|阴影裁切|组内|分数|评分)\s*[=:：]?\s*\d", stripped):
        return True
    return False


def _valid_critical_flaws(data: Mapping[str, Any]) -> bool:
    flaws = _text_list(data.get("critical_flaws"))
    if len([item for item in flaws if _valid_critical_flaw_text(item)]) >= 2:
        return True
    fallback = []
    for key in ("selection_risk", "edit_vs_select_warning", "subject_identity_uncertainty"):
        value = str(data.get(key) or "").strip()
        if value:
            fallback.append(value)
    fallback.extend(_text_list(data.get("frame_failure_reasons")))
    fallback.extend(_text_list(data.get("why_deprioritize")))
    review = data.get("professional_review")
    if isinstance(review, Mapping):
        fallback.extend(str(value) for value in review.values())
    fallback.extend(_text_list(data.get("visible_evidence")))
    fallback.extend(_text_list(data.get("evidence_chain")))
    return len([item for item in fallback if _valid_critical_flaw_text(item)]) >= 2


def _valid_critical_flaw_text(text: str) -> bool:
    stripped = text.strip()
    if len(stripped) < 6 or _mostly_metadata_claim(stripped):
        return False
    weak_phrases = (
        "暂无",
        "没有明显",
        "轻微",
        "可修",
        "不影响整体",
        "瑕不掩瑜",
        "仍有潜力",
        "具备一定价值",
    )
    if any(phrase in stripped for phrase in weak_phrases):
        return False
    flaw_terms = (
        "不可见",
        "看不清",
        "不可读",
        "无法",
        "缺乏",
        "缺少",
        "没有",
        "遮挡",
        "截断",
        "分散",
        "干扰",
        "压过",
        "抢眼",
        "过曝",
        "溢出",
        "模糊",
        "失焦",
        "弱",
        "平淡",
        "不成立",
        "无互动",
        "无视线",
        "无手势",
        "无表情",
        "普通",
        "形式",
        "结构",
        "仅",
        "不能靠修图",
        "不能补出",
        "不能挽救",
        "unclear",
        "not readable",
        "missing",
        "blocked",
        "occluded",
        "weak",
        "flat",
        "ordinary",
    )
    return any(term in stripped.lower() for term in flaw_terms) and _has_visual_anchor(stripped)


def _too_praise_heavy_review(data: Mapping[str, Any]) -> bool:
    text = _combined_review_text(data)
    if not text:
        return True
    praise_terms = (
        "非常成功",
        "优秀",
        "没有明显",
        "最平衡",
        "最能体现",
        "强烈形式感",
        "强烈作品候选",
        "非常强",
        "非常完整",
        "构图严谨",
        "非常成功",
        "成功",
        "独特",
        "丰富",
        "稳定",
        "excellent",
        "successful",
        "strong candidate",
    )
    praise_hits = sum(text.lower().count(term.lower()) for term in praise_terms)
    flaw_count = len([item for item in _text_list(data.get("critical_flaws")) if _valid_critical_flaw_text(item)])
    flaw_count += len([item for item in _text_list(data.get("why_deprioritize")) if _valid_critical_flaw_text(item)])
    for key in ("selection_risk", "edit_vs_select_warning", "subject_identity_uncertainty"):
        if _valid_critical_flaw_text(str(data.get(key) or "")):
            flaw_count += 1
    return praise_hits >= 3 and flaw_count < 2


def _overstated_story_or_human_value(data: Mapping[str, Any]) -> bool:
    people = _inventory_people(data)
    readable_people = [person for person in people if person.get("visibility") == "clear"]
    moment_status = str(data.get("moment_status") or "").lower()
    try:
        story_score = float(data.get("storytelling_score") or 0)
    except (TypeError, ValueError):
        story_score = 0.0
    try:
        human_score = float(data.get("human_documentary_value_score") or 0)
    except (TypeError, ValueError):
        human_score = 0.0
    try:
        decisive_score = float(data.get("decisive_moment_score") or 0)
    except (TypeError, ValueError):
        decisive_score = 0.0
    category = str(data.get("category") or "")
    action = ""
    verdict = data.get("editorial_verdict")
    if isinstance(verdict, Mapping):
        action = str(verdict.get("action") or "")

    if not readable_people and (story_score >= 72 or human_score >= 72 or decisive_score >= 68):
        return True
    if not readable_people and action == "keep" and category in {"portfolio_candidate", "strong_edit_candidate", "story_candidate"}:
        return True
    if moment_status in {"weak", "missed", "ambiguous"} and decisive_score >= 72:
        return True
    if moment_status in {"missed", "ambiguous"} and category in {"portfolio_candidate", "strong_edit_candidate"}:
        return True
    return False


def _unsupported_person_or_motion_claims(data: Mapping[str, Any]) -> bool:
    text = _combined_review_text(data)
    if not text:
        return False
    unsupported = []
    checks = data.get("hallucination_checks")
    if isinstance(checks, Mapping):
        unsupported = _text_list(checks.get("unsupported_claims"))
    if unsupported:
        return True

    people = _inventory_people(data)
    person_claim = _has_person_claim(text)
    motion_claim = _has_motion_claim(text)
    if not person_claim and not motion_claim:
        return False
    if not people:
        return True
    if motion_claim and not any(person.get("visibility") == "clear" for person in people) and not _uncertain_text(text):
        return True
    lower = text.lower()
    bottom_claim_terms = ("下方人物", "底部人物", "下方行人", "底部行人", "画面下方有人", "下方走", "底部走")
    if any(term in lower for term in bottom_claim_terms) and not _negated_bottom_person_claim(lower):
        return not any("下" in str(person.get("region") or "") or "底" in str(person.get("region") or "") for person in people)
    return False


def _negated_bottom_person_claim(text: str) -> bool:
    negated_terms = (
        "没有确认画面下方行人",
        "没有确认下方行人",
        "未确认画面下方行人",
        "未确认下方人物",
        "没有画面下方人物证据",
        "不能确认下方人物",
        "no confirmed lower person",
        "no bottom person",
    )
    return any(term in text for term in negated_terms)


def _inventory_people(data: Mapping[str, Any]) -> list[dict[str, str]]:
    inventory = data.get("visible_inventory")
    if not isinstance(inventory, Mapping):
        return []
    raw_people = inventory.get("people")
    people: list[dict[str, str]] = []
    if isinstance(raw_people, Sequence) and not isinstance(raw_people, (str, bytes, bytearray)):
        for item in raw_people:
            if isinstance(item, Mapping):
                people.append(
                    {
                        "region": str(item.get("region") or ""),
                        "visibility": _normal_visibility(item.get("visibility")),
                        "motion": str(item.get("pose_or_motion") or item.get("motion") or ""),
                    }
                )
    main_subject = str(inventory.get("main_subject") or "")
    motions = inventory.get("gesture_expression_motion")
    motion_text = " ".join(str(item) for item in motions) if isinstance(motions, Sequence) and not isinstance(motions, (str, bytes, bytearray)) else ""
    if _has_person_claim(main_subject):
        visibility = "uncertain" if _uncertain_text(main_subject + motion_text) else "clear"
        people.append({"region": main_subject, "visibility": visibility, "motion": motion_text})
    return people


def _normal_visibility(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text in {"clear", "visible", "readable", "清楚", "可见", "清晰"}:
        return "clear"
    if text in {"partial", "obscured", "uncertain", "blurred", "blocked", "部分", "遮挡", "不确定", "看不清"}:
        return "uncertain"
    return "uncertain" if text else ""


def _has_person_claim(text: str) -> bool:
    terms = ("人物", "行人", "游客", "旅人", "男子", "女性", "人群", "工人", "person", "pedestrian", "tourist", "man", "woman")
    return any(term in text.lower() for term in terms)


def _has_motion_claim(text: str) -> bool:
    terms = ("行走", "走向", "经过", "跨越", "手势", "表情", "视线", "看向", "互动", "站立", "蹲伏", "俯视", "walking", "gesture", "expression", "looking")
    return any(term in text.lower() for term in terms)


def _uncertain_text(text: str) -> bool:
    terms = ("疑似", "可能", "看不清", "不可辨", "不确定", "模糊", "遮挡", "uncertain", "unclear", "possible")
    return any(term in text.lower() for term in terms)


def _text_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [str(item) for item in value if str(item).strip()]
    return []


def _metric_driven_or_indecisive_review(data: Mapping[str, Any]) -> bool:
    text = _combined_review_text(data)
    if not text:
        return True
    metric_hits = sum(text.count(term) for term in _metadata_terms())
    hesitation_terms = (
        "需确认",
        "需要确认",
        "待确认",
        "不确定",
        "人工",
        "复核",
        "实际画面需",
        "实际画面判断",
        "视觉确认",
        "未经验证",
        "中等偏上",
        "非绝对优秀",
        "暗示",
    )
    hesitation_hits = sum(text.count(term) for term in hesitation_terms)
    action = ""
    verdict = data.get("editorial_verdict")
    if isinstance(verdict, Mapping):
        action = str(verdict.get("action") or "")
    evidence = data.get("visible_evidence")
    concrete_evidence = []
    metadata_evidence = 0
    if isinstance(evidence, Sequence) and not isinstance(evidence, (str, bytes, bytearray)):
        concrete_evidence = [str(item) for item in evidence if _looks_concrete(str(item))]
        metadata_evidence = sum(1 for item in evidence if _mostly_metadata_claim(str(item)))
    if metadata_evidence:
        return True
    if (
        _valid_editorial_verdict(data.get("editorial_verdict"))
        and _valid_professional_review(data.get("professional_review"))
        and metric_hits == 0
        and not _manual_deferral_review(text)
    ):
        return False
    if len(concrete_evidence) < 3:
        return True
    if metric_hits >= 2:
        return True
    if action in {"keep", "reject"} and len(concrete_evidence) >= 4 and metric_hits == 0 and hesitation_hits < 4:
        return False
    if action == "maybe" and hesitation_hits >= 4 and len(concrete_evidence) < 4:
        return True
    if hesitation_hits >= 5:
        return True
    return False


def _manual_deferral_review(text: str) -> bool:
    lower = text.lower()
    manual_terms = (
        "需要人工",
        "人工复核",
        "人工确认",
        "实际画面需",
        "视觉确认",
        "未经验证",
        "需确认主体",
        "需确认画面",
        "需重新深评",
        "manual review",
        "human review",
        "needs confirmation",
        "needs visual confirmation",
    )
    return any(term in text or term in lower for term in manual_terms)


def _combined_review_text(data: Mapping[str, Any]) -> str:
    parts: list[str] = []
    review = data.get("professional_review")
    if isinstance(review, Mapping):
        parts.extend(str(value) for value in review.values())
    for key in (
        "story_interpretation",
        "subject_relationship",
        "decisive_moment_read",
        "sequence_comparison",
        "selection_risk",
        "edit_vs_select_warning",
        "subject_identity_uncertainty",
        "why_this_frame",
        "best_editing_direction",
        "crop_strategy",
    ):
        value = data.get(key)
        if isinstance(value, str):
            parts.append(value)
    for key in ("visible_evidence", "critical_flaws", "frame_failure_reasons", "why_deprioritize"):
        value = data.get(key)
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            parts.extend(str(item) for item in value)
    checks = data.get("hallucination_checks")
    if isinstance(checks, Mapping):
        for value in checks.values():
            if isinstance(value, str):
                parts.append(value)
            elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
                parts.extend(str(item) for item in value)
    return "\n".join(part for part in parts if part)


def _valid_editorial_verdict(value: Any) -> bool:
    if not isinstance(value, Mapping):
        return False
    action = str(value.get("action") or "")
    reason = str(value.get("one_line_reason") or "")
    return action in {"keep", "maybe", "reject"} and _looks_concrete(reason)


def _valid_professional_review(value: Any) -> bool:
    if not isinstance(value, Mapping):
        return False
    checked = 0
    for key in ("editorial_summary", "story_read", "composition_read", "selection_logic", "editing_logic"):
        text = str(value.get(key) or "").strip()
        if len(text) >= 24 and _looks_concrete(text):
            checked += 1
    return checked >= 3


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
        if not reason or _mostly_metadata_claim(reason) or not isinstance(ids, Sequence) or isinstance(ids, (str, bytes, bytearray)):
            continue
        valid_ids = []
        for item in ids:
            try:
                index = int(item)
            except (TypeError, ValueError):
                continue
            if 0 <= index < evidence_count:
                valid_ids.append(index)
        if valid_ids and (_looks_concrete(reason) or _reason_supported_by_concrete_evidence(valid_ids, value)):
            checked += 1
    return checked >= 3


def _reason_supported_by_concrete_evidence(valid_ids: Sequence[int], rationales: Mapping[str, Any]) -> bool:
    return bool(valid_ids) and len(str(rationales)) >= 20


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
    if not _valid_crop_box(crop_plan.get("crop_box")):
        return False
    if not isinstance(masks, Sequence) or isinstance(masks, (str, bytes, bytearray)):
        return False
    for mask in masks:
        if not isinstance(mask, Mapping):
            continue
        if str(mask.get("target") or "").strip() and str(mask.get("operation") or "").strip() and _looks_concrete(str(mask.get("reason") or "")):
            return True
    return False


def _valid_crop_box(value: Any) -> bool:
    if not isinstance(value, Mapping):
        return False
    try:
        x = float(value.get("x"))
        y = float(value.get("y"))
        width = float(value.get("width"))
        height = float(value.get("height"))
    except (TypeError, ValueError):
        return False
    if not (0 <= x <= 1 and 0 <= y <= 1 and 0 < width <= 1 and 0 < height <= 1):
        return False
    if x + width > 1.02 or y + height > 1.02:
        return False
    return bool(str(value.get("reason") or value.get("composition_goal") or "").strip())

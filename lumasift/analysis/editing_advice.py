from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable


LIGHTROOM_PARAMETER_KEYS = [
    "exposure",
    "contrast",
    "highlights",
    "shadows",
    "whites",
    "blacks",
    "texture",
    "clarity",
    "dehaze",
    "vibrance",
    "saturation",
    "temperature",
    "tint",
]

_BW_STYLES = {"high_contrast_bw_documentary", "low_key_noir_street"}
_COLOR_STYLES = {
    "cinematic_urban_color",
    "muted_humanistic_color",
    "gritty_flash_street",
    "soft_editorial_documentary",
    "cold_metropolitan",
    "warm_memory_tone",
}

_BASE_PARAMETERS: dict[str, dict[str, float | int | str]] = {
    "high_contrast_bw_documentary": {
        "exposure": "-0.10",
        "contrast": "+28",
        "highlights": "-38",
        "shadows": "+18",
        "whites": "+8",
        "blacks": "-30",
        "texture": "+12",
        "clarity": "+18",
        "dehaze": "+6",
        "vibrance": "-100",
        "saturation": "-100",
        "temperature": "0K",
        "tint": "0",
    },
    "low_key_noir_street": {
        "exposure": "-0.35",
        "contrast": "+34",
        "highlights": "-45",
        "shadows": "-8",
        "whites": "+4",
        "blacks": "-36",
        "texture": "+10",
        "clarity": "+20",
        "dehaze": "+10",
        "vibrance": "-100",
        "saturation": "-100",
        "temperature": "0K",
        "tint": "0",
    },
    "cinematic_urban_color": {
        "exposure": "-0.05",
        "contrast": "+22",
        "highlights": "-42",
        "shadows": "+22",
        "whites": "+6",
        "blacks": "-24",
        "texture": "+8",
        "clarity": "+12",
        "dehaze": "+7",
        "vibrance": "+8",
        "saturation": "-6",
        "temperature": "-300K",
        "tint": "+4",
    },
    "muted_humanistic_color": {
        "exposure": "+0.10",
        "contrast": "+12",
        "highlights": "-34",
        "shadows": "+28",
        "whites": "+4",
        "blacks": "-14",
        "texture": "+4",
        "clarity": "+6",
        "dehaze": "+2",
        "vibrance": "+4",
        "saturation": "-12",
        "temperature": "+250K",
        "tint": "+3",
    },
    "gritty_flash_street": {
        "exposure": "-0.15",
        "contrast": "+30",
        "highlights": "-52",
        "shadows": "+10",
        "whites": "+10",
        "blacks": "-32",
        "texture": "+18",
        "clarity": "+22",
        "dehaze": "+8",
        "vibrance": "+2",
        "saturation": "-10",
        "temperature": "-150K",
        "tint": "+2",
    },
    "soft_editorial_documentary": {
        "exposure": "+0.15",
        "contrast": "+8",
        "highlights": "-30",
        "shadows": "+24",
        "whites": "+8",
        "blacks": "-8",
        "texture": "-4",
        "clarity": "-2",
        "dehaze": "0",
        "vibrance": "+10",
        "saturation": "-4",
        "temperature": "+200K",
        "tint": "+2",
    },
    "cold_metropolitan": {
        "exposure": "-0.10",
        "contrast": "+24",
        "highlights": "-40",
        "shadows": "+18",
        "whites": "+5",
        "blacks": "-26",
        "texture": "+10",
        "clarity": "+14",
        "dehaze": "+8",
        "vibrance": "-6",
        "saturation": "-8",
        "temperature": "-550K",
        "tint": "+5",
    },
    "warm_memory_tone": {
        "exposure": "+0.10",
        "contrast": "+10",
        "highlights": "-28",
        "shadows": "+24",
        "whites": "+6",
        "blacks": "-12",
        "texture": "+2",
        "clarity": "+4",
        "dehaze": "0",
        "vibrance": "+12",
        "saturation": "-2",
        "temperature": "+450K",
        "tint": "+6",
    },
    "do_not_overedit": {
        "exposure": "0.00",
        "contrast": "+6",
        "highlights": "-18",
        "shadows": "+12",
        "whites": "+2",
        "blacks": "-6",
        "texture": "0",
        "clarity": "+2",
        "dehaze": "0",
        "vibrance": "+4",
        "saturation": "-2",
        "temperature": "0K",
        "tint": "0",
    },
}


def build_selected_editing_advice(
    ranked_records: list[dict[str, Any]],
    selected_ranks: Iterable[int | str] | int | str | None = None,
    selected_paths: Iterable[str | Path] | str | Path | None = None,
    language: str = "zh",
) -> dict[str, Any]:
    """Build JSON-compatible editing advice for selected ranked report records."""
    language = "en" if language == "en" else "zh"
    ranks = _parse_rank_selection(selected_ranks)
    paths = _parse_path_selection(selected_paths)
    selected = select_ranked_records(ranked_records, selected_ranks=ranks, selected_paths=paths)
    advice = [_advice_for_record(record, language=language) for record in selected]
    return {
        "schema": "selected_editing_advice.v1",
        "language": language,
        "selection": {
            "ranks": sorted(ranks),
            "paths": sorted(paths),
        },
        "selected_count": len(advice),
        "selected_editing_advice": advice,
    }


def generate_selected_editing_advice(
    ranked_records: list[dict[str, Any]],
    selected_ranks: Iterable[int | str] | int | str | None = None,
    selected_paths: Iterable[str | Path] | str | Path | None = None,
    language: str = "zh",
) -> dict[str, Any]:
    return build_selected_editing_advice(
        ranked_records,
        selected_ranks=selected_ranks,
        selected_paths=selected_paths,
        language=language,
    )


def select_ranked_records(
    ranked_records: list[dict[str, Any]],
    selected_ranks: Iterable[int] | None = None,
    selected_paths: Iterable[str] | None = None,
) -> list[dict[str, Any]]:
    """Select records by rank and/or path, preserving ranked report order."""
    ranks = set(selected_ranks or [])
    path_keys = set()
    for selected_path in selected_paths or []:
        path_keys.update(_path_keys(selected_path))

    if not ranks and not path_keys:
        return list(ranked_records)

    selected: list[dict[str, Any]] = []
    for record in ranked_records:
        rank = _coerce_int(record.get("rank"))
        record_keys = _path_keys(record.get("path") or record.get("filename") or "")
        if (rank is not None and rank in ranks) or record_keys.intersection(path_keys):
            selected.append(record)
    return selected


def _advice_for_record(record: dict[str, Any], *, language: str) -> dict[str, Any]:
    style = _recommended_style(record)
    parameters = _lightroom_parameters(record, style)
    tone = _tone_recommendation(record, style, language=language)
    score = _float(record.get("final_selection_score"))
    photo_reading = _photo_reading(record, language=language)
    content_decision = _content_decision(record, language=language)
    editing_intent = _editing_intent(record, style, tone["recommendation"], language=language)
    has_vision = _has_vision_read(record)
    adjustments = _local_adjustments(record, style, tone["recommendation"], language=language) if has_vision else _technical_adjustments(record, language=language)
    local_masks = _local_masks(record, adjustments, language=language) if has_vision else []
    crop_plan = _crop_plan(record, language=language)
    blocked_reason = _blocked_reason(record, has_vision=has_vision, language=language)

    return {
        "rank": record.get("rank"),
        "path": record.get("path"),
        "filename": record.get("filename") or Path(str(record.get("path", ""))).name,
        "category": record.get("category"),
        "final_selection_score": score,
        "story_scores": {
            "storytelling": _float(record.get("storytelling_score")),
            "human_documentary_value": _float(record.get("human_documentary_value_score")),
            "decisive_moment": _float(record.get("decisive_moment_score")),
            "emotional_impact": _float(record.get("emotional_impact_score")),
            "visual_tension": _float(record.get("visual_tension_score")),
            "editing_potential": _float(record.get("editing_potential_score")),
            "technical_quality": _float(record.get("technical_quality_score")),
        },
        "recommended_style": style,
        "recommended_style_label": _style_label(style, language),
        "category_label": _category_label(record.get("category"), language),
        "analysis_status": _analysis_status(record, language=language),
        "analysis_source": "qwen_vision" if has_vision else str(record.get("analysis_source") or "local_proxy"),
        "analysis_quality": str(record.get("analysis_quality") or ("concrete" if has_vision else "missing_semantic_read")),
        "editing_advice_source": "vision_evidence" if has_vision else "technical_draft",
        "blocked_reason": blocked_reason,
        "advice_confidence": _advice_confidence(record, has_vision=has_vision),
        "photo_reading": photo_reading,
        "content_decision": content_decision,
        "editing_intent": editing_intent,
        "evidence_snapshot": _evidence_snapshot(record),
        "crop_plan": crop_plan,
        "local_masks": local_masks,
        "visible_evidence": _string_list(record.get("visible_evidence")),
        "subject_relationship": str(record.get("subject_relationship") or ""),
        "decisive_moment_read": str(record.get("decisive_moment_read") or ""),
        "why_this_frame": str(record.get("why_this_frame") or ""),
        "avoid_overediting": str(record.get("avoid_overediting") or ""),
        "story_interpretation": str(record.get("story_interpretation") or ""),
        "why_keep": _string_list(record.get("positive_reasons")),
        "why_deprioritize": _string_list(record.get("negative_reasons")),
        "editing_direction": editing_intent,
        "lightroom_parameters": parameters,
        "lightroom_parameter_labels": _parameter_labels(language),
        "crop_strategy": _crop_strategy(record, language=language),
        "local_adjustments": adjustments,
        "tone_recommendation": tone,
        "grain_sharpness_motion_blur": _grain_sharpness_motion_blur(record, style, tone["recommendation"], language=language),
    }


def _has_vision_read(record: dict[str, Any]) -> bool:
    if str(record.get("analysis_source") or "") != "qwen_vision":
        return False
    if str(record.get("analysis_quality") or "") != "concrete":
        return False
    evidence = [item for item in _string_list(record.get("visible_evidence")) if _looks_concrete_evidence(item)]
    if len(evidence) < 3:
        return False
    verdict = record.get("editorial_verdict")
    if not isinstance(verdict, dict) or not str(verdict.get("one_line_reason") or "").strip():
        return False
    plan = record.get("editing_plan")
    if not isinstance(plan, dict):
        return False
    crop_plan = plan.get("crop_plan")
    if not isinstance(crop_plan, dict) or not _string_list(crop_plan.get("keep")) or not _string_list(crop_plan.get("remove_or_reduce")):
        return False
    masks = plan.get("local_masks")
    if not isinstance(masks, list) or not masks:
        return False
    for mask in masks:
        if not isinstance(mask, dict):
            continue
        if str(mask.get("target") or "").strip() and str(mask.get("operation") or "").strip() and str(mask.get("reason") or "").strip():
            return True
    return False


def _looks_concrete_evidence(text: str) -> bool:
    anchors = ("左", "右", "上", "下", "前景", "中景", "背景", "人物", "行人", "车辆", "招牌", "标志", "标识", "街道", "路口", "栏杆", "车站", "文字", "手", "脸", "背影")
    english = ("left", "right", "foreground", "background", "pedestrian", "cyclist", "vehicle", "street", "sign", "storefront", "face", "hand")
    lower = text.lower()
    return len(text.strip()) >= 8 and (any(anchor in text for anchor in anchors) or any(anchor in lower for anchor in english))


def _blocked_reason(record: dict[str, Any], *, has_vision: bool, language: str) -> str:
    if has_vision:
        return ""
    if str(record.get("analysis_source") or "") == "qwen_vision":
        return (
            "Qwen 返回了部分视觉信息，但证据数量、结论、裁切计划或局部蒙版不完整；不能生成正式摄影修图方案。这里只给技术草案。"
            if language == "zh"
            else "Qwen returned partial visual information, but evidence, verdict, crop plan, or local masks are incomplete. This is only a technical draft."
        )
    return (
        "未完成 Qwen 视觉深评，不能生成正式摄影修图方案；这里只是曝光、明暗和风险控制草案。"
        if language == "zh"
        else "No Qwen vision review yet, so this is a technical grading draft rather than a photographic editing plan."
    )


def _analysis_status(record: dict[str, Any], *, language: str) -> dict[str, str]:
    if _has_vision_read(record):
        if language == "zh":
            return {"level": "vision_read", "label": "已深评", "note": "这份方案基于 Qwen 对画面内容的具体阅读。"}
        return {"level": "vision_read", "label": "Vision-read", "note": "This plan uses Qwen's concrete image read."}
    if str(record.get("analysis_source") or "") == "qwen_vision":
        if language == "zh":
            return {
                "level": "vision_incomplete",
                "label": "深评不完整",
                "note": "Qwen 返回了部分信息，但证据、裁切或局部蒙版不足，不能生成正式摄影修图方案。",
            }
        return {
            "level": "vision_incomplete",
            "label": "Incomplete vision review",
            "note": "Qwen returned partial information, but evidence or edit-plan structure is insufficient.",
        }
    if language == "zh":
        return {
            "level": "local_prefilter",
            "label": "仅本地预筛",
            "note": "这张尚未完成视觉深评；以下只依据技术指标和已有标签生成，不能替代摄影内容判断。",
        }
    return {
        "level": "local_prefilter",
        "label": "Local pre-screen only",
        "note": "This frame has not been vision-reviewed; the plan is based on technical proxies and labels only.",
    }


def _advice_confidence(record: dict[str, Any], *, has_vision: bool) -> int:
    if not has_vision:
        return 25
    verdict = record.get("editorial_verdict")
    if isinstance(verdict, dict):
        try:
            return max(0, min(100, int(float(verdict.get("confidence", 72)))))
        except (TypeError, ValueError):
            pass
    quality = str(record.get("analysis_quality") or "")
    if quality == "concrete":
        return 78
    if quality == "weak":
        return 55
    return 45


def _evidence_snapshot(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "visible_evidence": _string_list(record.get("visible_evidence")),
        "subject_relationship": str(record.get("subject_relationship") or ""),
        "decisive_moment_read": str(record.get("decisive_moment_read") or ""),
        "why_this_frame": str(record.get("why_this_frame") or ""),
        "avoid_overediting": str(record.get("avoid_overediting") or ""),
    }


def _photo_reading(record: dict[str, Any], *, language: str) -> dict[str, Any]:
    evidence = _string_list(record.get("visible_evidence"))
    if _has_vision_read(record):
        return {
            "summary": str(record.get("story_interpretation") or ""),
            "visible_evidence": evidence,
            "subject_relationship": str(record.get("subject_relationship") or ""),
            "decisive_moment_read": str(record.get("decisive_moment_read") or ""),
            "why_this_frame": str(record.get("why_this_frame") or ""),
        }
    metrics = record.get("local_metrics") if isinstance(record.get("local_metrics"), dict) else {}
    brightness = _float(metrics.get("brightness"))
    contrast = _float(metrics.get("contrast"))
    if language == "zh":
        return {
            "summary": (
                "未完成视觉深评。当前只能说这张在技术预筛中具备一定可修空间；"
                f"亮度约 {brightness:.0f}、对比约 {contrast:.0f}。请先对选中照片运行 Qwen 深评，再做真正的故事/瞬间判断。"
            ),
            "visible_evidence": [],
            "subject_relationship": "",
            "decisive_moment_read": "",
            "why_this_frame": "",
        }
    return {
        "summary": (
            "No vision review yet. Only technical pre-screening is available; "
            f"brightness is about {brightness:.0f} and contrast about {contrast:.0f}."
        ),
        "visible_evidence": [],
        "subject_relationship": "",
        "decisive_moment_read": "",
        "why_this_frame": "",
    }


def _crop_plan(record: dict[str, Any], *, language: str) -> dict[str, Any]:
    plan = record.get("editing_plan")
    if isinstance(plan, dict):
        crop_plan = plan.get("crop_plan")
        if isinstance(crop_plan, dict):
            return {
                "aspect_ratio": str(crop_plan.get("aspect_ratio") or "original"),
                "keep": _string_list(crop_plan.get("keep")),
                "remove_or_reduce": _string_list(crop_plan.get("remove_or_reduce")),
                "reason": str(record.get("crop_strategy") or ""),
            }
    if _has_vision_read(record):
        keep = _string_list(record.get("visible_evidence"))[:2]
        remove = _string_list(record.get("negative_reasons"))[:2]
        return {
            "aspect_ratio": _suggested_aspect(record),
            "keep": keep,
            "remove_or_reduce": remove,
            "reason": str(record.get("crop_strategy") or ""),
        }
    if language == "zh":
        return {
            "aspect_ratio": _suggested_aspect(record),
            "keep": ["未深评前保留原始画面信息，避免裁掉可能关键的环境线索。"],
            "remove_or_reduce": ["只在边缘明显干扰时做轻微裁切。"],
            "reason": "缺少视觉深评，裁切只能作为技术草案。",
        }
    return {
        "aspect_ratio": _suggested_aspect(record),
        "keep": ["Keep original context until vision review confirms what matters."],
        "remove_or_reduce": ["Trim only obvious edge clutter."],
        "reason": "Technical draft only because no vision review is available.",
    }


def _suggested_aspect(record: dict[str, Any]) -> str:
    width = _float(record.get("width"))
    height = _float(record.get("height"))
    if width and height and height > width:
        return "4:5"
    if width and height and width / height >= 1.6:
        return "16:9"
    return "3:2"


def _local_masks(record: dict[str, Any], adjustments: list[str], *, language: str) -> list[dict[str, Any]]:
    plan = record.get("editing_plan")
    if isinstance(plan, dict) and isinstance(plan.get("local_masks"), list):
        masks = [mask for mask in plan["local_masks"] if isinstance(mask, dict)]
        if masks:
            return masks
    evidence = _string_list(record.get("visible_evidence"))
    target = evidence[0] if evidence else ("主体/关键动作区域" if language == "zh" else "main subject or key gesture")
    reason = str(record.get("why_this_frame") or record.get("decisive_moment_read") or "")
    masks: list[dict[str, Any]] = []
    for adjustment in adjustments[:3]:
        masks.append(
            {
                "target": target,
                "operation": adjustment,
                "settings": {},
                "reason": reason,
            }
        )
    return masks


def _content_decision(record: dict[str, Any], *, language: str) -> dict[str, Any]:
    if _has_vision_read(record):
        keep = _string_list(record.get("positive_reasons"))
        risks = _string_list(record.get("negative_reasons"))
        if language == "zh":
            verdict = _category_label(record.get("category"), language)
            return {
                "verdict": verdict,
                "keep_reasons": keep,
                "risks": risks,
                "editor_note": str(record.get("why_this_frame") or record.get("decisive_moment_read") or ""),
            }
        return {
            "verdict": _category_label(record.get("category"), language),
            "keep_reasons": keep,
            "risks": risks,
            "editor_note": str(record.get("why_this_frame") or record.get("decisive_moment_read") or ""),
        }
    if language == "zh":
        return {
            "verdict": "等待深评",
            "keep_reasons": [],
            "risks": ["没有视觉深评时，软件不能可靠判断人物关系、决定性瞬间和故事价值。"],
            "editor_note": "不要把本地技术预筛当成摄影判断。",
        }
    return {
        "verdict": "Pending vision review",
        "keep_reasons": [],
        "risks": ["Without vision review, the app cannot reliably judge subject relationship, timing, or story value."],
        "editor_note": "Do not treat local technical pre-screening as a photographic read.",
    }


def _editing_intent(record: dict[str, Any], style: str, tone: str, *, language: str) -> str:
    plan = record.get("editing_plan")
    if isinstance(plan, dict) and str(plan.get("edit_intent") or "").strip():
        return str(plan["edit_intent"]).strip()
    existing = str(record.get("best_editing_direction") or "").strip()
    if _has_vision_read(record) and existing and "Run qwen_vision mode" not in existing:
        return existing
    avoid = str(record.get("avoid_overediting") or "").strip()
    if language == "zh":
        if _has_vision_read(record):
            subject = str(record.get("subject_relationship") or "主体关系").strip()
            moment = str(record.get("decisive_moment_read") or "瞬间判断").strip()
            base = f"修图目标不是让照片变漂亮，而是让「{subject}」和「{moment}」更容易被看见。"
            if tone == "black_and_white":
                base += "优先用黑白把颜色信息退后，让手势、遮挡和明暗关系成为主线。"
            elif style == "do_not_overedit":
                base += "只做轻微校正，避免把现场偶然性修成商业质感。"
            else:
                base += "保留克制彩色，让地点、标识、肤色和环境线索继续承担叙事。"
            if avoid:
                base += f"不要修掉：{avoid}"
            return base
        return "未深评前只做保守技术修正：校正曝光和边缘干扰，不要假设主体、故事或情绪已经成立。"
    if _has_vision_read(record):
        subject = str(record.get("subject_relationship") or "the subject relationship").strip()
        moment = str(record.get("decisive_moment_read") or "the timing").strip()
        return f"Edit to clarify {subject} and {moment}, not to cosmetically polish the file."
    return "Before vision review, make only conservative technical corrections; do not assume the story is confirmed."


def _technical_adjustments(record: dict[str, Any], *, language: str) -> list[str]:
    brightness = _metric(record, "brightness")
    contrast = _metric(record, "contrast")
    highlight_clip = _metric(record, "highlight_clipping_ratio")
    shadow_clip = _metric(record, "shadow_clipping_ratio")
    if language == "zh":
        adjustments = [
            "技术草案：先只校正曝光、对比和可读性；不要做主体/人物/手势类判断。",
        ]
        if brightness < 88:
            adjustments.append("整体曝光 +0.15 到 +0.30，阴影 +10 到 +20；只为了确认暗部是否还有信息。")
        elif brightness > 165:
            adjustments.append("整体曝光 -0.10 到 -0.25，高光 -25 到 -45；先保护亮部细节。")
        else:
            adjustments.append("曝光保持接近原片，只微调中间调，避免过早改变现场气质。")
        if contrast < 24:
            adjustments.append("对比 +8 到 +14，清晰度 +4；只测试结构是否能读出来。")
        elif contrast > 62:
            adjustments.append("对比不要继续猛加，优先用高光/阴影控制层次。")
        else:
            adjustments.append("对比只做小幅微调；不要把技术清晰度误当成照片成立。")
        if highlight_clip >= 0.02:
            adjustments.append("过曝区域高光 -35、白色色阶 -10；不要强行恢复到假灰。")
        if shadow_clip >= 0.02:
            adjustments.append("死黑区域阴影 +20、黑色色阶 +6；如果没有内容就保持黑。")
        return adjustments
    adjustments = [
        "Technical draft only: adjust exposure, contrast, and readability; do not infer subject or gesture.",
    ]
    if brightness < 88:
        adjustments.append("Exposure +0.15 to +0.30 and Shadows +10 to +20 to check whether dark areas hold information.")
    elif brightness > 165:
        adjustments.append("Exposure -0.10 to -0.25 and Highlights -25 to -45 to protect bright detail.")
    else:
        adjustments.append("Keep exposure close to the original and make only midtone checks.")
    if contrast < 24:
        adjustments.append("Contrast +8 to +14 and Clarity +4 only to test readability.")
    elif contrast > 62:
        adjustments.append("Avoid adding more global contrast; use highlight/shadow control first.")
    else:
        adjustments.append("Make only small contrast changes; do not confuse technical clarity with photographic strength.")
    return adjustments


def _recommended_style(record: dict[str, Any]) -> str:
    style = str(record.get("recommended_style") or "").strip()
    if style in _BASE_PARAMETERS:
        return style

    category = str(record.get("category") or "")
    visual_tension = _float(record.get("visual_tension_score"))
    human_value = _float(record.get("human_documentary_value_score"))
    editing_potential = _float(record.get("editing_potential_score"))
    contrast = _metric(record, "contrast")

    if "reject" in category:
        return "do_not_overedit"
    if visual_tension >= 70 and human_value >= 55:
        return "high_contrast_bw_documentary"
    if contrast >= 62 and visual_tension >= 55:
        return "low_key_noir_street"
    if editing_potential >= 70 and human_value >= 60:
        return "muted_humanistic_color"
    if visual_tension >= 65:
        return "cinematic_urban_color"
    return "muted_humanistic_color"


def _lightroom_parameters(record: dict[str, Any], style: str) -> dict[str, str]:
    parameters = {key: str(value) for key, value in _BASE_PARAMETERS[style].items()}
    existing = record.get("specific_edit_parameters")
    if isinstance(existing, dict):
        for key in LIGHTROOM_PARAMETER_KEYS:
            if key in existing and existing[key] not in (None, ""):
                parameters[key] = str(existing[key])

    brightness = _metric(record, "brightness")
    highlight_clip = _metric(record, "highlight_clipping_ratio")
    shadow_clip = _metric(record, "shadow_clipping_ratio")
    if brightness and brightness < 88:
        parameters["exposure"] = _format_decimal(_decimal(parameters["exposure"]) + 0.25)
        parameters["shadows"] = _format_signed_int(_int(parameters["shadows"]) + 12)
    elif brightness > 165:
        parameters["exposure"] = _format_decimal(_decimal(parameters["exposure"]) - 0.20)
        parameters["highlights"] = _format_signed_int(_int(parameters["highlights"]) - 12)

    if highlight_clip >= 0.02:
        parameters["highlights"] = _format_signed_int(min(_int(parameters["highlights"]), -55))
        parameters["whites"] = _format_signed_int(min(_int(parameters["whites"]), -8))
    if shadow_clip >= 0.02:
        parameters["shadows"] = _format_signed_int(max(_int(parameters["shadows"]), 32))
        parameters["blacks"] = _format_signed_int(max(_int(parameters["blacks"]), -8))

    return {key: parameters[key] for key in LIGHTROOM_PARAMETER_KEYS}


def _tone_recommendation(record: dict[str, Any], style: str, *, language: str) -> dict[str, str]:
    if style in _BW_STYLES:
        if language == "zh":
            return {
                "recommendation": "black_and_white",
                "label": "黑白",
                "rationale": "建议黑白优先，让手势、时机、明暗张力成为画面的主要支撑。",
            }
        return {
            "recommendation": "black_and_white",
            "label": "black and white",
            "rationale": "Use monochrome to make gesture, timing, and tonal tension carry the frame.",
        }
    if style in _COLOR_STYLES:
        if language == "zh":
            return {
                "recommendation": "color",
                "label": "彩色",
                "rationale": "建议保留彩色，因为环境氛围、旅行语境和现场感会增强这张照片的人文阅读。",
            }
        return {
            "recommendation": "color",
            "label": "color",
            "rationale": "Keep color because the selected style benefits from environmental mood and travel context.",
        }

    visual_tension = _float(record.get("visual_tension_score"))
    human_value = _float(record.get("human_documentary_value_score"))
    if visual_tension >= 68 and human_value >= 55:
        if language == "zh":
            return {
                "recommendation": "black_and_white",
                "label": "黑白",
                "rationale": "可先尝试黑白；这张照片更依赖人物瞬间和视觉张力，而不是色彩信息。",
            }
        return {
            "recommendation": "black_and_white",
            "label": "black and white",
            "rationale": "Try black and white first; the record scores favor human moment and tension over color description.",
        }
    if language == "zh":
        return {
            "recommendation": "color",
            "label": "彩色",
            "rationale": "使用克制的彩色处理，保留纪实语境，同时避免过度商业化修饰。",
        }
    return {
        "recommendation": "color",
        "label": "color",
        "rationale": "Use restrained color so the documentary context stays readable without cosmetic polish.",
    }


def _editing_direction(record: dict[str, Any], style: str, tone: str, *, language: str) -> str:
    if not _has_vision_read(record):
        return (
            "技术草案：只处理曝光、明暗和可读性；缺少具体视觉深评前，不生成摄影编辑结论。"
            if language == "zh"
            else "Technical draft only: adjust exposure, tone, and readability; no photographic edit verdict without concrete vision review."
        )
    existing = str(record.get("best_editing_direction") or "").strip()
    if existing and "Run qwen_vision mode" not in existing and (language != "zh" or _contains_cjk(existing)):
        return existing

    category = str(record.get("category") or "selected_candidate")
    if language == "zh":
        category_text = _category_label(category, language)
        if tone == "black_and_white":
            treatment = "做成有力度的黑白纪实风格"
        elif style == "do_not_overedit":
            treatment = "只做轻量校正"
        else:
            treatment = "做成克制的人文彩色风格"
        return (
            f"这张属于「{category_text}」。建议{treatment}：保护照片里真正有价值的瞬间和人物关系，"
            "适度压暗边缘干扰、加强主体与环境的层次，但不要把街头/纪实质感磨得太干净。"
        )
    if tone == "black_and_white":
        treatment = "build a firm black-and-white documentary edit"
    elif style == "do_not_overedit":
        treatment = "make a light corrective edit"
    else:
        treatment = "make a restrained color edit"
    return (
        f"For this {category}, {treatment}: protect the decisive content, deepen edge separation, "
        "and keep texture believable rather than polishing away the street/documentary feel."
    )


def _crop_strategy(record: dict[str, Any], *, language: str) -> str:
    existing = str(record.get("crop_strategy") or "").strip()
    if existing and (language != "zh" or _contains_cjk(existing)):
        return existing

    width = _float(record.get("width"))
    height = _float(record.get("height"))
    visual_tension = _float(record.get("visual_tension_score"))
    if language == "zh":
        if width and height and height > width:
            return "先试 4:5 竖构图；让主要人物/动作区域略微偏离中心，裁掉上下无效空间。"
        if width and height and width / height >= 1.6:
            return "优先保留宽幅关系；如果边缘干扰明显，再试 16:9，但不要破坏人物移动方向和环境语境。"
        if visual_tension >= 70:
            return "尽量保留原构图，只清理边缘杂物，避免把画面关系裁散。"
        return "先试 3:2；如果主体更清楚，再试更紧的 4:5，但不要裁掉关键环境线索。"
    if width and height and height > width:
        return "Start with a 4:5 vertical crop; keep the main human/gesture zone slightly off-center and trim empty top/bottom space."
    if width and height and width / height >= 1.6:
        return "Keep the wide frame unless the edges distract; test a 16:9 crop that preserves directional movement and environmental context."
    if visual_tension >= 70:
        return "Keep near-original framing; remove only edge clutter so the tension and spatial relationships do not collapse."
    return "Try a 3:2 crop first, then a tighter 4:5 if the subject reads stronger after removing quiet edge space."


def _local_adjustments(record: dict[str, Any], style: str, tone: str, *, language: str) -> list[str]:
    plan = record.get("editing_plan")
    if isinstance(plan, dict) and isinstance(plan.get("local_masks"), list):
        adjustments: list[str] = []
        for mask in plan["local_masks"]:
            if not isinstance(mask, dict):
                continue
            target = str(mask.get("target", "")).strip()
            operation = str(mask.get("operation", "")).strip()
            reason = str(mask.get("reason", "")).strip()
            if target or operation or reason:
                if language == "zh":
                    adjustments.append(f"{target}：{operation}；原因：{reason}".strip("；原因："))
                else:
                    adjustments.append(f"{target}: {operation}; reason: {reason}".strip("; reason: "))
        if adjustments:
            return adjustments
    existing = record.get("local_adjustments")
    if isinstance(existing, list) and existing and (language != "zh" or any(_contains_cjk(str(item)) for item in existing)):
        return [str(item) for item in existing]

    if language == "zh":
        adjustments = [
            "主体/手势蒙版：曝光 +0.20，阴影 +10，纹理 +5；羽化要大，避免看出修图痕迹。",
            "边缘压暗：对抢眼边缘做曝光 -0.25 到 -0.40；不要压到脸、手势或关键动作。",
        ]
        if tone == "black_and_white" or style in _BW_STYLES:
            adjustments.append("明暗分离笔刷：在主体轮廓或关键明暗边界上加清晰度 +8、去朦胧 +4。")
        else:
            adjustments.append("背景色彩清理：把过于跳出的背景颜色饱和度 -10，但保留肤色、标识和环境信息。")

        if _metric(record, "highlight_clipping_ratio") >= 0.02:
            adjustments.append("高光恢复蒙版：只在过曝亮部降低高光 -35、白色色阶 -10。")
        if _metric(record, "shadow_clipping_ratio") >= 0.02:
            adjustments.append("暗部可读性蒙版：对仍有故事信息的死黑区域提升阴影 +20、黑色色阶 +6。")
        return adjustments

    adjustments = [
        "Subject/gesture mask: Exposure +0.20, Shadows +10, Texture +5; feather broadly so the lift is not visible.",
        "Edge burn: Exposure -0.25 to -0.40 on distracting borders; keep the burn off faces and key gestures.",
    ]
    if tone == "black_and_white" or style in _BW_STYLES:
        adjustments.append("Tonal separation brush: Clarity +8 and Dehaze +4 on the main contrast boundary or silhouette.")
    else:
        adjustments.append("Color cleanup: reduce Saturation -10 on loud background colors, leaving skin/signage/context intact.")

    if _metric(record, "highlight_clipping_ratio") >= 0.02:
        adjustments.append("Highlight recovery mask: Highlights -35, Whites -10 on clipped bright areas only.")
    if _metric(record, "shadow_clipping_ratio") >= 0.02:
        adjustments.append("Shadow readability mask: Shadows +20, Blacks +6 in blocked areas that contain story information.")
    return adjustments


def _grain_sharpness_motion_blur(record: dict[str, Any], style: str, tone: str, *, language: str) -> dict[str, str]:
    technical = _float(record.get("technical_quality_score"))
    decisive = _float(record.get("decisive_moment_score"))
    story = _float(record.get("storytelling_score"))
    gritty = style in {"high_contrast_bw_documentary", "low_key_noir_street", "gritty_flash_street"}

    grain = "Amount 18, Size 24, Roughness 48" if gritty or tone == "black_and_white" else "Amount 8, Size 22, Roughness 35"
    if language == "zh":
        grain = "数量 18，大小 24，粗糙度 48" if gritty or tone == "black_and_white" else "数量 8，大小 22，粗糙度 35"
        if technical < 50 and (decisive >= 55 or story >= 55):
            sharpness = "数量 28，半径 0.9，细节 15，蒙版 80；只锐化可读的视觉锚点。"
            motion_blur = "如果运动模糊增强了瞬间感，就保留它；不要用过重清晰度或全局锐化追求假清楚。"
        elif technical < 50:
            sharpness = "数量 22，半径 1.0，细节 10，蒙版 85；避免把噪点和压缩痕迹锐化出来。"
            motion_blur = "把模糊当成限制处理；只有主体仍然可读时才考虑更紧裁切。"
        else:
            sharpness = "数量 40，半径 0.8，细节 25，蒙版 70；优先对主体局部锐化，不做全局硬锐化。"
            motion_blur = "保留自然运动感；只用小范围主体蒙版修正意外软。"
        return {"grain": grain, "sharpness": sharpness, "motion_blur": motion_blur}
    if technical < 50 and (decisive >= 55 or story >= 55):
        sharpness = "Amount 28, Radius 0.9, Detail 15, Masking 80; sharpen only the readable anchor point."
        motion_blur = "Keep motion blur if it supports timing; do not chase crispness with heavy clarity or global sharpening."
    elif technical < 50:
        sharpness = "Amount 22, Radius 1.0, Detail 10, Masking 85; avoid emphasizing noise or compression artifacts."
        motion_blur = "Treat blur as a limitation; crop tighter only if a readable subject remains."
    else:
        sharpness = "Amount 40, Radius 0.8, Detail 25, Masking 70; use local sharpening on the subject instead of global crunch."
        motion_blur = "Preserve natural movement; remove only accidental softness with a small subject mask."

    return {
        "grain": grain,
        "sharpness": sharpness,
        "motion_blur": motion_blur,
    }


def _style_label(style: str, language: str) -> str:
    if language != "zh":
        return style.replace("_", " ")
    return {
        "high_contrast_bw_documentary": "高反差黑白纪实",
        "low_key_noir_street": "低调黑色街头",
        "cinematic_urban_color": "电影感城市彩色",
        "muted_humanistic_color": "克制人文彩色",
        "gritty_flash_street": "粗粝闪光街头",
        "soft_editorial_documentary": "柔和编辑纪实",
        "cold_metropolitan": "冷调都市",
        "warm_memory_tone": "暖调记忆感",
        "do_not_overedit": "克制轻修",
    }.get(style, style.replace("_", " "))


def _category_label(category: Any, language: str) -> str:
    raw = str(category or "")
    if language != "zh":
        return raw.replace("_", " ")
    return {
        "portfolio_candidate": "作品候选",
        "strong_edit_candidate": "强修图候选",
        "story_candidate": "故事候选",
        "technically_weak_but_interesting": "技术弱但有趣",
        "ordinary_record": "普通记录",
        "reject_candidate": "淘汰候选",
        "failed": "处理失败",
    }.get(raw, raw.replace("_", " "))


def _parameter_labels(language: str) -> dict[str, str]:
    if language != "zh":
        return {key: key.replace("_", " ").title() for key in LIGHTROOM_PARAMETER_KEYS}
    return {
        "exposure": "曝光",
        "contrast": "对比度",
        "highlights": "高光",
        "shadows": "阴影",
        "whites": "白色色阶",
        "blacks": "黑色色阶",
        "texture": "纹理",
        "clarity": "清晰度",
        "dehaze": "去朦胧",
        "vibrance": "自然饱和度",
        "saturation": "饱和度",
        "temperature": "色温",
        "tint": "色调",
    }


def _contains_cjk(text: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in text)


def _parse_rank_selection(selection: Iterable[int | str] | int | str | None) -> set[int]:
    if selection is None:
        return set()
    items = [selection] if isinstance(selection, (int, str)) else list(selection)
    ranks: set[int] = set()
    for item in items:
        if isinstance(item, int):
            ranks.add(item)
            continue
        for part in str(item).split(","):
            token = part.strip()
            if not token:
                continue
            if "-" in token:
                start_text, end_text = token.split("-", 1)
                start = _coerce_int(start_text.strip())
                end = _coerce_int(end_text.strip())
                if start is not None and end is not None:
                    ranks.update(range(min(start, end), max(start, end) + 1))
                continue
            rank = _coerce_int(token)
            if rank is not None:
                ranks.add(rank)
    return {rank for rank in ranks if rank > 0}


def _parse_path_selection(selection: Iterable[str | Path] | str | Path | None) -> set[str]:
    if selection is None:
        return set()
    items = [selection] if isinstance(selection, (str, Path)) else list(selection)
    paths: set[str] = set()
    for item in items:
        for part in str(item).split(","):
            token = part.strip()
            if token:
                paths.add(token)
    return paths


def _path_keys(value: Any) -> set[str]:
    text = str(value or "").strip()
    if not text:
        return set()
    normalized = text.replace("\\", "/").lower()
    path = Path(text)
    keys = {normalized, path.name.lower()}
    try:
        keys.add(str(path.resolve(strict=False)).replace("\\", "/").lower())
    except OSError:
        pass
    return keys


def _metric(record: dict[str, Any], key: str) -> float:
    metrics = record.get("local_metrics")
    if isinstance(metrics, dict):
        return _float(metrics.get(key))
    return 0.0


def _float(value: Any) -> float:
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return 0.0


def _coerce_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _decimal(value: Any) -> float:
    text = str(value).replace("K", "").strip()
    try:
        return float(text)
    except ValueError:
        return 0.0


def _int(value: Any) -> int:
    return int(round(_decimal(value)))


def _format_decimal(value: float) -> str:
    if abs(value) < 0.005:
        return "0.00"
    return f"{value:+.2f}"


def _format_signed_int(value: int) -> str:
    if value == 0:
        return "0"
    return f"{value:+d}"


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []

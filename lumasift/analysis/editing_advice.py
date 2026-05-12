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
    direction = _editing_direction(record, style, tone["recommendation"], language=language)

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
        "editing_direction": direction,
        "lightroom_parameters": parameters,
        "lightroom_parameter_labels": _parameter_labels(language),
        "crop_strategy": _crop_strategy(record, language=language),
        "local_adjustments": _local_adjustments(record, style, tone["recommendation"], language=language),
        "tone_recommendation": tone,
        "grain_sharpness_motion_blur": _grain_sharpness_motion_blur(record, style, tone["recommendation"], language=language),
    }


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

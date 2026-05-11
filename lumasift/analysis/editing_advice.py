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
) -> dict[str, Any]:
    """Build JSON-compatible editing advice for selected ranked report records."""
    ranks = _parse_rank_selection(selected_ranks)
    paths = _parse_path_selection(selected_paths)
    selected = select_ranked_records(ranked_records, selected_ranks=ranks, selected_paths=paths)
    advice = [_advice_for_record(record) for record in selected]
    return {
        "schema": "selected_editing_advice.v1",
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
) -> dict[str, Any]:
    return build_selected_editing_advice(
        ranked_records,
        selected_ranks=selected_ranks,
        selected_paths=selected_paths,
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


def _advice_for_record(record: dict[str, Any]) -> dict[str, Any]:
    style = _recommended_style(record)
    parameters = _lightroom_parameters(record, style)
    tone = _tone_recommendation(record, style)
    score = _float(record.get("final_selection_score"))
    direction = _editing_direction(record, style, tone["recommendation"])

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
        "editing_direction": direction,
        "lightroom_parameters": parameters,
        "crop_strategy": _crop_strategy(record),
        "local_adjustments": _local_adjustments(record, style, tone["recommendation"]),
        "tone_recommendation": tone,
        "grain_sharpness_motion_blur": _grain_sharpness_motion_blur(record, style, tone["recommendation"]),
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


def _tone_recommendation(record: dict[str, Any], style: str) -> dict[str, str]:
    if style in _BW_STYLES:
        return {
            "recommendation": "black_and_white",
            "rationale": "Use monochrome to make gesture, timing, and tonal tension carry the frame.",
        }
    if style in _COLOR_STYLES:
        return {
            "recommendation": "color",
            "rationale": "Keep color because the selected style benefits from environmental mood and travel context.",
        }

    visual_tension = _float(record.get("visual_tension_score"))
    human_value = _float(record.get("human_documentary_value_score"))
    if visual_tension >= 68 and human_value >= 55:
        return {
            "recommendation": "black_and_white",
            "rationale": "Try black and white first; the record scores favor human moment and tension over color description.",
        }
    return {
        "recommendation": "color",
        "rationale": "Use restrained color so the documentary context stays readable without cosmetic polish.",
    }


def _editing_direction(record: dict[str, Any], style: str, tone: str) -> str:
    existing = str(record.get("best_editing_direction") or "").strip()
    if existing and "Run qwen_vision mode" not in existing:
        return existing

    category = str(record.get("category") or "selected_candidate")
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


def _crop_strategy(record: dict[str, Any]) -> str:
    existing = str(record.get("crop_strategy") or "").strip()
    if existing:
        return existing

    width = _float(record.get("width"))
    height = _float(record.get("height"))
    visual_tension = _float(record.get("visual_tension_score"))
    if width and height and height > width:
        return "Start with a 4:5 vertical crop; keep the main human/gesture zone slightly off-center and trim empty top/bottom space."
    if width and height and width / height >= 1.6:
        return "Keep the wide frame unless the edges distract; test a 16:9 crop that preserves directional movement and environmental context."
    if visual_tension >= 70:
        return "Keep near-original framing; remove only edge clutter so the tension and spatial relationships do not collapse."
    return "Try a 3:2 crop first, then a tighter 4:5 if the subject reads stronger after removing quiet edge space."


def _local_adjustments(record: dict[str, Any], style: str, tone: str) -> list[str]:
    existing = record.get("local_adjustments")
    if isinstance(existing, list) and existing:
        return [str(item) for item in existing]

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


def _grain_sharpness_motion_blur(record: dict[str, Any], style: str, tone: str) -> dict[str, str]:
    technical = _float(record.get("technical_quality_score"))
    decisive = _float(record.get("decisive_moment_score"))
    story = _float(record.get("storytelling_score"))
    gritty = style in {"high_contrast_bw_documentary", "low_key_noir_street", "gritty_flash_street"}

    grain = "Amount 18, Size 24, Roughness 48" if gritty or tone == "black_and_white" else "Amount 8, Size 22, Roughness 35"
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

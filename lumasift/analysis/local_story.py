from __future__ import annotations

from statistics import mean
from typing import Any

import numpy as np

from lumasift.io.image_loader import LoadedImage


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _technical_score(rgb: np.ndarray) -> tuple[float, dict[str, float]]:
    gray = np.mean(rgb.astype(np.float32), axis=2)
    brightness = float(np.mean(gray))
    contrast = float(np.std(gray))
    highlight_clip = float(np.mean(gray > 248))
    shadow_clip = float(np.mean(gray < 7))

    brightness_score = 100.0 - abs(brightness - 118.0) * 0.55
    contrast_score = min(100.0, contrast * 2.1)
    clipping_penalty = (highlight_clip + shadow_clip) * 160.0
    technical = _clamp(brightness_score * 0.45 + contrast_score * 0.45 - clipping_penalty + 10.0)
    return technical, {
        "brightness": round(brightness, 3),
        "contrast": round(contrast, 3),
        "highlight_clipping_ratio": round(highlight_clip, 5),
        "shadow_clipping_ratio": round(shadow_clip, 5),
    }


def _tone_profile(rgb: np.ndarray, metrics: dict[str, float]) -> dict[str, Any]:
    rgb_float = rgb.astype(np.float32)
    means = np.mean(rgb_float.reshape(-1, 3), axis=0)
    red, green, blue = [float(value) for value in means]
    max_channel = np.max(rgb_float, axis=2)
    min_channel = np.min(rgb_float, axis=2)
    saturation = float(np.mean((max_channel - min_channel) / np.maximum(max_channel, 1.0)))
    warmth = red - blue
    brightness = metrics["brightness"]
    contrast = metrics["contrast"]

    if saturation < 0.08:
        category = "monochrome_or_near_bw"
    elif contrast >= 58:
        category = "high_contrast"
    elif brightness < 82:
        category = "low_key"
    elif brightness > 168:
        category = "high_key"
    elif warmth >= 12:
        category = "warm_tone"
    elif warmth <= -12:
        category = "cool_tone"
    elif saturation >= 0.22:
        category = "vivid_color"
    else:
        category = "muted_color"

    return {
        "tone_category": category,
        "tone_brightness": round(brightness, 3),
        "tone_contrast": round(contrast, 3),
        "tone_saturation": round(saturation, 4),
        "tone_warmth": round(warmth, 3),
        "average_rgb": [round(red, 2), round(green, 2), round(blue, 2)],
    }


def _story_proxy_scores(rgb: np.ndarray) -> dict[str, float]:
    """Estimate story-facing priors without pretending to perform real semantic reading.

    These local scores are intentionally weak proxies. The product's decisive story,
    documentary, and editing judgments should come from a vision model or human review.
    """
    gray = np.mean(rgb.astype(np.float32), axis=2)
    h, w = gray.shape
    center = gray[h // 4 : h * 3 // 4, w // 4 : w * 3 // 4]
    edges_y, edges_x = np.gradient(gray)
    edge_energy = np.sqrt(edges_x**2 + edges_y**2)
    density = float(np.mean(edge_energy > 22.0))
    center_activity = float(np.mean(np.abs(center - np.mean(gray)))) if center.size else 0.0
    tonal_range = float(np.percentile(gray, 95) - np.percentile(gray, 5))

    visual_tension = _clamp(density * 260.0 + tonal_range * 0.2)
    editing_potential = _clamp(45.0 + tonal_range * 0.25 - density * 35.0)
    storytelling = _clamp(35.0 + center_activity * 0.35 + density * 110.0)
    human_documentary = _clamp(40.0 + density * 90.0)
    decisive_moment = _clamp(38.0 + density * 80.0 + center_activity * 0.18)
    emotional_impact = _clamp(mean([visual_tension, storytelling, editing_potential]))

    return {
        "storytelling_score": round(storytelling, 2),
        "human_documentary_value_score": round(human_documentary, 2),
        "decisive_moment_score": round(decisive_moment, 2),
        "emotional_impact_score": round(emotional_impact, 2),
        "visual_tension_score": round(visual_tension, 2),
        "editing_potential_score": round(editing_potential, 2),
    }


def _category(score: float) -> str:
    if score >= 86:
        return "portfolio_candidate"
    if score >= 74:
        return "strong_edit_candidate"
    if score >= 62:
        return "story_candidate"
    if score >= 48:
        return "technically_weak_but_interesting"
    if score >= 32:
        return "ordinary_record"
    return "reject_candidate"


def _local_reasons(metrics: dict[str, float], story_scores: dict[str, float]) -> tuple[list[str], list[str]]:
    brightness = metrics["brightness"]
    contrast = metrics["contrast"]
    highlight_clip = metrics["highlight_clipping_ratio"]
    shadow_clip = metrics["shadow_clipping_ratio"]
    visual_tension = story_scores["visual_tension_score"]
    editability = story_scores["editing_potential_score"]

    positive: list[str] = []
    negative: list[str] = []
    if contrast >= 42:
        positive.append("Local contrast and edge structure can support a stronger documentary edit.")
    elif contrast >= 24:
        positive.append("Moderate tonal separation leaves room for a restrained humanistic edit.")
    else:
        negative.append("Low contrast may need careful local separation before the frame reads clearly.")

    if 78 <= brightness <= 158:
        positive.append("Brightness is in a recoverable range with usable midtone information.")
    elif brightness < 78:
        negative.append("The frame is dark; check whether shadow detail still carries story information.")
    else:
        negative.append("The frame is bright; protect highlights before judging subtle subject detail.")

    if visual_tension >= 62:
        positive.append("Dense local structure suggests possible street-layer tension worth a vision pass.")
    if editability >= 68:
        positive.append("Tonal range suggests the file can tolerate meaningful Lightroom shaping.")
    if highlight_clip >= 0.02:
        negative.append("Highlight clipping is visible enough to constrain recovery.")
    if shadow_clip >= 0.02:
        negative.append("Shadow clipping may hide important documentary cues.")

    if not positive:
        positive.append("Local proxy found enough recoverable structure for manual review.")
    if not negative:
        negative.append("Semantic story, human relationship, and decisive moment still require a vision LLM or human review.")
    return positive[:4], negative[:4]


def _local_read(metrics: dict[str, float], story_scores: dict[str, float]) -> str:
    return (
        "Local pre-screen only: this pass can judge tonal recoverability, contrast, edge density, and editing headroom, "
        "but it cannot truly identify people, gestures, story, or decisive moment. "
        f"Brightness {metrics['brightness']:.0f}, contrast {metrics['contrast']:.0f}, "
        f"visual-structure proxy {story_scores['visual_tension_score']:.0f}, "
        f"editing-potential proxy {story_scores['editing_potential_score']:.0f}. "
        "Use LLM Deep Analysis for Top-N frames before making a final story-first keep/reject decision."
    )


def _format_exif(image: LoadedImage) -> dict[str, Any]:
    exif = image.exif or {}
    summary: dict[str, Any] = {}
    if exif.get("raw_preview_source"):
        summary["raw_preview_source"] = exif.get("raw_preview_source")
    mapping = {
        271: "camera_make",
        272: "camera_model",
        306: "date_time",
        36867: "date_time_original",
        33434: "shutter_speed",
        33437: "aperture",
        34855: "iso",
        37386: "focal_length",
        42036: "lens",
    }
    for tag, key in mapping.items():
        if tag not in exif:
            continue
        value = exif[tag]
        if key == "shutter_speed":
            summary[key] = _format_shutter(value)
        elif key == "aperture":
            summary[key] = f"f/{_rational_float(value):.1f}" if _rational_float(value) else str(value)
        elif key == "focal_length":
            summary[key] = f"{_rational_float(value):.0f}mm" if _rational_float(value) else str(value)
        else:
            summary[key] = str(value).strip()
    try:
        summary["file_size_bytes"] = image.path.stat().st_size
    except OSError:
        pass
    return {key: value for key, value in summary.items() if value not in {"", None}}


def _rational_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError, ZeroDivisionError):
        return 0.0


def _format_shutter(value: Any) -> str:
    shutter = _rational_float(value)
    if shutter <= 0:
        return str(value)
    if shutter >= 1:
        return f"{shutter:.1f}s"
    return f"1/{round(1 / shutter)}"


def analyze_local_story_proxy(image: LoadedImage) -> dict:
    technical, metrics = _technical_score(image.rgb)
    tone_profile = _tone_profile(image.rgb, metrics)
    metrics.update({key: value for key, value in tone_profile.items() if key.startswith("tone_")})
    story_scores = _story_proxy_scores(image.rgb)
    final = (
        story_scores["storytelling_score"] * 0.22
        + story_scores["human_documentary_value_score"] * 0.18
        + story_scores["decisive_moment_score"] * 0.16
        + story_scores["emotional_impact_score"] * 0.14
        + story_scores["visual_tension_score"] * 0.12
        + story_scores["editing_potential_score"] * 0.12
        + technical * 0.06
    )
    positive, negative = _local_reasons(metrics, story_scores)
    return {
        "path": str(image.path),
        "filename": image.path.name,
        "extension": image.path.suffix.lower(),
        "kind": image.kind,
        "width": image.width,
        "height": image.height,
        "exif": _format_exif(image),
        "technical_quality_score": round(technical, 2),
        **story_scores,
        "final_selection_score": round(final, 2),
        "category": _category(final),
        "analysis_source": "local_proxy",
        "analysis_quality": "missing_semantic_read",
        "needs_qwen_review": True,
        "editorial_verdict": {
            "action": "maybe",
            "confidence": 20,
            "one_line_reason": "Local technical pre-screen only; semantic photo reading has not been performed.",
        },
        "local_metrics": metrics,
        "tone_category": tone_profile["tone_category"],
        "tone_profile": tone_profile,
        "positive_reasons": positive,
        "negative_reasons": negative,
        "story_interpretation": _local_read(metrics, story_scores),
        "best_editing_direction": "Run vision LLM deep analysis for concrete artistic editing guidance.",
        "recommended_style": "pending_vision_review",
        "specific_edit_parameters": {},
        "errors": image.errors,
    }

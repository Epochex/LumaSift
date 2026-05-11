from __future__ import annotations

from statistics import mean

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


def analyze_local_story_proxy(image: LoadedImage) -> dict:
    technical, metrics = _technical_score(image.rgb)
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
    positive = ["Local proxy detected workable tonal/detail structure."]
    negative = ["Semantic story and human-documentary value require Qwen vision review."]
    return {
        "path": str(image.path),
        "filename": image.path.name,
        "extension": image.path.suffix.lower(),
        "kind": image.kind,
        "width": image.width,
        "height": image.height,
        "technical_quality_score": round(technical, 2),
        **story_scores,
        "final_selection_score": round(final, 2),
        "category": _category(final),
        "local_metrics": metrics,
        "positive_reasons": positive,
        "negative_reasons": negative,
        "story_interpretation": "Not available in local_only mode.",
        "best_editing_direction": "Run qwen_vision mode for concrete artistic editing guidance.",
        "recommended_style": "pending_vision_review",
        "specific_edit_parameters": {},
        "errors": image.errors,
    }

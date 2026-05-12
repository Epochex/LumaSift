from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image, ImageOps


DEFAULT_HASH_THRESHOLD = 8
ASPECT_TOLERANCE = 0.08
BRIGHTNESS_TOLERANCE = 12.0
COLOR_DISTANCE_TOLERANCE = 50.0


def compute_dhash(path: Path, *, hash_size: int = 8) -> str:
    with Image.open(path) as image:
        gray = ImageOps.grayscale(image)
        resized = gray.resize((hash_size + 1, hash_size), Image.Resampling.LANCZOS)
        bits = []
        for y in range(hash_size):
            for x in range(hash_size):
                bits.append(1 if resized.getpixel((x, y)) > resized.getpixel((x + 1, y)) else 0)
    value = 0
    for bit in bits:
        value = (value << 1) | bit
    return f"{value:016x}"


def compute_average_color(path: Path) -> str:
    with Image.open(path) as image:
        rgb = image.convert("RGB").resize((1, 1), Image.Resampling.BILINEAR)
        r, g, b = rgb.getpixel((0, 0))
    return f"{r},{g},{b}"


def hamming_distance(left: str, right: str) -> int:
    try:
        return (int(left, 16) ^ int(right, 16)).bit_count()
    except ValueError:
        return 64


def apply_similarity_groups(records: list[dict[str, Any]], *, threshold: int = DEFAULT_HASH_THRESHOLD) -> list[dict[str, Any]]:
    representatives: list[dict[str, Any]] = []
    groups: list[list[dict[str, Any]]] = []
    for record in records:
        visual_hash = str(record.get("visual_hash") or "")
        matched_index: int | None = None
        if visual_hash:
            for index, representative in enumerate(representatives):
                if _can_group(record, representative, threshold=threshold):
                    matched_index = index
                    break
        if matched_index is None:
            representatives.append(record)
            groups.append([record])
        else:
            groups[matched_index].append(record)

    for index, group in enumerate(groups, start=1):
        group_id = f"g{index:04d}"
        best = max(group, key=_group_best_score)
        best_score = _group_best_score(best)
        ordered = sorted(group, key=_group_best_score, reverse=True)
        for group_rank, record in enumerate(ordered, start=1):
            record["group_id"] = group_id
            record["group_size"] = len(group)
            record["group_rank"] = group_rank
            record["is_group_best"] = record is best
            record["group_best_path"] = best.get("path", "")
            record["group_score_delta"] = round(best_score - _group_best_score(record), 3)
    return records


def _can_group(record: dict[str, Any], representative: dict[str, Any], *, threshold: int) -> bool:
    left_hash = str(record.get("visual_hash") or "")
    right_hash = str(representative.get("visual_hash") or "")
    if not left_hash or not right_hash:
        return False
    if hamming_distance(left_hash, right_hash) > threshold:
        return False
    left_aspect = _aspect(record)
    right_aspect = _aspect(representative)
    if not left_aspect or not right_aspect:
        aspect_ok = True
    else:
        aspect_ok = abs(left_aspect - right_aspect) <= ASPECT_TOLERANCE
    if not aspect_ok:
        return False
    left_brightness = _brightness(record)
    right_brightness = _brightness(representative)
    if left_brightness is None or right_brightness is None:
        brightness_ok = True
    else:
        brightness_ok = abs(left_brightness - right_brightness) <= BRIGHTNESS_TOLERANCE
    if not brightness_ok:
        return False
    left_color = _color(record)
    right_color = _color(representative)
    if left_color is None or right_color is None:
        return True
    return _color_distance(left_color, right_color) <= COLOR_DISTANCE_TOLERANCE


def _aspect(record: dict[str, Any]) -> float:
    try:
        width = float(record.get("width") or 0)
        height = float(record.get("height") or 0)
    except (TypeError, ValueError):
        return 0.0
    return width / height if height else 0.0


def _group_best_score(record: dict[str, Any]) -> float:
    try:
        score = float(record.get("final_selection_score") or 0.0)
    except (TypeError, ValueError):
        score = 0.0
    try:
        feedback = float(record.get("user_feedback_priority") or 0.0)
    except (TypeError, ValueError):
        feedback = 0.0
    return score + feedback * 8.0


def _brightness(record: dict[str, Any]) -> float | None:
    metrics = record.get("local_metrics")
    if not isinstance(metrics, dict) or metrics.get("brightness") is None:
        return None
    try:
        return float(metrics["brightness"])
    except (TypeError, ValueError):
        return None


def _color(record: dict[str, Any]) -> tuple[float, float, float] | None:
    value = record.get("visual_color")
    if not isinstance(value, str):
        return None
    parts = value.split(",")
    if len(parts) != 3:
        return None
    try:
        return float(parts[0]), float(parts[1]), float(parts[2])
    except ValueError:
        return None


def _color_distance(left: tuple[float, float, float], right: tuple[float, float, float]) -> float:
    return sum((a - b) ** 2 for a, b in zip(left, right, strict=True)) ** 0.5

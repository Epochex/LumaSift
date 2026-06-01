from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps


DEFAULT_HASH_THRESHOLD = 8
ASPECT_TOLERANCE = 0.08
BRIGHTNESS_TOLERANCE = 12.0
COLOR_DISTANCE_TOLERANCE = 50.0
SCENE_HASH_THRESHOLD = 18
SCENE_BRIGHTNESS_TOLERANCE = 28.0
SCENE_COLOR_DISTANCE_TOLERANCE = 86.0
SCENE_SIGNATURE_DISTANCE_TOLERANCE = 38.0
SEQUENCE_FILENAME_WINDOW = 8
TIME_SEQUENCE_WINDOW_SECONDS = 8.0
TIME_SEQUENCE_MAX_SPAN_SECONDS = 45.0


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


def compute_scene_signature(path: Path, *, size: int = 8) -> str:
    with Image.open(path) as image:
        gray = ImageOps.grayscale(image)
        gray = ImageOps.autocontrast(gray)
        resized = gray.resize((size, size), Image.Resampling.BILINEAR)
        values = list(resized.getdata())
    mean = sum(values) / len(values)
    centered = [max(0, min(255, int(value - mean + 128))) for value in values]
    return "".join(f"{value:02x}" for value in centered)


def hamming_distance(left: str, right: str) -> int:
    try:
        return (int(left, 16) ^ int(right, 16)).bit_count()
    except ValueError:
        return 64


def apply_similarity_groups(records: list[dict[str, Any]], *, threshold: int = DEFAULT_HASH_THRESHOLD) -> list[dict[str, Any]]:
    if not records:
        return records

    parent = list(range(len(records)))
    representatives: list[int] = []
    for record_index, record in enumerate(records):
        visual_hash = str(record.get("visual_hash") or "")
        matched_index: int | None = None
        if visual_hash:
            for representative_position, representative_index in enumerate(representatives):
                if _can_group(record, records[representative_index], threshold=threshold):
                    matched_index = representative_position
                    break
        if matched_index is None:
            representatives.append(record_index)
        else:
            _union(parent, record_index, representatives[matched_index])

    for cluster in _time_clusters(records):
        first = cluster[0]
        for record_index in cluster[1:]:
            _union(parent, first, record_index)

    buckets: dict[int, list[dict[str, Any]]] = {}
    for record_index, record in enumerate(records):
        buckets.setdefault(_find(parent, record_index), []).append(record)
    groups = list(buckets.values())

    for index, group in enumerate(groups, start=1):
        group_id = f"g{index:04d}"
        best = max(group, key=_group_best_score)
        best_score = _group_best_score(best)
        ordered = sorted(group, key=_group_best_score, reverse=True)
        group_basis = _group_basis(group, threshold=threshold)
        time_span = _group_time_span_seconds(group)
        for group_rank, record in enumerate(ordered, start=1):
            record["group_id"] = group_id
            record["group_size"] = len(group)
            record["group_rank"] = group_rank
            record["is_group_best"] = record is best
            record["group_best_path"] = best.get("path", "")
            record["group_score_delta"] = round(best_score - _group_best_score(record), 3)
            record["group_basis"] = group_basis
            if time_span is not None:
                record["group_time_span_seconds"] = round(time_span, 3)
            moment_risk = _is_moment_risk_alternate(record, best, group_rank=group_rank)
            record["group_moment_risk"] = bool(moment_risk and record is not best)
            record["group_review_role"] = "best" if record is best else ("moment_risk" if moment_risk else "similar_non_best")
    return records


def _find(parent: list[int], index: int) -> int:
    while parent[index] != index:
        parent[index] = parent[parent[index]]
        index = parent[index]
    return index


def _union(parent: list[int], left: int, right: int) -> None:
    left_root = _find(parent, left)
    right_root = _find(parent, right)
    if left_root != right_root:
        parent[right_root] = left_root


def _is_moment_risk_alternate(record: dict[str, Any], best: dict[str, Any], *, group_rank: int) -> bool:
    if record is best:
        return False
    label = str(record.get("user_label") or "").strip().lower()
    if label in {"keep", "maybe"}:
        return True
    if _visually_same_as_best(record, best):
        return False
    delta = max(0.0, _group_best_score(best) - _group_best_score(record))
    if group_rank <= 3 and delta <= 4.0:
        return True
    if delta <= 15.0:
        for key in ("decisive_moment_score", "storytelling_score", "human_documentary_value_score"):
            if _score(record, key) >= _score(best, key) + 6.0:
                return True
    return False


def _visually_same_as_best(record: dict[str, Any], best: dict[str, Any]) -> bool:
    left_hash = str(record.get("visual_hash") or "")
    right_hash = str(best.get("visual_hash") or "")
    if not left_hash or left_hash != right_hash:
        return False
    left_color = _color(record)
    right_color = _color(best)
    if left_color is not None and right_color is not None and _color_distance(left_color, right_color) > 3.0:
        return False
    signature_distance = _scene_signature_distance(record, best)
    if signature_distance is not None and signature_distance > 2.0:
        return False
    left_brightness = _brightness(record)
    right_brightness = _brightness(best)
    if left_brightness is not None and right_brightness is not None and abs(left_brightness - right_brightness) > 2.0:
        return False
    return True


def _can_group(record: dict[str, Any], representative: dict[str, Any], *, threshold: int) -> bool:
    left_hash = str(record.get("visual_hash") or "")
    right_hash = str(representative.get("visual_hash") or "")
    if not left_hash or not right_hash:
        return False
    hash_distance = hamming_distance(left_hash, right_hash)
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
    color_distance = _color_distance(left_color, right_color) if left_color is not None and right_color is not None else None
    near_duplicate = hash_distance <= threshold and (color_distance is None or color_distance <= COLOR_DISTANCE_TOLERANCE)
    if near_duplicate:
        return True

    if hash_distance > SCENE_HASH_THRESHOLD:
        signature_distance = _scene_signature_distance(record, representative)
        if signature_distance is None or signature_distance > SCENE_SIGNATURE_DISTANCE_TOLERANCE:
            return False
    if color_distance is not None and color_distance > SCENE_COLOR_DISTANCE_TOLERANCE:
        return False
    if left_brightness is not None and right_brightness is not None and abs(left_brightness - right_brightness) > SCENE_BRIGHTNESS_TOLERANCE:
        return False
    sequence_distance = _sequence_distance(record, representative)
    if sequence_distance is None:
        return False
    return sequence_distance <= SEQUENCE_FILENAME_WINDOW


def _time_clusters(records: list[dict[str, Any]]) -> list[list[int]]:
    timed: list[tuple[datetime, int]] = []
    for index, record in enumerate(records):
        timestamp = _capture_time(record)
        if timestamp is not None:
            timed.append((timestamp, index))
    timed.sort(key=lambda item: (item[0], str(records[item[1]].get("path") or records[item[1]].get("filename") or "")))

    clusters: list[list[int]] = []
    current: list[int] = []
    current_start: datetime | None = None
    previous_time: datetime | None = None
    previous_index: int | None = None
    for timestamp, record_index in timed:
        can_continue = (
            bool(current)
            and current_start is not None
            and previous_time is not None
            and previous_index is not None
            and abs((timestamp - previous_time).total_seconds()) <= TIME_SEQUENCE_WINDOW_SECONDS
            and abs((timestamp - current_start).total_seconds()) <= TIME_SEQUENCE_MAX_SPAN_SECONDS
            and _time_group_compatible(records[previous_index], records[record_index])
        )
        if can_continue:
            current.append(record_index)
        else:
            if len(current) > 1:
                clusters.append(current)
            current = [record_index]
            current_start = timestamp
        previous_time = timestamp
        previous_index = record_index
    if len(current) > 1:
        clusters.append(current)
    return clusters


def _capture_time(record: dict[str, Any]) -> datetime | None:
    exif = record.get("exif") if isinstance(record.get("exif"), dict) else {}
    for value in (
        record.get("captured_at"),
        exif.get("date_time_original"),
        exif.get("date_time"),
    ):
        parsed = _parse_datetime(value)
        if parsed is not None:
            return parsed
    return None


def _parse_datetime(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    candidates = [text]
    if len(text) >= 10 and text[4] == ":" and text[7] == ":":
        candidates.append(f"{text[:4]}-{text[5:7]}-{text[8:]}")
    for candidate in candidates:
        for fmt in ("%Y:%m:%d %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
            try:
                return datetime.strptime(candidate[:19], fmt)
            except ValueError:
                pass
        try:
            parsed = datetime.fromisoformat(candidate)
        except ValueError:
            continue
        return parsed.replace(tzinfo=None)
    return None


def _time_group_compatible(left: dict[str, Any], right: dict[str, Any]) -> bool:
    if _parent_dir(left) != _parent_dir(right):
        return False
    left_camera = _camera_identity(left)
    right_camera = _camera_identity(right)
    if left_camera and right_camera and left_camera != right_camera:
        return False
    return True


def _parent_dir(record: dict[str, Any]) -> str:
    return str(Path(str(record.get("path") or record.get("filename") or "")).parent).lower()


def _camera_identity(record: dict[str, Any]) -> str:
    exif = record.get("exif") if isinstance(record.get("exif"), dict) else {}
    parts = [str(exif.get(key) or "").strip().lower() for key in ("camera_make", "camera_model")]
    return "|".join(part for part in parts if part)


def _group_basis(group: list[dict[str, Any]], *, threshold: int) -> str:
    has_visual = False
    has_time = False
    for left_index, left in enumerate(group):
        for right in group[left_index + 1 :]:
            if _can_group(left, right, threshold=threshold):
                has_visual = True
            left_time = _capture_time(left)
            right_time = _capture_time(right)
            if (
                left_time is not None
                and right_time is not None
                and abs((left_time - right_time).total_seconds()) <= TIME_SEQUENCE_MAX_SPAN_SECONDS
                and _time_group_compatible(left, right)
            ):
                has_time = True
    if has_visual and has_time:
        return "visual_time"
    if has_time:
        return "time"
    if has_visual:
        return "visual"
    return "single"


def _group_time_span_seconds(group: list[dict[str, Any]]) -> float | None:
    timestamps = [_capture_time(record) for record in group]
    timestamps = [timestamp for timestamp in timestamps if timestamp is not None]
    if len(timestamps) < 2:
        return None
    return (max(timestamps) - min(timestamps)).total_seconds()


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


def _score(record: dict[str, Any], key: str) -> float:
    try:
        return float(record.get(key) or 0.0)
    except (TypeError, ValueError):
        return 0.0


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


def _scene_signature_distance(record: dict[str, Any], representative: dict[str, Any]) -> float | None:
    left = str(record.get("visual_scene_signature") or "")
    right = str(representative.get("visual_scene_signature") or "")
    if not left or not right or len(left) != len(right) or len(left) % 2:
        return None
    try:
        values_left = [int(left[index : index + 2], 16) for index in range(0, len(left), 2)]
        values_right = [int(right[index : index + 2], 16) for index in range(0, len(right), 2)]
    except ValueError:
        return None
    return sum(abs(a - b) for a, b in zip(values_left, values_right, strict=True)) / len(values_left)


def _sequence_distance(record: dict[str, Any], representative: dict[str, Any]) -> int | None:
    left = _trailing_number(record)
    right = _trailing_number(representative)
    if left is None or right is None:
        return None
    return abs(left - right)


def _trailing_number(record: dict[str, Any]) -> int | None:
    source = str(record.get("filename") or Path(str(record.get("path", ""))).stem)
    digits = ""
    for char in reversed(Path(source).stem):
        if not char.isdigit():
            break
        digits = char + digits
    return int(digits) if digits else None

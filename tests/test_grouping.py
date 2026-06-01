from __future__ import annotations

from lumasift.analysis.grouping import apply_similarity_groups


def _record(name: str, hash_value: str, score: float) -> dict:
    return {
        "filename": name,
        "path": f"/photos/{name}",
        "visual_hash": hash_value,
        "visual_scene_signature": "80" * 64,
        "visual_color": "120,112,108",
        "width": 4000,
        "height": 6000,
        "local_metrics": {"brightness": 118},
        "final_selection_score": score,
    }


def test_scene_sequence_groups_related_frames_beyond_near_duplicates() -> None:
    records = [
        _record("DSC09892.ARW", "0000000000000000", 76),
        _record("DSC09894.ARW", "000000000000ffff", 75),
        _record("DSC09893.ARW", "0000000000000fff", 66.8),
        _record("DSC09895.ARW", "00000000000000ff", 66.7),
        _record("DSC09896.ARW", "000000000000f0ff", 52.0),
        _record("DSC10020.ARW", "ffffffffffffffff", 64),
    ]

    grouped = apply_similarity_groups(records)
    first_group = [record for record in grouped if record["group_id"] == grouped[0]["group_id"]]
    outsider = next(record for record in grouped if record["filename"] == "DSC10020.ARW")

    assert len(first_group) == 5
    assert outsider["group_size"] == 1
    assert first_group[0]["group_size"] == 5
    assert next(record for record in first_group if record["is_group_best"])["filename"] == "DSC09892.ARW"
    assert {record["group_review_role"] for record in first_group} >= {"best", "moment_risk", "similar_non_best"}
    assert any(record["group_moment_risk"] for record in first_group if not record["is_group_best"])


def test_exact_visual_duplicate_does_not_consume_moment_risk_review_slot() -> None:
    records = [
        _record("DSC01001.ARW", "0000000000000000", 76),
        _record("DSC01001_COPY.ARW", "0000000000000000", 75.9),
    ]

    grouped = apply_similarity_groups(records)
    duplicate = next(record for record in grouped if not record["is_group_best"])

    assert duplicate["group_size"] == 2
    assert duplicate["group_review_role"] == "similar_non_best"
    assert duplicate["group_moment_risk"] is False


def test_user_keep_priority_can_win_group_without_changing_model_score() -> None:
    records = [
        _record("DSC01001.ARW", "0000000000000000", 76),
        _record("DSC01002.ARW", "00000000000000ff", 75),
    ]
    records[1]["user_label"] = "keep"
    records[1]["user_feedback_priority"] = 2

    grouped = apply_similarity_groups(records)
    best = next(record for record in grouped if record["is_group_best"])

    assert best["filename"] == "DSC01002.ARW"
    assert best["final_selection_score"] == 75


def test_capture_time_groups_burst_frames_even_when_visual_hashes_differ() -> None:
    records = [
        _record("DSC02001.ARW", "0000000000000000", 74),
        _record("DSC02002.ARW", "ffffffffffffffff", 77),
        _record("DSC02020.ARW", "1234567890abcdef", 70),
    ]
    records[1]["visual_scene_signature"] = "ff" * 64
    records[1]["visual_color"] = "20,30,220"
    records[2]["visual_scene_signature"] = "44" * 64
    records[0]["exif"] = {"date_time_original": "2026:05:19 10:00:00", "camera_model": "X-T5"}
    records[1]["exif"] = {"date_time_original": "2026:05:19 10:00:05", "camera_model": "X-T5"}
    records[2]["exif"] = {"date_time_original": "2026:05:19 10:01:10", "camera_model": "X-T5"}

    grouped = apply_similarity_groups(records)
    time_group = [record for record in grouped if record["group_id"] == grouped[0]["group_id"]]
    outsider = next(record for record in grouped if record["filename"] == "DSC02020.ARW")

    assert len(time_group) == 2
    assert {record["group_basis"] for record in time_group} == {"time"}
    assert time_group[0]["group_time_span_seconds"] == 5
    assert next(record for record in time_group if record["is_group_best"])["filename"] == "DSC02002.ARW"
    assert outsider["group_size"] == 1


def test_capture_time_grouping_does_not_cross_camera_bodies() -> None:
    records = [
        _record("A0001.ARW", "0000000000000000", 74),
        _record("B0001.ARW", "ffffffffffffffff", 77),
    ]
    records[1]["visual_scene_signature"] = "ff" * 64
    records[1]["visual_color"] = "20,30,220"
    records[0]["exif"] = {"date_time_original": "2026:05:19 10:00:00", "camera_make": "Nikon", "camera_model": "Zf"}
    records[1]["exif"] = {"date_time_original": "2026:05:19 10:00:04", "camera_make": "Fuji", "camera_model": "X-T5"}

    grouped = apply_similarity_groups(records)

    assert all(record["group_size"] == 1 for record in grouped)

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

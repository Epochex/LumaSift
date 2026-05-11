from __future__ import annotations


def rank_records(records: list[dict]) -> list[dict]:
    ranked = sorted(records, key=lambda item: float(item.get("final_selection_score", 0.0)), reverse=True)
    for index, item in enumerate(ranked, start=1):
        item["rank"] = index
    return ranked

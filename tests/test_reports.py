import json
from pathlib import Path

from PIL import Image

from lumasift.reports.contact_sheet import _caption_lines, write_contact_sheet
from lumasift.reports.csv_report import write_csv_report
from lumasift.reports.json_report import write_json_report


def test_report_writers(tmp_path: Path) -> None:
    records = [
        {
            "rank": 1,
            "filename": "a.jpg",
            "final_selection_score": 77.7,
            "positive_reasons": ["x"],
            "story_interpretation": "具体街头关系成立。",
            "visible_evidence": ["行人和车流形成关系"],
        }
    ]
    csv_path = tmp_path / "report.csv"
    json_path = tmp_path / "report.json"

    write_csv_report(csv_path, records)
    write_json_report(json_path, {"records": records})

    assert "a.jpg" in csv_path.read_text(encoding="utf-8-sig")
    assert "story_interpretation" in csv_path.read_text(encoding="utf-8-sig")
    assert "具体街头关系成立" in csv_path.read_text(encoding="utf-8-sig")
    assert json.loads(json_path.read_text(encoding="utf-8"))["records"][0]["rank"] == 1


def test_contact_sheet_caption_includes_culling_context() -> None:
    record = {
        "rank": 3,
        "filename": "crosswalk_candidate.jpg",
        "final_selection_score": 81.25,
        "category": "strong_edit_candidate",
        "positive_reasons": ["Gesture and layered street tension stand out."],
        "recommended_style": "high_contrast_mono",
    }

    caption = "\n".join(_caption_lines(record))

    assert "#3  score 81.2" in caption
    assert "strong_edit_candidate" in caption
    assert "crosswalk_candidate.jpg" in caption
    assert "why: Gesture and layered street" in caption
    assert "style: high_contrast_mono" in caption


def test_contact_sheet_caption_prefers_story_evidence() -> None:
    record = {
        "rank": 2,
        "filename": "street_frame.jpg",
        "final_selection_score": 84.0,
        "category": "story_candidate",
        "why_this_frame": "This frame preserves the pedestrian gap before the car blocks it.",
        "positive_reasons": ["Generic fallback reason."],
        "recommended_style": "muted_humanistic_color",
    }

    caption = "\n".join(_caption_lines(record))

    assert "why: This frame preserves" in caption
    assert "Generic fallback" not in caption


def test_contact_sheet_writes_ranked_photo_sheet(tmp_path: Path) -> None:
    image_path = tmp_path / "candidate.jpg"
    Image.new("RGB", (120, 80), (80, 90, 100)).save(image_path)
    sheet_path = tmp_path / "sheet.jpg"

    write_contact_sheet(
        sheet_path,
        [
            {
                "path": str(image_path),
                "rank": 1,
                "filename": image_path.name,
                "final_selection_score": 76.0,
                "category": "story_candidate",
                "positive_reasons": ["Clean silhouette with recoverable tone."],
                "recommended_style": "natural_color",
            }
        ],
        columns=1,
    )

    with Image.open(sheet_path) as sheet:
        assert sheet.size == (260, 310)

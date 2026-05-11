import json
from pathlib import Path

from lumasift.reports.csv_report import write_csv_report
from lumasift.reports.json_report import write_json_report


def test_report_writers(tmp_path: Path) -> None:
    records = [{"rank": 1, "filename": "a.jpg", "final_selection_score": 77.7, "positive_reasons": ["x"]}]
    csv_path = tmp_path / "report.csv"
    json_path = tmp_path / "report.json"

    write_csv_report(csv_path, records)
    write_json_report(json_path, {"records": records})

    assert "a.jpg" in csv_path.read_text(encoding="utf-8-sig")
    assert json.loads(json_path.read_text(encoding="utf-8"))["records"][0]["rank"] == 1

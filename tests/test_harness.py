import json
from pathlib import Path

from PIL import Image

from lumasift.app.main import build_parser
from lumasift.core.config import Settings
from lumasift.core.harness import LumaSiftHarness


def test_harness_runs_local_only(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    Image.new("RGB", (32, 32), color=(200, 40, 40)).save(input_dir / "red.jpg")

    settings = Settings(input_dir=input_dir, output_dir=output_dir, ai_mode="local_only")
    result = LumaSiftHarness(settings=settings, run_id="test-run").run()

    assert result.summary["scanned"] == 1
    assert result.report_csv.exists()
    assert result.report_json.exists()
    assert (output_dir / "runs" / "test-run" / "events.jsonl").exists()


def test_harness_respects_limit(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    for index in range(3):
        Image.new("RGB", (32, 32), color=(200, 40 + index, 40)).save(input_dir / f"{index}.jpg")

    settings = Settings(input_dir=input_dir, output_dir=output_dir, ai_mode="local_only", limit=2)
    result = LumaSiftHarness(settings=settings, run_id="limit-run").run()
    report = json.loads(result.report_json.read_text(encoding="utf-8"))

    assert result.summary["scanned"] == 2
    assert result.summary["processed"] == 2
    assert len(report["records"]) == 2


def test_harness_resume_skips_checkpointed_prefix(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    for index in range(3):
        Image.new("RGB", (32, 32), color=(200, 40 + index, 40)).save(input_dir / f"{index}.jpg")

    first_settings = Settings(input_dir=input_dir, output_dir=output_dir, ai_mode="local_only", limit=1)
    LumaSiftHarness(settings=first_settings, run_id="resume-run").run()

    resume_settings = Settings(input_dir=input_dir, output_dir=output_dir, ai_mode="local_only", limit=3, resume=True)
    result = LumaSiftHarness(settings=resume_settings, run_id="resume-run").run()
    report = json.loads(result.report_json.read_text(encoding="utf-8"))

    assert result.summary["scanned"] == 3
    assert result.summary["processed"] == 2
    assert sorted(record["filename"] for record in report["records"]) == ["1.jpg", "2.jpg"]


def test_cli_parses_limit_and_resume() -> None:
    args = build_parser().parse_args(
        [
            "--input",
            "D:\\DCIM",
            "--limit",
            "12",
            "--run-id",
            "real-run",
            "--selected-ranks",
            "1,3-4",
            "--resume",
        ]
    )

    assert args.input == Path("D:\\DCIM")
    assert args.limit == 12
    assert args.run_id == "real-run"
    assert args.selected_ranks == "1,3-4"
    assert args.resume is True


def test_harness_writes_selected_editing_advice(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    Image.new("RGB", (32, 32), color=(200, 40, 40)).save(input_dir / "red.jpg")

    settings = Settings(
        input_dir=input_dir,
        output_dir=output_dir,
        ai_mode="local_only",
        selected_ranks="1",
    )
    LumaSiftHarness(settings=settings, run_id="selected-run").run()

    assert (output_dir / "selected_editing_advice.json").exists()
    assert "Rank 1" in (output_dir / "selected_editing_advice.md").read_text(encoding="utf-8")

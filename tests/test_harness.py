from pathlib import Path

from PIL import Image

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

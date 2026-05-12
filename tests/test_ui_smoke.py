from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def test_ui_smoke_script_runs(tmp_path: Path) -> None:
    env = os.environ.copy()
    env["QT_QPA_PLATFORM"] = "offscreen"
    result = subprocess.run(
        [
            sys.executable,
            "scripts/ui_smoke.py",
            "--output",
            str(tmp_path / "ui_smoke"),
            "--records",
            "6",
            "--language",
            "en",
        ],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        text=True,
        capture_output=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr + result.stdout
    assert (tmp_path / "ui_smoke" / "ui_smoke_report.json").exists()
    assert (tmp_path / "ui_smoke" / "setup_expanded.png").exists()
    assert (tmp_path / "ui_smoke" / "review_with_records.png").exists()

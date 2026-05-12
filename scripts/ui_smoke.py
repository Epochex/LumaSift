from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "outputs" / "ui_smoke"


@dataclass
class Snapshot:
    name: str
    path: str
    width: int
    height: int
    checks: list[dict[str, Any]]


def main() -> int:
    parser = argparse.ArgumentParser(description="Run LumaSift desktop UI smoke checks and screenshots.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--width", type=int, default=1500)
    parser.add_argument("--height", type=int, default=760)
    parser.add_argument("--language", choices=["zh", "en"], default="zh")
    parser.add_argument("--records", type=int, default=24)
    args = parser.parse_args()

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    args.output.mkdir(parents=True, exist_ok=True)

    from PySide6.QtCore import QEventLoop, QTimer, Qt
    from PySide6.QtWidgets import QApplication

    from lumasift.app.desktop import LumaSiftWindow

    app = QApplication.instance() or QApplication([])
    window = LumaSiftWindow()
    window.resize(args.width, args.height)
    window.output_dir = args.output / "app_output"
    window.output_dir.mkdir(parents=True, exist_ok=True)
    window.language = args.language
    window._retranslate_ui()
    window.show()
    app.processEvents()

    snapshots: list[Snapshot] = []
    snapshots.append(capture(window, args.output, "setup_collapsed", setup_collapsed_checks(window)))

    window._exit_review_mode(show_advanced=True)
    app.processEvents()
    snapshots.append(capture(window, args.output, "setup_expanded", setup_expanded_checks(window)))

    records = make_records(args.output / "synthetic_photos", count=args.records)
    window.records = records
    window._merge_user_labels()
    window._reset_filter_combos()
    window._populate_records()
    first_index = window.photo_model.index(0, 0) if window.photo_model else None
    if first_index and first_index.isValid():
        window.photo_list.selectionModel().select(first_index, window.photo_list.selectionModel().SelectionFlag.Select)
        window._show_selected_detail()
    window._enter_review_mode({"scanned": len(records), "processed": len(records), "failed": 0})
    app.processEvents()
    snapshots.append(capture(window, args.output, "review_with_records", review_checks(window)))

    drain_background_threads(app, window, QEventLoop, QTimer)
    window.close()
    app.processEvents()

    failures = [check for snap in snapshots for check in snap.checks if not check["ok"]]
    report = {
        "schema": "lumasift.ui_smoke.v1",
        "output_dir": str(args.output.resolve()),
        "window": {"width": args.width, "height": args.height, "language": args.language},
        "snapshots": [asdict(snapshot) for snapshot in snapshots],
        "summary": {"passed": len(failures) == 0, "failure_count": len(failures), "failures": failures},
    }
    json_path = args.output / "ui_smoke_report.json"
    md_path = args.output / "ui_smoke_report.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    print(f"UI smoke report: {json_path}")
    print(f"UI smoke markdown: {md_path}")
    if failures:
        for failure in failures:
            print(f"FAIL {failure['name']}: {failure['detail']}", file=sys.stderr)
        return 1
    return 0


def make_records(photo_dir: Path, *, count: int) -> list[dict[str, Any]]:
    photo_dir.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    categories = ["portfolio_candidate", "strong_edit_candidate", "technically_weak_but_interesting", "ordinary_record"]
    styles = ["high_contrast_bw", "natural_editorial", "cold_urban", "soft_documentary_color"]
    for index in range(count):
        path = photo_dir / f"smoke_{index + 1:03d}.jpg"
        create_synthetic_photo(path, index)
        score = 82.0 - index * 1.35
        records.append(
            {
                "rank": index + 1,
                "path": str(path),
                "filename": path.name,
                "category": categories[index % len(categories)],
                "recommended_style": styles[index % len(styles)],
                "user_label": "unlabeled",
                "final_selection_score": max(score, 35.0),
                "street_documentary_potential_score": max(score - 4, 30.0),
                "composition_score": max(score - 8, 25.0),
                "editability_score": max(score - 6, 25.0),
                "story_interpretation": "Synthetic UI smoke record for checking review density and detail hierarchy.",
                "best_editing_direction": "Preserve the humanistic read and increase local contrast without over-cleaning.",
                "crop_strategy": "Keep the subject relationship readable; avoid over-tight cropping.",
                "positive_reasons": ["clear subject relationship", "usable story signal"],
                "negative_reasons": ["watch edge distractions"],
                "specific_edit_parameters": {
                    "exposure": "+0.15",
                    "contrast": "+12",
                    "highlights": "-20",
                    "shadows": "+10",
                },
            }
        )
    return records


def create_synthetic_photo(path: Path, index: int) -> None:
    width, height = 360, 260
    base = (28 + index * 9) % 140
    image = Image.new("RGB", (width, height), (base, base + 24, base + 38))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, int(height * 0.68), width, height), fill=(35, 38, 42))
    draw.rectangle((30 + (index % 5) * 12, 40, 180, 190), outline=(210, 218, 226), width=3)
    draw.ellipse((205, 95, 245, 135), fill=(230, 230, 210))
    draw.rectangle((218, 135, 233, 210), fill=(50, 50, 55))
    draw.line((0, 60 + index % 40, width, 120 + index % 35), fill=(170, 180, 190), width=2)
    image.save(path, quality=88)


def capture(window: Any, output_dir: Path, name: str, checks: list[dict[str, Any]]) -> Snapshot:
    path = output_dir / f"{name}.png"
    pixmap = window.grab()
    pixmap.save(str(path))
    checks.append(check_file_nonempty(path, f"{name}_screenshot"))
    return Snapshot(name=name, path=str(path.resolve()), width=pixmap.width(), height=pixmap.height(), checks=checks)


def setup_collapsed_checks(window: Any) -> list[dict[str, Any]]:
    return [
        check_visible(window.controls_frame, "controls_visible"),
        check_not_visible(window.advanced_panel, "advanced_collapsed_by_default"),
        check_min_size(window.progress, "progress_bar_height", min_height=16),
        check_min_size(window.run_button, "analyze_button_size", min_width=92, min_height=44),
    ]


def setup_expanded_checks(window: Any) -> list[dict[str, Any]]:
    checks = [
        check_visible(window.advanced_panel, "advanced_visible"),
        check_min_size(window.advanced_panel, "advanced_panel_height", min_height=150),
        check_min_size(window.api_key_edit, "api_key_field_height", min_height=32),
        check_min_size(window.show_key_checkbox, "show_key_checkbox_height", min_height=20),
        check_min_size(window.save_keys_checkbox, "save_keys_checkbox_height", min_height=20),
    ]
    for name in ("mode_combo", "limit_spin", "top_n_spin", "selected_top_spin", "display_limit_spin"):
        checks.append(check_min_size(getattr(window, name), f"{name}_readable", min_width=110, min_height=32))
    return checks


def review_checks(window: Any) -> list[dict[str, Any]]:
    return [
        check_visible(window.review_bar, "review_bar_visible"),
        check_not_visible(window.header_frame, "header_hidden_in_review"),
        check_not_visible(window.workflow_frame, "workflow_hidden_in_review"),
        check_not_visible(window.controls_frame, "setup_controls_hidden_in_review"),
        check_min_size(window.photo_list, "photo_grid_size", min_width=520, min_height=320),
        check_min_size(window.detail_panel, "detail_panel_size", min_width=400, min_height=320),
        check_min_size(window.generate_advice_button, "editing_plan_button_size", min_width=120, min_height=34),
        check_value(window.photo_model.rowCount() >= 1, "records_rendered", f"row_count={window.photo_model.rowCount()}"),
    ]


def drain_background_threads(app: Any, window: Any, event_loop_type: Any, timer_type: Any) -> None:
    """Give preview/thumbnail workers a short deterministic window to finish before teardown."""
    deadline_ms = 2500
    elapsed = 0
    while getattr(window, "thumbnail_thread", None) is not None and elapsed < deadline_ms:
        app.processEvents()
        loop = event_loop_type()
        timer_type.singleShot(50, loop.quit)
        loop.exec()
        elapsed += 50
    if getattr(window, "thumbnail_thread", None) is not None:
        window._stop_thumbnail_worker()


def check_visible(widget: Any, name: str) -> dict[str, Any]:
    return check_value(widget.isVisible(), name, geometry_detail(widget))


def check_not_visible(widget: Any, name: str) -> dict[str, Any]:
    return check_value(not widget.isVisible(), name, geometry_detail(widget))


def check_min_size(widget: Any, name: str, *, min_width: int = 0, min_height: int = 0) -> dict[str, Any]:
    geometry = widget.geometry()
    ok = geometry.width() >= min_width and geometry.height() >= min_height
    return check_value(ok, name, f"{geometry.width()}x{geometry.height()} min={min_width}x{min_height}")


def check_file_nonempty(path: Path, name: str) -> dict[str, Any]:
    return check_value(path.exists() and path.stat().st_size > 0, name, f"{path} bytes={path.stat().st_size if path.exists() else 0}")


def check_value(ok: bool, name: str, detail: str) -> dict[str, Any]:
    return {"name": name, "ok": bool(ok), "detail": detail}


def geometry_detail(widget: Any) -> str:
    geometry = widget.geometry()
    return f"visible={widget.isVisible()} geometry={geometry.x()},{geometry.y()},{geometry.width()}x{geometry.height()}"


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# LumaSift UI Smoke Report",
        "",
        f"- Passed: `{report['summary']['passed']}`",
        f"- Failures: `{report['summary']['failure_count']}`",
        f"- Output: `{report['output_dir']}`",
        "",
        "## Snapshots",
    ]
    for snapshot in report["snapshots"]:
        lines.append(f"- `{snapshot['name']}`: `{snapshot['path']}` ({snapshot['width']}x{snapshot['height']})")
    lines.append("")
    lines.append("## Checks")
    for snapshot in report["snapshots"]:
        lines.append(f"### {snapshot['name']}")
        for check in snapshot["checks"]:
            mark = "PASS" if check["ok"] else "FAIL"
            lines.append(f"- {mark} `{check['name']}`: {check['detail']}")
    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())

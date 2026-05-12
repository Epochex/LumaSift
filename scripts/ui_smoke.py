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

    from PySide6.QtCore import QEventLoop, QItemSelectionModel, QTimer, Qt
    from PySide6.QtWidgets import QApplication

    from lumasift.app.desktop import LumaSiftWindow

    app = QApplication.instance() or QApplication([])
    window = LumaSiftWindow()
    window.resize(args.width, args.height)
    window.output_dir = args.output / "app_output"
    window.output_dir.mkdir(parents=True, exist_ok=True)
    window.language = args.language
    window._retranslate_ui()
    window._queue_visible_thumbnails = lambda: None
    window.show()
    app.processEvents()

    snapshots: list[Snapshot] = []
    snapshots.append(capture(window, args.output, "setup_collapsed", setup_collapsed_checks(window)))

    window._exit_review_mode(show_advanced=True)
    app.processEvents()
    snapshots.append(capture(window, args.output, "setup_expanded", setup_expanded_checks(window)))

    window._analysis_qwen_event({"type": "qwen_queue_prepared", "total": 5, "model": "qwen3.6-plus"})
    window._analysis_qwen_event({"type": "qwen_candidate_running", "filename": "smoke_001.jpg"})
    window._analysis_qwen_event({"type": "qwen_candidate_finished", "status": "cache-hit"})
    window._analysis_qwen_event({"type": "qwen_candidate_failed"})
    window._analysis_qwen_event({"type": "qwen_client_event", "client_event": {"type": "retrying"}})
    app.processEvents()
    snapshots.append(capture(window, args.output, "qwen_queue_status", qwen_queue_checks(window)))
    window.qwen_queue_label.setVisible(False)

    records = make_records(args.output / "synthetic_photos", count=args.records)
    window.records = records
    window._merge_user_labels()
    window._reset_filter_combos()
    window._populate_records()
    label_checks = exercise_label_workflow(window, QItemSelectionModel)
    first_index = window.photo_model.index(0, 0) if window.photo_model else None
    if first_index and first_index.isValid():
        window.photo_list.selectionModel().select(first_index, QItemSelectionModel.SelectionFlag.Select)
        window._show_selected_detail()
    window._enter_review_mode({"scanned": len(records), "processed": len(records), "failed": 0})
    app.processEvents()
    snapshots.append(capture(window, args.output, "review_with_records", review_checks(window) + label_checks))

    window._generate_selected_advice()
    app.processEvents()
    snapshots.append(capture(window, args.output, "editing_plan", editing_plan_checks(window)))

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


def exercise_label_workflow(window: Any, selection_model_type: Any) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    select_rows(window, [0, 1], selection_model_type)
    window._mark_selected("keep")
    checks.append(check_value(count_label(window, "keep") >= 2, "multi_select_keep_marked", f"keep={count_label(window, 'keep')}"))

    set_combo_data(window.label_filter, "keep")
    window._populate_records()
    checks.append(check_value(window.photo_model.rowCount() >= 2, "keep_filter_visible", f"rows={window.photo_model.rowCount()}"))
    checks.append(check_value(all_visible_labels(window, {"keep"}), "keep_filter_labels_clean", visible_label_detail(window)))

    select_rows(window, [0], selection_model_type)
    window._mark_selected("reject")
    checks.append(check_value(all_visible_labels(window, {"keep"}), "filtered_mark_repopulates", visible_label_detail(window)))

    set_combo_data(window.label_filter, "reject")
    window._populate_records()
    checks.append(check_value(count_visible_label(window, "reject") >= 1, "reject_filter_after_relabel", visible_label_detail(window)))

    set_combo_data(window.label_filter, "all")
    window._populate_records()
    select_rows(window, [0], selection_model_type)
    checks.append(check_value(bool(window._selected_record_indexes()), "selection_restored_after_filter_reset", f"selected={len(window._selected_record_indexes())}"))
    return checks


def select_rows(window: Any, rows: list[int], selection_model_type: Any) -> None:
    if window.photo_model is None or window.photo_list.selectionModel() is None:
        return
    selection_model = window.photo_list.selectionModel()
    selection_model.clearSelection()
    for row in rows:
        if row < 0 or row >= window.photo_model.rowCount():
            continue
        index = window.photo_model.index(row, 0)
        selection_model.select(
            index,
            selection_model_type.SelectionFlag.Select | selection_model_type.SelectionFlag.Rows,
        )
    window._show_selected_detail()


def set_combo_data(combo: Any, value: str) -> None:
    index = combo.findData(value)
    combo.setCurrentIndex(index if index >= 0 else 0)


def count_label(window: Any, label: str) -> int:
    return sum(1 for record in window.records if record.get("user_label") == label)


def count_visible_label(window: Any, label: str) -> int:
    return sum(1 for record in getattr(window.photo_model, "records", []) if record.get("user_label") == label)


def all_visible_labels(window: Any, allowed: set[str]) -> bool:
    records = getattr(window.photo_model, "records", [])
    return bool(records) and all((record.get("user_label") or "unlabeled") in allowed for record in records)


def visible_label_detail(window: Any) -> str:
    labels = [(record.get("filename"), record.get("user_label") or "unlabeled") for record in getattr(window.photo_model, "records", [])[:8]]
    return f"labels={labels}"


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


def qwen_queue_checks(window: Any) -> list[dict[str, Any]]:
    plain_text = window.qwen_queue_label.text()
    return [
        check_visible(window.qwen_queue_label, "qwen_queue_visible"),
        check_value("qwen3.6-plus" in plain_text, "qwen_queue_model_visible", plain_text),
        check_value(("缓存" in plain_text or "cache" in plain_text), "qwen_queue_cache_visible", plain_text),
        check_value(("失败" in plain_text or "failed" in plain_text), "qwen_queue_failed_visible", plain_text),
        check_value(("重试" in plain_text or "retrying" in plain_text), "qwen_queue_retry_visible", plain_text),
    ]


def review_checks(window: Any) -> list[dict[str, Any]]:
    plain_text = window.detail_text.toPlainText()
    return [
        check_visible(window.review_bar, "review_bar_visible"),
        check_not_visible(window.header_frame, "header_hidden_in_review"),
        check_not_visible(window.workflow_frame, "workflow_hidden_in_review"),
        check_not_visible(window.controls_frame, "setup_controls_hidden_in_review"),
        check_min_size(window.photo_list, "photo_grid_size", min_width=520, min_height=320),
        check_min_size(window.detail_panel, "detail_panel_size", min_width=540, min_height=320),
        check_min_size(window.generate_advice_button, "editing_plan_button_size", min_width=120, min_height=34),
        check_value(window.photo_model.rowCount() >= 1, "records_rendered", f"row_count={window.photo_model.rowCount()}"),
        check_value("Not available in local_only mode" not in plain_text, "review_no_english_local_fallback", "local fallback localized"),
        check_value("Run qwen_vision mode" not in plain_text, "review_no_english_qwen_fallback", "qwen fallback localized"),
    ]


def editing_plan_checks(window: Any) -> list[dict[str, Any]]:
    plain_text = window.detail_text.toPlainText()
    expected_title = "照片的修图方案" if window.language == "zh" else "Editing plan"
    forbidden_default = "# Selected Editing Advice" if window.language == "zh" else "选中照片修图方案"
    return [
        check_min_size(window.detail_panel, "editing_plan_panel_size", min_width=540, min_height=320),
        check_value(expected_title in plain_text, "editing_plan_language", f"contains={expected_title!r}"),
        check_value(forbidden_default not in plain_text, "editing_plan_not_wrong_language", f"forbidden={forbidden_default!r}"),
        check_value("Lightroom" in plain_text, "editing_plan_parameters_visible", "Lightroom section visible"),
        check_file_nonempty(window.output_dir / "selected_editing_advice.md", "editing_plan_markdown_written"),
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

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from lumasift.analysis.editing_advice import build_selected_editing_advice
from lumasift.analysis.local_story import analyze_local_story_proxy
from lumasift.analysis.qwen_story import QWEN_STORY_PROMPT, QWEN_STORY_PROMPT_VERSION, merge_qwen_story_analysis
from lumasift.analysis.scoring import rank_records
from lumasift.core.config import Settings
from lumasift.core.keyring import ApiKeyRing
from lumasift.core.manifest import discover_photos
from lumasift.core.run_state import RunState
from lumasift.io.image_loader import load_image
from lumasift.io.preview import create_jpeg_preview
from lumasift.analysis.qwen_client import QwenVisionClient
from lumasift.reports.contact_sheet import write_contact_sheet
from lumasift.reports.csv_report import write_csv_report
from lumasift.reports.json_report import write_json_report
from lumasift.reports.markdown_report import write_selected_editing_advice_markdown


@dataclass
class HarnessResult:
    summary: dict[str, int | str]
    report_csv: Path
    report_json: Path
    run_dir: Path

    def summary_text(self) -> str:
        lines = [
            "LumaSift run complete",
            f"run_id: {self.summary['run_id']}",
            f"scanned: {self.summary['scanned']}",
            f"processed: {self.summary['processed']}",
            f"failed: {self.summary['failed']}",
            f"csv: {self.report_csv}",
            f"json: {self.report_json}",
            f"run_dir: {self.run_dir}",
        ]
        return "\n".join(lines)


class LumaSiftHarness:
    def __init__(self, settings: Settings, run_id: str | None = None) -> None:
        self.settings = settings
        self.settings.ensure_dirs()
        self.run_id = run_id or time.strftime("%Y%m%d-%H%M%S")
        self.run_dir = self.settings.output_dir / "runs" / self.run_id
        self.state = RunState(self.run_dir)

    def run(self) -> HarnessResult:
        self.state.append_event("run_started", mode=self.settings.ai_mode, limit=self.settings.limit)
        photos = discover_photos(self.settings.input_dir, self.settings.supported_extensions, limit=self.settings.limit)
        self.state.append_event(
            "manifest_created",
            count=len(photos),
            input_dir=str(self.settings.input_dir),
            limit=self.settings.limit,
        )

        resume_from_index = 0
        if self.settings.resume:
            checkpoint = self.state.load_checkpoint()
            if checkpoint is None:
                self.state.append_event("resume_requested_but_no_checkpoint")
            else:
                resume_from_index = max(0, int(checkpoint.get("last_index", 0)))
                self.state.append_event("run_resumed", last_index=resume_from_index)

        records: list[dict] = []
        failed = 0
        for index, photo in enumerate(photos, start=1):
            stop_file = self.settings.output_dir / "STOP_LUMASIFT"
            if stop_file.exists():
                self.state.append_event("run_stopped_by_file", stop_file=str(stop_file))
                break
            if index <= resume_from_index:
                continue
            try:
                image = load_image(photo.path)
                record = analyze_local_story_proxy(image)
                records.append(record)
                self.state.append_event("photo_processed", index=index, path=str(photo.path))
            except Exception as exc:  # noqa: BLE001 - batch robustness is the boundary here.
                failed += 1
                records.append(
                    {
                        "path": str(photo.path),
                        "filename": photo.path.name,
                        "errors": [str(exc)],
                        "final_selection_score": 0.0,
                        "category": "failed",
                    }
                )
                self.state.append_event("photo_failed", index=index, path=str(photo.path), error=str(exc))

            self.state.save_checkpoint(
                {
                    "run_id": self.run_id,
                    "last_index": index,
                    "processed": len(records) - failed,
                    "failed": failed,
                }
            )

        ranked = rank_records(records)
        if self.settings.ai_mode == "qwen_vision":
            ranked = self._apply_qwen_vision(ranked)

        report_csv = self.settings.output_dir / "report.csv"
        report_json = self.settings.output_dir / "report.json"
        contact_sheet = self.settings.output_dir / "contact_sheet_top50.jpg"
        selected_advice_json = self.settings.output_dir / "selected_editing_advice.json"
        selected_advice_md = self.settings.output_dir / "selected_editing_advice.md"
        write_csv_report(report_csv, ranked)
        write_json_report(
            report_json,
            {
                "run_id": self.run_id,
                "ai_mode": self.settings.ai_mode,
                "input_dir": str(self.settings.input_dir),
                "records": ranked,
            },
        )
        write_contact_sheet(contact_sheet, ranked[:50])
        if self.settings.selected_ranks or self.settings.selected_paths:
            selected_payload = build_selected_editing_advice(
                ranked,
                selected_ranks=self.settings.selected_ranks,
                selected_paths=self.settings.selected_paths,
            )
            write_json_report(selected_advice_json, selected_payload)
            write_selected_editing_advice_markdown(selected_advice_md, selected_payload)
            self.state.append_event(
                "selected_editing_advice_written",
                count=selected_payload.get("selected_count", 0),
                json=str(selected_advice_json),
                markdown=str(selected_advice_md),
            )

        summary = {
            "run_id": self.run_id,
            "scanned": len(photos),
            "processed": len([item for item in ranked if item.get("category") != "failed"]),
            "failed": failed,
        }
        self.state.append_event("run_completed", **summary)
        return HarnessResult(summary=summary, report_csv=report_csv, report_json=report_json, run_dir=self.run_dir)

    def _apply_qwen_vision(self, ranked: list[dict]) -> list[dict]:
        if not self.settings.vision_api_keys:
            self.state.append_event("qwen_skipped", reason="no_api_keys")
            return ranked

        client = QwenVisionClient(
            base_url=self.settings.vision_api_base_url,
            model=self.settings.vision_model,
            keyring=ApiKeyRing(self.settings.vision_api_keys),
            max_tokens=self.settings.vision_max_tokens,
            timeout_seconds=self.settings.request_timeout_seconds,
        )
        preview_dir = self.settings.output_dir / "previews"
        updated = list(ranked)
        for record in updated[: self.settings.top_n_api_analysis]:
            if record.get("category") == "failed":
                continue
            try:
                preview_path = create_jpeg_preview(Path(record["path"]), preview_dir)
                response = client.analyze_image(
                    preview_path,
                    QWEN_STORY_PROMPT,
                    prompt_version=QWEN_STORY_PROMPT_VERSION,
                )
                merge_qwen_story_analysis(record, response)
                self.state.append_event("qwen_analyzed", path=record["path"])
            except Exception as exc:  # noqa: BLE001 - API failures should not kill local output.
                record.setdefault("errors", []).append(f"qwen_vision_failed: {exc}")
                self.state.append_event("qwen_failed", path=record.get("path"), error=str(exc))
        return rank_records(updated)

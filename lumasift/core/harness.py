from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from lumasift.analysis.editing_advice import build_selected_editing_advice
from lumasift.analysis.local_story import analyze_local_story_proxy
from lumasift.analysis.grouping import apply_similarity_groups, compute_average_color, compute_dhash, compute_scene_signature
from lumasift.analysis.qwen_story import (
    QWEN_STORY_PROMPT_VERSION,
    build_qwen_story_prompt,
    merge_qwen_story_analysis,
    parse_qwen_story_response,
)
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
from lumasift.analysis.user_feedback import apply_user_feedback_fields, normalized_user_label
from lumasift.storage.state_db import LumaSiftStateDb


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
    def __init__(
        self,
        settings: Settings,
        run_id: str | None = None,
        progress_callback: Callable[[str, int, int], None] | None = None,
        event_callback: Callable[[dict], None] | None = None,
        state_db: LumaSiftStateDb | None = None,
    ) -> None:
        self.settings = settings
        self.settings.ensure_dirs()
        self.run_id = run_id or time.strftime("%Y%m%d-%H%M%S")
        self.run_dir = self.settings.output_dir / "runs" / self.run_id
        self.state = RunState(self.run_dir)
        self.progress_callback = progress_callback
        self.event_callback = event_callback
        self.state_db = state_db

    def _progress(self, stage: str, current: int, total: int) -> None:
        if self.progress_callback is not None:
            self.progress_callback(stage, current, total)

    def _event(self, event_type: str, **payload: object) -> None:
        event = {"type": event_type, **payload}
        if self.event_callback is not None:
            self.event_callback(event)

    def run(self) -> HarnessResult:
        self.state.append_event("run_started", mode=self.settings.ai_mode, limit=self.settings.limit)
        photos = discover_photos(self.settings.input_dir, self.settings.supported_extensions, limit=self.settings.limit)
        self._progress("manifest", 0, len(photos))
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
            reusable = self._reusable_manifest_record(photo.path)
            if reusable is not None:
                reusable["manifest_status"] = "reused"
                records.append(reusable)
                self.state.append_event("photo_reused_from_manifest", index=index, path=str(photo.path))
                self.state.save_checkpoint(
                    {
                        "run_id": self.run_id,
                        "last_index": index,
                        "processed": len([item for item in records if item.get("category") != "failed"]),
                        "failed": len([item for item in records if item.get("category") == "failed"]),
                    }
                )
                self._progress("local", index, len(photos))
                continue
            try:
                image = load_image(photo.path)
                record = analyze_local_story_proxy(image)
                try:
                    record["preview_path"] = str(create_jpeg_preview(photo.path, self.settings.output_dir / "manifest_previews", max_side=360))
                except Exception as exc:  # noqa: BLE001 - preview cache failure should not fail local ranking.
                    record.setdefault("errors", []).append(f"manifest_preview_failed: {exc}")
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
            self._progress("local", index, len(photos))

        ranked = self._apply_persisted_user_feedback(rank_records(records))
        self._apply_similarity_grouping(ranked)
        if self.settings.ai_mode == "qwen_vision":
            ranked = self._apply_qwen_vision(ranked)
        ranked = self._apply_persisted_user_feedback(rank_records(ranked))
        self._apply_similarity_grouping(ranked)
        self._persist_manifest_records(ranked)

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

        failed_count = len([item for item in ranked if item.get("category") == "failed"])
        summary = {
            "run_id": self.run_id,
            "scanned": len(photos),
            "processed": len([item for item in ranked if item.get("category") != "failed"]),
            "failed": failed_count,
        }
        self.state.append_event("run_completed", **summary)
        self._progress("done", len(photos), len(photos))
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
            event_callback=lambda event: self._event("qwen_client_event", client_event=event),
            response_validator=lambda response: parse_qwen_story_response(response),
        )
        preview_dir = self.settings.output_dir / "previews"
        updated = list(ranked)
        if not self.settings.qwen_include_rejected:
            for record in updated:
                if normalized_user_label(record.get("user_label")) == "reject":
                    record["qwen_status"] = "skipped_user_reject"
                    record["qwen_skip_reason"] = "user_label_reject"
        if self.settings.qwen_group_winners_only:
            for record in updated:
                if int(record.get("group_size", 1) or 1) > 1 and not bool(record.get("is_group_best")):
                    if bool(record.get("group_moment_risk")):
                        record["qwen_status"] = "queued_moment_risk"
                        record["qwen_skip_reason"] = ""
                    else:
                        record["qwen_status"] = "skipped_similar_group"
                        record["qwen_skip_reason"] = "similar_group_non_winner"
        eligible = [
            record
            for record in updated
            if record.get("category") != "failed"
            and (self.settings.qwen_include_rejected or normalized_user_label(record.get("user_label")) != "reject")
            and (
                not self.settings.qwen_group_winners_only
                or int(record.get("group_size", 1) or 1) <= 1
                or bool(record.get("is_group_best"))
                or bool(record.get("group_moment_risk"))
            )
        ]
        candidates = eligible[: self.settings.top_n_api_analysis]
        candidate_ids = {id(record) for record in candidates}
        for record in eligible:
            if id(record) not in candidate_ids and not record.get("qwen_status"):
                record["qwen_status"] = "not_reviewed"
                record["qwen_skip_reason"] = "outside_qwen_top_n"
        self._event(
            "qwen_queue_prepared",
            total=len(candidates),
            model=self.settings.vision_model,
            base_url=self.settings.vision_api_base_url,
        )
        for record in candidates:
            if record.get("category") != "failed":
                record["qwen_status"] = "queued"
        for qwen_index, record in enumerate(candidates, start=1):
            if record.get("category") == "failed":
                continue
            if self._qwen_cancel_requested():
                self._cancel_pending_qwen_candidates(candidates[qwen_index - 1 :], qwen_index, len(candidates))
                break
            try:
                self._progress("qwen", qwen_index - 1, len(candidates))
                record["qwen_status"] = "running"
                self._event(
                    "qwen_candidate_running",
                    index=qwen_index,
                    total=len(candidates),
                    path=record.get("path"),
                    filename=record.get("filename"),
                )
                preview_path = create_jpeg_preview(Path(record["path"]), preview_dir)
                record["preview_path"] = str(preview_path)
                response = client.analyze_image(
                    preview_path,
                    build_qwen_story_prompt(record),
                    prompt_version=QWEN_STORY_PROMPT_VERSION,
                )
                merge_qwen_story_analysis(record, response)
                status = "cache-hit" if client.last_cache_hit else "done"
                record["qwen_status"] = status
                record["qwen_prompt_version"] = QWEN_STORY_PROMPT_VERSION
                if client.last_cache_key_digest:
                    record["qwen_cache_key"] = client.last_cache_key_digest
                self.state.append_event("qwen_analyzed", path=record["path"])
                self._event(
                    "qwen_candidate_finished",
                    index=qwen_index,
                    total=len(candidates),
                    path=record.get("path"),
                    filename=record.get("filename"),
                    status=status,
                )
            except Exception as exc:  # noqa: BLE001 - API failures should not kill local output.
                record["qwen_status"] = "failed"
                record.setdefault("errors", []).append(f"qwen_vision_failed: {exc}")
                self.state.append_event("qwen_failed", path=record.get("path"), error=str(exc))
                self._event(
                    "qwen_candidate_failed",
                    index=qwen_index,
                    total=len(candidates),
                    path=record.get("path"),
                    filename=record.get("filename"),
                    error=str(exc),
                )
            finally:
                self._progress("qwen", qwen_index, len(candidates))
        return rank_records(updated)

    def _apply_similarity_grouping(self, records: list[dict]) -> None:
        for record in records:
            if record.get("category") == "failed":
                continue
            if not record.get("visual_hash"):
                preview_path = record.get("preview_path") or record.get("path")
                if not preview_path:
                    continue
                try:
                    preview = Path(str(preview_path))
                    record["visual_hash"] = compute_dhash(preview)
                    record["visual_color"] = compute_average_color(preview)
                    record["visual_scene_signature"] = compute_scene_signature(preview)
                except Exception as exc:  # noqa: BLE001 - grouping should never block analysis output.
                    record.setdefault("errors", []).append(f"visual_hash_failed: {exc}")
        apply_similarity_groups([record for record in records if record.get("category") != "failed"])

    def _apply_persisted_user_feedback(self, records: list[dict]) -> list[dict]:
        labels: dict[str, str] = {}
        if self.state_db is not None:
            labels = self.state_db.load_labels(str(record.get("path", "")) for record in records if record.get("path"))
        for record in records:
            path = str(record.get("path", ""))
            normalized = str(Path(path).expanduser().resolve()) if path else ""
            if normalized in labels:
                record["user_label"] = labels[normalized]
            apply_user_feedback_fields(record)
        return records

    def _reusable_manifest_record(self, path: Path) -> dict | None:
        if self.state_db is None:
            return None
        record = self.state_db.reusable_record_for_file(path)
        if record is None:
            return None
        if record.get("category") == "failed":
            return None
        if self.settings.ai_mode == "local_only" and any(record.get(key) for key in ("qwen_model", "qwen_status", "qwen_cache_key")):
            return None
        return record

    def _persist_manifest_records(self, records: list[dict]) -> None:
        if self.state_db is None:
            return
        persisted = 0
        for record in records:
            raw_path = record.get("path")
            if not raw_path:
                continue
            path = Path(str(raw_path))
            try:
                resolved, size_bytes, mtime_ns, identity_hash = self._file_identity(path)
            except OSError as exc:
                self.state.append_event("manifest_photo_identity_failed", path=str(path), error=str(exc))
                continue
            scores = {
                key: record.get(key)
                for key in (
                    "storytelling_score",
                    "human_documentary_value_score",
                    "decisive_moment_score",
                    "emotional_impact_score",
                    "visual_tension_score",
                    "editing_potential_score",
                    "technical_quality_score",
                    "final_selection_score",
                )
                if key in record
            }
            self.state_db.upsert_photo_manifest(
                path=resolved,
                size_bytes=size_bytes,
                mtime_ns=mtime_ns,
                identity_hash=identity_hash,
                preview_path=record.get("preview_path"),
                last_run_id=self.run_id,
                rank=int(record["rank"]) if record.get("rank") is not None else None,
                score=float(record["final_selection_score"]) if record.get("final_selection_score") is not None else None,
                category=str(record.get("category")) if record.get("category") else None,
                technical_quality_score=float(record["technical_quality_score"]) if record.get("technical_quality_score") is not None else None,
                qwen_cache_key=str(record.get("qwen_cache_key")) if record.get("qwen_cache_key") else None,
                visual_hash=str(record.get("visual_hash")) if record.get("visual_hash") else None,
                visual_color=str(record.get("visual_color")) if record.get("visual_color") else None,
                visual_scene_signature=str(record.get("visual_scene_signature")) if record.get("visual_scene_signature") else None,
                group_id=str(record.get("group_id")) if record.get("group_id") else None,
                group_size=int(record["group_size"]) if record.get("group_size") is not None else None,
                group_rank=int(record["group_rank"]) if record.get("group_rank") is not None else None,
                is_group_best=bool(record.get("is_group_best")) if record.get("is_group_best") is not None else None,
                group_best_path=str(record.get("group_best_path")) if record.get("group_best_path") else None,
                group_score_delta=float(record["group_score_delta"]) if record.get("group_score_delta") is not None else None,
                scores=scores,
                record=record,
            )
            persisted += 1
        self.state.append_event("manifest_persisted", count=persisted)

    @staticmethod
    def _file_identity(path: Path) -> tuple[str, int, int, str]:
        resolved = path.resolve()
        stat = resolved.stat()
        digest = hashlib.sha256(f"{resolved}|{stat.st_size}|{stat.st_mtime_ns}".encode("utf-8", errors="ignore")).hexdigest()
        return str(resolved), stat.st_size, stat.st_mtime_ns, digest

    def _qwen_cancel_requested(self) -> bool:
        return (self.settings.output_dir / "STOP_LUMASIFT").exists()

    def _cancel_pending_qwen_candidates(self, pending: list[dict], start_index: int, total: int) -> None:
        cancelled = 0
        for offset, record in enumerate(pending):
            if record.get("category") == "failed":
                continue
            record["qwen_status"] = "cancelled"
            record.setdefault("errors", []).append("qwen_vision_cancelled")
            index = start_index + offset
            cancelled += 1
            self.state.append_event("qwen_cancelled", path=record.get("path"), index=index, total=total)
            self._event(
                "qwen_candidate_cancelled",
                index=index,
                total=total,
                path=record.get("path"),
                filename=record.get("filename"),
            )
        self._event("qwen_queue_cancelled", cancelled=cancelled, total=total)

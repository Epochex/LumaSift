from __future__ import annotations

import argparse
import collections
import getpass
import json
import time
from pathlib import Path
from typing import Any

from lumasift.analysis.qwen_story import is_current_concrete_qwen_review
from lumasift.analysis.scoring import rank_records
from lumasift.core.config import Settings
from lumasift.core.harness import LumaSiftHarness
from lumasift.reports.json_report import write_json_report


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a D:/DCIM Qwen stability probe through LumaSiftHarness.")
    parser.add_argument("--input", default="D:/DCIM")
    parser.add_argument("--top-n", type=int, default=30)
    parser.add_argument("--timeout", type=int, default=90)
    parser.add_argument("--max-retries", type=int, default=1)
    parser.add_argument("--preview-max-side", type=int, default=1280)
    parser.add_argument("--model", default="qwen3-vl-plus")
    parser.add_argument("--base-url", default="https://api.newcoin.top/v1")
    parser.add_argument("--run-id", default="")
    parser.add_argument("--source-report", default="", help="Reuse an existing report.json and rerun only the Qwen stage.")
    args = parser.parse_args()

    api_key = getpass.getpass("Qwen/NewCoin API key: ").strip()
    if not api_key:
        raise SystemExit("API key is required")

    run_id = args.run_id or time.strftime("dcim_qwen_probe_%Y%m%d_%H%M%S")
    output_dir = Path("outputs") / run_id
    stop_file = output_dir / "STOP_LUMASIFT"
    if stop_file.exists():
        stop_file.unlink()

    settings = Settings(
        input_dir=Path(args.input),
        output_dir=output_dir,
        ai_mode="qwen_vision",
        top_n_api_analysis=args.top_n,
        vision_api_base_url=args.base_url,
        vision_model=args.model,
        vision_api_keys=[api_key],
        vision_max_tokens=4096,
        vision_preview_max_side=args.preview_max_side,
        vision_max_retries=args.max_retries,
        request_timeout_seconds=args.timeout,
        qwen_group_winners_only=True,
    )

    def progress(stage: str, current: int, total: int) -> None:
        if stage in {"manifest", "done"} or current == total or current % 100 == 0:
            print(f"PROGRESS {stage} {current}/{total}", flush=True)

    def event(payload: dict[str, Any]) -> None:
        event_type = payload.get("type")
        if event_type == "qwen_queue_prepared":
            print(f"QWEN_QUEUE total={payload.get('total')} model={payload.get('model')}", flush=True)
        elif event_type == "qwen_candidate_running":
            print(f"RUN {payload.get('index')}/{payload.get('total')} {payload.get('filename')}", flush=True)
        elif event_type == "qwen_candidate_finished":
            print(f"DONE {payload.get('index')}/{payload.get('total')} {payload.get('filename')} status={payload.get('status')}", flush=True)
        elif event_type == "qwen_candidate_failed":
            print(
                f"FAIL {payload.get('index')}/{payload.get('total')} {payload.get('filename')} "
                f"kind={payload.get('failure_kind') or 'unknown'} error={str(payload.get('error') or '')[:220]}",
                flush=True,
            )
        elif event_type == "qwen_client_event":
            client_event = payload.get("client_event")
            if isinstance(client_event, dict) and client_event.get("type") == "retrying":
                print(
                    f"CLIENT retrying reason={client_event.get('reason')} "
                    f"model={client_event.get('model')} message={str(client_event.get('message') or '')[:180]}",
                    flush=True,
                )

    harness = LumaSiftHarness(settings=settings, run_id=run_id, progress_callback=progress, event_callback=event)
    if args.source_report:
        source_report = json.loads(Path(args.source_report).read_text(encoding="utf-8"))
        records = [_without_old_qwen_fields(record) for record in source_report.get("records", [])]
        records = rank_records(records)
        harness._apply_similarity_grouping(records)
        updated = harness._apply_qwen_vision(records)
        updated = rank_records(updated)
        harness._apply_similarity_grouping(updated)
        report_path = output_dir / "report.json"
        write_json_report(
            report_path,
            {"run_id": run_id, "ai_mode": settings.ai_mode, "input_dir": str(settings.input_dir), "records": updated},
        )
        result_summary = {
            "run_id": run_id,
            "scanned": len(updated),
            "processed": len([item for item in updated if item.get("category") != "failed"]),
            "failed": len([item for item in updated if item.get("category") == "failed"]),
            "raw_jpeg_pairs": len({item.get("pair_id") for item in updated if item.get("has_raw_jpeg_pair") and item.get("pair_id")}),
        }
        report = {"records": updated}
        report_file = report_path
    else:
        result = harness.run()
        report = json.loads(result.report_json.read_text(encoding="utf-8"))
        result_summary = result.summary
        report_file = result.report_json
    records = report.get("records", [])
    statuses = collections.Counter(str(record.get("qwen_status") or "") for record in records)
    failure_kinds = collections.Counter(str(record.get("qwen_failure_kind") or "") for record in records if record.get("qwen_status") == "failed")
    valid = sum(1 for record in records if is_current_concrete_qwen_review(record))
    print(f"SUMMARY {json.dumps(result_summary, ensure_ascii=False)}", flush=True)
    print(f"QWEN_STATUS {dict(statuses)}", flush=True)
    print(f"QWEN_FAILURE_KIND {dict(failure_kinds)}", flush=True)
    print(f"QWEN_CURRENT_CONCRETE {valid}", flush=True)
    print(f"REPORT {report_file}", flush=True)


def _without_old_qwen_fields(record: dict[str, Any]) -> dict[str, Any]:
    cloned = dict(record)
    for key in (
        "qwen_status",
        "qwen_skip_reason",
        "qwen_failure_kind",
        "qwen_failure_detail",
        "qwen_invalid_response_excerpt",
        "qwen_cache_key",
        "qwen_prompt_version",
        "qwen_model",
        "analysis_source",
        "analysis_quality",
        "professional_review",
        "visible_inventory",
        "visible_evidence",
        "evidence_chain",
        "score_rationales",
        "subject_relationship",
        "decisive_moment_read",
        "moment_status",
        "sequence_comparison",
        "selection_risk",
        "edit_vs_select_warning",
        "why_this_frame",
        "editing_plan",
    ):
        cloned.pop(key, None)
    return cloned


if __name__ == "__main__":
    main()

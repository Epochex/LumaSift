from __future__ import annotations

import argparse
import json
from pathlib import Path

from lumasift.evaluation.metrics import evaluate_reports, write_metrics_json, write_metrics_markdown


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate LumaSift ranking reports against exported labels.")
    parser.add_argument("--eval", type=Path, required=True, help="Evaluation dataset JSON from export_eval_dataset.py.")
    parser.add_argument("--report", type=Path, action="append", required=True, help="One or more report.json files to evaluate.")
    parser.add_argument("--k", type=int, default=10, help="Cutoff for Precision/Recall/NDCG.")
    parser.add_argument("--output-json", type=Path, required=True, help="Metrics JSON output path.")
    parser.add_argument("--output-md", type=Path, required=True, help="Metrics Markdown summary path.")
    args = parser.parse_args()

    eval_dataset = json.loads(args.eval.read_text(encoding="utf-8"))
    reports = [(str(path), json.loads(path.read_text(encoding="utf-8"))) for path in args.report]
    payload = evaluate_reports(eval_dataset, reports, k=args.k)
    write_metrics_json(args.output_json, payload)
    write_metrics_markdown(args.output_md, payload)
    print(f"Evaluated {len(reports)} report(s) against {payload['eval_photo_count']} labeled photos")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

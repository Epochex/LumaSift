from __future__ import annotations

import argparse
from pathlib import Path

from lumasift.evaluation.dataset import build_eval_dataset, write_eval_dataset_csv, write_eval_dataset_json
from lumasift.storage.state_db import LumaSiftStateDb, default_state_db_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Export privacy-safe LumaSift evaluation labels from SQLite.")
    parser.add_argument("--db", type=Path, default=default_state_db_path(), help="Path to lumasift.sqlite.")
    parser.add_argument("--output", type=Path, required=True, help="Output .json or .csv path.")
    parser.add_argument("--format", choices=["json", "csv"], default=None, help="Override output format.")
    parser.add_argument("--prompt-version", default="", help="Prompt/model prompt version these labels should evaluate.")
    parser.add_argument("--split", default="unassigned", help="Dataset split, e.g. train/dev/test.")
    parser.add_argument("--notes", default="", help="Optional note copied onto each exported row.")
    args = parser.parse_args()

    dataset = build_eval_dataset(
        LumaSiftStateDb(args.db),
        prompt_version=args.prompt_version,
        split=args.split,
        notes=args.notes,
    )
    output_format = args.format or ("csv" if args.output.suffix.lower() == ".csv" else "json")
    if output_format == "csv":
        write_eval_dataset_csv(args.output, dataset)
    else:
        write_eval_dataset_json(args.output, dataset)
    print(f"Exported {dataset['photo_count']} labeled records to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

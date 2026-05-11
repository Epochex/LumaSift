from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import time
from pathlib import Path

from lumasift.app.main import main as run_lumasift
from lumasift.core.config import Settings
from lumasift.core.manifest import discover_photos
from lumasift.reports.contact_sheet import write_contact_sheet
from lumasift.reports.csv_report import write_csv_report
from lumasift.reports.json_report import write_json_report


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "outputs" / "local_sample"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run LumaSift on a limited local sample without putting photos in the repo.",
    )
    parser.add_argument("--input", required=True, type=Path, help="Local photo folder to sample from.")
    parser.add_argument("--output", default=DEFAULT_OUTPUT, type=Path, help="Output folder for reports.")
    parser.add_argument("--limit", default=50, type=int, help="Maximum number of photos to stage and analyze.")
    parser.add_argument(
        "--mode",
        choices=["local_only", "qwen_vision"],
        default="local_only",
        help="Analysis mode. local_only avoids API calls.",
    )
    parser.add_argument("--top-n", default=None, type=int, help="Top-N candidates for Qwen analysis.")
    parser.add_argument("--run-id", default=None, help="Run id to use for this sample.")
    parser.add_argument(
        "--keep-staging",
        action="store_true",
        help="Keep staged links/copies under the output folder after the run.",
    )
    return parser


def _safe_name(name: str) -> str:
    safe = "".join("_" if char in '<>:"/\\|?*' else char for char in name)
    return safe.strip(" .") or "photo"


def _stage_photo(source: Path, destination: Path) -> str:
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(source, destination)
        return "hardlink"
    except OSError:
        pass
    try:
        os.symlink(source, destination)
        return "symlink"
    except OSError:
        pass
    shutil.copy2(source, destination)
    return "copy"


def _rewrite_reports(output_dir: Path, original_input: Path, path_map: dict[str, Path]) -> None:
    json_path = output_dir / "report.json"
    csv_path = output_dir / "report.csv"
    contact_sheet_path = output_dir / "contact_sheet_top50.jpg"
    if not json_path.exists():
        return

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    records = payload.get("records", [])
    for record in records:
        staged_path = str(Path(str(record.get("path", ""))).resolve())
        original_path = path_map.get(staged_path)
        if original_path is None:
            continue
        record["path"] = str(original_path)
        record["filename"] = original_path.name

    payload["input_dir"] = str(original_input)
    payload["sample_limit"] = len(path_map)
    write_json_report(json_path, payload)
    write_csv_report(csv_path, records)
    write_contact_sheet(contact_sheet_path, records[:50])


def _assert_safe_staging_dir(staging_dir: Path, output_dir: Path) -> None:
    staging = staging_dir.resolve()
    output = output_dir.resolve()
    if output not in staging.parents:
        raise ValueError(f"Refusing to use staging dir outside output: {staging}")


def main() -> int:
    args = build_parser().parse_args()
    input_dir = args.input.expanduser().resolve()
    output_dir = args.output.expanduser().resolve()
    if args.limit < 1:
        raise SystemExit("--limit must be at least 1")
    if not input_dir.exists():
        raise SystemExit(f"Input folder does not exist: {input_dir}")

    settings = Settings.from_env()
    photos = discover_photos(input_dir, settings.supported_extensions)
    selected = photos[: args.limit]
    if not selected:
        raise SystemExit(f"No supported photos found in: {input_dir}")

    run_id = args.run_id or f"local-sample-{time.strftime('%Y%m%d-%H%M%S')}"
    staging_dir = output_dir / "_local_sample_input" / run_id
    _assert_safe_staging_dir(staging_dir, output_dir)
    if staging_dir.exists():
        shutil.rmtree(staging_dir)
    staging_dir.mkdir(parents=True, exist_ok=True)

    path_map: dict[str, Path] = {}
    methods: dict[str, int] = {}
    for index, photo in enumerate(selected, start=1):
        staged_name = f"{index:04d}_{_safe_name(photo.path.name)}"
        staged_path = staging_dir / staged_name
        method = _stage_photo(photo.path, staged_path)
        methods[method] = methods.get(method, 0) + 1
        path_map[str(staged_path.resolve())] = photo.path.resolve()

    print(f"Staged {len(selected)} photo(s) in {staging_dir}")
    print("Staging methods: " + ", ".join(f"{key}={value}" for key, value in sorted(methods.items())))

    argv = [
        "--input",
        str(staging_dir),
        "--output",
        str(output_dir),
        "--mode",
        args.mode,
        "--run-id",
        run_id,
    ]
    if args.top_n is not None:
        argv.extend(["--top-n", str(args.top_n)])

    exit_code = run_lumasift(argv)
    if exit_code == 0:
        _rewrite_reports(output_dir, input_dir, path_map)

    if not args.keep_staging:
        shutil.rmtree(staging_dir, ignore_errors=True)
    else:
        manifest_path = output_dir / f"local_sample_manifest_{run_id}.csv"
        with manifest_path.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.writer(handle)
            writer.writerow(["staged_path", "original_path"])
            for staged_path, original_path in sorted(path_map.items()):
                writer.writerow([staged_path, str(original_path)])
        print(f"Kept staging manifest: {manifest_path}")

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())

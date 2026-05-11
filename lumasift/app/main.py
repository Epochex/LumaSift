from __future__ import annotations

import argparse
import logging
from pathlib import Path

from lumasift.core.config import Settings
from lumasift.core.harness import LumaSiftHarness
from lumasift.core.logging_setup import configure_logging


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lumasift",
        description="Run the LumaSift resumable photo selection harness.",
    )
    parser.add_argument("--input", type=Path, default=None, help="Input photo directory.")
    parser.add_argument("--output", type=Path, default=None, help="Output directory.")
    parser.add_argument(
        "--mode",
        choices=["local_only", "qwen_vision"],
        default=None,
        help="Analysis mode. local_only avoids API calls.",
    )
    parser.add_argument("--top-n", type=int, default=None, help="Top-N candidates for API analysis.")
    parser.add_argument("--run-id", default=None, help="Resume or name a run id.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = Settings.from_env()
    if args.input is not None:
        settings.input_dir = args.input
    if args.output is not None:
        settings.output_dir = args.output
    if args.mode is not None:
        settings.ai_mode = args.mode
    if args.top_n is not None:
        settings.top_n_api_analysis = args.top_n

    configure_logging(settings.output_dir)
    logging.info("Starting LumaSift run")
    result = LumaSiftHarness(settings=settings, run_id=args.run_id).run()
    logging.info("Run complete: %s", result.summary)
    print(result.summary_text())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

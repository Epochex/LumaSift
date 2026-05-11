# LumaSift

LumaSift is a local-first photo selection and editing-potential system for street, documentary, humanistic, and travel photography.

The goal is not to label photos as simply good or bad. The goal is to rank large folders of Sony ARW, PNG, JPG, and JPEG files by story value, human/documentary potential, emotional impact, visual tension, and editing potential, then produce concrete editing guidance for the strongest candidates.

## Current Status

Implemented:

- Python package and CLI: `python -m lumasift.app.main`
- Recursive image discovery
- PNG/JPG/JPEG loading with Pillow
- ARW loading path through optional `rawpy`
- Local-only baseline ranking that runs without API calls
- Story-first score fields:
  - `storytelling_score`
  - `human_documentary_value_score`
  - `decisive_moment_score`
  - `emotional_impact_score`
  - `visual_tension_score`
  - `editing_potential_score`
  - `technical_quality_score`
  - `final_selection_score`
- Optional Qwen vision backend scaffold for Top-N deep analysis
- Multi-key API rotation scaffold through environment variables
- CSV and JSON reports
- Top-50 contact sheet
- Demo image generator
- JSONL run events and checkpoint files for long-running jobs

The local-only scores are intentionally weak proxies. Real story, documentary, and artistic judgments should come from Qwen vision review or human selection. The local pass exists to make large-folder processing cheap and robust.

## Install

```bash
python -m pip install -e .[dev]
```

Optional ARW support:

```bash
python -m pip install -e .[raw]
```

## Run Demo

```bash
python scripts/run_demo.py
```

Expected outputs:

```text
outputs/report.csv
outputs/report.json
outputs/contact_sheet_top50.jpg
outputs/runs/<run_id>/events.jsonl
outputs/runs/<run_id>/checkpoint.json
```

## Run On A Folder

```bash
python -m lumasift.app.main --input "D:/Photos/trip" --output ./outputs --mode local_only
```

## Qwen Vision Mode

Create a local `.env` file. Do not commit it.

```env
LUMASIFT_AI_MODE=qwen_vision
LUMASIFT_VISION_API_BASE_URL=https://api.newcoin.top/v1
LUMASIFT_VISION_MODEL=qwen3.6-plus
LUMASIFT_VISION_API_KEYS=first_key,second_key
LUMASIFT_VISION_MAX_TOKENS=4096
LUMASIFT_TOP_N_API_ANALYSIS=20
```

Then run:

```bash
python -m lumasift.app.main --input "./sample_photos" --output ./outputs --mode qwen_vision --top-n 20
```

The pipeline first ranks locally, then sends only Top-N JPEG previews to Qwen for deeper story/editing analysis.

## Tests

```bash
python -m pytest -q
```

## Phone / Cloud Workflow

If you want to guide development while away from your computer, use Codex Cloud connected to `Epochex/LumaSift` on GitHub. Cloud mode is appropriate for code changes, tests, documentation, and small sample images.

Use local mode for private real-photo analysis, because the cloud environment cannot automatically access your Windows photo folders. If cloud analysis is needed, upload only deliberate test samples and configure API keys as cloud secrets, not repository files.

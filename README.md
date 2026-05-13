# LumaSift

LumaSift is a local-first photo selection and editing-potential system for street, documentary, humanistic, and travel photography.

The goal is not to label photos as simply good or bad. The goal is to rank large folders of Sony ARW, PNG, JPG, and JPEG files by story value, human/documentary potential, emotional impact, visual tension, and editing potential, then produce concrete editing guidance for the strongest candidates.

## Current Status

Implemented:

- Local desktop GUI entry point: `lumasift`
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
- Multi-key API rotation through environment variables
- Persistent Qwen response cache to avoid repeat API spend
- Selected-photo editing advice in JSON and Markdown
- CSV and JSON reports
- Top-50 contact sheet
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

## Launch The App

After installation, launch the graphical application:

```bash
lumasift
```

The first user-facing release is GUI-first. The previous command-line workflow has been removed from the product surface.

For friend testing on Windows, use the portable package:

```text
dist/LumaSift-Windows-Portable.zip
```

Unzip it and run:

```text
LumaSift/LumaSift.exe
```

For a normal Windows installation experience, use:

```text
dist/installer/LumaSiftSetup.exe
```

Expected outputs after running an analysis:

```text
outputs/report.csv
outputs/report.json
outputs/contact_sheet_top50.jpg
outputs/runs/<run_id>/events.jsonl
outputs/runs/<run_id>/checkpoint.json
```

## GUI Workflow

1. Choose a local photo folder, for example `D:/DCIM`.
2. Choose an output folder.
3. Select `local_only` for fast local culling or `qwen_vision` for Top-N visual review.
4. Set scan limit and Qwen Top-N.
5. Click **Analyze Folder**.
6. Review the thumbnail grid, select photos, and click **Generate Editing Advice for Selection**.

The app remembers recent folders and run settings. API keys can be entered in the GUI for Qwen mode; leave the field empty to use `.env`. Saving keys locally is optional.

The result grid uses placeholders first and fills thumbnails asynchronously, so review can start without waiting for every preview to finish.

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

The GUI first ranks locally, then sends only Top-N JPEG previews to Qwen for deeper story/editing analysis when `qwen_vision` is selected.

Qwen responses are cached under the output folder. Re-running the same preview/model/prompt combination should reuse cached responses instead of spending API credits again.

## Selected Editing Advice

Use the thumbnail grid to select one or more photos, then generate concrete editing plans.

Expected advice outputs:

```text
outputs/.../selected_editing_advice.json
outputs/.../selected_editing_advice.md
```

The advice includes recommended style, Lightroom-like global parameters, crop strategy, local dodge/burn actions, B&W/color recommendation, and grain/sharpness/motion-blur handling.

## Tests

```bash
python -m pytest -q
```

## Phone / Cloud Workflow

If you want to guide development while away from your computer, use Codex Cloud connected to `Epochex/LumaSift` on GitHub. Cloud mode is appropriate for code changes, tests, documentation, and small sample images.

Use local mode for private real-photo analysis, because the cloud environment cannot automatically access your Windows photo folders. If cloud analysis is needed, upload only deliberate test samples and configure API keys as cloud secrets, not repository files.

# LumaSift

LumaSift is a local-first photo selection and editing-potential system for street, documentary, humanistic, and travel photography.

The goal is not to label photos as simply good or bad. The goal is to rank large folders of RAW, PNG, JPG, and JPEG files by story value, human/documentary potential, emotional impact, visual tension, and editing potential, then produce concrete editing guidance for the strongest candidates.

## Current Status

Implemented:

- Local desktop GUI entry point: `lumasift`
- Recursive image discovery
- PNG/JPG/JPEG loading with Pillow
- Broad camera RAW loading path through optional `rawpy`/LibRaw-compatible formats, including Canon CR2/CR3, Nikon NEF/NRW, Sony ARW/SRF/SR2, Fujifilm RAF, Panasonic RW2, Olympus ORF, Adobe DNG, and other common RAW extensions
- RAW+JPG same-basename pairing metadata, pair-status filtering, and customizable keyboard culling shortcuts in the desktop review board
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
- Two explicit operating modes:
  - Local Fast Culling: no API calls; uses RAW/JPG pairing, local previews, technical recovery signals, sequence grouping, and manual keyboard labels.
  - LLM Deep Analysis: sends only Top-N compressed JPEG previews to an OpenAI-compatible image LLM endpoint for content, composition, story, and editing-plan analysis.
- Multi-key API rotation through environment variables
- Persistent vision response cache to avoid repeat API spend
- Selected-photo editing advice in JSON and Markdown
- CSV and JSON reports
- Top-50 contact sheet
- JSONL run events and checkpoint files for long-running jobs

The local-only scores are intentionally weak proxies. Real story, documentary, and artistic judgments should come from LLM Deep Analysis or human selection. The local pass exists to make large-folder processing cheap, private, and robust.

## Install

```bash
python -m pip install -e .[dev]
```

Optional RAW support:

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
3. Select Local for fast no-API culling or LLM Deep Analysis for Top-N visual review.
4. Set scan limit and Deep Top-N.
5. Click **Analyze Folder**.
6. Review the thumbnail grid, select photos, and click **Generate Editing Advice for Selection**.

The app remembers recent folders and run settings. API keys, an OpenAI-compatible base URL, and a model name can be entered in the GUI for LLM Deep Analysis mode; leave the key field empty to use `.env`. Saving keys locally is optional. The key check probes the configured API for vision-capable models, selects the strongest detected model, and shows remaining tokens/credit when the provider exposes that information.

Default review shortcuts are `Up` for keep, `Down` for reject, `S` for mark/unmark, and `D` for maybe. The Shortcuts page in the desktop app lets you remap these keys.

The result grid uses placeholders first and fills thumbnails asynchronously, so review can start without waiting for every preview to finish.

## LLM Deep Analysis Mode

Create a local `.env` file. Do not commit it.

```env
LUMASIFT_AI_MODE=vision_llm
LUMASIFT_VISION_API_BASE_URL=https://api.newcoin.top/v1
LUMASIFT_VISION_MODEL=qwen3.6-plus
LUMASIFT_VISION_API_KEYS=first_key,second_key
LUMASIFT_VISION_MAX_TOKENS=4096
LUMASIFT_TOP_N_API_ANALYSIS=20
```

The GUI first ranks locally, then sends only Top-N JPEG previews to the configured image LLM for deeper story/editing analysis when LLM Deep Analysis mode is selected. `qwen_vision` remains accepted as a backwards-compatible internal mode value.

Vision responses are cached under the output folder. Re-running the same preview/model/prompt combination should reuse cached responses instead of spending API credits again.

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

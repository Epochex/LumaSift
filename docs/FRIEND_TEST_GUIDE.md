# LumaSift Friend Test Guide

## Install

Preferred:

1. Run `LumaSiftSetup.exe`.
2. Launch LumaSift from the Start Menu or desktop shortcut.

Alternative portable mode:

1. Unzip `LumaSift-Windows-Portable.zip`.
2. Open the `LumaSift` folder.
3. Double-click `LumaSift.exe`.

No Python installation is required for the portable build.
No Python installation is required for the installer build.

## First Run

1. Choose a photo folder, for example `D:\DCIM`.
2. Choose an output folder.
3. Start with:
   - Mode: `local_only`
   - Scan limit: `50`
   - Display Top-N: `300`
4. Click **Analyze Folder**.
5. Review the thumbnail grid.
6. Select several photos.
7. Click **Generate Editing Advice for Selection**.

## Qwen Mode

Use `qwen_vision` only after local mode works.

1. Enter API keys in the Qwen API keys field, separated by commas.
2. Set Qwen Top-N to a small value such as `3` or `5`.
3. Click **Analyze Folder**.

The app sends only downscaled JPEG previews for Top-N candidates, not original RAW files.

## Outputs

The output folder contains:

- `report.csv`
- `report.json`
- `contact_sheet_top50.jpg`
- `selected_editing_advice.json`
- `selected_editing_advice.md`
- `runs/gui-run/events.jsonl`

## What Feedback To Send

Useful feedback:

- screenshot of the app;
- output folder path;
- whether RAW files loaded;
- whether ranking looked useful;
- whether editing advice was concrete enough;
- whether Qwen mode was too slow or failed;
- `lumasift.log` if the app failed.

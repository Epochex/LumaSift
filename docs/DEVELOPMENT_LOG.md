# Development Log

## 2026-05-12

- Established the first long-running development harness.
- Product surface is now a GUI-first local desktop application.
- Added resumable run directories under `outputs/runs/<run_id>`.
- Added JSONL event logging and atomic checkpoints.
- Added environment-driven API configuration and multi-key rotation scaffolding.
- Added story-first scoring fields so the product emphasizes humanistic/street-photo value over pure technical quality.
- Added limited local scanning for safe testing against large folders such as `D:\DCIM`.
- Added `--selected-ranks` and `--selected-paths` workflow for selected-photo editing plans.
- Added persistent Qwen response cache and retry/backoff, avoiding repeated API spend for the same preview/model/prompt.
- Improved RAW handling by using embedded RAW previews first, falling back to half-size RAW postprocess.
- Added richer contact sheet captions: rank, score, category, filename, top reason, and style.
- Validated real Sony ARW runs:
  - 5 ARW local-only: processed 5/5, 0 failures.
  - 10 ARW local-only: processed 10/10, 0 failures, roughly 3 seconds after preview optimization.
  - 10 ARW with Qwen Top-3: processed 10/10, Qwen analyzed 3 candidates and wrote editing guidance.
  - Qwen cache check: repeated same Top-3 run in roughly 2.5 seconds, indicating cached responses.
  - 200 ARW local-only: processed 200/200, 0 failures, roughly 29 seconds.
- Switched first deliverable to a local graphical application with PySide6:
  - folder picker;
  - local/qwen mode switch;
  - scan limit and Qwen Top-N controls;
  - thumbnail grid;
  - detail panel;
  - multi-select editing advice generation.
- Added commercial friend-test packaging:
  - PyInstaller spec;
  - Windows build script;
  - app icon;
  - portable zip output;
  - exe launch smoke test.
- Added async thumbnail loading in the GUI:
  - placeholders appear immediately;
  - thumbnails are generated off the UI thread;
  - thumbnail generation is cancellable when the window closes or results refresh;
  - preview cache filenames are collision-safe.
- Added result search, category filter, sort controls, and display limits.
- Added Inno Setup installer:
  - `dist/installer/LumaSiftSetup.exe`;
  - desktop/start menu shortcuts;
  - portable zip remains available.
- Reworked the desktop UI toward a more commercial local-first product flow:
  - added a top dashboard for scanned/shown/selected/mode state;
  - added a four-step workflow strip covering import, local pre-score, Qwen review, and editing plan;
  - replaced the old run form with a compact control deck;
  - added result-board styling, empty-state guidance, and fade-in transitions;
  - replaced plain text detail output with visual score bars and structured review/edit sections.
- Added the first persistent review-state layer:
  - local SQLite state database under the user profile;
  - run history table for GUI analysis runs;
  - per-photo keep/maybe/reject labels;
  - label filter in the review board;
  - labels are merged into future runs and written back to CSV/JSON reports.
- Added a durable planning-to-execution loop:
  - `docs/backlog.json` is the canonical executable backlog;
  - `docs/BACKLOG.md` defines how planning/review agents become engineering work;
  - `scripts/backlog.py next` selects the next ready task from dependencies and priority;
  - agent findings now have to be converted into backlog items before implementation.
- Completed the first virtualized review-grid slice:
  - replaced `QListWidget` with `QListView` plus `QAbstractListModel`;
  - thumbnail work is queued from the visible viewport instead of the whole result set;
  - stale thumbnail writes are guarded by a generation id;
  - verified 2000 synthetic records can be loaded into the model.
- Hardened the desktop app against common packaged-exe crashes:
  - added crash logging under the user profile;
  - changed window closing to wait for background analysis/thumbnail threads instead of destroying running `QThread`s;
  - moved thumbnail worker cleanup to thread-finished lifecycle;
  - added SQLite WAL/busy timeout and chunked label loading for large folders.
- Added GUI language switching and Chinese-first UI:
  - default UI is Chinese with an English switch in the header;
  - major buttons, labels, filters, messages, and detail panels are localized;
  - long explanatory UI text was shortened into workflow labels and state cues.

## 2026-05-12 - Detail panel UI pass
- Reworked the review panel into a scrollable detail area plus fixed two-row action bar so bottom-right actions no longer overlap detail content on shorter windows.
- Localized photo grid labels for Chinese default UI, including category and user mark display values.
- Added a minimum desktop window size to avoid compressed product controls at unsupported dimensions.

## 2026-05-12 - Large RAW preview
- Added double-click large preview from the photo grid using a background worker and cached 2400px JPEG previews.
- The large preview opens in a dark, near full-screen inspection window with Fit and 100% modes for focus/detail checks.
- Added a non-intrusive grid tooltip instead of adding more explanatory text to the main UI.

## 2026-05-12 - Dark workbench UI pass
- Shifted the desktop UI toward a photo-review dark workbench: image grid first, contrast-focused panels, and stronger active workflow states.
- Moved mode, scan limits, Qwen top-N, display count, and API key controls into a collapsed Advanced panel so the default path is folder -> analyze -> review.
- Made workflow steps clickable; each step focuses the relevant control instead of relying on explanatory text.
- Compressed photo cards and added a visual summary block in the review panel before detailed reasons and editing parameters.

## 2026-05-12 - Review mode collapse
- Added an automatic review mode after analysis completes: header, workflow, input, and advanced controls collapse into a compact review bar.
- Added setup/re-analyze buttons in review mode so the user can recover controls without losing screening space.
- Increased the review panel minimum width and split ratio so AI critique and action buttons remain usable during screening.
- Improved advanced numeric controls by widening them, removing tiny spin arrows, and increasing value contrast.

## 2026-05-12 - Advanced settings compression fix
- Replaced the advanced settings mini-card row with a stable grid so mode, scan count, Qwen count, advice count, and display count no longer collapse into clipped fields.
- Added fixed-height setting inputs and explicit height for the advanced panel so Qt cannot compress checkboxes, key fields, or helper text into unreadable rows.
- Verified the expanded setup state and compact review mode with offscreen UI screenshots.

## 2026-05-12 - Product goal and UI smoke harness
- Added `GOAL.md` as the durable v0.1 product target: local-first graphical release candidate, stable 200+ RAW workflow, Qwen Top-N review, selection labels, editing advice, exports, installer, and privacy-first behavior.
- Added `scripts/ui_smoke.py` to generate setup-collapsed, setup-expanded, and review-mode screenshots plus JSON/Markdown geometry checks under `outputs/ui_smoke/`.
- Added `tests/test_ui_smoke.py` so the visual smoke harness is covered by automated tests.
- Updated `docs/BACKLOG.md`, `docs/backlog.json`, `AGENTS.md`, and `scripts/backlog.py goal` so future `继续 goal` runs follow the formal loop: read goal, choose backlog task, implement, test, run UI smoke, update docs, rebuild, commit, and push.

## 2026-05-12 - Chinese editing plan and review layout fix
- Changed selected-photo editing advice to default to Chinese for Chinese users, including Markdown export, JSON payload labels, Lightroom parameter names, tone rationale, crop advice, local adjustments, and grain/sharpening guidance.
- Kept English output available when the UI language is switched to English before generating the editing plan.
- Replaced the right-side editing-plan preview from raw Markdown/code-block rendering with structured cards, parameter tables, and readable sections.
- Extended `scripts/ui_smoke.py` with an editing-plan screenshot and language checks so wrong-language or compressed advice panels are caught automatically.

## 2026-05-12 - Constructivist review cockpit pass
- Widened the right review cockpit and shifted the splitter balance so review/advice content is no longer cramped against the action buttons.
- Added constructivist visual guide rails and stronger cyan/yellow/red hierarchy for selection, decision, and rejection actions while keeping the photo grid readable.
- Removed English local-mode fallback strings from the Chinese review detail path and mapped categories, styles, labels, and local-only guidance to Chinese.
- Tightened `scripts/ui_smoke.py` so review/detail width and localized fallback text are checked automatically.

## 2026-05-12 - Selection and label state stabilization
- Fixed keep/maybe/reject marking to update canonical records by normalized photo path instead of relying on Qt `UserRole` object identity.
- Treated explicit `unlabeled` values as unlabeled in filters so generated records and persisted records behave consistently.
- Preserved selection by photo identity across filter/sort repopulation and refreshed the review cockpit/dashboard after batch marking.
- Extended `scripts/ui_smoke.py` with real multi-select, keep/reject relabeling, label-filter, and selection-restore checks.

## 2026-05-12 - Qwen queue visibility
- Added harness-level Qwen events for queue prepared, candidate running, candidate finished, cache hit, failure, and client retry activity.
- Added a compact GUI queue strip showing model, queued item count, current running file, done, cache-hit, failed, and retry counts.
- Preserved Qwen cache behavior while exposing `last_cache_hit` for product telemetry without changing cached response payloads.
- Extended UI smoke to verify the Qwen queue strip in Chinese and English without requiring a live API key.

## 2026-05-12 - Chinese glyph and graphic control gate
- Fixed the release-blocking Chinese UI glyph issue by selecting a Chinese-capable application font and registering Windows Microsoft YaHei font files for offscreen smoke screenshots.
- Replaced text-heavy review actions with graphic decision controls, icon-only output/contact-sheet controls, and a compact Qwen status chip strip.
- Fixed a language-state bug where the empty review detail panel could remain in English after switching the app back to Chinese.
- Strengthened `scripts/ui_smoke.py` so it now fails on missing Chinese glyph support, long log-style Qwen status text, compressed action buttons, and stale source-state ambiguity.
- Updated the executable backlog so 200+ RAW GUI stability and Chinese-first friend-test rehearsal precede Qwen cancellation work.

## 2026-05-12 - 200 RAW GUI release stability run
- Ran the current desktop GUI worker in local-only mode against 200 real ARW files from a private local camera folder, writing only ignored outputs under `outputs/raw200-gui-smoke/`.
- Result: 200 records loaded into review mode in 24.8 seconds, with the first thumbnail batch generated and no analysis failure reported.
- Verified post-run review behavior using the 200-record report: review board restored, keep marking worked, keep filter showed persisted labels, and selected-photo editing advice was written.
- Verified large RAW preview generation from the run output: the first ranked ARW opened as a 1616 x 1080 preview.
- Reduced the large preview image label minimum size so Fit mode is less likely to force scrollbars on smaller windows.
- Completed the Chinese-first friend-test workflow rehearsal gate by combining fresh Chinese smoke screenshots, the 200 RAW GUI run, review/label/advice checks, large preview verification, and output artifact checks.
- Rebuilt the Windows app directory and Inno installer, then confirmed `dist/LumaSift/LumaSift.exe` starts from the packaged build and `dist/installer/LumaSiftSetup.exe` exists.

## 2026-05-12 - Qwen cancellation and graceful downgrade
- Added Qwen-stage cancellation handling: when `STOP_LUMASIFT` exists during Qwen review, pending candidates are marked `cancelled`, keep their local ranking data, and are still written into the final report.
- The GUI queue strip now tracks cancelled Qwen items separately from queued, running, done, cache-hit, failed, and retry states.
- The cancel button marks the Qwen queue as cancelling immediately while allowing any in-flight request to finish safely rather than corrupting cache/report state.
- Extended UI smoke to cover the cancelled queue state without requiring live API access.
- Added regression coverage so pending Qwen candidates can be cancelled without making a network request.

## 2026-05-12 - SQLite run history view
- Added a recent-run history view backed by the existing local SQLite run table.
- The GUI now exposes a `历史` entry from both setup and review mode, listing recent runs with time, mode, scanned/processed/failed counts, output path, and availability state.
- Historical runs with a valid `report.json` can be restored directly into the review board; missing output folders or reports show an unavailable state instead of failing silently.
- Added tests for run listing order and GUI history restoration, and extended UI smoke to keep the history entry visible in setup and review modes.

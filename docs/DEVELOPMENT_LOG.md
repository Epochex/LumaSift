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

## 2026-05-12 - SQLite photo manifest and rerun reuse
- Extended the local SQLite `photos` table from label-only state into a photo manifest with size, mtime, identity hash, preview path, last run id, score/category/rank, full score JSON, cached record JSON, and Qwen cache key.
- Wired GUI analysis workers into the same state database so completed runs persist manifest rows while keeping JSON/CSV reports as normal export artifacts.
- Added safe rerun reuse: unchanged successful local records can be reused from SQLite, while failed records and Qwen-enriched records are not reused for local-only runs.
- Exposed the Qwen response cache key digest from the client and stored it on Qwen-reviewed records when available.
- Verified against 200 private local RAW files: first manifest run processed 200/200 in 32.18 seconds with 200 manifest preview paths; a second unchanged run reused 200/200 records in 3.39 seconds.

## 2026-05-12 - User feedback without score pollution
- Added explicit report fields separating model output from user feedback: `model_final_selection_score`, `model_category`, `user_feedback_priority`, `user_feedback_action`, and `qwen_skip_reason`.
- Existing keep/maybe/reject labels now surface as workflow priority without changing `final_selection_score` or `category`.
- Added a GUI `标记优先` / `Label priority` sort mode so previously kept images can be surfaced in future review sessions.
- Qwen review now skips records labeled `reject` by default and records `skipped_user_reject`; `LUMASIFT_QWEN_INCLUDE_REJECTED=1` can opt back in.
- Verified a 200 RAW manifest reuse run after the change: 200/200 reused in 3.79 seconds and all 200 records carried the new feedback/model fields.

## 2026-05-12 - Evaluation dataset export format
- Added `lumasift.eval_dataset.v1`, a privacy-safe metadata format for local ranking evaluation.
- Added `scripts/export_eval_dataset.py` to export labeled SQLite rows as JSON or CSV with `photo_id`, path, user/gold label, story rank, notes, split, prompt version, run context, score, and category.
- Documented a 100-300 photo evaluation workflow in `docs/EVALUATION_DATASET.md`.
- Added tests for JSON/CSV dataset writing and the command-line export script.

## 2026-05-12 - Ranking evaluation metrics
- Added `scripts/evaluate_ranking.py` and `lumasift.ranking_metrics.v1` metrics output for comparing one or more `report.json` files against exported evaluation labels.
- Metrics now include Precision@K, Recall@K, NDCG@K, MRR, label distribution, AI mode, prompt version, and observed Qwen model versions.
- Added Markdown summary output so local-only and Qwen/prompt-version comparisons can be inspected without opening raw JSON.

## 2026-05-12 - Qwen prompt-version evaluation loop
- Qwen-reviewed records now carry `qwen_prompt_version` in JSON/CSV reports, while the Qwen cache key continues to include prompt version and model identity.
- Ranking metrics now surface prompt version and Qwen model versions for each compared report, enabling local-only vs Qwen and prompt A/B comparisons.
- Metrics Markdown now lists false negatives: relevant keep/maybe photos outside the chosen K that look technically weak or were categorized as technically weak but interesting.

## 2026-05-12 - Similar-photo grouping and group winners
- Added conservative near-duplicate grouping using 64-bit dHash plus aspect-ratio, brightness, and average-color constraints so visibly different frames are less likely to be merged.
- Every successful record now carries grouping metadata: `visual_hash`, `visual_color`, `group_id`, `group_size`, `group_rank`, `is_group_best`, `group_best_path`, and `group_score_delta`.
- Persisted grouping fields in the SQLite manifest and CSV/JSON reports without changing model scores.
- Qwen review now defaults to group winners only; non-winning group members are marked `skipped_similar_group` with `qwen_skip_reason=similar_group_non_winner`.
- The review board shows compact group badges, adds group filters for all / group best / grouped / singles, and the right cockpit shows group position and best candidate.
- UI smoke now covers group badges, group filters, and group detail text.
- Verified against 200 private local RAW files: first grouping run processed 200/200 in 34.34 seconds, produced 114 groups, max group size 7, stored 200 visual hashes, and estimated 86 Qwen calls saved by skipping non-winning group members. Manifest reuse processed 200/200 in 3.49 seconds.
- Ran a live Qwen smoke using local development keys on 8 private RAW files with Top-2 group winners: 2 Qwen requests completed, 0 failed, and grouped non-winners were skipped as expected.

## 2026-05-12 - Review cockpit scroll fix and Qwen story prompt v2
- Removed the opacity graphics effect from the right `QTextEdit` detail cockpit because scrolling during Qt rich-text effects could repaint the panel incorrectly and make text appear dim.
- Simplified the cockpit HTML/CSS away from float/table-cell layout and added a UI smoke screenshot/check for the detail panel after scrolling to the bottom.
- Upgraded Qwen to `qwen-story-v2`, requiring visible evidence, subject relationship, decisive moment read, why-this-frame judgment, avoid-overediting guidance, and concrete story interpretation in Chinese text.
- The Qwen merge path, GUI cockpit, CSV report, and contact sheet now preserve or surface these story-evidence fields.
- Local-only fallback now explicitly presents itself as technical pre-screening and varies reasons by brightness, contrast, clipping, visual structure, and editability instead of repeating one generic line.
- Verification: `python -m pytest -q` passed with 50 tests, and `python scripts/ui_smoke.py --output outputs/ui_smoke --language zh --records 24` passed with the new scrolled-detail screenshot.
- Live Qwen v2 smoke on 4 private local RAW files with Top-1 deep review completed in 81.40 seconds, processed 4/4 with 0 failures, and returned concrete evidence for the reviewed frame including station signage, foreground passenger, background pedestrians, platform/signage context, and a negative decisive-moment judgment.

## 2026-05-12 - Photographer-grade evidence-bound advice
- Upgraded the Qwen story prompt to `qwen-story-v3`, adding `visible_inventory`, `editorial_verdict`, `score_rationales`, `moment_status`, `frame_failure_reasons`, and a structured `editing_plan`.
- Added a lightweight Qwen response quality classification so records carry `analysis_source=qwen_vision` and `analysis_quality` such as `concrete`, `weak`, `generic`, or `missing`.
- Local-only records now carry `analysis_source=local_proxy`, `analysis_quality=missing_semantic_read`, and `needs_qwen_review=true` so technical pre-screening is not presented as final photographic judgment.
- Reworked selected editing advice: Qwen-reviewed records use visible evidence, crop keep/reduce reasoning, structured local masks, editorial verdict, and do-not-overedit guidance; local-only records produce only a technical draft with a `blocked_reason`.
- The GUI advice page and Markdown export now show analysis status, photo reading, visible evidence, content decision, crop intent, local mask targets, and evidence-bound edit intent before Lightroom parameters.
- UI smoke now checks that advice output includes visible evidence, crop reasoning, do-not-overedit guidance, and does not reintroduce the generic phrase about protecting valuable moments and relationships.
- Verification: `python -m pytest -q` passed with 51 tests, and `python scripts/ui_smoke.py --output outputs/ui_smoke --language zh --records 24` passed.
- Live Qwen v3 smoke on 4 private local RAW files with Top-1 deep review completed in 86.81 seconds, processed 4/4 with 0 failures, and returned `analysis_quality=concrete` with concrete inventory, `moment_status=weak`, a `maybe` editorial verdict, 16:9 crop guidance, and local mask actions tied to the DB/Juten Tach sign and the left foreground passenger.

## 2026-05-12 - Qwen activation guardrails
- Diagnosed a GUI run where Qwen API keys were configured but the saved run still used `ai_mode=local_only`, so no deep-review queue was created and selected advice correctly remained a technical draft.
- Kept the API key field editable in local mode, switched to Qwen mode automatically when the user types or pastes a key, and added a visible Qwen warning strip when keys exist but the current mode is still local.
- Added a start-run confirmation when keys are configured but the mode is local, preventing silent local-only runs when the user expected Qwen deep visual review.
- Added desktop regression tests for key-entry mode promotion and local-mode Qwen warning visibility.
- Verification: `python -m pytest -q` passed with 53 tests, and `python scripts/ui_smoke.py --output outputs/ui_smoke --language zh --records 24` passed.

## 2026-05-12 - Compact top navigation and Qwen key checking
- Replaced the oversized first-screen hero with a compact top navigation bar that keeps language switching, history, settings, and run stats visible while letting the workflow strip sit near the top of the app.
- Made the whole setup/run panel collapsible from the top navigation so the review board can reclaim vertical space without losing the folder/run controls.
- Added a Qwen key check button that queries the NewCoin balance endpoint and reports valid-key count plus total, used, and remaining quota without printing or committing keys.
- Extended Qwen queue failure state so failures keep the last provider error in the status tooltip instead of showing only a red count.
- Added Qt click-path regression coverage for the settings toggle and kept the top navigation visible in review mode.
- Verification: `python -m pytest -q` passed with 57 tests, `python scripts/ui_smoke.py --output outputs/ui_smoke --language zh --records 24` passed, and a live key check reported 2 valid keys with about ¥24.699 remaining.
- Live Qwen smoke with 2 local RAW files and Top-1 completed with one grouped non-winner skipped and one Qwen `done`, confirming the current API chain is not globally failing.

## 2026-05-12 - VSCode-style navigation and full settings workspace
- Reworked the desktop chrome into a thin VSCode-style menu strip: the visible LumaSift wordmark, decorative subtitle, and scanned/shown/selected/mode cards were removed from the main canvas.
- Kept language switching in the top strip and moved operational state into tooltips and contextual controls instead of permanent summary cards.
- Changed the setup workspace so opening settings shows the full local/Qwen/run configuration directly; the nested advanced expand/collapse path was removed.
- Sharpened the constructivist UI language with square panels, hard borders, lower vertical chrome, and denser review action controls.
- Replaced text-heavy review decisions with compact geometric glyphs and Qt standard icons with tooltips for keep, maybe, reject, editing advice, output folder, and contact sheet.
- Updated desktop regression tests and UI smoke so the full settings workspace is visible by default and the review action strip remains compact after cockpit scrolling.
- Verification: `python -m pytest -q` passed with 57 tests, `python scripts/ui_smoke.py --output outputs/ui_smoke --language zh --records 24` passed, `packaging/build_windows.ps1` rebuilt `dist/LumaSift` and `dist/installer/LumaSiftSetup.exe`, and the packaged exe launched successfully in an offscreen smoke.

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

# LumaSift Executable Backlog

This file defines how planning-agent reviews become executable engineering work.

## Operating Rule

Planning and review agents do not directly change the execution direction. Their output must be converted into `docs/backlog.json` first.

The project goal is defined in `GOAL.md`. When the user says `继续 goal`, the main developer loop is:

1. Read `GOAL.md`.
2. Read `docs/backlog.json`.
3. Run `python scripts/backlog.py goal` or `python scripts/backlog.py next`.
4. Execute exactly one highest-priority unblocked item.
5. Run tests.
6. Run `python scripts/ui_smoke.py` after every UI change.
7. Inspect `outputs/ui_smoke/ui_smoke_report.json`, `outputs/ui_smoke/ui_smoke_report.md`, and relevant screenshots.
8. Update `docs/backlog.json` and `docs/DEVELOPMENT_LOG.md`.
9. Rebuild the Windows executable and installer for UI/product behavior changes.
10. Commit and push.
11. Report the result and the next recommended task.

## Status Values

- `todo`: ready to execute when dependencies are done.
- `in_progress`: currently owned by the main developer loop.
- `blocked`: cannot proceed without a concrete external dependency.
- `done`: implemented, tested, and pushed.

## Priority Scale

- `P0`: blocks product usability or future architecture.
- `P1`: high-value product or resume feature.
- `P2`: polish, packaging, or commercial hardening.
- `P3`: optional future work.

## Current Execution Policy

The next task is selected by:

1. lowest numeric priority;
2. unblocked dependencies;
3. highest user/product value;
4. smallest safe implementation slice.

The main loop should not jump to signing, auto-update, or commercial licensing before the core review workflow can handle large local folders, visible model queues, user labels, and evaluation metrics.

## UI Smoke Gate

`scripts/ui_smoke.py` is the required visual regression harness for the desktop app. It creates setup-collapsed, setup-expanded, and review-mode screenshots, then checks key widget geometry so compressed controls fail automatically.

Expected command:

```powershell
python scripts/ui_smoke.py
```

Expected outputs:

- `outputs/ui_smoke/setup_collapsed.png`
- `outputs/ui_smoke/setup_expanded.png`
- `outputs/ui_smoke/review_with_records.png`
- `outputs/ui_smoke/ui_smoke_report.json`
- `outputs/ui_smoke/ui_smoke_report.md`

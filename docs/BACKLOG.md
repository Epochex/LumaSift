# LumaSift Executable Backlog

This file defines how planning-agent reviews become executable engineering work.

## Operating Rule

Planning and review agents do not directly change the execution direction. Their output must be converted into `docs/backlog.json` first.

The main developer loop is:

1. Ask planning/review agents for findings.
2. Convert accepted findings into backlog items.
3. Run `python scripts/backlog.py next`.
4. Execute exactly one highest-priority unblocked item.
5. Run tests and GUI/package checks appropriate to the item.
6. Mark the item `done` or `blocked`.
7. Commit and push.
8. Repeat from step 1 when more agent feedback exists.

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

# LumaSift Product Goal

## North Star

LumaSift v0.1 is a local-first graphical AI photo curation product for street, documentary, humanistic, and travel photography. It must be treated as a release candidate product, not a code demo.

The core user journey is:

1. Choose a local photo folder containing RAW/JPG/PNG files.
2. Run local pre-scoring quickly and safely.
3. Send only high-value compressed previews to a vision model when enabled.
4. Review ranked photos in a smooth visual board.
5. Mark keep/maybe/reject.
6. Multi-select promising photos.
7. Generate practical editing parameters and humanistic visual direction.
8. Export reports/contact sheets without exposing private RAW files.

## Product Principles

- Ordinary users must be able to complete the workflow without understanding implementation details.
- The first screen must guide action through layout and state, not long explanatory text.
- RAW originals stay local. Remote AI calls may receive only selected compressed previews.
- Story, human presence, decisive moment, emotional impact, visual tension, and edit potential are primary.
- Sharpness, exposure, noise, and technical quality are useful signals, not final artistic judgment.
- A technically imperfect image can rank high when it has strong documentary or street-photography value.
- Every costly or slow stage must show progress, status, retry/failure state, and safe cancellation behavior.
- Product decisions should optimize for friend-test usability and future commercial release.

## Required v0.1 Release Shape

- Windows graphical desktop app.
- One-click installer output.
- Stable startup and shutdown.
- Robust processing of 200+ real RAW photos in local mode.
- Qwen vision review for a small Top-N sample without blocking local results.
- Persistent labels and run state.
- Useful editing advice for selected photos.
- CSV/JSON/contact sheet exports.
- Crash logs and privacy-safe diagnostics.
- No API keys, private photos, generated outputs, databases, or RAW files committed to git.

## Development Loop

When the user says `继续 goal`, the agent must:

1. Read `GOAL.md`.
2. Read `docs/backlog.json`.
3. Choose the highest-priority unblocked unfinished task.
4. Execute the task directly.
5. Run tests and `python scripts/ui_smoke.py`.
6. Inspect the UI smoke screenshots/report and decide whether another UI fix is required.
7. Update `docs/backlog.json` and `docs/DEVELOPMENT_LOG.md`.
8. Rebuild the Windows executable and installer when the change affects product behavior or UI.
9. Commit and push.
10. Report what changed, verification results, and the next recommended task.

## UI Regression Rule

All UI changes must run:

```powershell
python scripts/ui_smoke.py
```

The script must produce screenshots and a report under `outputs/ui_smoke/`. The agent must inspect the generated report and, when relevant, screenshots before declaring the UI change done.

## Backlog Rule

Planning/review findings do not become execution unless they are recorded in `docs/backlog.json`. The backlog is the executable source of truth for `继续 goal`.

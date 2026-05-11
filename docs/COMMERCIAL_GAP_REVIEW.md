# Commercial Gap Review

This document tracks the gap between the current MVP and a mature commercial photo product.

## Current Commercial Weak Points

1. UI polish is functional but not yet premium.
   The current PySide6 interface is usable, but it still needs richer visual hierarchy, better empty states, thumbnails that feel like a professional photo grid, and clearer affordances for review/selection.

2. Progress feedback is basic.
   The app now exposes progress stages, but it still needs per-stage estimates, elapsed time, remaining time, and a visible queue for Qwen requests.

3. Large-grid performance needs virtualized/lazy rendering.
   The current grid limits display count, but a commercial app should virtualize thousands of thumbnails and load previews asynchronously.

4. API configuration is usable but not fully secure.
   Keys can be entered in the GUI and optionally saved locally. A production product should use Windows Credential Manager/macOS Keychain instead of plain application settings.

5. No installer yet.
   The current friend-test package is a portable PyInstaller build. A commercial release should add signed installers, auto-update, versioned releases, and crash diagnostics.

6. No formal evaluation dashboard yet.
   The ranking pipeline needs a small labeled evaluation set and metrics such as Precision@K and NDCG@K to prove selection quality.

7. No Lightroom/Capture One export integration yet.
   The app generates editing advice, but a mature workflow should export sidecar files or structured presets where possible.

8. Qwen prompt quality needs iterative real-photo evaluation.
   The Qwen loop works, but prompt versions should be evaluated on 100-300 labeled real photos.

## MVP Friend-Test Standard

The current goal is not full commercial launch. The goal is a friend-test build that can:

- run as a Windows desktop app without Python knowledge;
- scan a local RAW/JPG folder;
- rank photos;
- show a thumbnail grid;
- use Qwen only for Top-N;
- support multi-select;
- generate concrete editing advice;
- export CSV/JSON/Markdown/contact sheet;
- avoid committing private photos or keys.

## Next Product Milestones

1. Thumbnail worker and virtualized grid.
2. Better Qwen job queue UI.
3. SQLite manifest/cache instead of JSON-only cache.
4. Evaluation set and ranking metrics.
5. Signed Windows installer.
6. Product landing README and demo video.
7. Lightroom/Capture One export experiments.

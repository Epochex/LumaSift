# Cloud Workflow

Use Codex Cloud when you need to guide development from a phone or when the local desktop is unavailable.

## Recommended Setup

1. Connect GitHub repository `Epochex/LumaSift` in Codex Cloud.
2. Add secrets in the cloud project environment, not in the repository:
   - `LUMASIFT_VISION_API_BASE_URL`
   - `LUMASIFT_VISION_MODEL`
   - `LUMASIFT_VISION_API_KEYS`
3. Keep private photo datasets out of Git.
4. Use small anonymized sample images for tests.
5. Ask Codex Cloud to commit changes to a branch or open a PR.

## Local vs Cloud

- Local mode can access your Windows files, private ARW folders, and local generated outputs.
- Cloud mode can keep working while your computer is off, but only sees repository files and configured secrets.
- For real private photo analysis, either run locally or upload a deliberate small test set to a private, controlled location.

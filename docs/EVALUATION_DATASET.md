# LumaSift Evaluation Dataset

The evaluation dataset is a metadata export for measuring ranking quality. It never copies original photos, RAW files, previews, cache entries, API keys, or generated output folders.

## Format

Schema: `lumasift.eval_dataset.v1`

Fields:

- `photo_id`: stable 16-character hash of the normalized local path.
- `path`: local source path for private evaluation on the same machine.
- `user_label`: current LumaSift label: `keep`, `maybe`, or `reject`.
- `gold_label`: initial gold label, defaulting to `user_label`; edit this manually if you want stricter evaluation labels.
- `story_rank`: optional human rank within a small evaluation set.
- `notes`: optional reviewer notes.
- `split`: `train`, `dev`, `test`, or `unassigned`.
- `prompt_version`: prompt/model version being evaluated.
- `run_id`, `rank`, `score`, `category`, `updated_at`: context copied from SQLite label state.

## Export

```powershell
python scripts\export_eval_dataset.py --output outputs\eval\labels.json --prompt-version qwen-story-v1 --split dev
python scripts\export_eval_dataset.py --output outputs\eval\labels.csv --format csv --prompt-version qwen-story-v1 --split dev
```

Use `--db` to export from a non-default SQLite file.

## 100-300 Photo Workflow

1. Run LumaSift on a private local folder and review 100-300 diverse photos.
2. Mark clear winners as `keep`, ambiguous/story-dependent images as `maybe`, and weak images as `reject`.
3. Export JSON or CSV with `scripts\export_eval_dataset.py`.
4. Edit `gold_label`, `story_rank`, and `notes` in the exported metadata if the first-pass labels need refinement.
5. Keep the dataset under `outputs/` or another ignored private folder. Do not commit exported labels if paths are sensitive.
6. Use the exported metadata to compare local-only and Qwen prompt versions with ranking metrics.

## Metrics

Evaluate one or more `report.json` files against the exported labels:

```powershell
python scripts\evaluate_ranking.py --eval outputs\eval\labels.json --report outputs\local\report.json --report outputs\qwen\report.json --k 20 --output-json outputs\eval\metrics.json --output-md outputs\eval\metrics.md
```

The metrics output includes Precision@K, Recall@K, NDCG@K, MRR, label distribution, AI mode, prompt version, and observed Qwen model versions for each report.

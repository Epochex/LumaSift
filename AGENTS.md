# AGENTS.md

## Project

LumaSift is a story-first photo selection and editing-potential system for street, documentary, humanistic, and travel photography. Keep development focused on usable selection, ranking, and editing guidance.

Prioritize functional completeness and development speed over unnecessary process work. Use lightweight engineering safeguards only when they directly help long-running runs, reproducibility, data safety, or API cost control.

## Setup

- Prefer Python 3.11+ unless the project later specifies another runtime.
- If `requirements.txt` exists, install dependencies with: `python -m pip install -r requirements.txt`
- If `pyproject.toml` exists, follow the package manager declared there.

## Checks

- Run tests with `pytest` when tests are present.
- Run `python scripts/run_demo.py` after changing the main pipeline.
- Run formatters or linters only when they are already configured in the repository.

## Data Handling

- Do not commit `.env` files, API keys, private photos, raw datasets, model weights, databases, or generated output folders.
- Use small anonymized sample files only when tests or examples require image input.

## Product Priority

- Primary value: story, human/documentary value, decisive moment, emotional impact, visual tension, and editing potential.
- Secondary value: technical quality metrics used as cheap filters and recovery signals.
- Do not let conventional technical imperfection automatically bury a photo if it has humanistic or street-photography potential.

# AGENTS.md

## Project

LumaSift is a photo auto-analysis project. Keep changes focused, avoid committing private images or datasets, and do not add secrets to the repository.

## Setup

- Prefer Python 3.11+ unless the project later specifies another runtime.
- If `requirements.txt` exists, install dependencies with: `python -m pip install -r requirements.txt`
- If `pyproject.toml` exists, follow the package manager declared there.

## Checks

- Run tests with `pytest` when tests are present.
- Run formatters or linters only when they are already configured in the repository.

## Data Handling

- Do not commit `.env` files, API keys, private photos, raw datasets, model weights, databases, or generated output folders.
- Use small anonymized sample files only when tests or examples require image input.

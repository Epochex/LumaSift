from __future__ import annotations

import os
import sqlite3
import time
from pathlib import Path
from typing import Any, Iterable


VALID_USER_LABELS = {"keep", "maybe", "reject"}


def default_state_db_path() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    if base:
        return Path(base) / "LumaSift" / "lumasift.sqlite"
    return Path.home() / ".lumasift" / "lumasift.sqlite"


class LumaSiftStateDb:
    """Small local SQLite store for user labels and run history.

    The reports remain portable JSON/CSV files, while this database keeps the
    durable product state needed for review history, evaluation sets, and future
    personal preference learning.
    """

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_state_db_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def record_run(self, *, run_id: str, input_dir: str, output_dir: str, ai_mode: str, summary: dict[str, Any]) -> None:
        now = int(time.time())
        with self._connect() as conn:
            conn.execute(
                """
                insert into runs(run_id, input_dir, output_dir, ai_mode, scanned, processed, failed, created_at)
                values(?, ?, ?, ?, ?, ?, ?, ?)
                on conflict(run_id) do update set
                    input_dir=excluded.input_dir,
                    output_dir=excluded.output_dir,
                    ai_mode=excluded.ai_mode,
                    scanned=excluded.scanned,
                    processed=excluded.processed,
                    failed=excluded.failed
                """,
                (
                    run_id,
                    input_dir,
                    output_dir,
                    ai_mode,
                    int(summary.get("scanned", 0) or 0),
                    int(summary.get("processed", 0) or 0),
                    int(summary.get("failed", 0) or 0),
                    now,
                ),
            )

    def load_labels(self, paths: Iterable[str | Path]) -> dict[str, str]:
        normalized = [self._normalize_path(path) for path in paths]
        if not normalized:
            return {}
        labels: dict[str, str] = {}
        with self._connect() as conn:
            for start in range(0, len(normalized), 500):
                chunk = normalized[start : start + 500]
                placeholders = ",".join("?" for _ in chunk)
                rows = conn.execute(
                    f"select path, user_label from photos where path in ({placeholders}) and user_label is not null",
                    chunk,
                ).fetchall()
                labels.update({str(row["path"]): str(row["user_label"]) for row in rows})
        return labels

    def set_user_label(
        self,
        *,
        path: str | Path,
        label: str | None,
        run_id: str | None = None,
        rank: int | None = None,
        score: float | None = None,
        category: str | None = None,
    ) -> None:
        if label is not None and label not in VALID_USER_LABELS:
            raise ValueError(f"Unsupported user label: {label}")
        now = int(time.time())
        normalized = self._normalize_path(path)
        with self._connect() as conn:
            conn.execute(
                """
                insert into photos(path, user_label, run_id, rank, score, category, updated_at)
                values(?, ?, ?, ?, ?, ?, ?)
                on conflict(path) do update set
                    user_label=excluded.user_label,
                    run_id=coalesce(excluded.run_id, photos.run_id),
                    rank=coalesce(excluded.rank, photos.rank),
                    score=coalesce(excluded.score, photos.score),
                    category=coalesce(excluded.category, photos.category),
                    updated_at=excluded.updated_at
                """,
                (normalized, label, run_id, rank, score, category, now),
            )

    def export_labeled_records(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                select path, user_label, run_id, rank, score, category, updated_at
                from photos
                where user_label is not null
                order by updated_at desc
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                create table if not exists runs(
                    run_id text primary key,
                    input_dir text not null,
                    output_dir text not null,
                    ai_mode text not null,
                    scanned integer not null default 0,
                    processed integer not null default 0,
                    failed integer not null default 0,
                    created_at integer not null
                )
                """
            )
            conn.execute(
                """
                create table if not exists photos(
                    path text primary key,
                    user_label text check(user_label in ('keep', 'maybe', 'reject') or user_label is null),
                    run_id text,
                    rank integer,
                    score real,
                    category text,
                    updated_at integer not null
                )
                """
            )
            conn.execute("create index if not exists idx_photos_user_label on photos(user_label)")
            conn.execute("create index if not exists idx_photos_run_id on photos(run_id)")

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("pragma journal_mode=WAL")
        conn.execute("pragma busy_timeout=5000")
        return conn

    def _normalize_path(self, path: str | Path) -> str:
        return str(Path(path).expanduser().resolve())

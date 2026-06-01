from __future__ import annotations

import os
import json
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
    """Small local SQLite store for user labels and reusable photo manifests.

    The reports remain portable JSON/CSV files, while this database keeps the
    durable product state needed for evaluation sets, preview reuse, API cache
    linkage, and future personal preference learning.
    """

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_state_db_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

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

    def load_manifest_record(self, path: str | Path) -> dict[str, Any] | None:
        normalized = self._normalize_path(path)
        with self._connect() as conn:
            row = conn.execute(
                """
                select path, size_bytes, mtime_ns, identity_hash, preview_path, last_run_id,
                       qwen_cache_key, technical_quality_score, final_selection_score,
                       visual_hash, visual_color, visual_scene_signature, group_id, group_size, group_rank, is_group_best,
                       group_best_path, group_score_delta,
                       scores_json, record_json, user_label, run_id, rank, score, category,
                       updated_at
                from photos
                where path = ?
                """,
                (normalized,),
            ).fetchone()
        return dict(row) if row is not None else None

    def reusable_record_for_file(self, path: str | Path) -> dict[str, Any] | None:
        normalized = self._normalize_path(path)
        try:
            stat = Path(normalized).stat()
        except OSError:
            return None
        row = self.load_manifest_record(normalized)
        if row is None:
            return None
        if int(row.get("size_bytes") or -1) != stat.st_size:
            return None
        if int(row.get("mtime_ns") or -1) != stat.st_mtime_ns:
            return None
        record_json = row.get("record_json")
        if not isinstance(record_json, str) or not record_json:
            return None
        try:
            record = json.loads(record_json)
        except json.JSONDecodeError:
            return None
        if not isinstance(record, dict):
            return None
        record["path"] = normalized
        if row.get("user_label"):
            record["user_label"] = row["user_label"]
        return record

    def upsert_photo_manifest(
        self,
        *,
        path: str | Path,
        size_bytes: int,
        mtime_ns: int,
        identity_hash: str,
        preview_path: str | Path | None = None,
        last_run_id: str | None = None,
        rank: int | None = None,
        score: float | None = None,
        category: str | None = None,
        technical_quality_score: float | None = None,
        qwen_cache_key: str | None = None,
        visual_hash: str | None = None,
        visual_color: str | None = None,
        visual_scene_signature: str | None = None,
        group_id: str | None = None,
        group_size: int | None = None,
        group_rank: int | None = None,
        is_group_best: bool | None = None,
        group_best_path: str | Path | None = None,
        group_score_delta: float | None = None,
        scores: dict[str, Any] | None = None,
        record: dict[str, Any] | None = None,
    ) -> None:
        now = int(time.time())
        normalized = self._normalize_path(path)
        preview = str(Path(preview_path).expanduser().resolve()) if preview_path else None
        group_best = str(Path(group_best_path).expanduser().resolve()) if group_best_path else None
        scores_json = json.dumps(scores or {}, ensure_ascii=False, sort_keys=True) if scores is not None else None
        record_json = json.dumps(record or {}, ensure_ascii=False, sort_keys=True) if record is not None else None
        with self._connect() as conn:
            conn.execute(
                """
                insert into photos(
                    path, size_bytes, mtime_ns, identity_hash, preview_path, last_run_id, run_id,
                    rank, score, category, technical_quality_score, final_selection_score,
                    qwen_cache_key, visual_hash, visual_color, visual_scene_signature, group_id, group_size, group_rank, is_group_best,
                    group_best_path, group_score_delta, scores_json, record_json, updated_at
                )
                values(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                on conflict(path) do update set
                    size_bytes=excluded.size_bytes,
                    mtime_ns=excluded.mtime_ns,
                    identity_hash=excluded.identity_hash,
                    preview_path=coalesce(excluded.preview_path, photos.preview_path),
                    last_run_id=coalesce(excluded.last_run_id, photos.last_run_id),
                    run_id=coalesce(excluded.last_run_id, photos.run_id),
                    rank=coalesce(excluded.rank, photos.rank),
                    score=coalesce(excluded.score, photos.score),
                    category=coalesce(excluded.category, photos.category),
                    technical_quality_score=coalesce(excluded.technical_quality_score, photos.technical_quality_score),
                    final_selection_score=coalesce(excluded.final_selection_score, photos.final_selection_score),
                    qwen_cache_key=coalesce(excluded.qwen_cache_key, photos.qwen_cache_key),
                    visual_hash=coalesce(excluded.visual_hash, photos.visual_hash),
                    visual_color=coalesce(excluded.visual_color, photos.visual_color),
                    visual_scene_signature=coalesce(excluded.visual_scene_signature, photos.visual_scene_signature),
                    group_id=coalesce(excluded.group_id, photos.group_id),
                    group_size=coalesce(excluded.group_size, photos.group_size),
                    group_rank=coalesce(excluded.group_rank, photos.group_rank),
                    is_group_best=coalesce(excluded.is_group_best, photos.is_group_best),
                    group_best_path=coalesce(excluded.group_best_path, photos.group_best_path),
                    group_score_delta=coalesce(excluded.group_score_delta, photos.group_score_delta),
                    scores_json=coalesce(excluded.scores_json, photos.scores_json),
                    record_json=coalesce(excluded.record_json, photos.record_json),
                    updated_at=excluded.updated_at
                """,
                (
                    normalized,
                    size_bytes,
                    mtime_ns,
                    identity_hash,
                    preview,
                    last_run_id,
                    last_run_id,
                    rank,
                    score,
                    category,
                    technical_quality_score,
                    score,
                    qwen_cache_key,
                    visual_hash,
                    visual_color,
                    visual_scene_signature,
                    group_id,
                    group_size,
                    group_rank,
                    int(is_group_best) if is_group_best is not None else None,
                    group_best,
                    group_score_delta,
                    scores_json,
                    record_json,
                    now,
                ),
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
            self._ensure_photo_manifest_columns(conn)
            conn.execute("create index if not exists idx_photos_user_label on photos(user_label)")
            conn.execute("create index if not exists idx_photos_run_id on photos(run_id)")
            conn.execute("create index if not exists idx_photos_last_run_id on photos(last_run_id)")
            conn.execute("create index if not exists idx_photos_identity_hash on photos(identity_hash)")
            conn.execute("create index if not exists idx_photos_qwen_cache_key on photos(qwen_cache_key)")
            conn.execute("create index if not exists idx_photos_visual_hash on photos(visual_hash)")
            conn.execute("create index if not exists idx_photos_visual_scene_signature on photos(visual_scene_signature)")
            conn.execute("create index if not exists idx_photos_group_id on photos(group_id)")
            conn.execute("create index if not exists idx_photos_is_group_best on photos(is_group_best)")

    def _ensure_photo_manifest_columns(self, conn: sqlite3.Connection) -> None:
        existing = {row["name"] for row in conn.execute("pragma table_info(photos)").fetchall()}
        columns = {
            "size_bytes": "integer",
            "mtime_ns": "integer",
            "identity_hash": "text",
            "preview_path": "text",
            "last_run_id": "text",
            "qwen_cache_key": "text",
            "visual_hash": "text",
            "visual_color": "text",
            "visual_scene_signature": "text",
            "group_id": "text",
            "group_size": "integer",
            "group_rank": "integer",
            "is_group_best": "integer",
            "group_best_path": "text",
            "group_score_delta": "real",
            "technical_quality_score": "real",
            "final_selection_score": "real",
            "scores_json": "text",
            "record_json": "text",
        }
        for name, definition in columns.items():
            if name not in existing:
                conn.execute(f"alter table photos add column {name} {definition}")

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("pragma journal_mode=WAL")
        conn.execute("pragma busy_timeout=5000")
        return conn

    def _normalize_path(self, path: str | Path) -> str:
        return str(Path(path).expanduser().resolve())

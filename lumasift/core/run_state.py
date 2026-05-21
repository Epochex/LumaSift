from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class RunEvent:
    event: str
    payload: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


class RunState:
    def __init__(self, run_dir: Path) -> None:
        self.run_dir = run_dir
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.events_path = self.run_dir / "events.jsonl"
        self.checkpoint_path = self.run_dir / "checkpoint.json"

    def append_event(self, event: str, **payload: Any) -> None:
        record = RunEvent(event=event, payload=payload)
        with self.events_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(asdict(record), ensure_ascii=False) + "\n")

    def save_checkpoint(self, data: dict[str, Any]) -> None:
        payload = json.dumps(data, ensure_ascii=False, indent=2)
        tmp_path = self.checkpoint_path.with_suffix(".tmp")
        tmp_path.write_text(payload, encoding="utf-8")
        try:
            tmp_path.replace(self.checkpoint_path)
        except PermissionError:
            return

    def load_checkpoint(self) -> dict[str, Any] | None:
        candidates = [
            self.checkpoint_path,
            self.checkpoint_path.with_suffix(".tmp"),
        ]
        best: tuple[float, dict[str, Any]] | None = None
        for path in candidates:
            if not path.exists():
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                continue
            if not isinstance(data, dict):
                continue
            try:
                mtime = path.stat().st_mtime
            except OSError:
                mtime = 0
            if best is None or mtime > best[0]:
                best = (mtime, data)
        return best[1] if best is not None else None

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

from lumasift.core.run_state import RunState


def test_load_checkpoint_prefers_newer_tmp(tmp_path: Path) -> None:
    state = RunState(tmp_path)
    state.checkpoint_path.write_text(json.dumps({"last_index": 1}), encoding="utf-8")

    tmp_checkpoint = state.checkpoint_path.with_suffix(".tmp")
    tmp_checkpoint.write_text(json.dumps({"last_index": 2}), encoding="utf-8")

    future = time.time() + 5
    os.utime(tmp_checkpoint, (future, future))

    assert state.load_checkpoint() == {"last_index": 2}


def test_load_checkpoint_uses_tmp_when_main_is_corrupted(tmp_path: Path) -> None:
    state = RunState(tmp_path)
    state.checkpoint_path.write_text("{", encoding="utf-8")

    tmp_checkpoint = state.checkpoint_path.with_suffix(".tmp")
    tmp_checkpoint.write_text(json.dumps({"run_id": "r1", "last_index": 7}), encoding="utf-8")

    assert state.load_checkpoint() == {"run_id": "r1", "last_index": 7}


def test_save_checkpoint_permission_error_leaves_tmp_for_recovery(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    state = RunState(tmp_path)

    def locked_replace(self: Path, target: Path) -> Path:  # noqa: ARG001
        raise PermissionError("locked")

    monkeypatch.setattr(Path, "replace", locked_replace)

    state.save_checkpoint({"last_index": 9})

    assert not state.checkpoint_path.exists()
    assert state.checkpoint_path.with_suffix(".tmp").exists()
    assert state.load_checkpoint() == {"last_index": 9}

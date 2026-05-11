from __future__ import annotations

from pathlib import Path

import pytest
import requests

from lumasift.analysis import qwen_client
from lumasift.analysis.qwen_client import QwenVisionClient
from lumasift.analysis.qwen_story import extract_qwen_response_text
from lumasift.core.keyring import ApiKeyRing


class FakeResponse:
    def __init__(self, status_code: int, payload: dict | None = None, text: str = "") -> None:
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def json(self) -> dict:
        return self._payload


def test_qwen_client_uses_persistent_cache_before_requiring_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    image_path = tmp_path / "image.jpg"
    image_path.write_bytes(b"stable image bytes")
    cache_dir = tmp_path / "qwen-cache"
    calls = 0
    payload = {
        "model": "qwen-test",
        "authorization": "Bearer should-not-be-stored",
        "choices": [{"message": {"content": '{"final_selection_score": 88}'}}],
    }

    def fake_post(*args: object, **kwargs: object) -> FakeResponse:
        nonlocal calls
        calls += 1
        return FakeResponse(200, payload=payload)

    monkeypatch.setattr(qwen_client.requests, "post", fake_post)
    client = QwenVisionClient(
        base_url="https://example.test/v1",
        model="qwen-test",
        keyring=ApiKeyRing(["live-key"]),
        cache_dir=cache_dir,
        sleep=lambda _: None,
    )

    first = client.analyze_image(image_path, "prompt", prompt_version="story-v1")
    cached_client = QwenVisionClient(
        base_url="https://example.test/v1",
        model="qwen-test",
        keyring=ApiKeyRing([]),
        cache_dir=cache_dir,
        sleep=lambda _: None,
    )
    second = cached_client.analyze_image(image_path, "prompt", prompt_version="story-v1")

    assert first == second
    assert calls == 1
    cache_text = next(cache_dir.glob("*.json")).read_text(encoding="utf-8")
    assert "should-not-be-stored" not in cache_text
    assert "[redacted]" in cache_text


def test_qwen_client_retries_transient_status_with_backoff(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    image_path = tmp_path / "image.jpg"
    image_path.write_bytes(b"retry image bytes")
    responses = [
        FakeResponse(503, text="temporary overload"),
        FakeResponse(200, payload={"model": "qwen-test", "choices": [{"message": {"content": "{}"}}]}),
    ]
    sleeps: list[float] = []

    def fake_post(*args: object, **kwargs: object) -> FakeResponse:
        return responses.pop(0)

    monkeypatch.setattr(qwen_client.requests, "post", fake_post)
    monkeypatch.setattr(qwen_client.random, "uniform", lambda start, stop: 0.0)
    client = QwenVisionClient(
        base_url="https://example.test/v1",
        model="qwen-test",
        keyring=ApiKeyRing(["live-key"]),
        cache_dir=tmp_path / "cache",
        initial_backoff_seconds=0.25,
        sleep=sleeps.append,
    )

    response = client.analyze_image(image_path, "prompt", prompt_version="story-v1")

    assert response["model"] == "qwen-test"
    assert sleeps == [0.25]
    assert responses == []


def test_extract_qwen_response_text_handles_multimodal_content() -> None:
    response = {
        "choices": [
            {
                "message": {
                    "content": [
                        {"type": "text", "text": '{"storytelling_score": 91}'},
                        {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,abc"}},
                    ]
                }
            }
        ]
    }

    assert extract_qwen_response_text(response) == '{"storytelling_score": 91}'


def test_extract_qwen_response_text_reports_missing_text() -> None:
    with pytest.raises(ValueError, match="text content"):
        extract_qwen_response_text({"choices": []})

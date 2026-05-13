from __future__ import annotations

from pathlib import Path

import pytest
import requests

from lumasift.analysis import qwen_client
from lumasift.analysis.qwen_client import QwenVisionClient
from lumasift.analysis.qwen_story import (
    build_qwen_story_prompt,
    extract_qwen_response_text,
    merge_qwen_story_analysis,
    parse_qwen_story_response,
)
from lumasift.core.keyring import ApiKeyRing
from lumasift.storage.qwen_cache import QwenResponseCache, identify_image


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
    assert cached_client.last_cache_hit is True
    assert cached_client.last_cache_key_digest
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


def test_qwen_client_retries_malformed_json_and_skips_bad_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    image_path = tmp_path / "image.jpg"
    image_path.write_bytes(b"malformed response image bytes")
    cache_dir = tmp_path / "cache"
    cache = QwenResponseCache(cache_dir)
    image_identity = identify_image(image_path)
    key = cache.make_key(image_identity, "qwen-test", "story-v1")
    cache.store(
        key,
        image_identity,
        {"model": "qwen-test", "choices": [{"message": {"content": '{"final_selection_score": 91'}}]},
    )
    responses = [
        FakeResponse(
            200,
            payload={"model": "qwen-test", "choices": [{"message": {"content": '{"final_selection_score": 92'}}]},
        ),
        FakeResponse(
            200,
            payload={"model": "qwen-test", "choices": [{"message": {"content": '{"final_selection_score": 93}'}}]},
        ),
    ]
    events: list[dict] = []

    def fake_post(*args: object, **kwargs: object) -> FakeResponse:
        return responses.pop(0)

    monkeypatch.setattr(qwen_client.requests, "post", fake_post)
    monkeypatch.setattr(qwen_client.random, "uniform", lambda start, stop: 0.0)
    client = QwenVisionClient(
        base_url="https://example.test/v1",
        model="qwen-test",
        keyring=ApiKeyRing(["live-key"]),
        cache_dir=cache_dir,
        initial_backoff_seconds=0.1,
        sleep=lambda _: None,
        event_callback=events.append,
        response_validator=lambda response: parse_qwen_story_response(response),
    )

    response = client.analyze_image(image_path, "prompt", prompt_version="story-v1")

    assert parse_qwen_story_response(response)["final_selection_score"] == 93
    assert len(responses) == 0
    assert any(event["type"] == "cache_invalid" for event in events)
    assert any(event["type"] == "retrying" and event["reason"] == "malformed_json" for event in events)


def test_qwen_client_caps_non_stream_tokens_and_retries_truncated_response(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    image_path = tmp_path / "image.jpg"
    image_path.write_bytes(b"truncated response image bytes")
    requests_payloads: list[dict] = []
    responses = [
        FakeResponse(
            200,
            payload={
                "model": "qwen-test",
                "choices": [{"finish_reason": "length", "message": {"content": '{"final_selection_score": 92}'}}],
            },
        ),
        FakeResponse(200, payload={"model": "qwen-test", "choices": [{"message": {"content": '{"final_selection_score": 93}'}}]}),
    ]
    events: list[dict] = []

    def fake_post(*args: object, **kwargs: object) -> FakeResponse:
        requests_payloads.append(kwargs["json"])
        return responses.pop(0)

    monkeypatch.setattr(qwen_client.requests, "post", fake_post)
    monkeypatch.setattr(qwen_client.random, "uniform", lambda start, stop: 0.0)
    client = QwenVisionClient(
        base_url="https://example.test/v1",
        model="qwen-test",
        keyring=ApiKeyRing(["live-key"]),
        cache_dir=tmp_path / "cache",
        max_tokens=8192,
        sleep=lambda _: None,
        event_callback=events.append,
        response_validator=lambda response: parse_qwen_story_response(response),
    )

    response = client.analyze_image(image_path, "prompt", prompt_version="story-v1")

    assert parse_qwen_story_response(response)["final_selection_score"] == 93
    assert [payload["max_tokens"] for payload in requests_payloads] == [4096, 4096]
    assert any(event["type"] == "max_tokens_capped" and event["used"] == 4096 for event in events)
    assert any(event["type"] == "retrying" and event["reason"] == "malformed_json" for event in events)


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


def test_qwen_prompt_requires_visible_story_evidence() -> None:
    prompt = build_qwen_story_prompt(
        {
            "filename": "frame.arw",
            "group_size": 3,
            "group_rank": 1,
            "is_group_best": True,
            "local_metrics": {"brightness": 118.2, "contrast": 42.1},
        }
    )

    assert "visible_evidence" in prompt
    assert "subject_relationship" in prompt
    assert "decisive_moment_read" in prompt
    assert "why_this_frame" in prompt
    assert "sequence_comparison" in prompt
    assert "selection_risk" in prompt
    assert "advanced_lightroom_parameters" in prompt
    assert "visible_inventory" in prompt
    assert "editing_plan" in prompt
    assert "analysis_quality" in prompt
    assert "不要写“画面有故事感”" in prompt
    assert "frame.arw" in prompt
    assert "group_size" in prompt


def test_merge_qwen_story_analysis_preserves_evidence_fields() -> None:
    record: dict[str, object] = {}
    response = {
        "model": "qwen-test",
        "choices": [
            {
                "message": {
                    "content": """
                    {
                      "final_selection_score": 88,
                      "visible_evidence": ["行人被车流和招牌夹在中间"],
                      "visible_inventory": {"main_subject": "路口中的行人"},
                      "subject_relationship": "人物和街道标识形成城市压力关系",
                      "decisive_moment_read": "人物刚进入路口，遮挡还没有破坏动作",
                      "moment_status": "strong",
                      "sequence_comparison": "比相似帧更完整地保留人物与车辆间距",
                      "selection_risk": "边缘车辆可能抢走注意力",
                      "edit_vs_select_warning": "遮挡若压住主体只能换帧",
                      "why_this_frame": "这一帧比邻近帧更清楚地保留了行人与车辆的间距",
                      "avoid_overediting": "不要抹掉街道颗粒和招牌信息",
                      "editing_plan": {"edit_intent": "突出行人与车流间距"},
                      "why_keep": ["具体动作和环境关系同时成立"],
                      "why_deprioritize": ["边缘车辆略抢眼"]
                    }
                    """
                }
            }
        ],
    }

    merge_qwen_story_analysis(record, response)

    assert record["visible_evidence"] == ["行人被车流和招牌夹在中间"]
    assert record["visible_inventory"] == {"main_subject": "路口中的行人"}
    assert record["subject_relationship"] == "人物和街道标识形成城市压力关系"
    assert record["moment_status"] == "strong"
    assert record["sequence_comparison"].startswith("比相似帧")
    assert record["selection_risk"] == "边缘车辆可能抢走注意力"
    assert record["edit_vs_select_warning"] == "遮挡若压住主体只能换帧"
    assert record["why_this_frame"].startswith("这一帧")
    assert record["editing_plan"] == {"edit_intent": "突出行人与车流间距"}
    assert record["analysis_source"] == "qwen_vision"
    assert record["analysis_quality"] in {"concrete", "weak"}
    assert record["avoid_overediting"] == "不要抹掉街道颗粒和招牌信息"
    assert record["positive_reasons"] == ["具体动作和环境关系同时成立"]


def test_merge_qwen_story_analysis_repairs_common_llm_json_formatting() -> None:
    record: dict[str, object] = {}
    response = {
        "model": "qwen-test",
        "choices": [
            {
                "message": {
                    "content": """
                    ```json
                    {
                      "final_selection_score": 88
                      "category": "strong_edit_candidate",
                      "visible_evidence": ["左侧行人与背景招牌同框"],
                    }
                    ```
                    """
                }
            }
        ],
    }

    merge_qwen_story_analysis(record, response)

    assert record["final_selection_score"] == 88
    assert record["category"] == "strong_edit_candidate"
    assert record["visible_evidence"] == ["左侧行人与背景招牌同框"]

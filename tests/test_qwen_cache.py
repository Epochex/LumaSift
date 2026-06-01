from __future__ import annotations

import json
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
    validate_qwen_story_response,
)
from lumasift.core.keyring import ApiKeyRing
from lumasift.storage.qwen_cache import QwenResponseCache, identify_image, prompt_fingerprint


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


def _qwen_response_from_data(data: dict) -> dict:
    return {"choices": [{"message": {"content": json.dumps(data, ensure_ascii=False)}}]}


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
    key = cache.make_key(image_identity, "qwen-test", f"story-v1:{prompt_fingerprint('prompt')}")
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


def test_qwen_client_records_validation_failure_diagnostics(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    image_path = tmp_path / "image.jpg"
    image_path.write_bytes(b"weak response image bytes")
    events: list[dict] = []

    def fake_post(*args: object, **kwargs: object) -> FakeResponse:
        return FakeResponse(
            200,
            payload={
                "model": "qwen-test",
                "choices": [{"message": {"content": '{"analysis_quality":"weak","professional_review":{}}'}}],
            },
        )

    monkeypatch.setattr(qwen_client.requests, "post", fake_post)
    client = QwenVisionClient(
        base_url="https://example.test/v1",
        model="qwen-test",
        keyring=ApiKeyRing(["live-key"]),
        cache_dir=tmp_path / "cache",
        max_retries=0,
        sleep=lambda _: None,
        event_callback=events.append,
        response_validator=lambda response: (_ for _ in ()).throw(ValueError("professional_review too generic")),
    )

    with pytest.raises(RuntimeError, match="professional_review too generic"):
        client.analyze_image(image_path, "prompt", prompt_version="story-v1")

    assert client.last_failure_kind == "weak_response"
    assert "professional_review too generic" in client.last_failure_message
    assert "analysis_quality" in client.last_invalid_response_excerpt


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
    assert "crop_box" in prompt
    assert "x/y/width/height" in prompt
    assert "analysis_quality" in prompt
    assert "professional_review" in prompt
    assert "review_depth_self_check" in prompt
    assert "evidence_chain" in prompt
    assert "critical_flaws" in prompt
    assert "hallucination_checks" in prompt
    assert '"people"' in prompt
    assert "资深图片编辑" in prompt
    assert "不要写“画面有故事感”" in prompt
    assert "前景米色背包遮住下方人物" not in prompt
    assert "frame.arw" in prompt
    assert "group_size" in prompt
    assert "118.2" not in prompt
    assert "42.1" not in prompt
    assert '"local_metrics"' not in prompt
    assert '"local_final_selection_score"' not in prompt


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
                      "evidence_chain": [{"evidence": "行人被车流和招牌夹在中间", "editorial_meaning": "城市压力具体", "selection_effect": "加分"}],
                      "professional_review": {
                        "editorial_summary": "路口中的行人被车辆和招牌夹住，城市压力比普通街景更具体，值得进入候选。",
                        "story_read": "人物刚进入路口，与车辆间距还没被遮挡破坏，街道标识提供了明确城市语境。",
                        "composition_read": "边缘车辆有干扰，但中间人物和路口关系仍可读，裁切应压低边缘抢眼部分。",
                        "selection_logic": "如果相邻帧保留更完整的人车间距，应优先比较；这一帧目前具备待保留价值。",
                        "editing_logic": "后期应强化人物与车流间距，保留招牌和街道颗粒，不要把现场修得过干净。",
                        "final_recommendation": "保留候选，优先做克制纪实彩色。"
                      },
                      "visible_inventory": {"main_subject": "路口中的行人"},
                      "subject_relationship": "人物和街道标识形成城市压力关系",
                      "decisive_moment_read": "人物刚进入路口，遮挡还没有破坏动作",
                      "moment_status": "strong",
                      "sequence_comparison": "比相似帧更完整地保留人物与车辆间距",
                      "selection_risk": "边缘车辆可能抢走注意力",
                      "edit_vs_select_warning": "遮挡若压住主体只能换帧",
                      "why_this_frame": "这一帧比邻近帧更清楚地保留了行人与车辆的间距",
                      "avoid_overediting": "不要抹掉街道颗粒和招牌信息",
                      "editing_plan": {
                        "edit_intent": "突出行人与车流间距",
                        "crop_plan": {
                          "aspect_ratio": "3:2",
                          "keep": ["行人", "路口"],
                          "remove_or_reduce": ["边缘车辆"],
                          "crop_box": {"x": 0.10, "y": 0.05, "width": 0.80, "height": 0.90, "reason": "压低边缘车辆并保留人车关系"}
                        }
                      },
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
    assert record["evidence_chain"][0]["selection_effect"] == "加分"
    assert record["professional_review"]["editorial_summary"].startswith("路口中的行人")
    assert record["visible_inventory"] == {"main_subject": "路口中的行人"}
    assert record["subject_relationship"] == "人物和街道标识形成城市压力关系"
    assert record["moment_status"] == "strong"
    assert record["sequence_comparison"].startswith("比相似帧")
    assert record["selection_risk"] == "边缘车辆可能抢走注意力"
    assert record["edit_vs_select_warning"] == "遮挡若压住主体只能换帧"
    assert record["why_this_frame"].startswith("这一帧")
    assert record["editing_plan"]["crop_plan"]["crop_box"]["x"] == 0.10
    assert record["editing_plan"]["crop_plan"]["crop_box"]["reason"] == "压低边缘车辆并保留人车关系"
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


def test_validate_qwen_story_response_rejects_fragmented_generic_output() -> None:
    response = {
        "choices": [
            {
                "message": {
                    "content": """
                    {
                      "final_selection_score": 86,
                      "visible_evidence": ["画面有故事感"],
                      "story_interpretation": "主体关系清晰"
                    }
                    """
                }
            }
        ]
    }

    with pytest.raises(ValueError, match="too generic|professional_review"):
        validate_qwen_story_response(response)


def test_validate_qwen_story_response_rejects_keyword_template_output() -> None:
    response = _qwen_response_from_data(
        {
            "editorial_verdict": {
                "action": "keep",
                "confidence": 78,
                "one_line_reason": "前景人物和背景街道形成清晰关系，画面具有现场感",
            },
            "professional_review": {
                "editorial_summary": "前景人物和背景街道形成关系，整体画面具有现场感和故事张力，适合进入候选。",
                "story_read": "左侧人物与右侧车辆形成层次，主体关系清晰，具备一定街头叙事价值。",
                "composition_read": "前景、背景和街道元素形成空间关系，边缘元素没有明显破坏画面成立。",
                "selection_logic": "这一帧的人物关系和环境层次更完整，因此可以作为候选照片保留。",
                "editing_logic": "后期强化主体与背景街道的关系，适度提升层次并保留现场感。",
            },
            "visible_evidence": [
                "前景人物和背景街道形成关系",
                "左侧人物与右侧车辆形成层次",
                "画面边缘元素提供现场感",
                "主体和环境关系清晰",
            ],
            "subject_relationship": "前景人物和背景街道形成清晰主体关系",
            "decisive_moment_read": "人物和车辆的瞬间关系较为完整",
            "score_rationales": {
                "storytelling_score": {"reason": "前景人物和背景街道形成关系", "evidence_ids": [0]},
                "human_documentary_value_score": {"reason": "主体和环境关系清晰", "evidence_ids": [3]},
                "decisive_moment_score": {"reason": "人物和车辆瞬间完整", "evidence_ids": [1]},
                "editing_potential_score": {"reason": "边缘元素提供现场感", "evidence_ids": [2]},
            },
            "editing_plan": {
                "edit_intent": "强化前景人物和背景街道的关系",
                "crop_plan": {
                    "keep": ["前景人物", "背景街道"],
                    "remove_or_reduce": ["边缘元素"],
                    "crop_box": {"x": 0, "y": 0, "width": 1, "height": 1, "reason": "保持主体关系"},
                },
                "local_masks": [{"target": "前景人物", "operation": "曝光 +0.2", "reason": "突出主体关系"}],
            },
        }
    )

    with pytest.raises(ValueError, match="generic|professional_review"):
        validate_qwen_story_response(response)


def test_validate_qwen_story_response_rejects_metric_driven_indecisive_review() -> None:
    response = {
        "choices": [
            {
                "message": {
                    "content": """
                    {
                      "editorial_verdict": {"action": "maybe", "confidence": 55, "one_line_reason": "左侧人物需确认是否成立"},
                      "professional_review": {
                        "editorial_summary": "brightness 88.7、contrast 72.2显示技术参数中等偏上，照片可能具有故事价值但需确认主体动作。",
                        "story_read": "作为story_candidate可能包含街头瞬间，但需确认人物互动、环境叙事或决定性瞬间。",
                        "composition_read": "从shadow_clipping_ratio推断空间可能可控，但边缘干扰仍需确认。",
                        "selection_logic": "local_final_selection_score中等偏上，若相邻帧更好应考虑替换。",
                        "editing_logic": "highlight_clipping_ratio轻微，可能通过后期修复，但主体关系需确认。"
                      },
                      "visible_evidence": ["brightness 88.7表明场景中高调", "contrast 72.2显示中高对比", "shadow_clipping_ratio 0.04暗部轻微损失"],
                      "subject_relationship": "需确认主体与环境关系",
                      "decisive_moment_read": "需确认瞬间是否成立",
                      "score_rationales": {
                        "storytelling_score": {"reason": "左侧人物可能有故事", "evidence_ids": [0]},
                        "human_documentary_value_score": {"reason": "背景可能有人文价值", "evidence_ids": [1]},
                        "decisive_moment_score": {"reason": "动作需确认", "evidence_ids": [2]},
                        "editing_potential_score": {"reason": "高光可修", "evidence_ids": [0]}
                      },
                      "editing_plan": {
                        "edit_intent": "处理左侧人物",
                        "crop_plan": {"keep": ["左侧人物"], "remove_or_reduce": ["边缘"], "crop_box": {"x": 0, "y": 0, "width": 1, "height": 1, "reason": "保留原图"}},
                        "local_masks": [{"target": "左侧人物", "operation": "曝光", "reason": "突出左侧人物"}]
                      }
                    }
                    """
                }
            }
        ]
    }

    with pytest.raises(ValueError, match="metric-driven|indecisive|generic"):
        validate_qwen_story_response(response)


def test_validate_qwen_story_response_rejects_metadata_disguised_as_deep_review() -> None:
    response = {
        "choices": [
            {
                "message": {
                    "content": """
                    {
                      "editorial_verdict": {"action": "keep", "confidence": 72, "one_line_reason": "group_rank=1说明组内最优"},
                      "professional_review": {
                        "editorial_summary": "DSC09927.ARW作为g0001组best帧，在亮度127、对比度55下呈现足够明暗结构。",
                        "story_read": "组照预筛将其定位为portfolio_candidate，暗示画面存在值得留存的人文叙事节点。",
                        "composition_read": "亮度127提供足够环境可见度，对比度55暗示空间层次可能存在于明暗交界处。",
                        "selection_logic": "同组7帧中本帧以group_rank=1胜出，local_final_selection_score达75分。",
                        "editing_logic": "高光裁切极低，texture与clarity的微调空间存在于低裁切保障的细节基础上。"
                      },
                      "visible_evidence": [
                        "亮度127：环境与主体有足够可见度",
                        "对比度55：存在可辨识的明暗层次",
                        "高光裁切1e-05：高光区域细节未丢失",
                        "local_final_selection_score=75：预筛系统认定具备收藏价值",
                        "group_rank=1：组内7帧中视觉质量最优"
                      ],
                      "subject_relationship": "主体可见性未经验证",
                      "decisive_moment_read": "实际画面需确认动作峰值与视线交汇",
                      "score_rationales": {
                        "storytelling_score": {"reason": "分数显示故事潜力", "evidence_ids": [0]},
                        "human_documentary_value_score": {"reason": "portfolio_candidate暗示内容价值", "evidence_ids": [1]},
                        "decisive_moment_score": {"reason": "moment_risk=false表示时间点稳定", "evidence_ids": [2]},
                        "editing_potential_score": {"reason": "高光裁切低所以可修", "evidence_ids": [3]}
                      },
                      "editing_plan": {
                        "edit_intent": "强化明暗层次",
                        "crop_plan": {"keep": ["原构图"], "remove_or_reduce": ["边缘杂光"], "crop_box": {"x": 0, "y": 0, "width": 1, "height": 1, "reason": "保留原构图"}},
                        "local_masks": [{"target": "主体", "operation": "曝光", "reason": "突出主体"}]
                      }
                    }
                    """
                }
            }
        ]
    }

    with pytest.raises(ValueError, match="metric-driven|indecisive|generic"):
        validate_qwen_story_response(response)


def test_validate_qwen_story_response_rejects_praise_only_without_critical_flaws() -> None:
    data = _valid_concrete_qwen_data()
    data["critical_flaws"] = ["暂无明显风险", "轻微可修"]
    data["why_deprioritize"] = []
    data["professional_review"]["editorial_summary"] = "红色钢梁和上方人物形成非常成功的结构，画面优秀且非常完整，是强烈作品候选。"

    with pytest.raises(ValueError, match="critical flaws|praise-heavy"):
        validate_qwen_story_response(_qwen_response_from_data(data))


def test_validate_qwen_story_response_rejects_unsupported_person_motion_claim() -> None:
    data = _valid_concrete_qwen_data()
    data["visible_inventory"] = {
        "main_subject": "红色钢梁和玻璃天窗",
        "people": [],
        "setting_context": ["工业建筑"],
        "gesture_expression_motion": ["没有可读人物动作"],
    }
    data["professional_review"]["story_read"] = "下方行人正在跨越平台并与上方人物形成动静互补，但这组动作被钢梁遮挡。"
    data["visible_evidence"][0] = "画面下方行人在黑色横梁旁行走，动作方向让工业空间更有故事"

    with pytest.raises(ValueError, match="unsupported person|human value"):
        validate_qwen_story_response(_qwen_response_from_data(data))


def test_validate_qwen_story_response_rejects_reported_unsupported_claims() -> None:
    data = _valid_concrete_qwen_data()
    data["hallucination_checks"]["unsupported_claims"] = ["下方行人动作看不清，不能作为确定事实"]

    with pytest.raises(ValueError, match="unsupported person"):
        validate_qwen_story_response(_qwen_response_from_data(data))


def test_validate_qwen_story_response_rejects_overstated_formal_photo_without_readable_person() -> None:
    data = _valid_concrete_qwen_data()
    data["storytelling_score"] = 78
    data["human_documentary_value_score"] = 76
    data["decisive_moment_score"] = 72
    data["category"] = "portfolio_candidate"
    data["editorial_verdict"]["action"] = "keep"
    data["visible_inventory"] = {
        "main_subject": "红色钢梁、玻璃天窗和金属网格",
        "people": [{"id": "u1", "region": "中部平台", "visibility": "uncertain", "pose_or_motion": "疑似人形但看不清", "confidence": 35}],
        "setting_context": ["工业建筑"],
        "gesture_expression_motion": ["看不清"],
    }

    with pytest.raises(ValueError, match="unsupported person|overstated story|human value"):
        validate_qwen_story_response(_qwen_response_from_data(data))


def test_validate_qwen_story_response_accepts_balanced_content_review() -> None:
    validate_qwen_story_response(_qwen_response_from_data(_valid_concrete_qwen_data()))


def _valid_concrete_qwen_data() -> dict:
    return {
        "analysis_source": "qwen_vision",
        "analysis_quality": "concrete",
        "editorial_verdict": {
            "action": "maybe",
            "confidence": 64,
            "one_line_reason": "画面上方站立人物被红色钢梁和网格包围，但面部不可读使人文判断受限",
        },
        "professional_review": {
            "editorial_summary": "红色钢梁和玻璃天窗给画面上方站立人物制造压迫结构，但人物面部不可读，作品性主要来自形式而非情节。",
            "story_read": "上方人物确实提供尺度参照，金属网格让空间更疏离；限制是没有表情和视线，故事只能停在环境观察。",
            "composition_read": "左侧红色斜梁能把视线带到上方人物，底部黑色横梁也压住画面；但网格过密会削弱人物可读性。",
            "selection_logic": "这帧可作为待定结构片保留比较，若相邻帧人物姿态或面部更清楚，应优先换掉这一帧。",
            "editing_logic": "后期可压高光并微提上方人物轮廓，但不能补出表情、视线或明确动作关系。",
            "final_recommendation": "待定，不直接升为作品候选；先比较同组是否有更可读的人物瞬间。",
        },
        "visible_inventory": {
            "main_subject": "上方站立人物和红色钢梁",
            "people": [{"id": "p1", "region": "画面上方偏右", "visibility": "clear", "pose_or_motion": "站立但面部不可读", "confidence": 82}],
            "setting_context": ["红色钢梁", "玻璃天窗", "金属网格"],
            "gesture_expression_motion": ["站立", "表情看不清"],
        },
        "visible_evidence": [
            "画面上方偏右的站立人物被红色钢梁包围，人物可见但面部不可读，因此故事分不能过高",
            "左侧红色斜梁从下往上切入画面，引导视线但也比人物更抢眼，选择上形成减分",
            "玻璃天窗大面积偏亮并压在人物背后，提供工业空间语境同时削弱轮廓细节",
            "金属网格覆盖人物和背景，制造疏离感但也让动作与表情更难读",
        ],
        "evidence_chain": [
            {"evidence": "上方偏右站立人物面部不可读", "editorial_meaning": "有人物尺度但没有明确情绪", "selection_effect": "减分"},
            {"evidence": "左侧红色斜梁强于人物", "editorial_meaning": "形式结构压过人文内容", "selection_effect": "减分"},
            {"evidence": "玻璃天窗和金属网格形成工业语境", "editorial_meaning": "环境可读但故事偏弱", "selection_effect": "加分"},
        ],
        "score_rationales": {
            "storytelling_score": {"reason": "上方人物被钢梁包围但面部不可读，故事只成立一半", "evidence_ids": [0]},
            "human_documentary_value_score": {"reason": "人物与工业空间有尺度关系，但缺少视线和表情", "evidence_ids": [0]},
            "decisive_moment_score": {"reason": "站立姿态稳定，不是决定性动作峰值", "evidence_ids": [0]},
            "editing_potential_score": {"reason": "红色钢梁和天窗可通过高光与局部对比整理", "evidence_ids": [2]},
        },
        "storytelling_score": 62,
        "human_documentary_value_score": 58,
        "decisive_moment_score": 45,
        "editing_potential_score": 78,
        "final_selection_score": 64,
        "category": "ordinary_record",
        "subject_relationship": "上方人物和红色钢梁形成尺度关系，但人物情绪与动作不可读",
        "decisive_moment_read": "瞬间偏弱，站立姿态没有明确动作峰值或视线关系",
        "moment_status": "weak",
        "critical_flaws": [
            "上方人物面部不可读，无法靠修图补出表情或视线",
            "红色钢梁比人物更抢眼，形式结构压过人文内容",
        ],
        "hallucination_checks": {"unsupported_claims": [], "uncertain_objects": ["中部平台暗部细节看不清"], "spatial_sanity_check": "可确认人物在上方偏右，没有确认画面下方行人"},
        "selection_risk": "人物情绪不可读，最终可能只是工业结构记录",
        "edit_vs_select_warning": "修图能整理钢梁和天窗，不能补出决定性瞬间",
        "why_this_frame": "保留为待定是因为上方人物与钢梁尺度关系清楚，但不是强作品候选",
        "frame_failure_reasons": ["人物面部不可读", "形式结构压过人文内容"],
        "why_keep": ["工业结构和人物尺度关系可读"],
        "why_deprioritize": ["缺少表情、视线和明确动作关系"],
        "editing_plan": {
            "edit_intent": "压住天窗高光并让上方人物轮廓更清楚",
            "crop_plan": {
                "keep": ["上方人物", "红色钢梁", "玻璃天窗"],
                "remove_or_reduce": ["底部暗部空白"],
                "crop_box": {"x": 0.04, "y": 0.02, "width": 0.90, "height": 0.94, "reason": "收紧边缘但保留工业空间尺度"},
            },
            "local_masks": [{"target": "上方人物轮廓", "operation": "阴影 +10", "reason": "只增强可见轮廓，不伪造表情"}],
        },
    }

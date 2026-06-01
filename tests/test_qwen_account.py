from __future__ import annotations

import requests

from lumasift.analysis.qwen_account import (
    choose_best_vision_model,
    format_balance_summary,
    format_vision_model_summary,
    query_newcoin_balances,
    query_vision_model_capabilities,
    recommended_qwen_vision_model,
    recommended_vision_model,
)


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


def fake_vision_probe_post(*args, **kwargs):  # noqa: ANN001
    return FakeResponse(
        200,
        {
            "choices": [
                {
                    "message": {
                        "content": '{"top_left_color":"cyan","top_right_shape":"circle","bottom_left_text":"K7","bottom_right_color":"yellow"}',
                    }
                }
            ]
        },
    )


def test_query_newcoin_balances_converts_credit_units(monkeypatch) -> None:
    def fake_get(*args, **kwargs):  # noqa: ANN001
        assert kwargs["headers"]["Authorization"] == "Bearer sk-test"
        return FakeResponse(
            200,
            {
                "code": True,
                "data": {
                    "total_granted": 2500000,
                    "total_available": 1250000,
                    "total_used": 1250000,
                },
            },
        )

    monkeypatch.setattr("lumasift.analysis.qwen_account.requests.get", fake_get)

    balances = query_newcoin_balances(["sk-test"])

    assert balances[0].total == 5.0
    assert balances[0].remaining == 2.5
    assert recommended_qwen_vision_model(balances) == "qwen3.6-plus"
    assert balances[0].supports_vision is True
    assert "剩余 ¥2.5000" in format_balance_summary(balances, language="zh")
    assert "视觉模型 qwen3.6-plus" in format_balance_summary(balances, language="zh")


def test_query_newcoin_balances_reports_all_key_failures(monkeypatch) -> None:
    def fake_get(*args, **kwargs):  # noqa: ANN001
        return FakeResponse(401, text="invalid key")

    monkeypatch.setattr("lumasift.analysis.qwen_account.requests.get", fake_get)

    try:
        query_newcoin_balances(["sk-bad"])
    except RuntimeError as exc:
        assert "key#1" in str(exc)
    else:
        raise AssertionError("expected failed balance query")


def test_openai_compatible_probe_selects_best_vision_model(monkeypatch) -> None:
    def fake_get(url, *args, **kwargs):  # noqa: ANN001
        if str(url).endswith("/models"):
            assert kwargs["headers"]["Authorization"] == "Bearer sk-test"
            return FakeResponse(
                200,
                {
                    "data": [
                        {"id": "text-embedding-3-large"},
                        {"id": "gpt-4o-mini"},
                        {"id": "gpt-4.1"},
                    ]
                },
            )
        return FakeResponse(404, text="not newcoin")

    monkeypatch.setattr("lumasift.analysis.qwen_account.requests.get", fake_get)
    monkeypatch.setattr("lumasift.analysis.qwen_account.requests.post", fake_vision_probe_post)

    capabilities = query_vision_model_capabilities(["sk-test"], base_url="https://api.example.test/v1")

    assert recommended_vision_model(capabilities) == "gpt-4.1"
    summary = format_vision_model_summary(capabilities, language="en")
    assert "LLM deep analysis model gpt-4.1" in summary
    assert "remaining tokens unknown" in summary


def test_auto_probe_tries_known_base_urls_until_models_work(monkeypatch) -> None:
    seen_urls: list[str] = []

    def fake_get(url, *args, **kwargs):  # noqa: ANN001
        seen_urls.append(str(url))
        if str(url) == "https://api.openai.com/v1/models":
            return FakeResponse(200, {"data": [{"id": "gpt-4o-mini"}, {"id": "gpt-4.1"}]})
        return FakeResponse(401, text='{"error":{"message":"invalid token for this endpoint"}}')

    monkeypatch.setattr("lumasift.analysis.qwen_account.requests.get", fake_get)
    monkeypatch.setattr("lumasift.analysis.qwen_account.requests.post", fake_vision_probe_post)

    capabilities = query_vision_model_capabilities(["sk-test"], base_url="")

    assert recommended_vision_model(capabilities) == "gpt-4.1"
    assert capabilities[0].base_url == "https://api.openai.com/v1"
    assert "https://api.newcoin.top/v1/models" in seen_urls
    assert "https://api.openai.com/v1/models" in seen_urls


def test_newcoin_probe_reports_tokens_and_credit_when_available(monkeypatch) -> None:
    def fake_get(url, *args, **kwargs):  # noqa: ANN001
        if str(url).endswith("/models"):
            return FakeResponse(200, {"data": [{"id": "qwen3.6-plus"}, {"id": "qwen3.5-plus"}]})
        return FakeResponse(
            200,
            {
                "code": True,
                "data": {
                    "total_granted": 2500000,
                    "total_available": 1250000,
                    "total_used": 1250000,
                },
            },
        )

    monkeypatch.setattr("lumasift.analysis.qwen_account.requests.get", fake_get)
    monkeypatch.setattr("lumasift.analysis.qwen_account.requests.post", fake_vision_probe_post)

    capabilities = query_vision_model_capabilities(["sk-test"], base_url="https://api.newcoin.top/v1")

    assert recommended_vision_model(capabilities) == "qwen3.6-plus"
    summary = format_vision_model_summary(capabilities, language="zh")
    assert "LLM深度分析模型 qwen3.6-plus" in summary
    assert "剩余 token 1,250,000" in summary
    assert "¥2.5000" in summary


def test_choose_best_vision_model_prefers_manual_supported_model() -> None:
    assert choose_best_vision_model(["gpt-4.1", "qwen3.6-plus"], preferred_model="gpt-4.1") == "gpt-4.1"


def test_newcoin_balance_fallback_must_pass_live_vision_probe(monkeypatch) -> None:
    def fake_get(url, *args, **kwargs):  # noqa: ANN001
        if str(url).endswith("/models"):
            return FakeResponse(503, text="models unavailable")
        return FakeResponse(
            200,
            {
                "code": True,
                "data": {
                    "total_granted": 2500000,
                    "total_available": 1250000,
                    "total_used": 1250000,
                },
            },
        )

    def blind_post(*args, **kwargs):  # noqa: ANN001
        return FakeResponse(
            200,
            {"choices": [{"message": {"content": '{"left_color":"red","right_color":"green"}'}}]},
        )

    monkeypatch.setattr("lumasift.analysis.qwen_account.requests.get", fake_get)
    monkeypatch.setattr("lumasift.analysis.qwen_account.requests.post", blind_post)

    try:
        query_vision_model_capabilities(["sk-test"], base_url="https://api.newcoin.top/v1")
    except RuntimeError as exc:
        assert "failed the live image-vision probe" in str(exc)
    else:
        raise AssertionError("expected blind provider recommendation to be rejected")

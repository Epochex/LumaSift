from __future__ import annotations

import requests

from lumasift.analysis.qwen_account import format_balance_summary, query_newcoin_balances, recommended_qwen_vision_model


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

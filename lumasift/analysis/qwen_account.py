from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests


NEWCOIN_BALANCE_URL = "https://cha.newcoin.tech/internal_query"
NEWCOIN_CREDIT_DIVISOR = 500000


@dataclass(frozen=True)
class QwenKeyBalance:
    key_index: int
    endpoint: str
    total: float
    remaining: float
    used: float


def query_newcoin_balance(api_key: str, *, timeout_seconds: int = 20) -> QwenKeyBalance:
    """Return the first successful NewCoin balance response for a Qwen-compatible key."""
    last_error = "no response"
    for endpoint in ("top", "tech"):
        try:
            response = requests.get(
                NEWCOIN_BALANCE_URL,
                params={"endpoint": endpoint},
                headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"},
                timeout=timeout_seconds,
            )
            if response.status_code in {401, 403}:
                last_error = _safe_error(response)
                continue
            response.raise_for_status()
            payload = response.json()
            if payload.get("code") is True and isinstance(payload.get("data"), dict):
                data: dict[str, Any] = payload["data"]
                return QwenKeyBalance(
                    key_index=1,
                    endpoint=endpoint,
                    total=_credit_value(data.get("total_granted")),
                    remaining=_credit_value(data.get("total_available")),
                    used=_credit_value(data.get("total_used")),
                )
            last_error = str(payload.get("message") or payload.get("error") or "invalid balance response")
        except requests.RequestException as exc:
            last_error = str(exc)
        except ValueError as exc:
            last_error = f"invalid JSON response: {exc}"
    raise RuntimeError(_compact_error(last_error))


def query_newcoin_balances(api_keys: list[str], *, timeout_seconds: int = 20) -> list[QwenKeyBalance]:
    balances: list[QwenKeyBalance] = []
    errors: list[str] = []
    for index, key in enumerate([item.strip() for item in api_keys if item.strip()], start=1):
        try:
            result = query_newcoin_balance(key, timeout_seconds=timeout_seconds)
            balances.append(
                QwenKeyBalance(
                    key_index=index,
                    endpoint=result.endpoint,
                    total=result.total,
                    remaining=result.remaining,
                    used=result.used,
                )
            )
        except Exception as exc:  # noqa: BLE001 - caller needs all key errors summarized.
            errors.append(f"key#{index}: {_compact_error(str(exc))}")
    if balances:
        return balances
    raise RuntimeError("; ".join(errors) if errors else "No Qwen API keys configured")


def format_balance_summary(balances: list[QwenKeyBalance], *, language: str = "zh") -> str:
    total = sum(item.total for item in balances)
    remaining = sum(item.remaining for item in balances)
    used = sum(item.used for item in balances)
    if language == "zh":
        return f"Key 有效：{len(balances)} 个；剩余 ¥{remaining:.4f} / 总额 ¥{total:.4f}；已用 ¥{used:.4f}"
    return f"Keys valid: {len(balances)}; remaining ¥{remaining:.4f} / total ¥{total:.4f}; used ¥{used:.4f}"


def _credit_value(value: Any) -> float:
    try:
        return round(float(value) / NEWCOIN_CREDIT_DIVISOR, 4)
    except (TypeError, ValueError):
        return 0.0


def _safe_error(response: requests.Response) -> str:
    text = response.text or ""
    if len(text) > 180:
        text = f"{text[:180]}..."
    return f"HTTP {response.status_code}: {text}"


def _compact_error(message: str) -> str:
    message = message.replace("\n", " ").replace("\r", " ").strip()
    return message[:240] + ("..." if len(message) > 240 else "")

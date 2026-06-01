from __future__ import annotations

import base64
import io
from dataclasses import dataclass
from typing import Any

import requests
from PIL import Image, ImageDraw


NEWCOIN_BALANCE_URL = "https://cha.newcoin.tech/internal_query"
NEWCOIN_CREDIT_DIVISOR = 500000
DEFAULT_VISION_BASE_URL = "https://api.newcoin.top/v1"
AUTO_VISION_BASE_URLS = (
    DEFAULT_VISION_BASE_URL,
    "https://api.newcoin.tech/v1",
    "https://api.openai.com/v1",
    "https://dashscope.aliyuncs.com/compatible-mode/v1",
)


@dataclass(frozen=True)
class QwenKeyBalance:
    key_index: int
    endpoint: str
    total: float
    remaining: float
    used: float
    recommended_model: str = "qwen3.6-plus"
    supports_vision: bool = True
    total_tokens: int | None = None
    remaining_tokens: int | None = None
    used_tokens: int | None = None


@dataclass(frozen=True)
class VisionModelCapability:
    key_index: int
    provider: str
    model: str
    supports_vision: bool
    base_url: str = ""
    remaining_tokens: int | None = None
    total_tokens: int | None = None
    used_tokens: int | None = None
    remaining_credit: float | None = None
    total_credit: float | None = None
    used_credit: float | None = None
    detail: str = ""


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
                    total_tokens=_token_value(data.get("total_granted")),
                    remaining_tokens=_token_value(data.get("total_available")),
                    used_tokens=_token_value(data.get("total_used")),
                    recommended_model=_recommended_model_for_endpoint(endpoint),
                    supports_vision=True,
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
                    recommended_model=result.recommended_model,
                    supports_vision=result.supports_vision,
                    total_tokens=result.total_tokens,
                    remaining_tokens=result.remaining_tokens,
                    used_tokens=result.used_tokens,
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
    model = recommended_qwen_vision_model(balances)
    if language == "zh":
        return f"Key 有效：{len(balances)} 个；视觉模型 {model}；剩余 ¥{remaining:.4f} / 总额 ¥{total:.4f}；已用 ¥{used:.4f}"
    return f"Keys valid: {len(balances)}; vision model {model}; remaining ¥{remaining:.4f} / total ¥{total:.4f}; used ¥{used:.4f}"


def recommended_qwen_vision_model(balances: list[QwenKeyBalance]) -> str:
    for balance in balances:
        if balance.supports_vision and balance.recommended_model:
            return balance.recommended_model
    return "qwen3.6-plus"


def query_vision_model_capabilities(
    api_keys: list[str],
    *,
    base_url: str = DEFAULT_VISION_BASE_URL,
    preferred_model: str = "",
    timeout_seconds: int = 20,
) -> list[VisionModelCapability]:
    capabilities: list[VisionModelCapability] = []
    errors: list[str] = []
    requested_base_url = base_url.strip().rstrip("/")
    candidate_base_urls = [requested_base_url] if requested_base_url else list(AUTO_VISION_BASE_URLS)
    for index, key in enumerate([item.strip() for item in api_keys if item.strip()], start=1):
        key_errors: list[str] = []
        for candidate_base_url in candidate_base_urls:
            try:
                models = query_openai_compatible_models(key, base_url=candidate_base_url, timeout_seconds=timeout_seconds)
                model = choose_best_vision_model(
                    models,
                    preferred_model=preferred_model,
                    api_key=key,
                    base_url=candidate_base_url,
                    timeout_seconds=timeout_seconds,
                )
                if not model:
                    raise RuntimeError("No suitable model passed the live image-vision probe")
                capability = VisionModelCapability(
                    key_index=index,
                    provider=_provider_name(candidate_base_url),
                    model=model,
                    supports_vision=True,
                    base_url=candidate_base_url,
                    detail=f"{len(models)} models detected",
                )
                balance = _try_newcoin_balance(key) if "newcoin" in candidate_base_url.lower() else None
                if balance is not None:
                    capability = VisionModelCapability(
                        key_index=index,
                        provider=f"NewCoin/{balance.endpoint}",
                        model=model,
                        supports_vision=True,
                        base_url=candidate_base_url,
                        remaining_tokens=balance.remaining_tokens,
                        total_tokens=balance.total_tokens,
                        used_tokens=balance.used_tokens,
                        remaining_credit=balance.remaining,
                        total_credit=balance.total,
                        used_credit=balance.used,
                        detail=f"{len(models)} models detected",
                    )
                capabilities.append(capability)
                break
            except Exception as exc:  # noqa: BLE001 - caller needs all key errors summarized.
                fallback = _try_newcoin_balance(key) if "newcoin" in candidate_base_url.lower() else None
                if fallback is not None:
                    if _probe_model_vision(
                        key,
                        base_url=candidate_base_url,
                        model=fallback.recommended_model,
                        timeout_seconds=timeout_seconds,
                    ):
                        capabilities.append(
                            VisionModelCapability(
                                key_index=index,
                                provider=f"NewCoin/{fallback.endpoint}",
                                model=fallback.recommended_model,
                                supports_vision=fallback.supports_vision,
                                base_url=candidate_base_url,
                                remaining_tokens=fallback.remaining_tokens,
                                total_tokens=fallback.total_tokens,
                                used_tokens=fallback.used_tokens,
                                remaining_credit=fallback.remaining,
                                total_credit=fallback.total,
                                used_credit=fallback.used,
                                detail="model list unavailable; provider recommendation passed live image-vision probe",
                            )
                        )
                        break
                    key_errors.append(
                        f"{_provider_name(candidate_base_url)}: provider recommendation failed the live image-vision probe"
                    )
                    continue
                key_errors.append(f"{_provider_name(candidate_base_url)}: {_compact_error(str(exc))}")
        if key_errors:
            errors.append(f"key#{index}: {' | '.join(key_errors)}")
    if capabilities:
        return capabilities
    raise RuntimeError("; ".join(errors) if errors else "No LLM Deep Analysis API keys configured")


def query_openai_compatible_models(api_key: str, *, base_url: str, timeout_seconds: int = 20) -> list[str]:
    models_url = f"{base_url.rstrip('/')}/models"
    response = requests.get(
        models_url,
        headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"},
        timeout=timeout_seconds,
    )
    if response.status_code in {401, 403}:
        raise RuntimeError(_safe_error(response))
    response.raise_for_status()
    payload = response.json()
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, list):
        raise RuntimeError("invalid /models response")
    models: list[str] = []
    for item in data:
        if isinstance(item, dict) and str(item.get("id") or "").strip():
            models.append(str(item["id"]).strip())
        elif isinstance(item, str) and item.strip():
            models.append(item.strip())
    if not models:
        raise RuntimeError("empty /models response")
    return models


def choose_best_vision_model(
    models: list[str],
    *,
    preferred_model: str = "",
    api_key: str = "",
    base_url: str = "",
    timeout_seconds: int = 20,
) -> str:
    normalized = [model for model in models if model.strip()]
    if preferred_model and preferred_model in normalized and _looks_like_vision_model(preferred_model) and _is_strong_preferred_vision_model(preferred_model):
        if not api_key or _probe_model_vision(api_key, base_url=base_url, model=preferred_model, timeout_seconds=timeout_seconds):
            return preferred_model
    ranked = sorted(
        (model for model in normalized if _looks_like_vision_model(model)),
        key=_vision_model_rank,
        reverse=True,
    )
    if not api_key:
        return ranked[0] if ranked else ""
    for model in ranked:
        if _probe_model_vision(api_key, base_url=base_url, model=model, timeout_seconds=timeout_seconds):
            return model
    return ""


def _probe_model_vision(api_key: str, *, base_url: str, model: str, timeout_seconds: int = 20) -> bool:
    if not api_key or not base_url or not model:
        return False
    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "Look at the attached test image. Return JSON only with keys: "
                            "top_left_color, top_right_shape, bottom_left_text, bottom_right_color. "
                            "Do not guess if you cannot see the image."
                        ),
                    },
                    {"type": "image_url", "image_url": {"url": _vision_probe_image_data_url()}},
                ],
            }
        ],
        "temperature": 0,
        "max_tokens": 80,
        "response_format": {"type": "json_object"},
    }
    try:
        response = requests.post(
            f"{base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
            timeout=timeout_seconds,
        )
        if response.status_code == 400:
            payload.pop("response_format", None)
            response = requests.post(
                f"{base_url.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json=payload,
                timeout=timeout_seconds,
            )
        if response.status_code in {401, 403}:
            return False
        response.raise_for_status()
        text = _response_text(response.json()).lower()
    except Exception:  # noqa: BLE001 - failed probe means the model is not safe to auto-select.
        return False
    left_ok = any(token in text for token in ("cyan", "青", "青色", "blue-green", "蓝绿"))
    shape_ok = any(token in text for token in ("circle", "圆", "圆形"))
    text_ok = "k7" in text or "k 7" in text or "k-7" in text
    right_ok = any(token in text for token in ("yellow", "黄", "黄色"))
    blind = any(token in text for token in ("cannot", "can't", "unable", "无法", "不能", "看不到"))
    return left_ok and shape_ok and text_ok and right_ok and not blind


def _vision_probe_image_data_url() -> str:
    image = Image.new("RGB", (220, 140), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 109, 69), fill=(0, 190, 210))
    draw.rectangle((110, 0, 219, 69), fill=(250, 245, 245))
    draw.ellipse((145, 15, 190, 60), fill=(210, 0, 160))
    draw.rectangle((0, 70, 109, 139), fill=(20, 25, 35))
    draw.text((34, 90), "K7", fill=(255, 255, 255))
    draw.rectangle((110, 70, 219, 139), fill=(30, 34, 42))
    draw.polygon([(165, 82), (198, 128), (132, 128)], fill=(255, 214, 0))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def _response_text(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""
    choices = payload.get("choices")
    if not isinstance(choices, list):
        return ""
    parts: list[str] = []
    for choice in choices:
        if not isinstance(choice, dict):
            continue
        message = choice.get("message")
        if isinstance(message, dict):
            content = message.get("content")
            if isinstance(content, str):
                parts.append(content)
            elif isinstance(content, list):
                for item in content:
                    if isinstance(item, dict) and isinstance(item.get("text"), str):
                        parts.append(item["text"])
        for key in ("text", "content"):
            value = choice.get(key)
            if isinstance(value, str):
                parts.append(value)
    return "\n".join(parts)


def format_vision_model_summary(capabilities: list[VisionModelCapability], *, language: str = "zh") -> str:
    model = recommended_vision_model(capabilities)
    valid = len([item for item in capabilities if item.supports_vision])
    remaining_tokens = _sum_optional(item.remaining_tokens for item in capabilities)
    total_tokens = _sum_optional(item.total_tokens for item in capabilities)
    remaining_credit = _sum_float_optional(item.remaining_credit for item in capabilities)
    total_credit = _sum_float_optional(item.total_credit for item in capabilities)
    provider = capabilities[0].provider if capabilities else "unknown"
    if language == "zh":
        token_text = (
            f"剩余 token {remaining_tokens:,} / 总 token {total_tokens:,}"
            if remaining_tokens is not None and total_tokens is not None
            else "剩余 token 未知"
        )
        credit_text = (
            f"；剩余额度 ¥{remaining_credit:.4f} / 总额度 ¥{total_credit:.4f}"
            if remaining_credit is not None and total_credit is not None
            else ""
        )
        return f"API 有效：{valid} 个；供应商 {provider}；LLM深度分析模型 {model}；{token_text}{credit_text}"
    token_text = (
        f"remaining tokens {remaining_tokens:,} / total tokens {total_tokens:,}"
        if remaining_tokens is not None and total_tokens is not None
        else "remaining tokens unknown"
    )
    credit_text = (
        f"; remaining credit ¥{remaining_credit:.4f} / total credit ¥{total_credit:.4f}"
        if remaining_credit is not None and total_credit is not None
        else ""
    )
    return f"API valid: {valid}; provider {provider}; LLM deep analysis model {model}; {token_text}{credit_text}"


def recommended_vision_model(capabilities: list[VisionModelCapability]) -> str:
    for capability in capabilities:
        if capability.supports_vision and capability.model:
            return capability.model
    return "qwen3.6-plus"


def _recommended_model_for_endpoint(endpoint: str) -> str:
    if endpoint == "top":
        return "qwen3.6-plus"
    return "qwen3.5-plus"


def _credit_value(value: Any) -> float:
    try:
        return round(float(value) / NEWCOIN_CREDIT_DIVISOR, 4)
    except (TypeError, ValueError):
        return 0.0


def _token_value(value: Any) -> int | None:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _try_newcoin_balance(api_key: str) -> QwenKeyBalance | None:
    try:
        return query_newcoin_balance(api_key, timeout_seconds=10)
    except Exception:  # noqa: BLE001 - generic providers do not have this endpoint.
        return None


def _provider_name(base_url: str) -> str:
    text = base_url.lower()
    if "newcoin" in text:
        return "NewCoin"
    if "openai" in text:
        return "OpenAI-compatible"
    return base_url.rstrip("/").replace("https://", "").replace("http://", "")


def _looks_like_vision_model(model: str) -> bool:
    lower = model.lower()
    positive_tokens = (
        "qwen3-vl",
        "qwen3.6",
        "qwen-vl",
        "qwen2.5-vl",
        "qwen2-vl",
        "vl-",
        "-vl",
        "vision",
        "gpt-4o",
        "gpt-4.1",
        "o4-mini",
        "gemini",
        "pixtral",
        "llava",
        "omni",
        "multimodal",
    )
    negative_tokens = ("embedding", "rerank", "tts", "whisper", "audio", "text-", "coder")
    return any(token in lower for token in positive_tokens) and not any(token in lower for token in negative_tokens)


def _vision_model_rank(model: str) -> tuple[int, str]:
    lower = model.lower()
    priorities = [
        ("qwen3-vl-plus", 1120),
        ("qwen-vl-max", 1050),
        ("qwen2.5-vl-72b", 1030),
        ("gpt-4.1", 1000),
        ("gpt-4o", 980),
        ("gemini-2.5", 960),
        ("pixtral-large", 920),
        ("qwen-vl-plus", 900),
        ("qwen2.5-vl", 880),
        ("o4-mini", 850),
        ("gpt-4o-mini", 820),
        ("qwen3.6-plus", 760),
        ("vision", 700),
        ("vl", 650),
    ]
    for token, score in priorities:
        if token in lower:
            return score, model
    return 500, model


def _is_strong_preferred_vision_model(model: str) -> bool:
    lower = model.lower()
    return any(token in lower for token in ("vl", "vision", "gpt-4o", "gpt-4.1", "o4-mini", "gemini", "pixtral", "llava"))


def _sum_optional(values: Any) -> int | None:
    collected = [value for value in values if value is not None]
    return sum(collected) if collected else None


def _sum_float_optional(values: Any) -> float | None:
    collected = [float(value) for value in values if value is not None]
    return sum(collected) if collected else None


def _safe_error(response: requests.Response) -> str:
    text = response.text or ""
    if len(text) > 180:
        text = f"{text[:180]}..."
    return f"HTTP {response.status_code}: {text}"


def _compact_error(message: str) -> str:
    message = message.replace("\n", " ").replace("\r", " ").strip()
    return message[:240] + ("..." if len(message) > 240 else "")

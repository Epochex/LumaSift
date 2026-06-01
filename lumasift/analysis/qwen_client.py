from __future__ import annotations

import base64
import json
import mimetypes
import random
import time
from pathlib import Path
from typing import Any, Callable

import requests

from lumasift.core.keyring import ApiKeyRing
from lumasift.storage.qwen_cache import (
    QwenResponseCache,
    default_qwen_cache_dir,
    identify_image,
    prompt_fingerprint,
    scrub_secrets,
)


TRANSIENT_STATUS_CODES = {408, 409, 425, 429, 500, 502, 503, 504}
NON_STREAM_MAX_TOKENS = 4096


class QwenVisionClient:
    def __init__(
        self,
        base_url: str,
        model: str,
        keyring: ApiKeyRing,
        max_tokens: int = 4096,
        timeout_seconds: int = 90,
        response_cache: QwenResponseCache | None = None,
        cache_dir: Path | None = None,
        cache_enabled: bool = True,
        max_retries: int = 3,
        initial_backoff_seconds: float = 1.0,
        max_backoff_seconds: float = 30.0,
        sleep: Callable[[float], None] = time.sleep,
        event_callback: Callable[[dict[str, Any]], None] | None = None,
        response_validator: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.keyring = keyring
        self.max_tokens = max_tokens
        self.timeout_seconds = timeout_seconds
        self.response_cache = response_cache
        self.cache_dir = cache_dir
        self.cache_enabled = cache_enabled
        self.max_retries = max_retries
        self.initial_backoff_seconds = initial_backoff_seconds
        self.max_backoff_seconds = max_backoff_seconds
        self.sleep = sleep
        self.event_callback = event_callback
        self.response_validator = response_validator
        self.last_cache_hit = False
        self.last_cache_key_digest: str | None = None
        self.last_failure_kind: str = ""
        self.last_failure_message: str = ""
        self.last_invalid_response_excerpt: str = ""

    def _event(self, event_type: str, **payload: Any) -> None:
        payload.setdefault("model", self.model)
        if self.event_callback is not None:
            self.event_callback({"type": event_type, **payload})

    def analyze_image(self, image_path: Path, prompt: str, prompt_version: str | None = None) -> dict[str, Any]:
        self.last_cache_hit = False
        self.last_cache_key_digest = None
        self.last_failure_kind = ""
        self.last_failure_message = ""
        self.last_invalid_response_excerpt = ""
        image_identity = identify_image(image_path)
        cache = self._cache_for(image_path)
        cache_key = None
        if cache is not None:
            cache_prompt_version = f"{prompt_version}:{prompt_fingerprint(prompt)}" if prompt_version else prompt_fingerprint(prompt)
            cache_key = cache.make_key(
                image=image_identity,
                model=self.model,
                prompt_version=cache_prompt_version,
            )
            self.last_cache_key_digest = cache_key.digest
            cached = cache.load(cache_key)
            if cached is not None:
                try:
                    self._validate_response(cached)
                except ValueError as exc:
                    cache.delete(cache_key)
                    self._event("cache_invalid", image=str(image_path), model=self.model, error=str(exc)[:240])
                else:
                    self.last_cache_hit = True
                    self._event("cache_hit", image=str(image_path), model=self.model)
                    return cached

        if not self.keyring.has_keys():
            raise RuntimeError("No LLM Deep Analysis API keys configured")

        data_url = self._image_data_url(image_path)
        max_tokens = min(self.max_tokens, NON_STREAM_MAX_TOKENS)
        if max_tokens != self.max_tokens:
            self._event("max_tokens_capped", requested=self.max_tokens, used=max_tokens)
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                }
            ],
            "temperature": 0.2,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
        }
        last_error: Exception | None = None
        tried_without_response_format = False
        tried_validation_repair = False
        retry_count = 0
        while True:
            try:
                response = requests.post(
                    f"{self.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.keyring.current()}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                    timeout=self.timeout_seconds,
                )
                if response.status_code == 400 and payload.get("response_format") and not tried_without_response_format:
                    payload.pop("response_format", None)
                    tried_without_response_format = True
                    self._event("retrying", reason="response_format_fallback", status_code=response.status_code)
                    continue
                if response.status_code in {401, 403} and self.keyring.rotate():
                    self._event("retrying", reason="key_rotated", status_code=response.status_code)
                    continue
                if response.status_code == 429 and self.keyring.rotate():
                    retry_count = 0
                    self._event("retrying", reason="rate_limit_key_rotated", status_code=response.status_code)
                    continue
                if response.status_code in TRANSIENT_STATUS_CODES and retry_count < self.max_retries:
                    last_error = RuntimeError(self._status_error_message(response))
                    self._event("retrying", reason="transient_http", status_code=response.status_code, retry=retry_count + 1)
                    self._backoff(retry_count)
                    retry_count += 1
                    continue
                response.raise_for_status()
                response_data = scrub_secrets(response.json())
                try:
                    self._validate_response(response_data)
                except ValueError:
                    self.last_invalid_response_excerpt = self._response_excerpt(response_data)
                    raise
                if cache is not None and cache_key is not None:
                    cache.store(cache_key, image_identity, response_data)
                return response_data
            except ValueError as exc:
                last_error = exc
                validation_message = str(exc)
                self.last_failure_message = validation_message
                reason = (
                    "response_validation_failed"
                    if "professional_review" in validation_message or "too generic" in validation_message or "metric-driven" in validation_message
                    else "malformed_json"
                )
                self.last_failure_kind = "weak_response" if reason == "response_validation_failed" else "malformed_json"
                if retry_count < self.max_retries:
                    self._event(
                        "retrying",
                        reason=reason,
                        retry=retry_count + 1,
                        message=validation_message[:240],
                    )
                    if reason == "response_validation_failed":
                        if tried_validation_repair:
                            break
                        payload["messages"][0]["content"][0]["text"] = self._validation_repair_prompt(prompt, validation_message)
                        tried_validation_repair = True
                        retry_count += 1
                        continue
                    self._backoff(retry_count)
                    retry_count += 1
                    continue
                break
            except requests.HTTPError as exc:
                last_error = exc
                self.last_failure_kind = "http_error"
                self.last_failure_message = str(exc)
                break
            except requests.RequestException as exc:
                last_error = exc
                self.last_failure_kind = "request_exception"
                self.last_failure_message = str(exc)
                if retry_count < self.max_retries:
                    self._event("retrying", reason="request_exception", retry=retry_count + 1)
                    self._backoff(retry_count)
                    retry_count += 1
                    continue
                if self.keyring.rotate():
                    retry_count = 0
                    self._event("retrying", reason="request_exception_key_rotated")
                    continue
                break
        raise RuntimeError(f"LLM Deep Analysis request failed after key rotation: {last_error}")

    def _validate_response(self, response: dict[str, Any]) -> None:
        self._raise_if_truncated(response)
        if self.response_validator is not None:
            self.response_validator(response)

    @staticmethod
    def _raise_if_truncated(response: dict[str, Any]) -> None:
        choices = response.get("choices")
        if not isinstance(choices, list):
            return
        for choice in choices:
            if isinstance(choice, dict) and choice.get("finish_reason") == "length":
                raise ValueError("LLM Deep Analysis response was truncated before valid JSON completed")

    def _cache_for(self, image_path: Path) -> QwenResponseCache | None:
        if not self.cache_enabled:
            return None
        if self.response_cache is not None:
            return self.response_cache
        return QwenResponseCache(self.cache_dir or default_qwen_cache_dir(image_path))

    def _backoff(self, retry_count: int) -> None:
        delay = min(self.max_backoff_seconds, self.initial_backoff_seconds * (2**retry_count))
        jitter = random.uniform(0, delay * 0.25)
        self.sleep(delay + jitter)

    @staticmethod
    def _status_error_message(response: requests.Response) -> str:
        body = getattr(response, "text", "")
        if len(body) > 240:
            body = f"{body[:240]}..."
        return f"LLM Deep Analysis transient HTTP {response.status_code}: {body}"

    @staticmethod
    def _image_data_url(path: Path) -> str:
        mime_type = mimetypes.guess_type(path.name)[0] or "image/jpeg"
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        return f"data:{mime_type};base64,{encoded}"

    @staticmethod
    def _response_excerpt(response: dict[str, Any]) -> str:
        try:
            text = response.get("output_text")
            choices = response.get("choices")
            if not text and isinstance(choices, list) and choices:
                first = choices[0]
                if isinstance(first, dict):
                    message = first.get("message")
                    if isinstance(message, dict):
                        text = message.get("content") or message.get("reasoning_content")
                    text = text or first.get("text") or first.get("content")
            if not isinstance(text, str):
                text = json.dumps(response, ensure_ascii=False, separators=(",", ":"))
        except Exception:  # noqa: BLE001 - diagnostics should never mask the real API failure.
            text = repr(response)
        return text[:1200]

    @staticmethod
    def _validation_repair_prompt(prompt: str, validation_message: str) -> str:
        return (
            f"{prompt}\n\n"
            "上一次返回没有通过专业深评校验，失败原因："
            f"{validation_message}\n"
            "请重新看同一张照片并只返回一个完整 JSON。必须修正以下问题：\n"
            "1. 不要复述本地分数、亮度、对比度或组内排名。\n"
            "2. 每个 score_rationales.reason 必须写出具体可见对象，并用 evidence_ids 指向 visible_evidence。\n"
            "3. editing_plan.edit_intent 和 local_masks.reason 必须绑定可见对象，例如标牌文字、人物面部、边缘车辆、天空高光。\n"
            "4. professional_review 每段都要引用照片里的具体对象或关系。\n"
            "5. 不要脑补外语、地名、职业或文化含义；只写照片中能看见的文字/符号如何影响画面。\n"
            "6. 先做事实核查再重写：把所有人物、动作、上下位置、互动、表情、视线声明逐条核对照片；看不清就写入 hallucination_checks.uncertain_objects，不要补成确定事实。\n"
            "7. 必须输出 visible_inventory.people；只有清楚可见头部/躯干/肢体或人体姿态时 visibility 才能写 clear，否则写 partial/uncertain。\n"
            "8. keep/maybe 也必须输出至少 2 条不能靠修图解决的 critical_flaws，并且专业深评不能只夸优点。\n"
            "如果内容不成立，直接给 reject 或 maybe，但仍必须基于可见证据。"
        )

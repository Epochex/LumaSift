from __future__ import annotations

import base64
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

    def _event(self, event_type: str, **payload: Any) -> None:
        if self.event_callback is not None:
            self.event_callback({"type": event_type, **payload})

    def analyze_image(self, image_path: Path, prompt: str, prompt_version: str | None = None) -> dict[str, Any]:
        self.last_cache_hit = False
        self.last_cache_key_digest = None
        image_identity = identify_image(image_path)
        cache = self._cache_for(image_path)
        cache_key = None
        if cache is not None:
            cache_key = cache.make_key(
                image=image_identity,
                model=self.model,
                prompt_version=prompt_version or prompt_fingerprint(prompt),
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
            raise RuntimeError("No Qwen API keys configured")

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
                self._validate_response(response_data)
                if cache is not None and cache_key is not None:
                    cache.store(cache_key, image_identity, response_data)
                return response_data
            except ValueError as exc:
                last_error = exc
                if retry_count < self.max_retries:
                    self._event("retrying", reason="malformed_json", retry=retry_count + 1)
                    self._backoff(retry_count)
                    retry_count += 1
                    continue
                break
            except requests.HTTPError as exc:
                last_error = exc
                break
            except requests.RequestException as exc:
                last_error = exc
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
        raise RuntimeError(f"Qwen vision request failed after key rotation: {last_error}")

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
                raise ValueError("Qwen response was truncated before valid JSON completed")

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
        return f"Qwen transient HTTP {response.status_code}: {body}"

    @staticmethod
    def _image_data_url(path: Path) -> str:
        mime_type = mimetypes.guess_type(path.name)[0] or "image/jpeg"
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        return f"data:{mime_type};base64,{encoded}"

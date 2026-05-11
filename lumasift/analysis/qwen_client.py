from __future__ import annotations

import base64
import mimetypes
from pathlib import Path
from typing import Any

import requests

from lumasift.core.keyring import ApiKeyRing


class QwenVisionClient:
    def __init__(
        self,
        base_url: str,
        model: str,
        keyring: ApiKeyRing,
        max_tokens: int = 1024,
        timeout_seconds: int = 90,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.keyring = keyring
        self.max_tokens = max_tokens
        self.timeout_seconds = timeout_seconds

    def analyze_image(self, image_path: Path, prompt: str) -> dict[str, Any]:
        if not self.keyring.has_keys():
            raise RuntimeError("No Qwen API keys configured")
        data_url = self._image_data_url(image_path)
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
            "max_tokens": self.max_tokens,
            "response_format": {"type": "json_object"},
        }
        last_error: Exception | None = None
        tried_without_response_format = False
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
                    continue
                if response.status_code in {401, 403, 429} and self.keyring.rotate():
                    continue
                response.raise_for_status()
                return response.json()
            except requests.RequestException as exc:
                last_error = exc
                if not self.keyring.rotate():
                    break
        raise RuntimeError(f"Qwen vision request failed after key rotation: {last_error}")

    @staticmethod
    def _image_data_url(path: Path) -> str:
        mime_type = mimetypes.guess_type(path.name)[0] or "image/jpeg"
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        return f"data:{mime_type};base64,{encoded}"

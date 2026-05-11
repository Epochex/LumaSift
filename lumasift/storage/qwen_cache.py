from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


CACHE_SCHEMA_VERSION = 1
SECRET_FIELD_NAMES = {
    "api_key",
    "apikey",
    "authorization",
    "cookie",
    "proxy-authorization",
    "secret",
    "set-cookie",
    "token",
}


@dataclass(frozen=True)
class ImageIdentity:
    path: str
    size_bytes: int
    mtime_ns: int
    sha256: str


@dataclass(frozen=True)
class QwenCacheKey:
    image_sha256: str
    model: str
    prompt_version: str

    @property
    def digest(self) -> str:
        payload = {
            "image_sha256": self.image_sha256,
            "model": self.model,
            "prompt_version": self.prompt_version,
            "schema_version": CACHE_SCHEMA_VERSION,
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


def default_qwen_cache_dir(image_path: Path) -> Path:
    if image_path.parent.name == "previews":
        return image_path.parent.parent / "qwen_cache"
    return Path(".lumasift_cache") / "qwen"


def identify_image(path: Path) -> ImageIdentity:
    resolved = path.resolve()
    stat = resolved.stat()
    digest = hashlib.sha256()
    with resolved.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return ImageIdentity(
        path=str(resolved),
        size_bytes=stat.st_size,
        mtime_ns=stat.st_mtime_ns,
        sha256=digest.hexdigest(),
    )


def prompt_fingerprint(prompt: str) -> str:
    digest = hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:16]
    return f"prompt-sha256-{digest}"


def scrub_secrets(value: Any) -> Any:
    if isinstance(value, Mapping):
        scrubbed: dict[str, Any] = {}
        for key, item in value.items():
            if str(key).lower() in SECRET_FIELD_NAMES:
                scrubbed[str(key)] = "[redacted]"
            else:
                scrubbed[str(key)] = scrub_secrets(item)
        return scrubbed
    if isinstance(value, list):
        return [scrub_secrets(item) for item in value]
    return value


class QwenResponseCache:
    def __init__(self, cache_dir: Path) -> None:
        self.cache_dir = cache_dir

    def make_key(self, image: ImageIdentity, model: str, prompt_version: str) -> QwenCacheKey:
        return QwenCacheKey(image_sha256=image.sha256, model=model, prompt_version=prompt_version)

    def load(self, key: QwenCacheKey) -> dict[str, Any] | None:
        path = self._entry_path(key)
        if not path.exists():
            return None
        with path.open("r", encoding="utf-8") as handle:
            entry = json.load(handle)
        if entry.get("schema_version") != CACHE_SCHEMA_VERSION:
            return None
        response = entry.get("response")
        if not isinstance(response, dict):
            return None
        return response

    def store(self, key: QwenCacheKey, image: ImageIdentity, response: dict[str, Any]) -> Path:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        path = self._entry_path(key)
        entry = {
            "schema_version": CACHE_SCHEMA_VERSION,
            "key": {
                "image_sha256": key.image_sha256,
                "model": key.model,
                "prompt_version": key.prompt_version,
            },
            "image_identity": {
                "path": image.path,
                "size_bytes": image.size_bytes,
                "mtime_ns": image.mtime_ns,
                "sha256": image.sha256,
            },
            "response": scrub_secrets(response),
        }
        temp_path = path.with_suffix(f"{path.suffix}.tmp")
        with temp_path.open("w", encoding="utf-8") as handle:
            json.dump(entry, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(temp_path, path)
        return path

    def _entry_path(self, key: QwenCacheKey) -> Path:
        return self.cache_dir / f"{key.digest}.json"

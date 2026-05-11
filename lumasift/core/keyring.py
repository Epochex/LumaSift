from __future__ import annotations

from dataclasses import dataclass


def mask_secret(secret: str) -> str:
    if len(secret) <= 10:
        return "***"
    return f"{secret[:5]}...{secret[-4:]}"


@dataclass
class ApiKeyRing:
    keys: list[str]
    index: int = 0

    def has_keys(self) -> bool:
        return bool(self.keys)

    def current(self) -> str:
        if not self.keys:
            raise RuntimeError("No API keys configured")
        return self.keys[self.index]

    def current_label(self) -> str:
        if not self.keys:
            return "none"
        return f"key#{self.index + 1}:{mask_secret(self.current())}"

    def rotate(self) -> bool:
        if self.index + 1 >= len(self.keys):
            return False
        self.index += 1
        return True

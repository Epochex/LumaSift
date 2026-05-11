from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PhotoFile:
    path: Path
    extension: str


def discover_photos(input_dir: Path, supported_extensions: tuple[str, ...]) -> list[PhotoFile]:
    if not input_dir.exists():
        return []
    supported = set(supported_extensions)
    photos: list[PhotoFile] = []
    for path in input_dir.rglob("*"):
        if path.is_file() and path.suffix in supported:
            photos.append(PhotoFile(path=path, extension=path.suffix.lower()))
    return sorted(photos, key=lambda item: str(item.path).lower())

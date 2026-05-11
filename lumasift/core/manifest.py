from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PhotoFile:
    path: Path
    extension: str


def discover_photos(input_dir: Path, supported_extensions: tuple[str, ...], limit: int | None = None) -> list[PhotoFile]:
    if limit is not None and limit < 0:
        raise ValueError("limit must be greater than or equal to 0")
    if not input_dir.exists():
        return []
    if limit == 0:
        return []

    supported = set(supported_extensions)
    photos: list[PhotoFile] = []

    if limit is None:
        for path in input_dir.rglob("*"):
            if path.is_file() and path.suffix in supported:
                photos.append(PhotoFile(path=path, extension=path.suffix.lower()))
        return sorted(photos, key=lambda item: str(item.path).lower())

    def scan(directory: Path) -> bool:
        try:
            children = sorted(directory.iterdir(), key=lambda item: str(item).lower())
        except OSError:
            return False

        for path in children:
            if path.is_dir():
                if scan(path):
                    return True
            elif path.is_file() and path.suffix in supported:
                photos.append(PhotoFile(path=path, extension=path.suffix.lower()))
                if len(photos) >= limit:
                    return True
        return False

    scan(input_dir)
    return photos

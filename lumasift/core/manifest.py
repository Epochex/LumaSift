from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


RAW_EXTENSIONS = {
    ".3fr",
    ".ari",
    ".arw",
    ".bay",
    ".cap",
    ".cr2",
    ".cr3",
    ".crw",
    ".dcr",
    ".dng",
    ".erf",
    ".fff",
    ".gpr",
    ".iiq",
    ".k25",
    ".kdc",
    ".mef",
    ".mos",
    ".mrw",
    ".nef",
    ".nrw",
    ".obm",
    ".orf",
    ".pef",
    ".ptx",
    ".pxn",
    ".r3d",
    ".raf",
    ".raw",
    ".rwl",
    ".rw2",
    ".rwz",
    ".sr2",
    ".srf",
    ".srw",
    ".x3f",
}
JPEG_EXTENSIONS = {".jpg", ".jpeg"}


@dataclass(frozen=True)
class PhotoFile:
    path: Path
    extension: str
    pair_id: str | None = None
    pair_role: str = "single"
    paired_raw_path: Path | None = None
    paired_jpeg_path: Path | None = None

    @property
    def has_raw_jpeg_pair(self) -> bool:
        return self.paired_raw_path is not None and self.paired_jpeg_path is not None


def discover_photos(input_dir: Path, supported_extensions: tuple[str, ...], limit: int | None = None) -> list[PhotoFile]:
    if limit is not None and limit < 0:
        raise ValueError("limit must be greater than or equal to 0")
    if not input_dir.exists():
        return []
    if limit == 0:
        return []

    supported = {extension.lower() for extension in supported_extensions}
    paths: list[Path] = []

    if limit is None:
        for path in input_dir.rglob("*"):
            if path.is_file() and path.suffix.lower() in supported:
                paths.append(path)
        return _with_pair_metadata(sorted(paths, key=lambda item: str(item).lower()), input_dir)

    def scan(directory: Path) -> bool:
        try:
            children = sorted(directory.iterdir(), key=lambda item: str(item).lower())
        except OSError:
            return False

        for path in children:
            if path.is_dir():
                if scan(path):
                    return True
            elif path.is_file() and path.suffix.lower() in supported:
                paths.append(path)
                if len(paths) >= limit:
                    return True
        return False

    scan(input_dir)
    return _with_pair_metadata(paths, input_dir)


def _with_pair_metadata(paths: list[Path], input_dir: Path) -> list[PhotoFile]:
    buckets: dict[str, dict[str, list[Path]]] = {}
    for path in paths:
        suffix = path.suffix.lower()
        key = _pair_key(path, input_dir)
        bucket = buckets.setdefault(key, {"raw": [], "jpeg": []})
        if suffix in RAW_EXTENSIONS:
            bucket["raw"].append(path)
        elif suffix in JPEG_EXTENSIONS:
            bucket["jpeg"].append(path)

    photos: list[PhotoFile] = []
    for path in paths:
        suffix = path.suffix.lower()
        bucket = buckets.get(_pair_key(path, input_dir), {})
        raw_path = sorted(bucket.get("raw", []), key=lambda item: str(item).lower())[0] if bucket.get("raw") else None
        jpeg_path = sorted(bucket.get("jpeg", []), key=lambda item: str(item).lower())[0] if bucket.get("jpeg") else None
        if suffix in RAW_EXTENSIONS:
            role = "raw"
        elif suffix in JPEG_EXTENSIONS:
            role = "jpeg"
        else:
            role = "single"
        pair_id = _pair_key(path, input_dir) if raw_path and jpeg_path else None
        photos.append(
            PhotoFile(
                path=path,
                extension=suffix,
                pair_id=pair_id,
                pair_role=role,
                paired_raw_path=raw_path,
                paired_jpeg_path=jpeg_path,
            )
        )
    return photos


def _pair_key(path: Path, input_dir: Path) -> str:
    try:
        relative = path.relative_to(input_dir)
    except ValueError:
        relative = path
    return str(relative.with_suffix("")).replace("\\", "/").lower()

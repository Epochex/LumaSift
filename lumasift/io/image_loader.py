from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageOps


@dataclass
class LoadedImage:
    path: Path
    kind: str
    rgb: np.ndarray
    width: int
    height: int
    exif: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


def _load_bitmap(path: Path) -> LoadedImage:
    with Image.open(path) as image:
        image = ImageOps.exif_transpose(image)
        exif = dict(image.getexif() or {})
        rgb_image = image.convert("RGB")
        rgb = np.asarray(rgb_image, dtype=np.uint8)
        width, height = rgb_image.size
    return LoadedImage(path=path, kind="bitmap", rgb=rgb, width=width, height=height, exif=exif)


def _load_raw(path: Path) -> LoadedImage:
    try:
        import rawpy  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError("rawpy is required for ARW files. Install lumasift[raw].") from exc

    with rawpy.imread(str(path)) as raw:
        rgb = raw.postprocess(use_camera_wb=True, output_bps=8)
    height, width = rgb.shape[:2]
    return LoadedImage(path=path, kind="raw", rgb=rgb.astype(np.uint8), width=width, height=height)


def load_image(path: Path) -> LoadedImage:
    suffix = path.suffix.lower()
    if suffix == ".arw":
        return _load_raw(path)
    if suffix in {".png", ".jpg", ".jpeg"}:
        return _load_bitmap(path)
    raise ValueError(f"Unsupported image extension: {path.suffix}")

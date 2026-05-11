from __future__ import annotations

from pathlib import Path

from PIL import Image

from lumasift.io.image_loader import load_image


def create_jpeg_preview(path: Path, output_dir: Path, max_side: int = 1536) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{path.stem}.preview.jpg"
    if output_path.exists():
        return output_path

    loaded = load_image(path)
    image = Image.fromarray(loaded.rgb)
    image.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    image.save(output_path, format="JPEG", quality=88, optimize=True)
    return output_path

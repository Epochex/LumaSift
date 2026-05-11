from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter


ROOT = Path(__file__).resolve().parents[1]
SAMPLE_DIR = ROOT / "sample_photos"
OUTPUT_DIR = ROOT / "outputs"


def _save(path: Path, image: Image.Image) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, quality=92)


def generate_demo_images() -> None:
    SAMPLE_DIR.mkdir(exist_ok=True)
    base = Image.new("RGB", (900, 620), (35, 35, 35))
    draw = ImageDraw.Draw(base)
    draw.rectangle((120, 120, 300, 520), fill=(220, 220, 210))
    draw.rectangle((500, 180, 650, 520), fill=(120, 130, 155))
    draw.line((0, 520, 900, 450), fill=(240, 240, 240), width=6)
    _save(SAMPLE_DIR / "street_tension.jpg", base)

    thirds = Image.new("RGB", (900, 620), (185, 190, 185))
    draw = ImageDraw.Draw(thirds)
    draw.ellipse((570, 210, 710, 430), fill=(30, 30, 30))
    draw.rectangle((0, 450, 900, 620), fill=(80, 80, 80))
    _save(SAMPLE_DIR / "subject_near_thirds.jpg", thirds)

    bright = Image.new("RGB", (900, 620), (252, 248, 235))
    draw = ImageDraw.Draw(bright)
    draw.rectangle((350, 250, 470, 520), fill=(120, 110, 105))
    _save(SAMPLE_DIR / "overexposed_but_recoverable.jpg", bright)

    blurred = base.filter(ImageFilter.GaussianBlur(radius=6))
    _save(SAMPLE_DIR / "blurred_motion.jpg", blurred)

    negative = Image.new("RGB", (900, 620), (20, 25, 30))
    draw = ImageDraw.Draw(negative)
    draw.rectangle((710, 300, 790, 500), fill=(210, 210, 200))
    _save(SAMPLE_DIR / "negative_space.jpg", negative)


def main() -> int:
    generate_demo_images()
    return subprocess.call(
        [
            sys.executable,
            "-m",
            "lumasift.app.main",
            "--input",
            str(SAMPLE_DIR),
            "--output",
            str(OUTPUT_DIR),
            "--mode",
            "local_only",
            "--run-id",
            "demo",
        ],
        cwd=ROOT,
    )


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from lumasift.io.image_loader import load_image


def _fit_thumb(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    image = image.copy()
    image.thumbnail(size, Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", size, "white")
    x = (size[0] - image.width) // 2
    y = (size[1] - image.height) // 2
    canvas.paste(image, (x, y))
    return canvas


def write_contact_sheet(path: Path, records: list[dict], columns: int = 5) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not records:
        Image.new("RGB", (800, 300), "white").save(path)
        return

    thumb_size = (240, 180)
    caption_h = 78
    cell_w = thumb_size[0]
    cell_h = thumb_size[1] + caption_h
    rows = (len(records) + columns - 1) // columns
    sheet = Image.new("RGB", (columns * cell_w, rows * cell_h), "white")
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default()

    for idx, record in enumerate(records):
        row = idx // columns
        col = idx % columns
        x = col * cell_w
        y = row * cell_h
        try:
            loaded = load_image(Path(record["path"]))
            thumb = _fit_thumb(Image.fromarray(loaded.rgb), thumb_size)
        except Exception:
            thumb = Image.new("RGB", thumb_size, (230, 230, 230))
        sheet.paste(thumb, (x, y))
        caption = [
            f"#{record.get('rank', '?')} {float(record.get('final_selection_score', 0)):.1f}",
            str(record.get("category", ""))[:28],
            str(record.get("filename", ""))[:30],
        ]
        draw.multiline_text((x + 6, y + thumb_size[1] + 4), "\n".join(caption), fill="black", font=font, spacing=3)

    sheet.save(path, format="JPEG", quality=90)

from __future__ import annotations

import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from lumasift.io.image_loader import load_image


THUMB_SIZE = (260, 190)
CAPTION_H = 120
PADDING = 8


def _fit_thumb(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    image = image.copy()
    image.thumbnail(size, Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", size, (246, 246, 242))
    x = (size[0] - image.width) // 2
    y = (size[1] - image.height) // 2
    canvas.paste(image, (x, y))
    return canvas


def _load_font(size: int = 12) -> ImageFont.ImageFont:
    for font_path in (
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ):
        try:
            return ImageFont.truetype(font_path, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def _text_value(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, (int, float)):
        return str(value)
    return str(value).replace("\n", " ").strip()


def _first_reason(record: dict) -> str:
    for field in ("why_this_frame", "decisive_moment_read", "subject_relationship"):
        value = record.get(field)
        if isinstance(value, str) and value.strip():
            return _text_value(value)
    value = record.get("visible_evidence")
    if isinstance(value, list) and value:
        return _text_value(value[0])
    if isinstance(value, str) and value:
        return _text_value(value)
    for field in ("positive_reasons", "negative_reasons", "errors"):
        value = record.get(field)
        if isinstance(value, list) and value:
            return _text_value(value[0])
        if isinstance(value, str) and value:
            return _text_value(value)
    return _text_value(record.get("best_editing_direction"))


def _ellipsize(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    if limit <= 1:
        return text[:limit]
    return f"{text[: limit - 1]}..."


def _wrap_line(label: str, value: str, width: int, max_lines: int = 1) -> list[str]:
    value = " ".join(value.split())
    if not value:
        return [label.rstrip()]
    wrapped = textwrap.wrap(
        f"{label}{value}",
        width=width,
        max_lines=max_lines,
        placeholder="...",
        break_long_words=False,
        break_on_hyphens=False,
    )
    return wrapped or [_ellipsize(f"{label}{value}", width)]


def _caption_lines(record: dict, width: int = 34) -> list[str]:
    score = float(record.get("final_selection_score", 0) or 0)
    rank = _text_value(record.get("rank") or "?")
    category = _text_value(record.get("category") or "uncategorized")
    filename = _text_value(record.get("filename") or Path(_text_value(record.get("path"))).name)
    style = _text_value(record.get("recommended_style") or "style_pending")
    reason = _first_reason(record) or "No reason recorded."

    lines = [
        f"#{rank}  score {score:.1f}",
        _ellipsize(category, width),
        _ellipsize(filename, width),
    ]
    lines.extend(_wrap_line("why: ", reason, width=width, max_lines=2))
    lines.extend(_wrap_line("style: ", style, width=width, max_lines=1))
    return lines


def _draw_text(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str, **kwargs: object) -> None:
    try:
        draw.text(xy, text, **kwargs)
    except UnicodeEncodeError:
        safe = text.encode("latin-1", errors="replace").decode("latin-1")
        draw.text(xy, safe, **kwargs)


def _category_color(category: str) -> tuple[int, int, int]:
    if category in {"portfolio_candidate", "strong_edit_candidate"}:
        return (27, 102, 89)
    if category in {"story_candidate", "technically_weak_but_interesting"}:
        return (178, 118, 37)
    if category == "failed":
        return (154, 52, 45)
    return (92, 92, 92)


def write_contact_sheet(path: Path, records: list[dict], columns: int = 5) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not records:
        sheet = Image.new("RGB", (800, 300), (248, 248, 245))
        draw = ImageDraw.Draw(sheet)
        _draw_text(draw, (24, 24), "No photos to review.", fill=(40, 40, 40), font=_load_font(14))
        sheet.save(path)
        return

    columns = max(1, columns)
    thumb_size = THUMB_SIZE
    cell_w = thumb_size[0]
    cell_h = thumb_size[1] + CAPTION_H
    rows = (len(records) + columns - 1) // columns
    sheet = Image.new("RGB", (columns * cell_w, rows * cell_h), (248, 248, 245))
    draw = ImageDraw.Draw(sheet)
    font = _load_font(12)
    title_font = _load_font(14)

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
            thumb_draw = ImageDraw.Draw(thumb)
            _draw_text(thumb_draw, (PADDING, PADDING), "preview unavailable", fill=(85, 85, 85), font=font)
        sheet.paste(thumb, (x, y))
        caption_y = y + thumb_size[1]
        category = _text_value(record.get("category"))
        draw.rectangle((x, caption_y, x + cell_w, caption_y + CAPTION_H), fill=(255, 255, 255))
        draw.rectangle((x, caption_y, x + 5, caption_y + CAPTION_H), fill=_category_color(category))

        lines = _caption_lines(record)
        for line_idx, line in enumerate(lines):
            line_y = caption_y + PADDING + line_idx * 17
            line_font = title_font if line_idx == 0 else font
            fill = (20, 20, 20) if line_idx <= 2 else (70, 70, 70)
            _draw_text(draw, (x + PADDING + 5, line_y), line, fill=fill, font=line_font)

    sheet.save(path, format="JPEG", quality=90)

from pathlib import Path

from PIL import Image

from lumasift.io.preview import create_jpeg_preview


def test_preview_names_are_collision_safe_for_same_stem(tmp_path: Path) -> None:
    first_dir = tmp_path / "a"
    second_dir = tmp_path / "b"
    first_dir.mkdir()
    second_dir.mkdir()
    first = first_dir / "same.jpg"
    second = second_dir / "same.jpg"
    Image.new("RGB", (30, 30), (255, 0, 0)).save(first)
    Image.new("RGB", (30, 30), (0, 0, 255)).save(second)

    preview_dir = tmp_path / "previews"
    first_preview = create_jpeg_preview(first, preview_dir, max_side=64)
    second_preview = create_jpeg_preview(second, preview_dir, max_side=64)

    assert first_preview != second_preview
    assert first_preview.exists()
    assert second_preview.exists()

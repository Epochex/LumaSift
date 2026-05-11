from pathlib import Path

from lumasift.core.manifest import discover_photos


def test_discover_photos_recursively(tmp_path: Path) -> None:
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "one.jpg").write_bytes(b"x")
    (tmp_path / "two.txt").write_text("x", encoding="utf-8")

    photos = discover_photos(tmp_path, (".jpg", ".png"))

    assert [photo.path.name for photo in photos] == ["one.jpg"]

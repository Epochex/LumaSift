from pathlib import Path

import pytest

from lumasift.core.manifest import discover_photos


def test_discover_photos_recursively(tmp_path: Path) -> None:
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "one.jpg").write_bytes(b"x")
    (tmp_path / "two.txt").write_text("x", encoding="utf-8")

    photos = discover_photos(tmp_path, (".jpg", ".png"))

    assert [photo.path.name for photo in photos] == ["one.jpg"]


def test_discover_photos_honors_limit(tmp_path: Path) -> None:
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "one.jpg").write_bytes(b"x")
    (tmp_path / "b").mkdir()
    (tmp_path / "b" / "two.jpg").write_bytes(b"x")
    (tmp_path / "three.jpg").write_bytes(b"x")

    photos = discover_photos(tmp_path, (".jpg",), limit=2)

    assert [photo.path.name for photo in photos] == ["one.jpg", "two.jpg"]


def test_discover_photos_allows_zero_limit(tmp_path: Path) -> None:
    (tmp_path / "one.jpg").write_bytes(b"x")

    assert discover_photos(tmp_path, (".jpg",), limit=0) == []


def test_discover_photos_rejects_negative_limit(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        discover_photos(tmp_path, (".jpg",), limit=-1)

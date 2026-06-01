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


def test_discover_photos_marks_raw_jpeg_pairs_case_insensitively(tmp_path: Path) -> None:
    (tmp_path / "DSC0001.RAF").write_bytes(b"raw")
    (tmp_path / "DSC0001.jpg").write_bytes(b"jpg")
    (tmp_path / "DSC0002.NEF").write_bytes(b"raw")

    photos = discover_photos(tmp_path, (".raf", ".nef", ".jpg"))
    by_name = {photo.path.name: photo for photo in photos}

    assert by_name["DSC0001.RAF"].has_raw_jpeg_pair
    assert by_name["DSC0001.RAF"].pair_role == "raw"
    assert by_name["DSC0001.jpg"].pair_role == "jpeg"
    assert by_name["DSC0001.jpg"].paired_raw_path == tmp_path / "DSC0001.RAF"
    assert not by_name["DSC0002.NEF"].has_raw_jpeg_pair
    assert by_name["DSC0002.NEF"].pair_role == "raw"

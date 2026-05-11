from lumasift.core.keyring import ApiKeyRing, mask_secret


def test_mask_secret_hides_middle() -> None:
    assert mask_secret("sk-abcdefghijklmnopqrstuvwxyz").startswith("sk-ab")
    assert "klmnop" not in mask_secret("sk-abcdefghijklmnopqrstuvwxyz")


def test_keyring_rotates() -> None:
    ring = ApiKeyRing(["first", "second"])
    assert ring.current() == "first"
    assert ring.rotate() is True
    assert ring.current() == "second"
    assert ring.rotate() is False

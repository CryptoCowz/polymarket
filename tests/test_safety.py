from pathlib import Path


def test_package_source_has_no_order_or_key_paths():
    root = Path("src/aroonbot")
    text = "\n".join(path.read_text() for path in root.rglob("*.py"))
    lowered = text.lower()
    for token in (
        "private_key",
        "polymarket_private_key",
        "eth_account",
        "create_wallet",
        "post_order",
        "place_order",
    ):
        assert token not in lowered
    polymarket = (root / "polymarket.py").read_text()
    assert ".post(" not in polymarket
    assert "/order" not in polymarket
    assert "prices-history" in polymarket
    scripts = "\n".join(path.read_text() for path in Path("scripts").glob("*.py")).lower()
    assert "private_key" not in scripts
    assert "place_order" not in scripts

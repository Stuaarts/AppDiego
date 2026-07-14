from __future__ import annotations

from decimal import Decimal

from price_monitor.scraping.structured_data import extract_json_ld_product, extract_meta_product


def test_extract_json_ld_product(fixtures_dir) -> None:
    html = (fixtures_dir / "generic_jsonld_product.html").read_text()
    metadata = extract_json_ld_product(html, default_currency="BRL")
    assert metadata is not None
    assert metadata.price == Decimal("1299.90")
    assert metadata.currency == "BRL"
    assert metadata.availability == "in_stock"
    assert metadata.seller_name == "Loja Demo"


def test_extract_meta_product(fixtures_dir) -> None:
    html = (fixtures_dir / "generic_meta_product.html").read_text()
    metadata = extract_meta_product(html, default_currency="BRL")
    assert metadata is not None
    assert metadata.price == Decimal("299.99")
    assert metadata.availability == "out_of_stock"


def test_invalid_json_ld_is_ignored() -> None:
    html = '<script type="application/ld+json">{bad json</script>'
    assert extract_json_ld_product(html, default_currency="BRL") is None

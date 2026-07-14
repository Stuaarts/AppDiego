from __future__ import annotations

from decimal import Decimal

import pytest

from price_monitor.scraping.adapters.generic import GenericStoreAdapter
from price_monitor.scraping.base import ScrapeContext


@pytest.mark.asyncio
async def test_generic_adapter_json_ld(fixtures_dir) -> None:
    html = (fixtures_dir / "generic_jsonld_product.html").read_text()
    adapter = GenericStoreAdapter()
    result = await adapter.extract(
        ScrapeContext(
            listing_id=1,
            url="https://example.com/product",
            currency="BRL",
            store_name="Example",
            store_domain="example.com",
            html=html,
            http_status=200,
            response_time_ms=12,
        )
    )
    assert result.success
    assert result.price == Decimal("1299.90")
    assert result.extraction_method == "json_ld"


@pytest.mark.asyncio
async def test_generic_adapter_css_selectors(fixtures_dir) -> None:
    html = (fixtures_dir / "sale_product.html").read_text()
    adapter = GenericStoreAdapter()
    result = await adapter.extract(
        ScrapeContext(
            listing_id=1,
            url="https://example.com/product",
            currency="BRL",
            store_name="Example",
            store_domain="example.com",
            html=html,
            price_selector=".price",
            regular_price_selector=".regular",
            availability_selector=".availability",
            title_selector=".title",
            http_status=200,
        )
    )
    assert result.success
    assert result.price == Decimal("399.90")
    assert result.regular_price == Decimal("499.90")
    assert result.sale_price == Decimal("399.90")
    assert result.availability == "in_stock"


@pytest.mark.asyncio
async def test_generic_adapter_missing_price() -> None:
    adapter = GenericStoreAdapter()
    result = await adapter.extract(
        ScrapeContext(
            listing_id=1,
            url="https://example.com/product",
            currency="BRL",
            store_name="Example",
            store_domain="example.com",
            html="<html><title>No price</title><body>Indisponivel</body></html>",
            http_status=200,
        )
    )
    assert not result.success
    assert result.error_code == "price_not_found"

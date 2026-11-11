from decimal import Decimal

import httpx
import pytest

from price_monitor.scraping.adapters.generic import GenericStoreAdapter
from price_monitor.scraping.base import ScrapeContext
from price_monitor.scraping.mercado_livre import fetch_mercado_livre_offer, offer_id


def test_exact_offer_id_is_distinct_from_catalog_id():
    url = "https://www.mercadolivre.com.br/product/p/MLB12345"
    assert offer_id(url) is None
    assert offer_id(url + "#wid=MLB987654") == "MLB987654"
    assert offer_id(url + "?item_id=MLB222222#wid=MLB987654") is None
    assert offer_id("https://example.org/p/MLB12345#wid=MLB987654") is None


@pytest.mark.asyncio
async def test_api_pairs_current_sale_price_with_exact_seller():
    def response(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "api.mercadolibre.com"
        assert request.headers["Authorization"] == "Bearer test-token"
        data = {
            "/items/MLB987654": {"id": "MLB987654", "seller_id": 42, "status": "active"},
            "/items/MLB987654/sale_price": {"amount": 119.99, "currency_id": "BRL"},
            "/users/42": {"id": 42, "nickname": "SELLER42"},
        }
        return httpx.Response(200, json=data[request.url.path])

    result = await fetch_mercado_livre_offer(
        "MLB987654", "test-token", transport=httpx.MockTransport(response)
    )
    assert result.success
    assert result.price == Decimal("119.99")
    assert result.seller_name == "SELLER42"


@pytest.mark.asyncio
async def test_amazon_does_not_substitute_a_different_featured_seller():
    context = ScrapeContext(
        1,
        "https://www.amazon.com.br/dp/EXAMPLE123",
        "BRL",
        "Amazon",
        "www.amazon.com.br",
        requested_url="https://www.amazon.com.br/dp/EXAMPLE123?smid=A123",
        html="""
        <div id="corePrice_feature_div">
            <span class="a-price"><span class="a-offscreen">R$ 100,50</span></span>
        </div>
        <a id="sellerProfileTriggerId" href="/sp?seller=A456">Other seller</a>
        """,
    )
    result = await GenericStoreAdapter().extract(context)
    assert not result.success
    assert result.error_code == "marketplace_offer_unverified"

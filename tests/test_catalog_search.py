from decimal import Decimal

import httpx
import pytest

from price_monitor.services import catalog_search

EAN = "7898742842100"


def _product(host: str, sku: str, ean: str, price: float) -> dict:
    return {
        "productName": "Cafeteira Oster",
        "link": f"https://{host}/cafeteira/p",
        "items": [
            {
                "itemId": sku,
                "ean": ean,
                "name": "Cafeteira Oster 220V",
                "sellers": [
                    {
                        "sellerName": "Seller",
                        "commertialOffer": {"Price": price, "IsAvailable": True},
                    },
                    {
                        "sellerName": "Sold out",
                        "commertialOffer": {"Price": 1, "IsAvailable": False},
                    },
                ],
            }
        ],
    }


@pytest.mark.asyncio
async def test_name_search_handles_multiple_words_and_unavailable_store(monkeypatch) -> None:
    monkeypatch.setattr(catalog_search, "CATALOGS", {"A": "a.test", "B": "b.test"})

    def respond(request: httpx.Request) -> httpx.Response:
        assert request.url.raw_path.startswith(
            b"/api/catalog_system/pub/products/search/Cafeteira%20Oster?"
        )
        if request.url.host == "b.test":
            return httpx.Response(429)
        return httpx.Response(200, json=[_product("a.test", "123", EAN, 19.99)])

    result = await catalog_search.search_catalogs(
        " Cafeteira   Oster ", transport=httpx.MockTransport(respond)
    )
    assert result.unavailable_stores == ["B"]
    assert [(offer.store, offer.price) for offer in result.offers] == [("A", Decimal("19.99"))]


@pytest.mark.asyncio
async def test_store_sku_expands_by_barcode_and_excludes_sibling_variant(monkeypatch) -> None:
    monkeypatch.setattr(catalog_search, "CATALOGS", {"A": "a.test", "B": "b.test"})

    def respond(request: httpx.Request) -> httpx.Response:
        host = request.url.host
        search_filter = request.url.params.get("fq")
        products = []
        if search_filter == "skuId:123" and host == "a.test":
            products = [_product(host, "123", EAN, 20)]
        elif search_filter == f"alternateIds_Ean:{EAN}":
            products = (
                [_product(host, "123", EAN, 20)]
                if host == "a.test"
                else [
                    _product(host, "456", EAN, 15),
                    _product(host, "789", "7898742842094", 5),
                    _product("other.test", "10", EAN, 1),
                ]
            )
        return httpx.Response(200, json=products)

    result = await catalog_search.search_catalogs("123", transport=httpx.MockTransport(respond))
    assert [(offer.store, offer.price) for offer in result.offers] == [("B", 15), ("A", 20)]
    assert all(offer.barcode == EAN and offer.exact_code for offer in result.offers)

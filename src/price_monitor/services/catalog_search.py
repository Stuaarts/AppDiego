from __future__ import annotations

import asyncio
import json
import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import quote, urlsplit, urlunsplit

import httpx

CATALOGS = {
    "Lojas Mel": "www.lojasmel.com",
    "Webcontinental": "www.webcontinental.com.br",
    "Oster": "www.oster.com.br",
    "Philco": "www.philco.com.br",
    "Britânia": "www.britania.com.br",
    "Arno": "www.arno.com.br",
    "Electrolux": "loja.electrolux.com.br",
    "Midea": "www.midea.com.br",
    "Multi": "www.multilaser.com.br",
    "Obramax": "www.obramax.com.br",
    "Extrafarma": "www.extrafarma.com.br",
}
SEARCH_PATH = "/api/catalog_system/pub/products/search"
MAX_RESPONSE_BYTES = 3_000_000


@dataclass(frozen=True)
class CatalogOffer:
    store: str
    product: str
    variant: str
    sku: str
    barcode: str
    seller: str
    price: Decimal
    url: str
    exact_code: bool


@dataclass(frozen=True)
class CatalogResults:
    offers: list[CatalogOffer]
    unavailable_stores: list[str]


def normalize_query(query: str) -> str:
    return " ".join(query.split())


async def search_catalogs(
    query: str, *, transport: httpx.AsyncBaseTransport | None = None
) -> CatalogResults:
    query = normalize_query(query)
    if not 2 <= len(query) <= 100 or not _words(query):
        raise ValueError("Digite de 2 a 100 caracteres para buscar um produto.")

    code = bool(re.fullmatch(r"[A-Za-z0-9._/-]+", query))
    barcode = _barcode_key(query)
    filters = [{"fq": f"alternateIds_Ean:{query}"}] if barcode else [{"ft": query}]
    if code and not barcode:
        filters.append({"fq": f"alternateIds_RefId:{query}"})
        if query.isdecimal() and len(query) <= 10 and int(query) <= 2_147_483_647:
            filters.append({"fq": f"skuId:{query}"})

    async with httpx.AsyncClient(
        transport=transport,
        trust_env=False,
        timeout=5,
        limits=httpx.Limits(max_connections=12),
        headers={"Accept": "application/json", "User-Agent": "PriceMonitorDashboard/0.1"},
    ) as client:
        offers, unavailable = await _query_catalogs(client, query, code, filters)
        exact_barcodes = {offer.barcode for offer in offers if offer.exact_code and offer.barcode}
        if code and not barcode and len(exact_barcodes) == 1:
            found_barcode = exact_barcodes.pop()
            matching, second_failures = await _query_catalogs(
                client, found_barcode, True, [{"fq": f"alternateIds_Ean:{found_barcode}"}]
            )
            offers.extend(matching)
            unavailable &= second_failures

    unique: dict[tuple[str, str, str, str], CatalogOffer] = {}
    for offer in sorted(offers, key=lambda entry: (not entry.exact_code, entry.price)):
        key = (offer.store, offer.url, offer.sku, offer.seller)
        unique.setdefault(key, offer)
    return CatalogResults(list(unique.values()), sorted(unavailable))


async def _query_catalogs(
    client: httpx.AsyncClient, query: str, code: bool, filters: list[dict[str, str]]
) -> tuple[list[CatalogOffer], set[str]]:
    requests = [(store, host, params) for params in filters for store, host in CATALOGS.items()]
    pages = await asyncio.gather(*(_fetch(client, host, params) for _, host, params in requests))
    offers: list[CatalogOffer] = []
    available: set[str] = set()
    for (store, host, params), page in zip(requests, pages, strict=True):
        if page is not None:
            available.add(store)
            offers.extend(_offers(page, store, host, query, code, exact_only="fq" in params))
    return offers, set(CATALOGS) - available


async def _fetch(client: httpx.AsyncClient, host: str, params: dict[str, str]) -> list[Any] | None:
    url = f"https://{host}{SEARCH_PATH}"
    if "ft" in params:
        url += "/" + quote(params["ft"], safe="")
        params = {}
    try:
        async with client.stream("GET", url, params={**params, "_from": 0, "_to": 9}) as response:
            response.raise_for_status()
            body = bytearray()
            async for chunk in response.aiter_bytes():
                if len(body) + len(chunk) > MAX_RESPONSE_BYTES:
                    return None
                body.extend(chunk)
        data = json.loads(body, parse_float=Decimal)
    except (httpx.HTTPError, ValueError, RecursionError):
        return None
    return data if isinstance(data, list) else None


def _offers(
    products: list[Any], store: str, host: str, query: str, code: bool, *, exact_only: bool
) -> list[CatalogOffer]:
    results = []
    terms = set(_words(query))
    barcode = _barcode_key(query)
    for product in _objects(products):
        name = _string(product.get("productName"))
        url = _product_url(product.get("link"), host)
        if not name or not url:
            continue
        for item in _objects(product.get("items")):
            variant = _string(item.get("nameComplete")) or _string(item.get("name")) or name
            sku = _string(item.get("itemId"))
            ean = _string(item.get("ean"))
            refs = [_string(ref.get("Value")) for ref in _objects(item.get("referenceId"))]
            exact = (
                barcode == _barcode_key(ean)
                if barcode
                else code and query.casefold() in {s.casefold() for s in [sku, *refs]}
            )
            item_words = set(_words(f"{name} {variant} {' '.join(refs)}"))
            if not exact and (exact_only or not terms <= item_words):
                continue
            for seller in _objects(item.get("sellers")):
                offer = seller.get("commertialOffer")
                if not isinstance(offer, dict) or offer.get("IsAvailable") is not True:
                    continue
                price = _price(offer.get("Price"))
                if price is not None:
                    results.append(
                        CatalogOffer(
                            store,
                            name,
                            variant,
                            sku,
                            ean if _barcode_key(ean) else "",
                            _string(seller.get("sellerName")),
                            price,
                            url,
                            exact,
                        )
                    )
    return results


def _objects(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _string(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _words(value: str) -> list[str]:
    normalized = unicodedata.normalize("NFKD", value.casefold())
    plain = "".join(character for character in normalized if not unicodedata.combining(character))
    return re.findall(r"[^\W_]+", plain)


def _barcode_key(value: str) -> str:
    if value.isascii() and value.isdecimal() and len(value) in (8, 12, 13, 14):
        digits = value.zfill(14)
        checksum = sum(int(digit) * (1 if i % 2 else 3) for i, digit in enumerate(digits))
        if checksum % 10 == 0 and int(value) > 0:
            return digits
    return ""


def _product_url(value: Any, host: str) -> str:
    try:
        parsed = urlsplit(_string(value))
    except ValueError:
        return ""
    if parsed.scheme != "https" or parsed.netloc.lower() != host:
        return ""
    if not re.fullmatch(r"/[\w%./-]+/p/?", parsed.path) or "//" in parsed.path:
        return ""
    return urlunsplit(("https", host, parsed.path, "", ""))


def _price(value: Any) -> Decimal | None:
    if not isinstance(value, (int, Decimal, str)) or isinstance(value, bool):
        return None
    try:
        amount = Decimal(value)
    except InvalidOperation:
        return None
    return amount if amount.is_finite() and 0 < amount <= 999_999_999 else None

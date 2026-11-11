from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from urllib.parse import parse_qs, urlsplit

import httpx

from price_monitor.scraping.base import ScrapeResult

HOSTS = {"mercadolivre.com.br", "www.mercadolivre.com.br", "produto.mercadolivre.com.br"}
ITEM_ID = re.compile(r"MLB-?([0-9]{5,15})", re.IGNORECASE)


def offer_id(url: str) -> str | None:
    parts = urlsplit(url)
    if parts.hostname not in HOSTS:
        return None
    values = [
        value
        for component in (parts.query, parts.fragment)
        for key, items in parse_qs(component).items()
        if key in {"wid", "item_id"}
        for value in items
    ]
    if parts.hostname == "produto.mercadolivre.com.br":
        direct = re.match(r"/(MLB-[0-9]{5,15})(?:-|/|$)", parts.path, re.IGNORECASE)
        if direct:
            values.append(direct.group(1))
    matches = {"MLB" + match[1] for value in values if (match := ITEM_ID.fullmatch(value))}
    return matches.pop() if len(matches) == 1 else None


async def fetch_mercado_livre_offer(
    item_id: str, token: str, *, transport: httpx.AsyncBaseTransport | None = None
) -> ScrapeResult:
    if not ITEM_ID.fullmatch(item_id):
        return ScrapeResult(success=False, error_code="marketplace_offer_unverified")
    try:
        async with httpx.AsyncClient(
            base_url="https://api.mercadolibre.com",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            timeout=7,
            trust_env=False,
            transport=transport,
        ) as client:
            item = await _json(client, f"/items/{item_id}")
            seller_id = item.get("seller_id")
            if item.get("id") != item_id or type(seller_id) is not int or seller_id <= 0:
                return ScrapeResult(success=False, error_code="marketplace_offer_unverified")
            if item.get("status") != "active" or item.get("available_quantity") == 0:
                return ScrapeResult(success=False, error_code="marketplace_offer_inactive")
            price = await _json(
                client, f"/items/{item_id}/sale_price", params={"context": "channel_marketplace"}
            )
            seller = await _json(client, f"/users/{seller_id}")
    except httpx.HTTPStatusError as exc:
        code = exc.response.status_code
        error = "marketplace_api_denied" if code in {401, 403} else f"http_{code}"
        return ScrapeResult(success=False, http_status=code, error_code=error)
    except (httpx.HTTPError, ValueError):
        return ScrapeResult(success=False, error_code="marketplace_api_unavailable")

    amount = _price(price.get("amount"))
    nickname = seller.get("nickname")
    if (
        amount is None
        or price.get("currency_id") != "BRL"
        or seller.get("id") != seller_id
        or not isinstance(nickname, str)
        or not nickname.strip()
    ):
        return ScrapeResult(success=False, error_code="marketplace_offer_unverified")
    title = item.get("title")
    return ScrapeResult(
        success=True,
        price=amount,
        currency="BRL",
        availability="in_stock",
        seller_name=nickname.strip()[:180],
        page_title=title[:500] if isinstance(title, str) else None,
        extraction_method="mercado_livre_api",
        http_status=200,
    )


async def _json(
    client: httpx.AsyncClient, path: str, *, params: dict[str, str] | None = None
) -> dict:
    response = await client.get(path, params=params)
    response.raise_for_status()
    value = response.json(parse_float=Decimal)
    if not isinstance(value, dict):
        raise ValueError("Unexpected marketplace response.")
    return value


def _price(raw: object) -> Decimal | None:
    if not isinstance(raw, (int, Decimal, str)) or isinstance(raw, bool):
        return None
    try:
        amount = Decimal(raw)
    except InvalidOperation:
        return None
    return amount if amount.is_finite() and 0 < amount < 10**10 else None

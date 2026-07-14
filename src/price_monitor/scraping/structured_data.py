from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from bs4 import BeautifulSoup

from price_monitor.scraping.base import normalize_availability
from price_monitor.scraping.price_parser import parse_price


@dataclass(frozen=True)
class ProductMetadata:
    price: Decimal | None = None
    regular_price: Decimal | None = None
    sale_price: Decimal | None = None
    currency: str | None = None
    availability: str = "unknown"
    seller_name: str | None = None
    page_title: str | None = None
    method: str = "unknown"
    diagnostics: tuple[str, ...] = ()


def extract_json_ld_product(
    html: str, default_currency: str | None = None
) -> ProductMetadata | None:
    soup = BeautifulSoup(html, "lxml")
    diagnostics: list[str] = []
    for block in soup.find_all("script", attrs={"type": "application/ld+json"}):
        if not block.string:
            continue
        try:
            payload = json.loads(block.string)
        except json.JSONDecodeError:
            diagnostics.append("invalid_json_ld")
            continue
        for node in _flatten_json_ld(payload):
            if _node_type_matches(node, "Product"):
                metadata = _metadata_from_product_node(node, default_currency)
                if metadata.price is not None or metadata.regular_price is not None:
                    return metadata
            if _node_type_matches(node, "Offer") or _node_type_matches(node, "AggregateOffer"):
                metadata = _metadata_from_offer_node(node, default_currency, page_title=None)
                if metadata.price is not None:
                    return metadata
    return None


def extract_meta_product(html: str, default_currency: str | None = None) -> ProductMetadata | None:
    soup = BeautifulSoup(html, "lxml")
    title = _text_or_none(soup.find("title"))
    fields = {}
    for tag in soup.find_all("meta"):
        key = tag.get("property") or tag.get("name") or tag.get("itemprop")
        content = tag.get("content")
        if key and content:
            fields[key.lower()] = content.strip()

    price_raw = (
        fields.get("product:price:amount")
        or fields.get("og:price:amount")
        or fields.get("twitter:data1")
        or fields.get("price")
    )
    if not price_raw:
        return None
    currency = (
        fields.get("product:price:currency")
        or fields.get("og:price:currency")
        or fields.get("pricecurrency")
        or default_currency
    )
    parsed = parse_price(price_raw, default_currency=currency)
    if not parsed.ok:
        return ProductMetadata(
            currency=currency,
            page_title=fields.get("og:title") or title,
            method="meta",
            diagnostics=tuple(parsed.diagnostics),
        )
    return ProductMetadata(
        price=parsed.value,
        currency=parsed.currency or currency,
        availability=normalize_availability(fields.get("product:availability")),
        page_title=fields.get("og:title") or title,
        method="meta",
        diagnostics=tuple(parsed.diagnostics),
    )


def _flatten_json_ld(payload: Any) -> Iterable[dict[str, Any]]:
    if isinstance(payload, list):
        for item in payload:
            yield from _flatten_json_ld(item)
        return
    if not isinstance(payload, dict):
        return
    yield payload
    graph = payload.get("@graph")
    if isinstance(graph, list):
        for item in graph:
            yield from _flatten_json_ld(item)
    for key in ("offers", "mainEntity", "itemOffered"):
        child = payload.get(key)
        if isinstance(child, (dict, list)):
            yield from _flatten_json_ld(child)


def _node_type_matches(node: dict[str, Any], expected: str) -> bool:
    node_type = node.get("@type")
    if isinstance(node_type, list):
        return any(str(value).lower() == expected.lower() for value in node_type)
    return str(node_type).lower() == expected.lower()


def _metadata_from_product_node(
    node: dict[str, Any], default_currency: str | None
) -> ProductMetadata:
    offers = node.get("offers")
    page_title = _as_text(node.get("name"))
    if isinstance(offers, list):
        offer_nodes = [offer for offer in offers if isinstance(offer, dict)]
        parsed_offers = [
            _metadata_from_offer_node(offer, default_currency, page_title=page_title)
            for offer in offer_nodes
        ]
        valid = [metadata for metadata in parsed_offers if metadata.price is not None]
        if valid:
            return min(valid, key=lambda item: item.price or Decimal("0"))
    if isinstance(offers, dict):
        return _metadata_from_offer_node(offers, default_currency, page_title=page_title)
    price = node.get("price")
    currency = _as_text(node.get("priceCurrency")) or default_currency
    parsed = parse_price(_as_text(price), default_currency=currency) if price is not None else None
    return ProductMetadata(
        price=parsed.value if parsed and parsed.ok else None,
        currency=(parsed.currency if parsed else None) or currency,
        availability=normalize_availability(_as_text(node.get("availability"))),
        page_title=page_title,
        method="json_ld",
        diagnostics=tuple(parsed.diagnostics if parsed else []),
    )


def _metadata_from_offer_node(
    node: dict[str, Any], default_currency: str | None, page_title: str | None
) -> ProductMetadata:
    currency = _as_text(node.get("priceCurrency")) or default_currency
    raw_price = node.get("price") or node.get("lowPrice") or node.get("highPrice")
    parsed = (
        parse_price(_as_text(raw_price), default_currency=currency)
        if raw_price is not None
        else None
    )
    seller = node.get("seller")
    seller_name = seller.get("name") if isinstance(seller, dict) else _as_text(seller)
    return ProductMetadata(
        price=parsed.value if parsed and parsed.ok else None,
        currency=(parsed.currency if parsed else None) or currency,
        availability=normalize_availability(_as_text(node.get("availability"))),
        seller_name=seller_name,
        page_title=page_title,
        method="json_ld",
        diagnostics=tuple(parsed.diagnostics if parsed else ["missing_offer_price"]),
    )


def _as_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (int, float, Decimal)):
        return str(value)
    if isinstance(value, str):
        return value.strip() or None
    return None


def _text_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = value.get_text(" ", strip=True)
    return text or None

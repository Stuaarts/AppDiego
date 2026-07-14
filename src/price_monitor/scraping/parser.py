from __future__ import annotations

from dataclasses import replace

from bs4 import BeautifulSoup

from price_monitor.scraping.base import normalize_availability
from price_monitor.scraping.price_parser import parse_all_prices, parse_price
from price_monitor.scraping.structured_data import (
    ProductMetadata,
    extract_json_ld_product,
    extract_meta_product,
)


def extract_product_metadata(
    html: str,
    default_currency: str,
    price_selector: str | None = None,
    regular_price_selector: str | None = None,
    availability_selector: str | None = None,
    title_selector: str | None = None,
) -> ProductMetadata:
    json_ld = extract_json_ld_product(html, default_currency=default_currency)
    if json_ld and json_ld.price is not None:
        return _with_selector_overrides(
            json_ld,
            html,
            default_currency,
            price_selector,
            regular_price_selector,
            availability_selector,
            title_selector,
        )

    meta = extract_meta_product(html, default_currency=default_currency)
    if meta and meta.price is not None:
        return _with_selector_overrides(
            meta,
            html,
            default_currency,
            price_selector,
            regular_price_selector,
            availability_selector,
            title_selector,
        )

    selector_result = _extract_from_selectors(
        html,
        default_currency,
        price_selector,
        regular_price_selector,
        availability_selector,
        title_selector,
    )
    if selector_result.price is not None:
        return selector_result

    fallback = _extract_from_text(html, default_currency)
    return _with_selector_overrides(
        fallback,
        html,
        default_currency,
        price_selector,
        regular_price_selector,
        availability_selector,
        title_selector,
    )


def _with_selector_overrides(
    metadata: ProductMetadata,
    html: str,
    default_currency: str,
    price_selector: str | None,
    regular_price_selector: str | None,
    availability_selector: str | None,
    title_selector: str | None,
) -> ProductMetadata:
    selectors = _extract_from_selectors(
        html,
        default_currency,
        price_selector,
        regular_price_selector,
        availability_selector,
        title_selector,
    )
    price = selectors.price if price_selector and selectors.price is not None else metadata.price
    regular_price = (
        selectors.regular_price
        if regular_price_selector and selectors.regular_price is not None
        else metadata.regular_price
    )
    availability = (
        selectors.availability
        if availability_selector and selectors.availability != "unknown"
        else metadata.availability
    )
    page_title = (
        selectors.page_title if title_selector and selectors.page_title else metadata.page_title
    )
    method = "selector" if selectors.price is not None and price_selector else metadata.method
    return replace(
        metadata,
        price=price,
        regular_price=regular_price,
        availability=availability,
        page_title=page_title,
        method=method,
    )


def _extract_from_selectors(
    html: str,
    default_currency: str,
    price_selector: str | None,
    regular_price_selector: str | None,
    availability_selector: str | None,
    title_selector: str | None,
) -> ProductMetadata:
    soup = BeautifulSoup(html, "lxml")
    diagnostics: list[str] = []
    price = None
    regular_price = None
    currency = default_currency
    if price_selector:
        text = _selector_text(soup, price_selector)
        parsed = parse_price(text, default_currency=default_currency)
        diagnostics.extend(parsed.diagnostics)
        if parsed.ok:
            price = parsed.value
            currency = parsed.currency or currency
    if regular_price_selector:
        text = _selector_text(soup, regular_price_selector)
        parsed = parse_price(text, default_currency=default_currency)
        diagnostics.extend(parsed.diagnostics)
        if parsed.ok:
            regular_price = parsed.value
            currency = parsed.currency or currency
    availability = normalize_availability(_selector_text(soup, availability_selector))
    title = _selector_text(soup, title_selector) or _selector_text(soup, "title")
    return ProductMetadata(
        price=price,
        regular_price=regular_price,
        sale_price=price if regular_price and price and price < regular_price else None,
        currency=currency,
        availability=availability,
        page_title=title,
        method="selector",
        diagnostics=tuple(diagnostics),
    )


def _extract_from_text(html: str, default_currency: str) -> ProductMetadata:
    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text(" ", strip=True)
    prices = parse_all_prices(text[:20_000], default_currency=default_currency)
    title = _selector_text(soup, "title")
    if not prices:
        return ProductMetadata(
            currency=default_currency,
            page_title=title,
            method="text_fallback",
            diagnostics=("price_not_found",),
        )
    first = prices[0]
    return ProductMetadata(
        price=first.value,
        currency=first.currency or default_currency,
        page_title=title,
        method="text_fallback",
        diagnostics=tuple(first.diagnostics),
    )


def _selector_text(soup: BeautifulSoup, selector: str | None) -> str | None:
    if not selector:
        return None
    try:
        element = soup.select_one(selector)
    except Exception:
        return None
    if element is None:
        return None
    if element.name == "meta":
        content = element.get("content")
        return content.strip() if isinstance(content, str) else None
    text = element.get_text(" ", strip=True)
    return text or None

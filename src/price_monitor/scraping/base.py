from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Protocol

AVAILABILITY_VALUES = {
    "in_stock",
    "out_of_stock",
    "preorder",
    "backorder",
    "limited",
    "unknown",
}


@dataclass(frozen=True)
class ScrapeContext:
    listing_id: int
    url: str
    currency: str
    store_name: str
    store_domain: str
    requires_browser: bool = False
    scraping_method: str = "auto"
    price_selector: str | None = None
    regular_price_selector: str | None = None
    availability_selector: str | None = None
    title_selector: str | None = None
    html: str | None = None
    http_status: int | None = None
    response_time_ms: int | None = None
    content_fingerprint: str | None = None
    requested_url: str | None = None


@dataclass(frozen=True)
class ScrapeResult:
    success: bool
    price: Decimal | None = None
    regular_price: Decimal | None = None
    sale_price: Decimal | None = None
    currency: str | None = None
    availability: str = "unknown"
    seller_name: str | None = None
    page_title: str | None = None
    extraction_method: str | None = None
    http_status: int | None = None
    response_time_ms: int | None = None
    error_code: str | None = None
    error_message: str | None = None
    content_fingerprint: str | None = None
    diagnostics: list[str] = field(default_factory=list)


class StoreAdapter(Protocol):
    key: str

    def supports(self, url: str) -> bool: ...

    async def extract(self, context: ScrapeContext) -> ScrapeResult: ...


def normalize_availability(value: str | None) -> str:
    if not value:
        return "unknown"
    text = value.strip().lower()
    positive = [
        "instock",
        "in stock",
        "disponivel",
        "disponivel em estoque",
        "em estoque",
        "available",
        "availability/instock",
    ]
    negative = [
        "outofstock",
        "out of stock",
        "indisponivel",
        "sem estoque",
        "unavailable",
        "esgotado",
        "availability/outofstock",
    ]
    limited = ["limited", "baixo estoque", "ultimas unidades", "last units"]
    preorder = ["preorder", "pre-order", "pre venda", "pre-venda"]
    backorder = ["backorder", "sob encomenda"]
    if any(term in text for term in negative):
        return "out_of_stock"
    if any(term in text for term in positive):
        return "in_stock"
    if any(term in text for term in limited):
        return "limited"
    if any(term in text for term in preorder):
        return "preorder"
    if any(term in text for term in backorder):
        return "backorder"
    return "unknown"

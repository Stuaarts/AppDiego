from __future__ import annotations

from dataclasses import replace
from urllib.parse import urlsplit

from bs4 import BeautifulSoup

from price_monitor.config import load_settings
from price_monitor.scraping.base import ScrapeContext, ScrapeResult
from price_monitor.scraping.browser import fetch_rendered_html
from price_monitor.scraping.parser import extract_product_metadata
from price_monitor.security import sanitize_error_message


class GenericStoreAdapter:
    key = "generic"

    def supports(self, url: str) -> bool:
        return url.startswith(("http://", "https://"))

    async def extract(self, context: ScrapeContext) -> ScrapeResult:
        html = context.html
        response_time_ms = context.response_time_ms
        fingerprint = context.content_fingerprint
        if not html:
            return ScrapeResult(
                success=False,
                http_status=context.http_status,
                response_time_ms=response_time_ms,
                content_fingerprint=fingerprint,
                error_code="price_not_found",
                error_message="Nenhum HTML disponivel para extracao.",
            )
        if _looks_like_captcha(html):
            return ScrapeResult(
                success=False,
                http_status=context.http_status,
                response_time_ms=response_time_ms,
                content_fingerprint=fingerprint,
                error_code="captcha_detected",
                error_message="Pagina parece exigir CAPTCHA ou verificacao manual.",
            )

        amazon = urlsplit(context.url).hostname in {"amazon.com.br", "www.amazon.com.br"}
        metadata = extract_product_metadata(
            html,
            default_currency=context.currency,
            price_selector=context.price_selector
            or (
                "#corePrice_feature_div .a-price:not(.a-text-price) .a-offscreen"
                if amazon
                else None
            ),
            regular_price_selector=context.regular_price_selector,
            availability_selector=context.availability_selector,
            title_selector=context.title_selector,
        )
        if amazon and metadata.price is not None and not metadata.seller_name:
            seller = BeautifulSoup(html, "lxml").select_one("#sellerProfileTriggerId")
            if seller is not None:
                metadata = replace(metadata, seller_name=seller.get_text(" ", strip=True) or None)
        if metadata.price is None and _should_try_browser(context):
            rendered = await fetch_rendered_html(
                context.url,
                load_settings(validate=False),
                wait_selector=context.price_selector,
            )
            if rendered.ok and rendered.html:
                response_time_ms = rendered.response_time_ms
                fingerprint = rendered.content_fingerprint
                metadata = extract_product_metadata(
                    rendered.html,
                    default_currency=context.currency,
                    price_selector=context.price_selector,
                    regular_price_selector=context.regular_price_selector,
                    availability_selector=context.availability_selector,
                    title_selector=context.title_selector,
                )
            elif rendered.error_code:
                return ScrapeResult(
                    success=False,
                    http_status=context.http_status,
                    response_time_ms=response_time_ms,
                    content_fingerprint=fingerprint,
                    error_code=rendered.error_code,
                    error_message=rendered.error_message,
                )

        if metadata.price is None or (
            context.scraping_method == "structured" and metadata.method == "text_fallback"
        ):
            return ScrapeResult(
                success=False,
                currency=metadata.currency or context.currency,
                availability=metadata.availability,
                page_title=metadata.page_title,
                http_status=context.http_status,
                response_time_ms=response_time_ms,
                content_fingerprint=fingerprint,
                extraction_method=metadata.method,
                error_code="price_not_found",
                error_message=sanitize_error_message(
                    "; ".join(metadata.diagnostics) or "Preco nao encontrado."
                ),
                diagnostics=list(metadata.diagnostics),
            )
        return ScrapeResult(
            success=True,
            price=metadata.price,
            regular_price=metadata.regular_price,
            sale_price=metadata.sale_price,
            currency=metadata.currency or context.currency,
            availability=metadata.availability,
            seller_name=metadata.seller_name,
            page_title=metadata.page_title,
            extraction_method=metadata.method,
            http_status=context.http_status,
            response_time_ms=response_time_ms,
            content_fingerprint=fingerprint,
            diagnostics=list(metadata.diagnostics),
        )


def _looks_like_captcha(html: str) -> bool:
    soup = BeautifulSoup(html, "lxml")
    title = soup.title.get_text(" ", strip=True).lower() if soup.title else ""
    return any(term in title for term in ("captcha", "robot check", "just a moment")) or (
        soup.select_one("form[action*='validateCaptcha'], form#challenge-form") is not None
    )


def _should_try_browser(context: ScrapeContext) -> bool:
    return context.scraping_method != "structured" and (
        context.requires_browser or context.scraping_method == "browser"
    )

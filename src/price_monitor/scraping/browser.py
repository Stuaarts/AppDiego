from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass

from price_monitor.config import Settings
from price_monitor.security import normalize_public_url, sanitize_error_message


@dataclass(frozen=True)
class BrowserFetchResult:
    ok: bool
    html: str | None = None
    response_time_ms: int | None = None
    content_fingerprint: str | None = None
    error_code: str | None = None
    error_message: str | None = None


async def fetch_rendered_html(
    url: str, settings: Settings, wait_selector: str | None = None
) -> BrowserFetchResult:
    if not settings.playwright_enabled:
        return BrowserFetchResult(
            ok=False, error_code="browser_error", error_message="Playwright desativado."
        )
    validation = normalize_public_url(url)
    if not validation.ok:
        return BrowserFetchResult(
            ok=False,
            error_code=validation.error_code,
            error_message=validation.error_message,
        )

    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return BrowserFetchResult(
            ok=False,
            error_code="browser_error",
            error_message="Playwright nao esta instalado neste ambiente.",
        )

    start = time.perf_counter()
    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            context = await browser.new_context(java_script_enabled=True)
            page = await context.new_page()

            async def route_handler(route: object) -> None:
                request = route.request
                if request.resource_type in {"font", "media"}:
                    await route.abort()
                else:
                    await route.continue_()

            await page.route("**/*", route_handler)
            await page.goto(
                validation.normalized_url, wait_until="domcontentloaded", timeout=30_000
            )
            if wait_selector:
                await page.wait_for_selector(wait_selector, timeout=10_000)
            html = await page.content()
            await context.close()
            await browser.close()
    except Exception as exc:
        return BrowserFetchResult(
            ok=False,
            response_time_ms=int((time.perf_counter() - start) * 1000),
            error_code="browser_error",
            error_message=sanitize_error_message(str(exc)),
        )
    content = html.encode()
    return BrowserFetchResult(
        ok=True,
        html=html,
        response_time_ms=int((time.perf_counter() - start) * 1000),
        content_fingerprint=hashlib.sha256(content).hexdigest(),
    )

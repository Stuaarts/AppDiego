from __future__ import annotations

import asyncio
import hashlib
import time
from dataclasses import dataclass
from urllib.parse import urljoin

import httpx

from price_monitor.config import Settings
from price_monitor.security import (
    normalize_public_url,
    sanitize_error_message,
    validate_redirect_url,
)


@dataclass(frozen=True)
class HttpFetchResult:
    ok: bool
    url: str
    html: str | None = None
    status_code: int | None = None
    response_time_ms: int | None = None
    content_fingerprint: str | None = None
    error_code: str | None = None
    error_message: str | None = None


class ScrapeHttpClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.headers = {
            "User-Agent": (
                "PriceMonitorDashboard/0.1 (+internal price research; contact owner if needed)"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }

    async def fetch(self, url: str) -> HttpFetchResult:
        validation = normalize_public_url(url)
        if not validation.ok:
            return HttpFetchResult(
                ok=False,
                url=url,
                error_code=validation.error_code,
                error_message=validation.error_message,
            )
        current_url = validation.normalized_url
        start = time.perf_counter()
        async with httpx.AsyncClient(
            headers=self.headers,
            timeout=self.settings.request_timeout_seconds,
            follow_redirects=False,
        ) as client:
            for attempt in range(self.settings.max_retries + 1):
                try:
                    return await self._fetch_with_redirects(client, current_url, start)
                except httpx.TimeoutException as exc:
                    if attempt >= self.settings.max_retries:
                        return self._exception_result("request_timeout", exc, current_url, start)
                except httpx.ConnectError as exc:
                    if attempt >= self.settings.max_retries:
                        return self._exception_result("connection_error", exc, current_url, start)
                except httpx.HTTPError as exc:
                    if attempt >= self.settings.max_retries:
                        return self._exception_result("unexpected_error", exc, current_url, start)
                await asyncio.sleep(0.5 * (2**attempt))
        return HttpFetchResult(ok=False, url=current_url, error_code="unexpected_error")

    async def _fetch_with_redirects(
        self, client: httpx.AsyncClient, url: str, start: float
    ) -> HttpFetchResult:
        for _ in range(6):
            response = await client.get(url)
            if not response.is_redirect:
                return self._response_to_result(response, url, start)
            url, error = self._handle_redirect(response, url)
            if error:
                return error
        return HttpFetchResult(
            ok=False,
            url=url,
            error_code="too_many_redirects",
            error_message="A loja redirecionou a página muitas vezes.",
        )

    def _handle_redirect(
        self, response: httpx.Response, current_url: str
    ) -> tuple[str, HttpFetchResult | None]:
        if not response.is_redirect:
            return current_url, None
        location = response.headers.get("location")
        if not location:
            return current_url, HttpFetchResult(
                ok=False,
                url=current_url,
                status_code=response.status_code,
                error_code="invalid_url",
                error_message="Redirecionamento sem destino.",
            )
        redirected = urljoin(current_url, location)
        validation = validate_redirect_url(redirected)
        if not validation.ok:
            return current_url, HttpFetchResult(
                ok=False,
                url=current_url,
                status_code=response.status_code,
                error_code=validation.error_code,
                error_message=f"Destino de redirecionamento rejeitado: {validation.error_message}",
            )
        return validation.normalized_url, None

    def _response_to_result(
        self, response: httpx.Response, url: str, start: float
    ) -> HttpFetchResult:
        duration_ms = int((time.perf_counter() - start) * 1000)
        status = response.status_code
        if status == 403:
            return HttpFetchResult(
                False, url, status_code=status, response_time_ms=duration_ms, error_code="http_403"
            )
        if status == 404:
            return HttpFetchResult(
                False, url, status_code=status, response_time_ms=duration_ms, error_code="http_404"
            )
        if status == 429:
            return HttpFetchResult(
                False, url, status_code=status, response_time_ms=duration_ms, error_code="http_429"
            )
        if status >= 500:
            return HttpFetchResult(
                False,
                url,
                status_code=status,
                response_time_ms=duration_ms,
                error_code="http_server_error",
            )
        if status >= 400:
            return HttpFetchResult(
                False,
                url,
                status_code=status,
                response_time_ms=duration_ms,
                error_code="http_error",
            )
        content_type = response.headers.get("content-type", "")
        if "html" not in content_type and "xml" not in content_type and content_type:
            return HttpFetchResult(
                False,
                url,
                status_code=status,
                response_time_ms=duration_ms,
                error_code="unsupported_content_type",
                error_message="Resposta nao parece ser HTML.",
            )
        content = response.content[: self.settings.max_response_bytes + 1]
        if len(content) > self.settings.max_response_bytes:
            return HttpFetchResult(
                False,
                url,
                status_code=status,
                response_time_ms=duration_ms,
                error_code="response_too_large",
                error_message="Resposta excedeu o limite configurado.",
            )
        html = response.text
        fingerprint = hashlib.sha256(content).hexdigest()
        return HttpFetchResult(
            ok=True,
            url=url,
            html=html,
            status_code=status,
            response_time_ms=duration_ms,
            content_fingerprint=fingerprint,
        )

    def _exception_result(
        self, code: str, exc: Exception, url: str, start: float
    ) -> HttpFetchResult:
        return HttpFetchResult(
            ok=False,
            url=url,
            response_time_ms=int((time.perf_counter() - start) * 1000),
            error_code=code,
            error_message=sanitize_error_message(str(exc)),
        )

from __future__ import annotations

import asyncio
from collections import defaultdict
from dataclasses import replace

from price_monitor.config import Settings
from price_monitor.scraping.base import ScrapeContext, ScrapeResult
from price_monitor.scraping.client import ScrapeHttpClient
from price_monitor.services.price_report import ImportedTable, OfferReview, PriceReport, PriceRow
from price_monitor.services.product_import import count_import_links, valid_import_links
from price_monitor.services.scrape_service import Fetcher, fetch_price

MAX_REPORT_LINKS = 50
FAILURES = {
    "captcha_detected": "A loja exige verificação humana.",
    "http_403": "A loja bloqueou a consulta (403).",
    "http_404": "Página do produto não encontrada (404).",
    "http_429": "A loja limitou as consultas (429).",
    "http_server_error": "A loja retornou erro de servidor.",
    "too_many_redirects": "A loja redirecionou a página muitas vezes.",
    "request_timeout": "A loja não respondeu a tempo.",
    "price_not_found": "A página não expôs um preço verificável.",
    "invalid_url": "A página ou destino do redirecionamento é inválido.",
    "marketplace_offer_unverified": "Não foi possível confirmar a oferta do vendedor do link.",
    "marketplace_offer_inactive": "A oferta do vendedor está inativa ou sem estoque.",
    "marketplace_api_denied": "A API do Mercado Livre recusou a autorização.",
    "marketplace_api_required": "Conecte a API do Mercado Livre para confirmar esta oferta.",
    "marketplace_api_unavailable": "A API do Mercado Livre não respondeu.",
}


async def report_link_prices(
    table: ImportedTable,
    product_column: int,
    link_columns: tuple[int, ...],
    settings: Settings,
    *,
    fetcher: Fetcher | None = None,
) -> PriceReport:
    if count_import_links(table, link_columns) > MAX_REPORT_LINKS:
        raise ValueError(f"Consulte até {MAX_REPORT_LINKS} links por relatório.")
    entries: list[tuple[int, str, str, str]] = []
    report = PriceReport(from_links=True)
    for line, row in table.rows:
        product = str(row[product_column])
        if not product:
            report.issues.append((line, "", "Nome do produto ausente."))
            continue
        issues: list[tuple[int, str]] = []
        links = valid_import_links(table.headers, line, row, link_columns, issues)
        report.issues.extend((line, product, reason) for _, reason in issues)
        if not links and not issues:
            report.issues.append((line, product, "Nenhum link preenchido."))
        entries.extend((line, product, url, host) for url, host in links.items())

    by_host: dict[str, set[str]] = defaultdict(set)
    for _, _, url, host in entries:
        by_host[host].add(url)
    fetcher = fetcher or ScrapeHttpClient(
        replace(
            settings,
            request_timeout_seconds=min(settings.request_timeout_seconds, 8),
            max_retries=0,
        )
    )
    results = await _check_urls(by_host, fetcher)
    for line, product, url, host in entries:
        result = results.get(url)
        if result is None:
            reason = "Tempo limite do relatório atingido."
        elif result.success and result.price is not None and result.availability == "out_of_stock":
            reason = "Produto indisponível na loja."
        elif result.success and result.price is not None and result.currency == "BRL":
            if not result.seller_name:
                report.reviews.append(
                    OfferReview(
                        line, product, host, url, "Vendedor não informado.", len(report.rows)
                    )
                )
            origin = (
                "API Mercado Livre"
                if result.extraction_method == "mercado_livre_api"
                else "Página da loja"
            )
            report.rows.append(
                PriceRow(
                    result.price,
                    product,
                    result.seller_name or "",
                    store=host,
                    url=url,
                    origin=origin,
                )
            )
            continue
        elif result.success and result.currency != "BRL":
            reason = "A página informa preço em outra moeda."
        else:
            reason = FAILURES.get(result.error_code, "Não foi possível consultar a página.")
        report.reviews.append(OfferReview(line, product, host, url, reason))
    return report


async def _check_urls(by_host: dict[str, set[str]], fetcher: Fetcher) -> dict[str, ScrapeResult]:
    results: dict[str, ScrapeResult] = {}
    slots = asyncio.Semaphore(4)

    async def check_host(host: str, urls: set[str]) -> None:
        for url in sorted(urls):
            async with slots:
                context = ScrapeContext(0, url, "BRL", host, host, scraping_method="structured")
                results[url] = await fetch_price(context, fetcher)

    if by_host:
        tasks = [asyncio.create_task(check_host(host, urls)) for host, urls in by_host.items()]
        _, pending = await asyncio.wait(tasks, timeout=55)
        for task in pending:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
    return results

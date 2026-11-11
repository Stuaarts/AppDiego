from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass, replace
from datetime import timedelta
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from price_monitor.config import Settings
from price_monitor.models import Listing, PriceObservation, RunLock, ScrapeRun
from price_monitor.scraping.base import ScrapeContext, ScrapeResult
from price_monitor.scraping.client import HttpFetchResult, ScrapeHttpClient
from price_monitor.scraping.registry import get_adapter
from price_monitor.security import sanitize_error_message
from price_monitor.time import ensure_aware_utc, utc_now


class Fetcher(Protocol):
    async def fetch(self, url: str) -> HttpFetchResult: ...


@dataclass(frozen=True)
class ScrapeBatchResult:
    run_id: int
    total: int
    successful: int
    failed: int
    status: str


class ScrapeAlreadyRunningError(RuntimeError):
    pass


async def scrape(
    session_factory: sessionmaker[Session],
    settings: Settings,
    *,
    trigger_source: str,
    product_id: int | None = None,
    listing_id: int | None = None,
    fetcher: Fetcher | None = None,
) -> ScrapeBatchResult:
    fetcher = fetcher or ScrapeHttpClient(settings)
    token = _acquire_lock(session_factory)
    try:
        with session_factory() as session:
            run = ScrapeRun(trigger_source=trigger_source, status="running")
            session.add(run)
            session.commit()
            run_id = run.id

        listing_ids = _select_listing_ids(
            session_factory, product_id=product_id, listing_id=listing_id
        )
        sem = asyncio.Semaphore(settings.global_scrape_concurrency)
        results: list[ScrapeResult] = []
        for current_listing_id in listing_ids:
            async with sem:
                results.append(
                    await _scrape_listing(
                        session_factory,
                        run_id=run_id,
                        listing_id=current_listing_id,
                        fetcher=fetcher,
                    )
                )

        successful = sum(1 for result in results if result.success)
        failed = len(results) - successful
        with session_factory() as session:
            run = session.get(ScrapeRun, run_id)
            if run is not None:
                run.total_listings = len(results)
                run.successful_listings = successful
                run.failed_listings = failed
                run.status = "success" if failed == 0 else "partial_success"
                run.finished_at = utc_now()
                run.duration_ms = int(
                    (
                        ensure_aware_utc(run.finished_at) - ensure_aware_utc(run.started_at)
                    ).total_seconds()
                    * 1000
                )
                run.summary = json.dumps(
                    {"successful": successful, "failed": failed}, ensure_ascii=False
                )
            session.commit()
        status = "success" if failed == 0 else "partial_success"
        return ScrapeBatchResult(run_id, len(results), successful, failed, status)
    except Exception:
        _mark_latest_run_failed(session_factory)
        raise
    finally:
        _release_lock(session_factory, token)


def _acquire_lock(session_factory: sessionmaker[Session]) -> str:
    token = str(uuid.uuid4())
    now = utc_now()
    locked_until = now + timedelta(hours=1)
    with session_factory() as session:
        lock = session.get(RunLock, "scrape")
        if lock and ensure_aware_utc(lock.locked_until) > now:
            raise ScrapeAlreadyRunningError("A price collection run is already active.")
        if lock is None:
            lock = RunLock(name="scrape", token=token, locked_until=locked_until)
            session.add(lock)
        else:
            lock.token = token
            lock.locked_until = locked_until
        session.commit()
    return token


def _release_lock(session_factory: sessionmaker[Session], token: str) -> None:
    with session_factory() as session:
        lock = session.get(RunLock, "scrape")
        if lock and lock.token == token:
            lock.locked_until = utc_now() - timedelta(seconds=1)
            session.commit()


def _mark_latest_run_failed(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        run = session.scalar(select(ScrapeRun).order_by(ScrapeRun.id.desc()).limit(1))
        if run and run.status == "running":
            run.status = "failed"
            run.finished_at = utc_now()
            session.commit()


def _select_listing_ids(
    session_factory: sessionmaker[Session],
    *,
    product_id: int | None,
    listing_id: int | None,
) -> list[int]:
    with session_factory() as session:
        query = select(Listing.id).where(Listing.active.is_(True))
        if product_id is not None:
            query = query.where(Listing.product_id == product_id)
        if listing_id is not None:
            query = query.where(Listing.id == listing_id)
        return list(session.scalars(query.order_by(Listing.id)))


async def _scrape_listing(
    session_factory: sessionmaker[Session],
    *,
    run_id: int,
    listing_id: int,
    fetcher: Fetcher,
) -> ScrapeResult:
    with session_factory() as session:
        listing = session.get(Listing, listing_id)
        if listing is None or not listing.active:
            return ScrapeResult(success=False, error_code="invalid_listing")
        context = _context_from_listing(listing)
        adapter_key = listing.store.adapter_key

    result = await fetch_price(context, fetcher, adapter_key)
    _record_result(session_factory, run_id=run_id, listing_id=listing_id, result=result)
    return result


async def fetch_price(
    context: ScrapeContext, fetcher: Fetcher, adapter_key: str = "generic"
) -> ScrapeResult:
    try:
        fetch = await fetcher.fetch(context.url)
    except ValueError:
        return ScrapeResult(success=False, error_code="invalid_url")
    if not fetch.ok:
        return ScrapeResult(
            success=False,
            currency=context.currency,
            availability="unknown",
            http_status=fetch.status_code,
            response_time_ms=fetch.response_time_ms,
            error_code=fetch.error_code or "request_error",
            error_message=fetch.error_message,
        )
    try:
        return await get_adapter(adapter_key).extract(
            replace(
                context,
                url=fetch.url,
                html=fetch.html,
                http_status=fetch.status_code,
                response_time_ms=fetch.response_time_ms,
                content_fingerprint=fetch.content_fingerprint,
            )
        )
    except Exception as exc:
        return ScrapeResult(
            success=False,
            currency=context.currency,
            http_status=fetch.status_code,
            response_time_ms=fetch.response_time_ms,
            error_code="unexpected_error",
            error_message=sanitize_error_message(str(exc)),
            content_fingerprint=fetch.content_fingerprint,
        )


def _context_from_listing(listing: Listing) -> ScrapeContext:
    return ScrapeContext(
        listing_id=listing.id,
        url=listing.url,
        currency=listing.currency or listing.store.default_currency,
        store_name=listing.store.name,
        store_domain=listing.store.domain,
        requires_browser=listing.store.requires_browser,
        scraping_method=listing.scraping_method,
        price_selector=listing.price_selector,
        regular_price_selector=listing.regular_price_selector,
        availability_selector=listing.availability_selector,
        title_selector=listing.title_selector,
    )


def _record_result(
    session_factory: sessionmaker[Session],
    *,
    run_id: int,
    listing_id: int,
    result: ScrapeResult,
) -> None:
    now = utc_now()
    with session_factory() as session:
        listing = session.get(Listing, listing_id)
        if listing is None:
            return
        observation = PriceObservation(
            listing_id=listing_id,
            scrape_run_id=run_id,
            checked_at=now,
            price=result.price,
            regular_price=result.regular_price,
            sale_price=result.sale_price,
            currency=result.currency or listing.currency,
            availability=result.availability,
            seller_name=result.seller_name or listing.seller_name,
            page_title=result.page_title,
            success=result.success,
            http_status=result.http_status,
            extraction_method=result.extraction_method,
            response_time_ms=result.response_time_ms,
            error_code=result.error_code,
            error_message=sanitize_error_message(result.error_message or ""),
            content_fingerprint=result.content_fingerprint,
        )
        session.add(observation)
        listing.last_attempt_at = now
        if result.success:
            listing.last_success_at = now
            listing.consecutive_failures = 0
        else:
            listing.consecutive_failures += 1
        session.commit()

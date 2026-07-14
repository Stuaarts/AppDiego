from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import select

from price_monitor.models import Listing, PriceObservation, Product, RunLock, Store
from price_monitor.scraping.client import HttpFetchResult
from price_monitor.services.scrape_service import ScrapeAlreadyRunningError, scrape
from price_monitor.time import utc_now


class FakeFetcher:
    def __init__(self, html: str | None = None, error_code: str | None = None):
        self.html = html
        self.error_code = error_code

    async def fetch(self, url: str) -> HttpFetchResult:
        if self.error_code:
            return HttpFetchResult(ok=False, url=url, status_code=500, error_code=self.error_code)
        return HttpFetchResult(
            ok=True,
            url=url,
            html=self.html,
            status_code=200,
            response_time_ms=5,
            content_fingerprint="abc123",
        )


@pytest.mark.asyncio
async def test_scrape_success_preserves_observation(
    session_factory, test_settings, fixtures_dir
) -> None:
    html = (fixtures_dir / "generic_jsonld_product.html").read_text()
    listing_id = _seed_listing(session_factory)
    result = await scrape(
        session_factory,
        test_settings,
        trigger_source="test",
        listing_id=listing_id,
        fetcher=FakeFetcher(html=html),
    )
    assert result.successful == 1
    with session_factory() as session:
        observations = session.scalars(select(PriceObservation)).all()
        listing = session.get(Listing, listing_id)
    assert len(observations) == 1
    assert observations[0].success
    assert observations[0].price == Decimal("1299.90")
    assert listing.consecutive_failures == 0


@pytest.mark.asyncio
async def test_scrape_failure_records_observation(session_factory, test_settings) -> None:
    listing_id = _seed_listing(session_factory)
    result = await scrape(
        session_factory,
        test_settings,
        trigger_source="test",
        listing_id=listing_id,
        fetcher=FakeFetcher(error_code="http_server_error"),
    )
    assert result.failed == 1
    with session_factory() as session:
        observation = session.scalar(select(PriceObservation))
        listing = session.get(Listing, listing_id)
    assert observation is not None
    assert not observation.success
    assert observation.error_code == "http_server_error"
    assert listing.consecutive_failures == 1


@pytest.mark.asyncio
async def test_run_lock_blocks_overlap(session_factory, test_settings, fixtures_dir) -> None:
    html = (fixtures_dir / "generic_jsonld_product.html").read_text()
    listing_id = _seed_listing(session_factory)
    with session_factory() as session:
        session.add(
            RunLock(
                name="scrape",
                token="locked",
                locked_until=utc_now().replace(year=2099),
            )
        )
        session.commit()
    with pytest.raises(ScrapeAlreadyRunningError):
        await scrape(
            session_factory,
            test_settings,
            trigger_source="test",
            listing_id=listing_id,
            fetcher=FakeFetcher(html=html),
        )


def _seed_listing(session_factory) -> int:
    with session_factory() as session:
        store = Store(
            name="Example", domain="example.com", default_currency="BRL", adapter_key="generic"
        )
        product = Product(name="Produto Demo", internal_code="T-1", default_currency="BRL")
        session.add_all([store, product])
        session.flush()
        listing = Listing(
            product_id=product.id,
            store_id=store.id,
            url="https://example.com/product",
            normalized_url="https://example.com/product",
            currency="BRL",
            scraping_method="auto",
        )
        session.add(listing)
        session.commit()
        return listing.id

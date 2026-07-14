from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from price_monitor.models import Listing
from price_monitor.security import normalize_public_url


def create_listing(
    session: Session,
    *,
    product_id: int,
    store_id: int,
    url: str,
    store_sku: str | None = None,
    seller_name: str | None = None,
    currency: str = "BRL",
    scraping_method: str = "auto",
    price_selector: str | None = None,
    regular_price_selector: str | None = None,
    availability_selector: str | None = None,
    title_selector: str | None = None,
) -> Listing:
    validation = normalize_public_url(url)
    if not validation.ok:
        raise ValueError(validation.error_message)
    listing = Listing(
        product_id=product_id,
        store_id=store_id,
        url=url.strip(),
        normalized_url=validation.normalized_url,
        store_sku=(store_sku or "").strip() or None,
        seller_name=(seller_name or "").strip() or None,
        currency=currency.upper(),
        scraping_method=scraping_method,
        price_selector=(price_selector or "").strip() or None,
        regular_price_selector=(regular_price_selector or "").strip() or None,
        availability_selector=(availability_selector or "").strip() or None,
        title_selector=(title_selector or "").strip() or None,
    )
    session.add(listing)
    session.flush()
    return listing


def list_active_listings(session: Session) -> list[Listing]:
    return list(
        session.scalars(select(Listing).where(Listing.active.is_(True)).order_by(Listing.id))
    )


def list_active_listings_for_product(session: Session, product_id: int) -> list[Listing]:
    return list(
        session.scalars(
            select(Listing)
            .where(Listing.active.is_(True), Listing.product_id == product_id)
            .order_by(Listing.id)
        )
    )

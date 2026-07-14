from __future__ import annotations

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from price_monitor.models import Listing, PriceObservation


def latest_success_for_listing(session: Session, listing_id: int) -> PriceObservation | None:
    return session.scalar(
        select(PriceObservation)
        .where(PriceObservation.listing_id == listing_id, PriceObservation.success.is_(True))
        .order_by(desc(PriceObservation.checked_at))
        .limit(1)
    )


def latest_attempt_for_listing(session: Session, listing_id: int) -> PriceObservation | None:
    return session.scalar(
        select(PriceObservation)
        .where(PriceObservation.listing_id == listing_id)
        .order_by(desc(PriceObservation.checked_at))
        .limit(1)
    )


def observations_for_product(session: Session, product_id: int) -> list[PriceObservation]:
    return list(
        session.scalars(
            select(PriceObservation)
            .join(Listing)
            .where(Listing.product_id == product_id)
            .order_by(PriceObservation.checked_at)
        )
    )

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from price_monitor.models import Listing, PriceObservation, Product
from price_monitor.time import ensure_aware_utc, utc_now


@dataclass(frozen=True)
class ProductSnapshot:
    product_id: int
    product_name: str
    internal_code: str | None
    lowest_price: Decimal | None
    highest_price: Decimal | None
    spread: Decimal | None
    lowest_store: str | None
    valid_listings: int
    failed_listings: int
    stale_listings: int


def build_current_snapshot(session: Session, stale_after_hours: int) -> list[ProductSnapshot]:
    products = session.scalars(
        select(Product)
        .where(Product.active.is_(True))
        .options(selectinload(Product.listings).selectinload(Listing.store))
        .order_by(Product.name)
    ).all()
    snapshots: list[ProductSnapshot] = []
    stale_cutoff = utc_now() - timedelta(hours=stale_after_hours)
    for product in products:
        latest = [
            _latest_success(session, listing.id) for listing in product.listings if listing.active
        ]
        latest = [observation for observation in latest if observation is not None]
        valid = [
            observation
            for observation in latest
            if observation.price is not None
            and observation.availability != "out_of_stock"
            and ensure_aware_utc(observation.checked_at) >= stale_cutoff
        ]
        failed_count = sum(
            1 for listing in product.listings if listing.active and listing.consecutive_failures
        )
        stale_count = sum(
            1
            for observation in latest
            if observation.checked_at and ensure_aware_utc(observation.checked_at) < stale_cutoff
        )
        if valid:
            lowest = min(valid, key=lambda observation: observation.price or Decimal("0"))
            highest = max(valid, key=lambda observation: observation.price or Decimal("0"))
            snapshots.append(
                ProductSnapshot(
                    product_id=product.id,
                    product_name=product.name,
                    internal_code=product.internal_code,
                    lowest_price=lowest.price,
                    highest_price=highest.price,
                    spread=(highest.price - lowest.price)
                    if highest.price and lowest.price
                    else None,
                    lowest_store=lowest.listing.store.name,
                    valid_listings=len(valid),
                    failed_listings=failed_count,
                    stale_listings=stale_count,
                )
            )
        else:
            snapshots.append(
                ProductSnapshot(
                    product_id=product.id,
                    product_name=product.name,
                    internal_code=product.internal_code,
                    lowest_price=None,
                    highest_price=None,
                    spread=None,
                    lowest_store=None,
                    valid_listings=0,
                    failed_listings=failed_count,
                    stale_listings=stale_count,
                )
            )
    return snapshots


def current_snapshot_dataframe(session: Session, stale_after_hours: int) -> pd.DataFrame:
    rows = [
        {
            "Produto": snapshot.product_name,
            "Codigo": snapshot.internal_code,
            "Menor preco": snapshot.lowest_price,
            "Maior preco": snapshot.highest_price,
            "Diferenca": snapshot.spread,
            "Melhor loja": snapshot.lowest_store,
            "Listagens validas": snapshot.valid_listings,
            "Falhas": snapshot.failed_listings,
            "Desatualizadas": snapshot.stale_listings,
        }
        for snapshot in build_current_snapshot(session, stale_after_hours)
    ]
    return pd.DataFrame(rows)


def history_dataframe(session: Session, product_id: int | None = None) -> pd.DataFrame:
    query = (
        select(PriceObservation)
        .join(Listing)
        .join(Product)
        .options(
            selectinload(PriceObservation.listing).selectinload(Listing.store),
            selectinload(PriceObservation.listing).selectinload(Listing.product),
        )
        .order_by(PriceObservation.checked_at)
    )
    if product_id is not None:
        query = query.where(Listing.product_id == product_id)
    observations = session.scalars(query).all()
    rows = []
    for observation in observations:
        rows.append(
            {
                "Produto": observation.listing.product.name,
                "Loja": observation.listing.store.name,
                "URL": observation.listing.url,
                "Data": observation.checked_at,
                "Preco": observation.price,
                "Preco regular": observation.regular_price,
                "Preco promocional": observation.sale_price,
                "Moeda": observation.currency,
                "Disponibilidade": observation.availability,
                "Sucesso": observation.success,
                "Erro": observation.error_code,
            }
        )
    return pd.DataFrame(rows)


def _latest_success(session: Session, listing_id: int) -> PriceObservation | None:
    return session.scalar(
        select(PriceObservation)
        .where(PriceObservation.listing_id == listing_id, PriceObservation.success.is_(True))
        .order_by(PriceObservation.checked_at.desc())
        .limit(1)
    )

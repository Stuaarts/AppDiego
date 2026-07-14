from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from price_monitor.models import Listing, PriceObservation, Product, Store


def test_product_internal_code_unique(session_factory) -> None:
    with session_factory() as session:
        session.add_all(
            [
                Product(name="A", internal_code="ABC", default_currency="BRL"),
                Product(name="B", internal_code="ABC", default_currency="BRL"),
            ]
        )
        with pytest.raises(IntegrityError):
            session.commit()


def test_money_precision_and_soft_deactivation(session_factory) -> None:
    with session_factory() as session:
        store = Store(name="Example", domain="example.com")
        product = Product(name="Produto", default_currency="BRL")
        session.add_all([store, product])
        session.flush()
        listing = Listing(
            product_id=product.id,
            store_id=store.id,
            url="https://example.com/p",
            normalized_url="https://example.com/p",
            currency="BRL",
        )
        session.add(listing)
        session.flush()
        session.add(
            PriceObservation(
                listing_id=listing.id,
                price=Decimal("123.45"),
                currency="BRL",
                availability="in_stock",
                success=True,
            )
        )
        listing.active = False
        session.commit()
    with session_factory() as session:
        observation = session.scalar(select(PriceObservation))
        listing = session.scalar(select(Listing))
    assert observation.price == Decimal("123.45")
    assert listing.active is False

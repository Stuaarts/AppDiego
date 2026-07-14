from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from price_monitor.models import Product


def create_product(
    session: Session,
    *,
    name: str,
    internal_code: str | None = None,
    manufacturer: str | None = None,
    model_number: str | None = None,
    sku: str | None = None,
    upc_or_ean: str | None = None,
    category: str | None = None,
    description: str | None = None,
    target_price: Decimal | None = None,
    default_currency: str = "BRL",
) -> Product:
    product = Product(
        name=name.strip(),
        internal_code=(internal_code or "").strip() or None,
        manufacturer=(manufacturer or "").strip() or None,
        model_number=(model_number or "").strip() or None,
        sku=(sku or "").strip() or None,
        upc_or_ean=(upc_or_ean or "").strip() or None,
        category=(category or "").strip() or None,
        description=(description or "").strip() or None,
        target_price=target_price,
        default_currency=default_currency.upper(),
    )
    session.add(product)
    session.flush()
    return product


def list_active_products(session: Session) -> list[Product]:
    return list(
        session.scalars(select(Product).where(Product.active.is_(True)).order_by(Product.name))
    )


def get_product(session: Session, product_id: int) -> Product | None:
    return session.get(Product, product_id)

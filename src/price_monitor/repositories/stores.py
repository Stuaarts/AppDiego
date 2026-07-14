from __future__ import annotations

from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from price_monitor.models import Store


def normalize_domain(domain_or_url: str) -> str:
    value = domain_or_url.strip().lower()
    if "://" in value:
        value = urlparse(value).hostname or value
    return value.strip("/")


def create_store(
    session: Session,
    *,
    name: str,
    domain: str,
    requires_browser: bool = False,
    request_delay_seconds: int = 2,
    default_currency: str = "BRL",
    adapter_key: str = "generic",
) -> Store:
    store = Store(
        name=name.strip(),
        domain=normalize_domain(domain),
        requires_browser=requires_browser,
        request_delay_seconds=request_delay_seconds,
        default_currency=default_currency.upper(),
        adapter_key=adapter_key,
    )
    session.add(store)
    session.flush()
    return store


def list_active_stores(session: Session) -> list[Store]:
    return list(session.scalars(select(Store).where(Store.active.is_(True)).order_by(Store.name)))


def get_store(session: Session, store_id: int) -> Store | None:
    return session.get(Store, store_id)

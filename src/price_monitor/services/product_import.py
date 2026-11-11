from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.orm import Session

from price_monitor.models import Listing, Product, Store
from price_monitor.repositories.products import create_product
from price_monitor.repositories.stores import create_store
from price_monitor.security import normalize_public_url
from price_monitor.services.price_report import ImportedTable

MAX_LINKS = 250


@dataclass(frozen=True)
class ImportedProducts:
    products_created: int
    listings_created: int
    listings_existing: int
    issues: list[tuple[int, str]]


def save_products(
    session: Session,
    table: ImportedTable,
    *,
    product_column: int,
    link_columns: tuple[int, ...],
    id_column: int | None,
    currency: str,
) -> ImportedProducts:
    if count_import_links(table, link_columns) > MAX_LINKS:
        raise ValueError(f"Salve até {MAX_LINKS} links por arquivo.")

    products_created = listings_created = listings_existing = 0
    issues: list[tuple[int, str]] = []
    for line, row in table.rows:
        name = str(row[product_column])
        if not name or len(name) > 255:
            issues.append((line, "Nome do produto ausente ou muito longo."))
            continue
        links = valid_import_links(table.headers, line, row, link_columns, issues)
        if not links:
            issues.append((line, "Nenhum link de produto válido."))
            continue

        source_id = str(row[id_column]) if id_column is not None else ""
        identity = f"{source_id}\n{' '.join(name.casefold().split())}"
        code = "import-" + sha256(identity.encode()).hexdigest()[:32]
        product = session.scalar(select(Product).where(Product.internal_code == code))
        if product is None:
            product = create_product(
                session, name=name, internal_code=code, default_currency=currency
            )
            products_created += 1
        for url, host in links.items():
            existing = session.scalar(
                select(Listing.id).where(
                    Listing.product_id == product.id, Listing.normalized_url == url
                )
            )
            if existing is not None:
                listings_existing += 1
                continue
            store = session.scalar(select(Store).where(Store.domain == host))
            if store is None:
                store = create_store(
                    session,
                    name=host.removeprefix("www.")[:180],
                    domain=host,
                    default_currency=currency,
                )
            session.add(
                Listing(
                    product_id=product.id,
                    store_id=store.id,
                    url=url,
                    normalized_url=url,
                    currency=currency,
                    scraping_method="structured",
                )
            )
            session.flush()
            listings_created += 1
    return ImportedProducts(products_created, listings_created, listings_existing, issues)


def count_import_links(table: ImportedTable, columns: tuple[int, ...]) -> int:
    return sum(_has_link(str(row[index])) for _, row in table.rows for index in columns)


def _has_link(value: str) -> bool:
    return bool(value.strip(" ,;-"))


def valid_import_links(
    headers: tuple[str, ...],
    line: int,
    row: tuple[str | int | float, ...],
    columns: tuple[int, ...],
    issues: list[tuple[int, str]],
) -> dict[str, str]:
    links = {}
    for index in columns:
        url = str(row[index])
        if not _has_link(url):
            continue
        try:
            valid = normalize_public_url(url) if len(url) <= 2048 else None
            if valid and valid.ok and len(valid.normalized_url) <= 2048:
                host = urlsplit(valid.normalized_url).hostname
                if host and len(host) <= 255:
                    links[valid.normalized_url] = host
                    continue
        except ValueError:
            pass
        issues.append((line, f"{headers[index]}: link inválido ou inacessível."))
    return links

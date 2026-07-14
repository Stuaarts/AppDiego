from __future__ import annotations

import argparse
import asyncio
import subprocess
import sys
from decimal import Decimal

from sqlalchemy import select

from price_monitor.config import load_settings, redact_database_url
from price_monitor.database import check_database, make_engine, make_session_factory
from price_monitor.models import PriceObservation, Product
from price_monitor.repositories.listings import create_listing
from price_monitor.repositories.products import create_product
from price_monitor.repositories.stores import create_store
from price_monitor.services.scrape_service import scrape
from price_monitor.time import utc_now


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="price-monitor")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("healthcheck")
    subparsers.add_parser("seed-demo")
    subparsers.add_parser("migrate")
    hash_parser = subparsers.add_parser("hash-password")
    hash_parser.add_argument("password")

    scrape_parser = subparsers.add_parser("scrape")
    scrape_parser.add_argument("--all", action="store_true", help="Scrape all active listings.")
    scrape_parser.add_argument("--product-id", type=int)
    scrape_parser.add_argument("--listing-id", type=int)
    scrape_parser.add_argument("--trigger", default="manual_cli")

    args = parser.parse_args(argv)
    if args.command == "hash-password":
        from price_monitor.security import hash_password

        print(hash_password(args.password))
        return 0
    settings = load_settings(validate=args.command != "migrate")
    engine = make_engine(settings)
    session_factory = make_session_factory(engine)

    if args.command == "healthcheck":
        check_database(engine)
        print(f"database=ok url={redact_database_url(settings.database_url)}")
        return 0
    if args.command == "migrate":
        return subprocess.call([sys.executable, "-m", "alembic", "upgrade", "head"])
    if args.command == "seed-demo":
        with session_factory() as session:
            seed_demo(session, settings.default_currency)
            session.commit()
        print("demo seed complete")
        return 0
    if args.command == "scrape":
        result = asyncio.run(
            scrape(
                session_factory,
                settings,
                trigger_source=args.trigger,
                product_id=args.product_id,
                listing_id=args.listing_id,
            )
        )
        print(
            f"run_id={result.run_id} total={result.total} "
            f"successful={result.successful} failed={result.failed} status={result.status}"
        )
        return 0
    return 1


def seed_demo(session, default_currency: str = "BRL") -> None:
    if session.scalar(select(Product).where(Product.internal_code == "DEMO-CAF-001")):
        return
    store_a = create_store(
        session,
        name="Loja Exemplo A",
        domain="example.com",
        default_currency=default_currency,
        adapter_key="generic",
    )
    store_b = create_store(
        session,
        name="Loja Exemplo B",
        domain="example.org",
        default_currency=default_currency,
        adapter_key="generic",
    )
    product = create_product(
        session,
        name="Cafeteira Demo 12 Xicaras",
        internal_code="DEMO-CAF-001",
        manufacturer="Fabricante Demo",
        model_number="CAF-12",
        category="Eletroportateis",
        description="Produto ficticio para demonstracao.",
        target_price=Decimal("250.00"),
        default_currency=default_currency,
    )
    listing_a = create_listing(
        session,
        product_id=product.id,
        store_id=store_a.id,
        url="https://example.com/demo/cafeteira",
        currency=default_currency,
        price_selector=".price",
        availability_selector=".availability",
    )
    listing_b = create_listing(
        session,
        product_id=product.id,
        store_id=store_b.id,
        url="https://example.org/demo/cafeteira",
        currency=default_currency,
        price_selector=".price",
        availability_selector=".availability",
    )
    for offset, price_a, price_b in [
        (5, Decimal("289.90"), Decimal("279.90")),
        (4, Decimal("279.90"), Decimal("275.90")),
        (3, Decimal("269.90"), Decimal("279.90")),
        (2, Decimal("259.90"), Decimal("269.90")),
        (1, Decimal("249.90"), Decimal("264.90")),
        (0, Decimal("255.90"), Decimal("259.90")),
    ]:
        checked_at = utc_now().replace(hour=12, minute=0, second=0, microsecond=0)
        checked_at = checked_at.replace(day=max(1, checked_at.day - offset))
        session.add(
            PriceObservation(
                listing_id=listing_a.id,
                checked_at=checked_at,
                price=price_a,
                currency=default_currency,
                availability="in_stock",
                page_title="Cafeteira Demo 12 Xicaras",
                success=True,
                extraction_method="seed",
            )
        )
        session.add(
            PriceObservation(
                listing_id=listing_b.id,
                checked_at=checked_at,
                price=price_b,
                currency=default_currency,
                availability="in_stock",
                page_title="Cafeteira Demo 12 Xicaras",
                success=True,
                extraction_method="seed",
            )
        )
    listing_a.last_success_at = utc_now()
    listing_b.last_success_at = utc_now()


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from price_monitor.time import utc_now


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class Store(Base, TimestampMixin):
    __tablename__ = "stores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    domain: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    requires_browser: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    request_delay_seconds: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    default_currency: Mapped[str] = mapped_column(String(3), default="BRL", nullable=False)
    adapter_key: Mapped[str] = mapped_column(String(80), default="generic", nullable=False)

    listings: Mapped[list[Listing]] = relationship(back_populates="store")


class Product(Base, TimestampMixin):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    internal_code: Mapped[str | None] = mapped_column(String(120), unique=True)
    manufacturer: Mapped[str | None] = mapped_column(String(180))
    model_number: Mapped[str | None] = mapped_column(String(120))
    sku: Mapped[str | None] = mapped_column(String(120))
    upc_or_ean: Mapped[str | None] = mapped_column(String(120))
    category: Mapped[str | None] = mapped_column(String(180))
    description: Mapped[str | None] = mapped_column(Text)
    target_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    default_currency: Mapped[str] = mapped_column(String(3), default="BRL", nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)

    listings: Mapped[list[Listing]] = relationship(back_populates="product")


class Listing(Base, TimestampMixin):
    __tablename__ = "listings"
    __table_args__ = (
        UniqueConstraint("product_id", "normalized_url", name="uq_listing_product_url"),
        Index("ix_listings_product_active", "product_id", "active"),
        Index("ix_listings_failed", "active", "consecutive_failures"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    store_id: Mapped[int] = mapped_column(
        ForeignKey("stores.id", ondelete="RESTRICT"), nullable=False
    )
    url: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    store_sku: Mapped[str | None] = mapped_column(String(120))
    seller_name: Mapped[str | None] = mapped_column(String(180))
    currency: Mapped[str] = mapped_column(String(3), default="BRL", nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    scraping_method: Mapped[str] = mapped_column(String(40), default="auto", nullable=False)
    price_selector: Mapped[str | None] = mapped_column(String(255))
    regular_price_selector: Mapped[str | None] = mapped_column(String(255))
    availability_selector: Mapped[str | None] = mapped_column(String(255))
    title_selector: Mapped[str | None] = mapped_column(String(255))
    last_success_at: Mapped[object | None] = mapped_column(DateTime(timezone=True))
    last_attempt_at: Mapped[object | None] = mapped_column(DateTime(timezone=True))
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    product: Mapped[Product] = relationship(back_populates="listings")
    store: Mapped[Store] = relationship(back_populates="listings")
    observations: Mapped[list[PriceObservation]] = relationship(back_populates="listing")


class ScrapeRun(Base):
    __tablename__ = "scrape_runs"
    __table_args__ = (Index("ix_scrape_runs_started_at", "started_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    started_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    finished_at: Mapped[object | None] = mapped_column(DateTime(timezone=True))
    trigger_source: Mapped[str] = mapped_column(String(60), nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="running", nullable=False)
    total_listings: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    successful_listings: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_listings: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    summary: Mapped[str | None] = mapped_column(Text)

    observations: Mapped[list[PriceObservation]] = relationship(back_populates="scrape_run")


class PriceObservation(Base):
    __tablename__ = "price_observations"
    __table_args__ = (
        Index("ix_observations_listing_checked", "listing_id", "checked_at"),
        Index("ix_observations_latest_success", "listing_id", "success", "checked_at"),
        Index("ix_observations_run", "scrape_run_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    listing_id: Mapped[int] = mapped_column(
        ForeignKey("listings.id", ondelete="RESTRICT"), nullable=False
    )
    scrape_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("scrape_runs.id", ondelete="SET NULL")
    )
    checked_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    regular_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    sale_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    currency: Mapped[str | None] = mapped_column(String(3))
    availability: Mapped[str] = mapped_column(String(40), default="unknown", nullable=False)
    seller_name: Mapped[str | None] = mapped_column(String(180))
    page_title: Mapped[str | None] = mapped_column(String(500))
    success: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    http_status: Mapped[int | None] = mapped_column(Integer)
    extraction_method: Mapped[str | None] = mapped_column(String(80))
    response_time_ms: Mapped[int | None] = mapped_column(Integer)
    error_code: Mapped[str | None] = mapped_column(String(80))
    error_message: Mapped[str | None] = mapped_column(Text)
    content_fingerprint: Mapped[str | None] = mapped_column(String(64))

    listing: Mapped[Listing] = relationship(back_populates="observations")
    scrape_run: Mapped[ScrapeRun | None] = relationship(back_populates="observations")


class RunLock(Base):
    __tablename__ = "run_locks"

    name: Mapped[str] = mapped_column(String(80), primary_key=True)
    token: Mapped[str] = mapped_column(String(80), nullable=False)
    locked_until: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

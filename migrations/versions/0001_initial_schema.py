"""Initial production schema.

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-07-14 00:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "stores",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=180), nullable=False),
        sa.Column("domain", sa.String(length=255), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("requires_browser", sa.Boolean(), nullable=False),
        sa.Column("request_delay_seconds", sa.Integer(), nullable=False),
        sa.Column("default_currency", sa.String(length=3), nullable=False),
        sa.Column("adapter_key", sa.String(length=80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("domain"),
    )
    op.create_index(op.f("ix_stores_active"), "stores", ["active"], unique=False)

    op.create_table(
        "products",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("internal_code", sa.String(length=120), nullable=True),
        sa.Column("manufacturer", sa.String(length=180), nullable=True),
        sa.Column("model_number", sa.String(length=120), nullable=True),
        sa.Column("sku", sa.String(length=120), nullable=True),
        sa.Column("upc_or_ean", sa.String(length=120), nullable=True),
        sa.Column("category", sa.String(length=180), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("target_price", sa.Numeric(12, 2), nullable=True),
        sa.Column("default_currency", sa.String(length=3), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("internal_code"),
    )
    op.create_index(op.f("ix_products_active"), "products", ["active"], unique=False)

    op.create_table(
        "scrape_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("trigger_source", sa.String(length=60), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("total_listings", sa.Integer(), nullable=False),
        sa.Column("successful_listings", sa.Integer(), nullable=False),
        sa.Column("failed_listings", sa.Integer(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_scrape_runs_started_at", "scrape_runs", ["started_at"], unique=False)

    op.create_table(
        "run_locks",
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("token", sa.String(length=80), nullable=False),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("name"),
    )

    op.create_table(
        "listings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("store_id", sa.Integer(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("normalized_url", sa.String(length=2048), nullable=False),
        sa.Column("store_sku", sa.String(length=120), nullable=True),
        sa.Column("seller_name", sa.String(length=180), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("scraping_method", sa.String(length=40), nullable=False),
        sa.Column("price_selector", sa.String(length=255), nullable=True),
        sa.Column("regular_price_selector", sa.String(length=255), nullable=True),
        sa.Column("availability_selector", sa.String(length=255), nullable=True),
        sa.Column("title_selector", sa.String(length=255), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("product_id", "normalized_url", name="uq_listing_product_url"),
    )
    op.create_index(op.f("ix_listings_active"), "listings", ["active"], unique=False)
    op.create_index(
        "ix_listings_failed",
        "listings",
        ["active", "consecutive_failures"],
        unique=False,
    )
    op.create_index(
        "ix_listings_product_active",
        "listings",
        ["product_id", "active"],
        unique=False,
    )

    op.create_table(
        "price_observations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("listing_id", sa.Integer(), nullable=False),
        sa.Column("scrape_run_id", sa.Integer(), nullable=True),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("price", sa.Numeric(12, 2), nullable=True),
        sa.Column("regular_price", sa.Numeric(12, 2), nullable=True),
        sa.Column("sale_price", sa.Numeric(12, 2), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=True),
        sa.Column("availability", sa.String(length=40), nullable=False),
        sa.Column("seller_name", sa.String(length=180), nullable=True),
        sa.Column("page_title", sa.String(length=500), nullable=True),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("extraction_method", sa.String(length=80), nullable=True),
        sa.Column("response_time_ms", sa.Integer(), nullable=True),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("content_fingerprint", sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(["listing_id"], ["listings.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["scrape_run_id"], ["scrape_runs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_observations_latest_success",
        "price_observations",
        ["listing_id", "success", "checked_at"],
        unique=False,
    )
    op.create_index(
        "ix_observations_listing_checked",
        "price_observations",
        ["listing_id", "checked_at"],
        unique=False,
    )
    op.create_index("ix_observations_run", "price_observations", ["scrape_run_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_observations_run", table_name="price_observations")
    op.drop_index("ix_observations_listing_checked", table_name="price_observations")
    op.drop_index("ix_observations_latest_success", table_name="price_observations")
    op.drop_table("price_observations")
    op.drop_index("ix_listings_product_active", table_name="listings")
    op.drop_index("ix_listings_failed", table_name="listings")
    op.drop_index(op.f("ix_listings_active"), table_name="listings")
    op.drop_table("listings")
    op.drop_table("run_locks")
    op.drop_index("ix_scrape_runs_started_at", table_name="scrape_runs")
    op.drop_table("scrape_runs")
    op.drop_index(op.f("ix_products_active"), table_name="products")
    op.drop_table("products")
    op.drop_index(op.f("ix_stores_active"), table_name="stores")
    op.drop_table("stores")

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from price_monitor.config import Settings
from price_monitor.models import Base


@pytest.fixture
def fixtures_dir() -> Path:
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def test_settings() -> Settings:
    return Settings(
        app_env="development",
        database_url="sqlite://",
        database_schema="",
        app_password_hash="",
        auth_disabled=True,
        default_currency="BRL",
        request_timeout_seconds=5,
        max_retries=0,
        global_scrape_concurrency=2,
        domain_scrape_concurrency=1,
        browser_concurrency=1,
        max_response_bytes=1_000_000,
        stale_after_hours=24,
        display_timezone="America/Sao_Paulo",
        log_level="INFO",
        playwright_enabled=False,
        app_base_url="",
    )


@pytest.fixture
def session_factory() -> Iterator[sessionmaker[Session]]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
    Base.metadata.drop_all(engine)
    engine.dispose()

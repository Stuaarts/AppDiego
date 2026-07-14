from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def _int(name: str, default: int, minimum: int | None = None) -> int:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if minimum is not None and value < minimum:
        raise ValueError(f"{name} must be at least {minimum}")
    return value


def _str(name: str, default: str = "") -> str:
    value = os.getenv(name)
    return default if value is None else value.strip()


@dataclass(frozen=True)
class Settings:
    app_env: str
    database_url: str
    database_schema: str
    app_password_hash: str
    auth_disabled: bool
    default_currency: str
    request_timeout_seconds: int
    max_retries: int
    global_scrape_concurrency: int
    domain_scrape_concurrency: int
    browser_concurrency: int
    max_response_bytes: int
    stale_after_hours: int
    display_timezone: str
    log_level: str
    playwright_enabled: bool
    enable_internal_scheduler: bool
    internal_scrape_interval_hours: int
    app_base_url: str

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"

    @property
    def requires_auth(self) -> bool:
        return not self.auth_disabled

    def validate_for_startup(self) -> None:
        if self.is_production and not self.database_url:
            raise ValueError("DATABASE_URL is required in production")
        if self.is_production and self.auth_disabled:
            raise ValueError("AUTH_DISABLED must be false in production")
        if self.requires_auth and not self.app_password_hash:
            raise ValueError("APP_PASSWORD_HASH is required when authentication is enabled")


def default_sqlite_url() -> str:
    return f"sqlite:///{Path.cwd() / 'price_monitor.db'}"


def load_settings(validate: bool = True) -> Settings:
    load_dotenv()
    settings = Settings(
        app_env=_str("APP_ENV", "development") or "development",
        database_url=_str("DATABASE_URL", "") or default_sqlite_url(),
        database_schema=_str("DB_SCHEMA", ""),
        app_password_hash=_str("APP_PASSWORD_HASH", ""),
        auth_disabled=_bool("AUTH_DISABLED", True),
        default_currency=(_str("DEFAULT_CURRENCY", "BRL") or "BRL").upper(),
        request_timeout_seconds=_int("REQUEST_TIMEOUT_SECONDS", 20, 1),
        max_retries=_int("MAX_RETRIES", 2, 0),
        global_scrape_concurrency=_int("GLOBAL_SCRAPE_CONCURRENCY", 4, 1),
        domain_scrape_concurrency=_int("DOMAIN_SCRAPE_CONCURRENCY", 1, 1),
        browser_concurrency=_int("BROWSER_CONCURRENCY", 1, 1),
        max_response_bytes=_int("MAX_RESPONSE_BYTES", 5_000_000, 100_000),
        stale_after_hours=_int("STALE_AFTER_HOURS", 24, 1),
        display_timezone=_str("DISPLAY_TIMEZONE", "America/Sao_Paulo") or "America/Sao_Paulo",
        log_level=(_str("LOG_LEVEL", "INFO") or "INFO").upper(),
        playwright_enabled=_bool("PLAYWRIGHT_ENABLED", True),
        enable_internal_scheduler=_bool("ENABLE_INTERNAL_SCHEDULER", False),
        internal_scrape_interval_hours=_int("INTERNAL_SCRAPE_INTERVAL_HOURS", 6, 1),
        app_base_url=_str("APP_BASE_URL", ""),
    )
    if validate:
        settings.validate_for_startup()
    return settings


def redact_database_url(url: str) -> str:
    if not url:
        return ""
    if "://" not in url:
        return url
    scheme, rest = url.split("://", 1)
    if "@" not in rest:
        return f"{scheme}://{rest.split('?', 1)[0]}"
    credentials, host = rest.split("@", 1)
    username = credentials.split(":", 1)[0]
    return f"{scheme}://{username}:***@{host.split('?', 1)[0]}"

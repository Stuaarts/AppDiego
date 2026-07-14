from __future__ import annotations

import re

from sqlalchemy import create_engine, text

from price_monitor.config import load_settings
from price_monitor.database import normalize_database_url


def main() -> int:
    settings = load_settings(validate=False)
    schema = settings.database_schema
    if not schema or settings.database_url.startswith("sqlite"):
        return 0
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", schema):
        raise ValueError("DB_SCHEMA must be a valid PostgreSQL identifier")
    engine = create_engine(normalize_database_url(settings.database_url), future=True)
    with engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))
    engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

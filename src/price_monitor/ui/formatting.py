from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from price_monitor.time import ensure_aware_utc


def money(value: Decimal | None, currency: str = "BRL") -> str:
    if value is None:
        return "-"
    amount = f"{value:,.2f}"
    if currency == "BRL":
        amount = amount.replace(",", "X").replace(".", ",").replace("X", ".")
        return f"R$ {amount}"
    return f"{currency} {amount}"


def local_datetime(value: datetime | None, timezone_name: str) -> str:
    if value is None:
        return "-"
    try:
        zone = ZoneInfo(timezone_name)
    except Exception:
        zone = ZoneInfo("UTC")
    return ensure_aware_utc(value).astimezone(zone).strftime("%Y-%m-%d %H:%M")

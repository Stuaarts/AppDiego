from __future__ import annotations

from decimal import Decimal, InvalidOperation


def parse_optional_decimal(value: str | None) -> Decimal | None:
    raw = (value or "").strip()
    if not raw:
        return None
    try:
        return Decimal(raw.replace(",", "."))
    except InvalidOperation as exc:
        raise ValueError("Valor decimal invalido.") from exc

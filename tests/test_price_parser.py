from __future__ import annotations

from decimal import Decimal

import pytest

from price_monitor.scraping.price_parser import parse_price


@pytest.mark.parametrize(
    ("raw", "currency", "expected"),
    [
        ("R$ 1.299,90", "BRL", Decimal("1299.90")),
        ("R$1.299,90", "BRL", Decimal("1299.90")),
        ("1.299,90", "BRL", Decimal("1299.90")),
        ("$1,299.90", "USD", Decimal("1299.90")),
        ("CAD 1,299.90", "CAD", Decimal("1299.90")),
        ("US$ 299.99", "USD", Decimal("299.99")),
        ("299,99 €", "EUR", Decimal("299.99")),
        ("1 299,90", "BRL", Decimal("1299.90")),
        ("0,00", "BRL", Decimal("0.00")),
    ],
)
def test_parse_localized_prices(raw: str, currency: str, expected: Decimal) -> None:
    parsed = parse_price(raw, default_currency=currency)
    assert parsed.ok
    assert parsed.value == expected
    assert parsed.currency == currency


@pytest.mark.parametrize("raw", ["", "preco indisponivel", "-R$ 10,00", "R$ 1000000000,00"])
def test_reject_invalid_prices(raw: str) -> None:
    parsed = parse_price(raw, default_currency="BRL")
    assert not parsed.ok
    assert parsed.value is None


def test_reports_multiple_prices() -> None:
    parsed = parse_price("De R$ 299,90 por R$ 199,90", default_currency="BRL")
    assert parsed.ok
    assert parsed.value == Decimal("299.90")
    assert "multiple_prices_detected" in parsed.diagnostics

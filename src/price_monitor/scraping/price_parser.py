from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

CURRENCY_PATTERNS = [
    ("BRL", re.compile(r"\bBRL\b|R\$", re.IGNORECASE)),
    ("CAD", re.compile(r"\bCAD\b|C\$", re.IGNORECASE)),
    ("USD", re.compile(r"\bUSD\b|US\$|\$", re.IGNORECASE)),
    ("EUR", re.compile(r"\bEUR\b|€", re.IGNORECASE)),
]

PRICE_CANDIDATE_RE = re.compile(
    r"[-+]?\s*(?:(?:R\$|US\$|C\$|\$|CAD|USD|BRL|EUR)\s*)?"
    r"\d[\d\s\u00a0.,]*"
    r"(?:\s*(?:€|CAD|USD|BRL|EUR))?",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class PriceParseResult:
    ok: bool
    value: Decimal | None = None
    currency: str | None = None
    diagnostics: list[str] = field(default_factory=list)


def parse_price(text: str | None, default_currency: str | None = None) -> PriceParseResult:
    candidates = extract_price_candidates(text)
    diagnostics: list[str] = []
    if not candidates:
        return PriceParseResult(
            ok=False, currency=default_currency, diagnostics=["no_price_candidate"]
        )
    if len(candidates) > 1:
        diagnostics.append("multiple_prices_detected")

    for candidate in candidates:
        parsed = _parse_candidate(candidate, default_currency=default_currency)
        diagnostics.extend(parsed.diagnostics)
        if parsed.ok:
            return PriceParseResult(
                ok=True,
                value=parsed.value,
                currency=parsed.currency,
                diagnostics=diagnostics,
            )
    return PriceParseResult(ok=False, currency=default_currency, diagnostics=diagnostics)


def parse_all_prices(
    text: str | None, default_currency: str | None = None
) -> list[PriceParseResult]:
    return [
        parsed
        for candidate in extract_price_candidates(text)
        if (parsed := _parse_candidate(candidate, default_currency=default_currency)).ok
    ]


def extract_price_candidates(text: str | None) -> list[str]:
    if not text:
        return []
    normalized = text.replace("\u00a0", " ")
    candidates: list[str] = []
    for match in PRICE_CANDIDATE_RE.finditer(normalized):
        value = match.group(0).strip()
        if not value:
            continue
        if not re.search(r"\d", value):
            continue
        candidates.append(value)
    return candidates


def _parse_candidate(candidate: str, default_currency: str | None = None) -> PriceParseResult:
    diagnostics: list[str] = []
    currency = _detect_currency(candidate) or default_currency
    clean = re.sub(r"(R\$|US\$|C\$|\$|CAD|USD|BRL|EUR|€)", "", candidate, flags=re.IGNORECASE)
    clean = clean.replace("\u00a0", " ").strip()
    if clean.startswith("-"):
        return PriceParseResult(ok=False, currency=currency, diagnostics=["negative_price"])
    clean = clean.lstrip("+")
    clean = re.sub(r"\s+", "", clean)
    if not clean or not re.search(r"\d", clean):
        return PriceParseResult(ok=False, currency=currency, diagnostics=["empty_numeric_value"])

    number = _normalize_number(clean, has_currency=currency is not None, diagnostics=diagnostics)
    if number is None:
        return PriceParseResult(ok=False, currency=currency, diagnostics=diagnostics)
    try:
        value = Decimal(number)
    except InvalidOperation:
        return PriceParseResult(
            ok=False, currency=currency, diagnostics=["decimal_conversion_failed"]
        )
    if value < 0:
        return PriceParseResult(ok=False, currency=currency, diagnostics=["negative_price"])
    if value > Decimal("999999999.99"):
        return PriceParseResult(ok=False, currency=currency, diagnostics=["price_too_large"])
    return PriceParseResult(ok=True, value=value, currency=currency, diagnostics=diagnostics)


def _detect_currency(text: str) -> str | None:
    for currency, pattern in CURRENCY_PATTERNS:
        if pattern.search(text):
            return currency
    return None


def _normalize_number(value: str, has_currency: bool, diagnostics: list[str]) -> str | None:
    comma_positions = [m.start() for m in re.finditer(",", value)]
    dot_positions = [m.start() for m in re.finditer(r"\.", value)]
    if comma_positions and dot_positions:
        decimal_sep = "," if comma_positions[-1] > dot_positions[-1] else "."
        return _remove_grouping(value, decimal_sep)

    if comma_positions:
        return _normalize_single_separator(value, ",", has_currency, diagnostics)
    if dot_positions:
        return _normalize_single_separator(value, ".", has_currency, diagnostics)
    if not value.isdigit():
        diagnostics.append("invalid_numeric_characters")
        return None
    return value


def _normalize_single_separator(
    value: str, separator: str, has_currency: bool, diagnostics: list[str]
) -> str | None:
    parts = value.split(separator)
    if len(parts) == 2:
        left, right = parts
        if len(right) in {1, 2}:
            return f"{left}.{right}" if separator == "," else value
        if len(right) == 3 and has_currency:
            return left + right
        diagnostics.append("ambiguous_separator")
        return None

    if all(len(part) == 3 for part in parts[1:]):
        return "".join(parts)
    diagnostics.append("invalid_grouping")
    return None


def _remove_grouping(value: str, decimal_sep: str) -> str:
    group_sep = "." if decimal_sep == "," else ","
    without_grouping = value.replace(group_sep, "")
    if decimal_sep == ",":
        return without_grouping.replace(",", ".")
    return without_grouping

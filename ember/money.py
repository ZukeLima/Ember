"""Money helpers. All monetary values are handled as integer cents and
serialized as fixed two-decimal strings, so output is byte-stable and
never depends on float formatting."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal


def cents_to_str(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    cents = abs(cents)
    return f"{sign}{cents // 100}.{cents % 100:02d}"


def str_to_cents(value: str | float | int | Decimal) -> int:
    d = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return int(d * 100)

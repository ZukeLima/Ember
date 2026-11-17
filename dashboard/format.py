"""pt-BR formatting without depending on system locales."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal


def brl(value, with_symbol: bool = True) -> str:
    """1234.5 → 'R$ 1.234,50'. None → '-'."""
    if value is None:
        return "-"
    d = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    sign = "-" if d < 0 else ""
    d = abs(d)
    whole, frac = divmod(int(d * 100), 100)
    whole_s = f"{whole:,}".replace(",", ".")
    out = f"{sign}{whole_s},{frac:02d}"
    return f"R$ {out}" if with_symbol else out


def integer(value) -> str:
    if value is None:
        return "-"
    return f"{int(value):,}".replace(",", ".")


def pct(value) -> str:
    if value is None:
        return "-"
    d = Decimal(str(value)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    arrow = "▲" if d > 0 else ("▼" if d < 0 else "=")
    return f"{arrow} {str(abs(d)).replace('.', ',')}%"

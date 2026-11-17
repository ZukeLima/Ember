"""Hypothetical sales scenarios, separate from published business metrics."""

from __future__ import annotations

import random
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

import pandas as pd

STRATEGIES = {
    "Manter operação": (0, 0, 0),
    "Campanha promocional": (25, 0, 10),
    "Retenção de clientes": (15, 0, 3),
    "Ajuste de preço": (-5, 10, 0),
}


def simulate_sales(
    *,
    start: date,
    days: int,
    baseline_days: int,
    completed_orders: int,
    eligible_gross: float,
    refunded_amount: float,
    volume_change: float = 0,
    price_change: float = 0,
    discount: float = 0,
    refund_rate: float = 0,
    variability: float = 25,
    seed: int = 7,
) -> pd.DataFrame:
    """Project gross/order and orders/day from the selected historical interval.

    Percentage inputs are assumptions, not estimated causal effects. Random daily
    demand is shared by reference and strategy for a comparable counterfactual.
    Monetary results are rounded per day, and totals are sums of those rows.
    """
    if not 1 <= days <= 365 or baseline_days < 1:
        raise ValueError("Days must be 1–365 and baseline_days must be positive.")
    if completed_orders <= 0 or eligible_gross < 0 or refunded_amount < 0:
        raise ValueError("A non-negative baseline with completed orders is required.")
    if refunded_amount > eligible_gross:
        raise ValueError("Baseline refunds cannot exceed gross sales.")
    if volume_change < -100 or price_change < -100:
        raise ValueError("Changes cannot be below -100%.")
    if not 0 <= discount <= 100 or not 0 <= refund_rate <= 100 or not 0 <= variability <= 100:
        raise ValueError("Discount, refund rate and variability must be 0–100%.")

    rng = random.Random(seed)
    gross_per_order = eligible_gross / completed_orders
    orders_per_day = completed_orders / baseline_days
    baseline_refund_rate = refunded_amount / eligible_gross if eligible_gross else 0

    def money(value: float) -> float:
        return float(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

    rows = []
    for offset in range(days):
        demand = rng.uniform(1 - variability / 100, 1 + variability / 100)
        expected_orders = orders_per_day * demand
        rounding = rng.random()
        reference_orders = int(expected_orders + rounding)
        orders = int(expected_orders * (1 + volume_change / 100) + rounding)
        gross = money(orders * gross_per_order * (1 + price_change / 100) * (1 - discount / 100))
        refunds = money(gross * refund_rate / 100)
        reference_gross = money(reference_orders * gross_per_order)
        reference_refunds = money(reference_gross * baseline_refund_rate)
        rows.append(
            {
                "order_date": start + timedelta(days=offset),
                "completed_orders": orders,
                "eligible_gross": gross,
                "refunded_amount": refunds,
                "net_sales": money(gross - refunds),
                "reference_net_sales": money(reference_gross - reference_refunds),
            }
        )
    return pd.DataFrame(rows)

"""Scenario assumptions must conserve money and never modify historical inputs."""

from datetime import date

import pandas as pd
import pytest

from dashboard.scenarios import simulate_sales

BASE = dict(
    start=date(2026, 4, 1),
    days=90,
    baseline_days=30,
    completed_orders=300,
    eligible_gross=30000,
    refunded_amount=3000,
    refund_rate=10,
    variability=0,
    seed=7,
)


def test_neutral_scenario_matches_reference_and_requested_dates():
    result = simulate_sales(**BASE)
    assert len(result) == 90
    assert result.iloc[0].order_date == date(2026, 4, 1)
    assert result.iloc[-1].order_date == date(2026, 6, 29)
    assert result.net_sales.sum() == 81000
    assert result.net_sales.equals(result.reference_net_sales)
    assert result.completed_orders.sum() == 900


def test_discount_volume_and_refunds_are_applied_in_order():
    result = simulate_sales(**BASE, volume_change=100, price_change=10, discount=20)
    # 20 orders/day × R$100/order × 1.1 × 0.8 = R$1760 gross/day; 10% refunded.
    assert (result.eligible_gross == 1760).all()
    assert (result.refunded_amount == 176).all()
    assert (result.net_sales == 1584).all()
    assert (result.reference_net_sales == 900).all()


def test_seed_replays_and_different_seed_changes_daily_demand():
    args = BASE | {"variability": 40}
    pd.testing.assert_frame_equal(simulate_sales(**args), simulate_sales(**args))
    assert not simulate_sales(**args).equals(simulate_sales(**(args | {"seed": 8})))


def test_zero_volume_and_full_refund_remain_nonnegative():
    zero = simulate_sales(**BASE, volume_change=-100)
    assert (zero.net_sales == 0).all()
    full_refund = simulate_sales(**(BASE | {"refund_rate": 100}))
    assert (full_refund.net_sales == 0).all()
    assert (full_refund.refunded_amount <= full_refund.eligible_gross).all()


@pytest.mark.parametrize(
    "override",
    [
        {"days": 0},
        {"baseline_days": 0},
        {"completed_orders": 0},
        {"discount": 101},
        {"refund_rate": -1},
        {"volume_change": -101},
        {"refunded_amount": 30001},
    ],
)
def test_invalid_assumptions_are_rejected(override):
    with pytest.raises(ValueError):
        simulate_sales(**(BASE | override))

"""The nine cases the models must pass (docs/data-contracts.md → Test scenarios)."""

from __future__ import annotations

from decimal import Decimal

from tests.scenarios.conftest import Batch, Pipeline, item, money, order, refund


def _base() -> Batch:
    b = Batch()
    b.orders = [order("O1"), order("O2", created="2026-01-06T09:00:00Z", seq=2)]
    b.order_items = [item("I1", "O1", price="100.00"), item("I2", "O2", qty=2, price="50.00")]
    return b


# 1 · Duplicated input batch → same final counts/sums after replay -------------


def test_01_duplicated_batch_replay_is_idempotent(pipeline: Pipeline):
    run1 = pipeline.run(_base())
    assert run1["status"] == "ok"
    before = pipeline.kpis()

    # same rows delivered again as a *new* batch (different directory → same bytes
    # → same batch_id → skipped), and once more with a cosmetic difference so it
    # is a genuinely new batch id that raw keeps and staging must collapse.
    run2 = pipeline.run(_base())
    assert run2["stages"]["ingest"]["status"] == "skipped"

    b = _base()
    b.orders = list(reversed(b.orders))  # different CSV bytes, identical records
    run3 = pipeline.run(b)
    assert run3["status"] == "ok"
    assert run3["stages"]["ingest"]["batches_loaded"] == 2

    assert pipeline.kpis() == before
    assert pipeline.query("select count(*) from marts.fct_order_item") == [(2,)]


# 2 · completed → cancelled → contribution disappears on reprocess -------------


def test_02_completed_to_cancelled_removes_contribution(pipeline: Pipeline):
    pipeline.run(_base())
    assert money(pipeline.kpis()["eligible_gross"]) == Decimal("200.00")

    late = Batch()
    late.orders = [order("O1", status="cancelled", updated="2026-01-08T00:00:00Z", seq=3)]
    run = pipeline.run(late)
    assert run["status"] == "ok"

    k = pipeline.kpis()
    assert money(k["eligible_gross"]) == Decimal("100.00")
    assert k["completed_orders"] == 1
    assert pipeline.query(
        "select order_status from marts.fct_order_item where order_id = 'O1'"
    ) == [("cancelled",)]


# 3 · One order with three items → order count stays one ----------------------


def test_03_three_items_count_as_one_order(pipeline: Pipeline):
    b = Batch()
    b.orders = [order("O1")]
    b.order_items = [
        item("I1", "O1", price="10.00"),
        item("I2", "O1", price="20.00"),
        item("I3", "O1", price="30.00"),
    ]
    assert pipeline.run(b)["status"] == "ok"
    k = pipeline.kpis()
    assert k["completed_orders"] == 1
    assert money(k["eligible_gross"]) == Decimal("60.00")
    assert money(k["average_order_value"]) == Decimal("60.00")


# 4 · One item with two partial refunds → gross once, both refunds counted ----


def test_04_two_partial_refunds_no_fanout(pipeline: Pipeline):
    b = Batch()
    b.orders = [order("O1")]
    b.order_items = [item("I1", "O1", price="100.00")]
    b.refunds = [refund("R1", "I1", "30.00"), refund("R2", "I1", "20.00")]
    assert pipeline.run(b)["status"] == "ok"
    k = pipeline.kpis()
    assert money(k["eligible_gross"]) == Decimal("100.00")  # not 200 (fanout)
    assert money(k["refunded_amount"]) == Decimal("50.00")
    assert money(k["net_sales"]) == Decimal("50.00")


# 5 · Refund greater than item value → quality gate fails ----------------------


def test_05_refund_over_item_value_blocks_publication(pipeline: Pipeline):
    pipeline.run(_base())
    good = pipeline.published_fingerprint()

    b = Batch()
    b.orders = [order("O1")]
    b.order_items = [item("I1", "O1", price="100.00")]
    b.refunds = [refund("R1", "I1", "150.00")]
    run = pipeline.run(b)
    assert run["status"] == "failed"
    assert run["test_status"] == "critical_failure"
    failed = {f["test"] for f in run["stages"]["dbt"]["failures"]}
    assert "assert_refunds_within_item_value" in failed
    # offending record is reported, last known-good is untouched
    recs = run["failing_records"]["assert_refunds_within_item_value"]
    assert recs and recs[0]["order_item_id"] == "I1"
    assert pipeline.published_fingerprint() == good


# 6 · Missing customer reference → quality gate fails -------------------------


def test_06_missing_customer_fk_blocks_publication(pipeline: Pipeline):
    b = Batch()
    b.orders = [order("O1", cid="C_DOES_NOT_EXIST")]
    b.order_items = [item("I1", "O1")]
    run = pipeline.run(b)
    assert run["status"] == "failed"
    failed = {f["test"] for f in run["stages"]["dbt"]["failures"]}
    assert any(t.startswith("relationships_stg_orders_customer_id") for t in failed)
    assert not pipeline.published.exists()


# 7 · Zero completed orders → AOV is NULL, not division error -----------------


def test_07_no_completed_orders_gives_null_aov(pipeline: Pipeline):
    b = Batch()
    b.orders = [order("O1", status="pending"), order("O2", status="cancelled", seq=2)]
    b.order_items = [item("I1", "O1"), item("I2", "O2")]
    run = pipeline.run(b)
    assert run["status"] == "ok"
    k = pipeline.kpis()
    assert k["completed_orders"] == 0
    assert money(k["net_sales"]) == Decimal("0.00")
    assert k["average_order_value"] is None
    assert pipeline.query("select count(*) from marts.mart_daily_sales") == [(0,)]


# 8 · Late refund → original order date's net sales is corrected --------------


def test_08_late_refund_restates_original_order_date(pipeline: Pipeline):
    pipeline.run(_base())  # O1 on 2026-01-05, 100.00
    assert pipeline.query(
        "select net_sales from marts.mart_daily_sales where order_date = date '2026-01-05'"
    ) == [(Decimal("100.00"),)]

    late = Batch()
    late.refunds = [refund("R9", "I1", "40.00", at="2026-02-15T00:00:00Z")]
    assert pipeline.run(late)["status"] == "ok"

    rows = pipeline.query(
        "select order_date, net_sales, refunded_amount from marts.mart_daily_sales "
        "order by order_date"
    )
    by_date = {str(r[0]): (r[1], r[2]) for r in rows}
    assert by_date["2026-01-05"] == (Decimal("60.00"), Decimal("40.00"))  # restated
    assert "2026-02-15" not in by_date  # no row on the refund date (order-cohort)


# 9 · Two conflicting snapshots at identical ordering keys → load rejected ----


def test_09_conflicting_snapshots_are_rejected(pipeline: Pipeline):
    b = Batch()
    b.orders = [order("O1", status="completed", seq=1), order("O1", status="cancelled", seq=1)]
    b.order_items = [item("I1", "O1")]
    run = pipeline.run(b)
    assert run["status"] == "failed"
    failed = {f["test"] for f in run["stages"]["dbt"]["failures"]}
    assert "assert_no_conflicting_order_snapshots" in failed
    rec = run["failing_records"]["assert_no_conflicting_order_snapshots"][0]
    assert rec["order_id"] == "O1" and rec["conflicting_versions"] == 2
    assert not pipeline.published.exists()


# bonus · exact duplicate snapshot (same hash) is an accepted replay ----------


def test_exact_duplicate_snapshot_is_accepted(pipeline: Pipeline):
    b = Batch()
    b.orders = [order("O1"), order("O1")]
    b.order_items = [item("I1", "O1")]
    assert pipeline.run(b)["status"] == "ok"
    assert pipeline.kpis()["completed_orders"] == 1

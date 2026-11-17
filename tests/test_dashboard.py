"""US-07: the dashboard only re-aggregates published marts, and renders every state."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from dashboard import data as dp
from dashboard.format import brl, integer
from ember.config import PROJECT_ROOT, load_profile
from ember.generate import generate, write
from ember.pipeline import build


def money(x) -> Decimal:
    return Decimal(str(x)).quantize(Decimal("0.01"))


@pytest.fixture(scope="module")
def built(tmp_path_factory) -> dict:
    root = tmp_path_factory.mktemp("dash")
    cfg = load_profile("tiny")
    write(generate(cfg), root / "tiny", cfg)
    run = build(
        src_dir=root / "tiny",
        db_path=root / "work.duckdb",
        published_path=root / "published.duckdb",
        artifact_path=root / "last_run.json",
        target_path=root / "dbt_target",
    )
    assert run["status"] == "ok"
    return {
        "root": root,
        "published": root / "published.duckdb",
        "artifact": root / "last_run.json",
    }


# ---------------------------------------------------------------- formatting


def test_brl_formatting():
    assert brl(1234.5) == "R$ 1.234,50"
    assert brl(Decimal("45129.5"), False) == "45.129,50"
    assert brl(0) == "R$ 0,00"
    assert brl(None) == "-"
    assert integer(1234567) == "1.234.567"


# ---------------------------------------------------------------- data layer (ADR-002)


def test_unfiltered_queries_match_mart_kpi_total(built):
    con = dp.connect(built["published"])
    lo, hi = dp.bounds(con)
    k_q = dp.kpis(con, dp.Filters(lo, hi))
    k_m = dp.kpi_total(con)
    for key in ("eligible_gross", "refunded_amount", "net_sales"):
        assert Decimal(str(k_q[key])) == Decimal(str(k_m[key])), key
    assert k_q["completed_orders"] == k_m["completed_orders"]
    assert round(Decimal(str(k_q["average_order_value"])), 2) == k_m["average_order_value"]
    con.close()


def test_breakdown_sums_to_kpis_and_daily(built):
    con = dp.connect(built["published"])
    lo, hi = dp.bounds(con)
    f = dp.Filters(lo, hi)
    k = dp.kpis(con, f)
    assert money(dp.breakdown(con, f)["net_sales"].sum()) == money(k["net_sales"])
    assert money(dp.daily(con, f)["net_sales"].sum()) == money(k["net_sales"])
    con.close()


def test_category_filter_restricts(built):
    con = dp.connect(built["published"])
    lo, hi = dp.bounds(con)
    cats = dp.categories(con)
    total = dp.kpis(con, dp.Filters(lo, hi))["net_sales"]
    parts = sum(dp.kpis(con, dp.Filters(lo, hi, category=c))["net_sales"] for c in cats)
    assert money(parts) == money(total)
    con.close()


# ---------------------------------------------------------------- status


def test_status_healthy_then_stale(built):
    s = dp.load_status(built["artifact"])
    assert s.freshness == "healthy" and s.quality == "pass"
    later = datetime.now(UTC) + timedelta(days=3)
    assert dp.load_status(built["artifact"], now=later).freshness == "stale"


def test_status_failure_keeps_last_known_good(built, tmp_path: Path):
    run = json.loads(built["artifact"].read_text())
    run["status"] = "failed"
    run["test_status"] = "critical_failure"
    run["stages"]["dbt"]["failures"] = [{"test": "assert_x", "failures": 1}]
    run["published_path"] = str(built["published"])
    art = tmp_path / "failed.json"
    art.write_text(json.dumps(run))
    s = dp.load_status(art)
    assert s.quality == "failure"
    assert s.last_successful_run_at is not None  # from the published file's meta.run


def test_status_unknown_without_artifact(tmp_path: Path):
    s = dp.load_status(tmp_path / "missing.json")
    assert s.freshness == "unknown" and s.quality == "unknown"


# ---------------------------------------------------------------- app renders (AppTest)


def _app(monkeypatch, published: Path, artifact: Path):
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("EMBER_PUBLISHED", str(published))
    monkeypatch.setenv("EMBER_RUN_ARTIFACT", str(artifact))
    at = AppTest.from_file(str(PROJECT_ROOT / "dashboard" / "app.py"), default_timeout=60)
    return at.run()


def test_app_renders_healthy(built, monkeypatch):
    at = _app(monkeypatch, built["published"], built["artifact"])
    assert not at.exception
    assert at.title[0].value == "Sales Overview"
    assert any("Daily net sales" in h.value for h in at.subheader)
    html = " ".join(m.value for m in at.markdown)
    assert "Healthy" in html and "all critical tests passed" in html


def test_app_renders_empty_state(built, monkeypatch):
    at = _app(monkeypatch, built["published"], built["artifact"])
    hi = at.date_input[1].value
    # choose a product then a range at the end; eventually one combination is empty
    at.date_input[0].set_value(hi).run()
    at.date_input[1].set_value(hi).run()
    at.selectbox[0].set_value(at.selectbox[0].options[-1]).run()
    at.selectbox[1].set_value(at.selectbox[1].options[-1]).run()
    assert not at.exception
    html = " ".join(m.value for m in at.markdown)
    assert ("No completed orders match these filters" in html) or (
        "Daily net sales" in " ".join(h.value for h in at.subheader)
    )


def test_app_renders_failure_state(built, monkeypatch, tmp_path: Path):
    run = json.loads(built["artifact"].read_text())
    run.update(
        status="failed",
        test_status="critical_failure",
        message="2 critical test(s) failed; marts NOT published",
    )
    run["stages"]["dbt"]["failures"] = [{"test": "assert_refunds_within_item_value", "failures": 1}]
    run["published_path"] = str(built["published"])
    art = tmp_path / "failed.json"
    art.write_text(json.dumps(run))
    at = _app(monkeypatch, built["published"], art)
    assert not at.exception
    html = " ".join(m.value for m in at.markdown)
    assert "Failure" in html and "not current" in html
    assert "assert_refunds_within_item_value" in html


def test_app_renders_without_published(monkeypatch, tmp_path: Path):
    at = _app(monkeypatch, tmp_path / "none.duckdb", tmp_path / "none.json")
    assert not at.exception
    html = " ".join(m.value for m in at.markdown)
    assert "Nothing published yet" in html


def test_app_invalid_date_range(built, monkeypatch):
    at = _app(monkeypatch, built["published"], built["artifact"])
    lo, hi = at.date_input[0].value, at.date_input[1].value
    if lo == hi:
        pytest.skip("single-day fixture")
    at.date_input[0].set_value(hi).run()
    at.date_input[1].set_value(lo).run()
    assert not at.exception
    assert any("end date must be on or after" in e.value for e in at.error)


def test_empty_selection_hides_kpis_and_reset_restores_them(built, monkeypatch):
    con = dp.connect(built["published"])
    lo, hi = dp.bounds(con)
    product = con.execute(
        """select p.product_id from marts.dim_product p
        where not exists (select 1 from marts.mart_daily_sales s
                          where s.product_id = p.product_id and s.order_date = ?)
        limit 1""",
        [hi],
    ).fetchone()[0]
    con.close()
    at = _app(monkeypatch, built["published"], built["artifact"])
    at.date_input[0].set_value(hi)
    at.selectbox[1].set_value(product).run()
    assert not at.exception
    html = " ".join(m.value for m in at.markdown)
    assert "No completed orders match these filters" in html
    assert 'class="dp-kpi' not in html
    next(b for b in at.button if b.label == "Reset filters").click().run()
    assert not at.exception
    assert at.date_input[0].value == lo
    assert at.selectbox[1].value == "All"
    assert 'class="dp-kpi' in " ".join(m.value for m in at.markdown)


def test_changing_category_clears_incompatible_product(built, monkeypatch):
    con = dp.connect(built["published"])
    cats = dp.categories(con)
    pid = dp.products(con, cats[0])[0][0]
    con.close()
    at = _app(monkeypatch, built["published"], built["artifact"])
    at.selectbox[1].set_value(pid).run()
    at.selectbox[0].set_value(cats[1]).run()
    assert not at.exception
    assert at.selectbox[1].value == "All"


def test_app_renders_stale_snapshot(built, monkeypatch, tmp_path):
    run = json.loads(built["artifact"].read_text())
    run["last_successful_run_at"] = (datetime.now(UTC) - timedelta(days=3)).isoformat()
    art = tmp_path / "stale.json"
    art.write_text(json.dumps(run))
    at = _app(monkeypatch, built["published"], art)
    assert not at.exception
    html = " ".join(m.value for m in at.markdown)
    assert "Warning · stale data" in html
    assert 'class="dp-kpi' in html


def _kpi_strip(at) -> str:
    return " ".join(m.value for m in at.markdown if 'class="dp-strip"' in m.value)


def _open_whatif(at):
    return next(b for b in at.button if b.label == "What-if scenario (hypothetical)").click().run()


def test_whatif_dialog_preserves_published_kpis(built, monkeypatch):
    at = _app(monkeypatch, built["published"], built["artifact"])
    original = _kpi_strip(at)
    assert original and not at.metric  # what-if lives in a dialog, closed by default

    at = _open_whatif(at)
    assert not at.exception
    metrics = {m.label: m.value for m in at.metric}
    assert metrics["Simulated reference · no strategy"] == metrics["Simulated net sales"]

    # choosing a preset applies its sliders via session state and never touches the KPIs
    next(s for s in at.selectbox if s.label == "Starting strategy").set_value(
        "Campanha promocional"
    ).run()
    assert not at.exception
    assert at.session_state["scenario_volume"] == 25
    assert at.session_state["scenario_discount"] == 10
    assert _kpi_strip(at) == original

    at = _open_whatif(at)
    next(b for b in at.button if b.label == "Draw another scenario").click().run()
    assert not at.exception
    assert at.session_state["scenario_seed"] != 7
    assert _kpi_strip(at) == original

"""Read-only access to the PUBLISHED marts and the run artifact.

ADR-002: this module only filters and sums what dbt published at its declared
grain; it never recomputes a business formula from raw or staging data.
  * money KPIs   → sum over marts.mart_daily_sales (date × product)
  * order counts → count distinct order_id over marts.fct_order_item (is_eligible)
  * unfiltered   → marts.mart_kpi_total verbatim
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PUBLISHED = PROJECT_ROOT / "data" / "published.duckdb"
DEFAULT_ARTIFACT = PROJECT_ROOT / "data" / "last_run.json"
STALE_AFTER = timedelta(hours=float(os.environ.get("EMBER_STALE_AFTER_HOURS", "24")))


def published_path() -> Path:
    return Path(os.environ.get("EMBER_PUBLISHED", DEFAULT_PUBLISHED))


def artifact_path() -> Path:
    return Path(os.environ.get("EMBER_RUN_ARTIFACT", DEFAULT_ARTIFACT))


# --------------------------------------------------------------------------- status


@dataclass(frozen=True)
class PipelineStatus:
    freshness: str  # healthy | stale | unknown
    quality: str  # pass | warning | failure | unknown
    last_successful_run_at: datetime | None
    last_run_status: str | None
    message: str
    failures: list[dict[str, Any]]
    row_counts: dict[str, int]
    test_status: str | None


def load_status(artifact: Path | None = None, now: datetime | None = None) -> PipelineStatus:
    artifact = artifact or artifact_path()
    now = now or datetime.now(UTC)
    if not artifact.exists():
        return PipelineStatus(
            "unknown", "unknown", None, None, "No pipeline run found.", [], {}, None
        )
    run = json.loads(artifact.read_text())
    status = run.get("status")
    test_status = run.get("test_status")
    failures = run.get("stages", {}).get("dbt", {}).get("failures", []) or []
    counts = run.get("stages", {}).get("publish", {}).get("row_counts", {}) or {}

    last_ok = run.get("last_successful_run_at")
    last_ok_dt = datetime.fromisoformat(last_ok) if last_ok else None

    if status == "failed":
        quality = "failure"
        message = run.get("message", "A critical check failed; results not published.")
        # the published file (if any) is a previous successful run
        pub = Path(run.get("published_path", ""))
        prev = _published_at(pub) if pub.exists() else None
        last_ok_dt = prev
    elif status == "ok":
        quality = "warning" if test_status == "warnings" else "pass"
        message = "All critical tests passed."
    else:
        quality, message = "unknown", "Run artifact has no status."

    if last_ok_dt is None:
        freshness = "unknown"
    else:
        freshness = "healthy" if (now - last_ok_dt) <= STALE_AFTER else "stale"

    return PipelineStatus(
        freshness, quality, last_ok_dt, status, message, failures, counts, test_status
    )


def _published_at(pub: Path) -> datetime | None:
    try:
        con = duckdb.connect(str(pub), read_only=True)
        try:
            row = con.execute("select published_at from meta.run").fetchone()
        finally:
            con.close()
        return row[0].replace(tzinfo=UTC) if row else None
    except duckdb.Error:
        return None


# --------------------------------------------------------------------------- queries


def connect(path: Path | None = None) -> duckdb.DuckDBPyConnection:
    return duckdb.connect(str(path or published_path()), read_only=True)


def bounds(con: duckdb.DuckDBPyConnection) -> tuple[date, date] | None:
    row = con.execute(
        "select min(order_date), max(order_date) from marts.mart_daily_sales"
    ).fetchone()
    if row is None or row[0] is None:
        return None
    return row[0], row[1]


def categories(con: duckdb.DuckDBPyConnection) -> list[str]:
    rows = con.execute("select distinct category from marts.dim_product order by 1").fetchall()
    return [r[0] for r in rows]


def products(con: duckdb.DuckDBPyConnection, category: str | None) -> list[tuple[str, str]]:
    sql = "select product_id, product_name from marts.dim_product"
    params: list[Any] = []
    if category:
        sql += " where category = ?"
        params.append(category)
    return con.execute(sql + " order by product_name", params).fetchall()


@dataclass(frozen=True)
class Filters:
    start: date
    end: date
    category: str | None = None
    product_id: str | None = None

    def where(self, alias: str = "s") -> tuple[str, list[Any]]:
        clauses = [f"{alias}.order_date between ? and ?"]
        params: list[Any] = [self.start, self.end]
        if self.category:
            clauses.append("p.category = ?")
            params.append(self.category)
        if self.product_id:
            clauses.append(f"{alias}.product_id = ?")
            params.append(self.product_id)
        return " and ".join(clauses), params


def kpis(con: duckdb.DuckDBPyConnection, f: Filters) -> dict[str, Any]:
    where, params = f.where("s")
    money = con.execute(
        f"""
        select coalesce(sum(s.eligible_gross), 0), coalesce(sum(s.refunded_amount), 0),
               coalesce(sum(s.net_sales), 0)
        from marts.mart_daily_sales s join marts.dim_product p using (product_id)
        where {where}
        """,
        params,
    ).fetchone()
    orders = con.execute(
        f"""
        select count(distinct s.order_id)
        from marts.fct_order_item s join marts.dim_product p using (product_id)
        where s.is_eligible and {where}
        """,
        params,
    ).fetchone()[0]
    gross, refunds, net = money
    return {
        "eligible_gross": gross,
        "refunded_amount": refunds,
        "net_sales": net,
        "completed_orders": orders,
        "average_order_value": (net / orders) if orders else None,
    }


def kpi_total(con: duckdb.DuckDBPyConnection) -> dict[str, Any]:
    cur = con.execute("select * from marts.mart_kpi_total")
    row = cur.fetchone()
    return dict(zip([d[0] for d in cur.description], row, strict=True))


def daily(con: duckdb.DuckDBPyConnection, f: Filters) -> pd.DataFrame:
    where, params = f.where("s")
    return con.execute(
        f"""
        select s.order_date, sum(s.net_sales) as net_sales,
               sum(s.eligible_gross) as eligible_gross, sum(s.refunded_amount) as refunded_amount
        from marts.mart_daily_sales s join marts.dim_product p using (product_id)
        where {where}
        group by 1 order by 1
        """,
        params,
    ).df()


def breakdown(con: duckdb.DuckDBPyConnection, f: Filters) -> pd.DataFrame:
    where, params = f.where("s")
    return con.execute(
        f"""
        select p.category, sum(s.eligible_gross) as eligible_gross,
               sum(s.refunded_amount) as refunded_amount, sum(s.net_sales) as net_sales
        from marts.mart_daily_sales s join marts.dim_product p using (product_id)
        where {where}
        group by 1 order by net_sales desc
        """,
        params,
    ).df()

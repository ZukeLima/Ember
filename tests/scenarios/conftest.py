"""Helpers for the nine end-to-end scenarios (docs/data-contracts.md).

Each scenario hand-writes a tiny batch of source rows, runs the full pipeline
(ingest → dbt build → publish) against a throw-away DuckDB file and inspects
the published marts. dbt runs in-process, ~2 s per build.
"""

from __future__ import annotations

import csv
import hashlib
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any

import duckdb
import pytest

from ember.generate import COLUMNS, TABLES, order_record_hash
from ember.pipeline import build

Row = dict[str, Any]

# ---- row factories -----------------------------------------------------------


def customer(cid: str = "C1", segment: str = "consumer") -> Row:
    return {"customer_id": cid, "signup_at": "2025-06-01T00:00:00Z", "segment": segment}


def product(pid: str = "P1", category: str = "home", price: str = "100.00") -> Row:
    return {"product_id": pid, "category": category, "name": f"Item {pid}", "list_price": price}


def order(
    oid: str,
    status: str = "completed",
    created: str = "2026-01-05T10:00:00Z",
    updated: str | None = None,
    seq: int = 1,
    cid: str = "C1",
) -> Row:
    row = {
        "order_id": oid,
        "customer_id": cid,
        "created_at": created,
        "status": status,
        "updated_at": updated or created,
        "source_sequence": seq,
    }
    row["record_hash"] = order_record_hash(row)
    return row


def item(iid: str, oid: str, pid: str = "P1", qty: int = 1, price: str = "100.00") -> Row:
    return {
        "order_item_id": iid,
        "order_id": oid,
        "product_id": pid,
        "quantity": qty,
        "unit_price": price,
    }


def refund(
    rid: str,
    iid: str,
    amount: str,
    status: str = "succeeded",
    at: str = "2026-01-20T00:00:00Z",
) -> Row:
    return {
        "refund_id": rid,
        "order_item_id": iid,
        "refunded_at": at,
        "amount": amount,
        "status": status,
    }


# ---- batch ------------------------------------------------------------------


@dataclass
class Batch:
    customers: list[Row] = field(default_factory=lambda: [customer()])
    products: list[Row] = field(default_factory=lambda: [product()])
    orders: list[Row] = field(default_factory=list)
    order_items: list[Row] = field(default_factory=list)
    refunds: list[Row] = field(default_factory=list)

    def write(self, out: Path) -> Path:
        out.mkdir(parents=True, exist_ok=True)
        for name in TABLES:
            with open(out / f"{name}.csv", "w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=COLUMNS[name], lineterminator="\n")
                w.writeheader()
                for row in getattr(self, name):
                    w.writerow({k: row[k] for k in COLUMNS[name]})
        return out


@dataclass
class Pipeline:
    root: Path
    _n: int = 0

    @property
    def db(self) -> Path:
        return self.root / "work.duckdb"

    @property
    def published(self) -> Path:
        return self.root / "published.duckdb"

    def run(self, batch: Batch, name: str | None = None) -> dict[str, Any]:
        self._n += 1
        src = batch.write(self.root / (name or f"batch{self._n}"))
        return build(
            src_dir=src,
            db_path=self.db,
            published_path=self.published,
            artifact_path=self.root / "last_run.json",
            target_path=self.root / "dbt_target",
        )

    def query(self, sql: str) -> list[tuple]:
        con = duckdb.connect(str(self.published), read_only=True)
        try:
            return con.execute(sql).fetchall()
        finally:
            con.close()

    def kpis(self) -> dict[str, Any]:
        cur = duckdb.connect(str(self.published), read_only=True)
        try:
            r = cur.execute("select * from marts.mart_kpi_total").fetchone()
            cols = [d[0] for d in cur.description]
        finally:
            cur.close()
        return dict(zip(cols, r, strict=True))

    def published_fingerprint(self) -> str:
        return hashlib.sha256(self.published.read_bytes()).hexdigest()


@pytest.fixture
def pipeline(tmp_path: Path) -> Pipeline:
    return Pipeline(root=tmp_path)


def money(x: Any) -> Decimal:
    return Decimal(str(x)).quantize(Decimal("0.01"))

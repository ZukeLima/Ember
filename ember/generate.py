"""Deterministic synthetic e-commerce data generator (US-01).

Produces five CSV sources (customers, products, orders, order_items, refunds)
plus a manifest.json. Same config + seed → byte-identical files.

Design notes
------------
* All randomness goes through one `random.Random(seed)`; no `time.time()`,
  no dict-order dependence, no floats in money.
* `orders` is emitted as **snapshots**: an order with a late status change has
  two rows (same `order_id`, increasing `updated_at` / `source_sequence`).
  Downstream staging must deduplicate (see docs/data-contracts.md).
* `record_hash` is a sha256 over the business fields of a row, so an exact
  replay of the same record collapses to one, while a *conflicting* snapshot
  (same order_id / updated_at / source_sequence, different content) is detectable.
* Dirty fixtures are the clean output plus deliberately injected violations,
  each listed in the manifest so tests can assert the quality gate catches them.
"""

from __future__ import annotations

import csv
import hashlib
import json
import random
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from ember.money import cents_to_str

TABLES = ("customers", "products", "orders", "order_items", "refunds")

COLUMNS: dict[str, list[str]] = {
    "customers": ["customer_id", "signup_at", "segment"],
    "products": ["product_id", "category", "name", "list_price"],
    "orders": [
        "order_id",
        "customer_id",
        "created_at",
        "status",
        "updated_at",
        "source_sequence",
        "record_hash",
    ],
    "order_items": ["order_item_id", "order_id", "product_id", "quantity", "unit_price"],
    "refunds": ["refund_id", "order_item_id", "refunded_at", "amount", "status"],
}

SORT_KEYS: dict[str, list[str]] = {
    "customers": ["customer_id"],
    "products": ["product_id"],
    "orders": ["order_id", "source_sequence"],
    "order_items": ["order_item_id"],
    "refunds": ["refund_id"],
}

Row = dict[str, Any]


@dataclass
class Dataset:
    customers: list[Row] = field(default_factory=list)
    products: list[Row] = field(default_factory=list)
    orders: list[Row] = field(default_factory=list)
    order_items: list[Row] = field(default_factory=list)
    refunds: list[Row] = field(default_factory=list)
    injected: list[dict[str, Any]] = field(default_factory=list)

    def table(self, name: str) -> list[Row]:
        return getattr(self, name)


# --------------------------------------------------------------------------- helpers


def _ts(dt: datetime) -> str:
    """ISO-8601 UTC with explicit Z suffix, second precision."""
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _weighted(rng: random.Random, weights: dict[Any, float]) -> Any:
    keys = list(weights.keys())
    return rng.choices(keys, weights=[weights[k] for k in keys], k=1)[0]


def order_record_hash(row: Row) -> str:
    """Hash over the business content of an order snapshot (not the hash itself,
    not source_sequence; sequence is delivery metadata)."""
    payload = "|".join(
        str(row[k]) for k in ("order_id", "customer_id", "created_at", "status", "updated_at")
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


# --------------------------------------------------------------------------- generation


def generate(cfg: dict[str, Any]) -> Dataset:
    rng = random.Random(int(cfg["seed"]))
    base_date = datetime.fromisoformat(str(cfg["base_date"])).replace(tzinfo=UTC)
    days = int(cfg["days"])
    counts = cfg["row_counts"]
    ds = Dataset()

    # customers -------------------------------------------------------------
    for i in range(1, counts["customers"] + 1):
        signup = base_date - timedelta(days=rng.randint(1, 365), seconds=rng.randint(0, 86399))
        segment = _weighted(rng, cfg["segments"])
        ds.customers.append(
            {
                "customer_id": f"C{i:06d}",
                "signup_at": _ts(signup),
                "segment": "" if segment is None else segment,
            }
        )

    # products --------------------------------------------------------------
    categories = list(cfg["categories"])
    for i in range(1, counts["products"] + 1):
        cat = categories[(i - 1) % len(categories)]
        list_price_cents = rng.randint(990, 49990)
        ds.products.append(
            {
                "product_id": f"P{i:04d}",
                "category": cat,
                "name": f"{cat.title()} item {i:04d}",
                "list_price": cents_to_str(list_price_cents),
            }
        )
    price_by_product = {p["product_id"]: int(p["list_price"].replace(".", "")) for p in ds.products}

    # orders (snapshots) + items --------------------------------------------
    item_weights = {int(k): v for k, v in cfg["items_per_order"].items()}
    final_status_of: dict[str, str] = {}
    final_updated_of: dict[str, datetime] = {}
    snapshots: list[tuple[datetime, Row]] = []
    item_seq = 0

    for i in range(1, counts["orders"] + 1):
        order_id = f"O{i:07d}"
        customer = rng.choice(ds.customers)["customer_id"]
        created = base_date + timedelta(
            days=rng.randint(0, days - 1), seconds=rng.randint(0, 86399)
        )
        final_status = _weighted(rng, cfg["order_status"])
        late = rng.random() < float(cfg["late_update_share"])

        if late:
            # initial snapshot, then a status change 1–5 days later
            initial = "pending" if rng.random() < 0.5 else "completed"
            final_status = "completed" if rng.random() < 0.7 else "cancelled"
            if initial == final_status:
                final_status = "cancelled"
            updated = created + timedelta(days=rng.randint(1, 5), seconds=rng.randint(0, 86399))
            snapshots.append(
                (
                    created,
                    {
                        "order_id": order_id,
                        "customer_id": customer,
                        "created_at": _ts(created),
                        "status": initial,
                        "updated_at": _ts(created),
                    },
                )
            )
            snapshots.append(
                (
                    updated,
                    {
                        "order_id": order_id,
                        "customer_id": customer,
                        "created_at": _ts(created),
                        "status": final_status,
                        "updated_at": _ts(updated),
                    },
                )
            )
        else:
            updated = created
            snapshots.append(
                (
                    created,
                    {
                        "order_id": order_id,
                        "customer_id": customer,
                        "created_at": _ts(created),
                        "status": final_status,
                        "updated_at": _ts(created),
                    },
                )
            )
        final_status_of[order_id] = final_status
        final_updated_of[order_id] = updated

        n_items = _weighted(rng, item_weights)
        chosen = rng.sample(ds.products, k=n_items)
        for p in chosen:
            item_seq += 1
            qty = rng.choices([1, 2, 3], weights=[0.75, 0.2, 0.05], k=1)[0]
            # unit price around list price (−10%..+0%) to look like promotions
            unit = int(price_by_product[p["product_id"]] * (1 - rng.random() * 0.10))
            ds.order_items.append(
                {
                    "order_item_id": f"I{item_seq:08d}",
                    "order_id": order_id,
                    "product_id": p["product_id"],
                    "quantity": qty,
                    "unit_price": cents_to_str(unit),
                }
            )

    # assign source_sequence in delivery order (by updated_at, then order_id)
    snapshots.sort(key=lambda t: (t[0], t[1]["order_id"]))
    for seq, (_, row) in enumerate(snapshots, start=1):
        row["source_sequence"] = seq
        row["record_hash"] = order_record_hash(row)
        ds.orders.append(row)

    # refunds ---------------------------------------------------------------
    rcfg = cfg["refunds"]
    refund_seq = 0
    for item in ds.order_items:
        status = final_status_of[item["order_id"]]
        eligible = status == "completed"
        # mostly on completed items; a small share on non-eligible ones
        # (those must be excluded downstream by the metric definition)
        p_refund = float(rcfg["share_of_completed_items"]) if eligible else 0.01
        if rng.random() >= p_refund:
            continue
        item_amount = int(item["unit_price"].replace(".", "")) * int(item["quantity"])
        when = final_updated_of[item["order_id"]] + timedelta(
            days=rng.randint(1, 20), seconds=rng.randint(0, 86399)
        )
        partial = rng.random() < float(rcfg["partial_share"])
        amounts: list[int] = []
        if partial:
            first = int(item_amount * (0.10 + rng.random() * 0.80))
            amounts.append(first)
            if rng.random() < float(rcfg["second_partial_share"]):
                remaining = item_amount - first
                amounts.append(int(remaining * (0.20 + rng.random() * 0.80)))
        else:
            amounts.append(item_amount)
        for k, amt in enumerate(amounts):
            refund_seq += 1
            ds.refunds.append(
                {
                    "refund_id": f"R{refund_seq:07d}",
                    "order_item_id": item["order_item_id"],
                    "refunded_at": _ts(when + timedelta(days=3 * k)),
                    "amount": cents_to_str(amt),
                    "status": _weighted(rng, rcfg["status"]),
                }
            )

    # dirty injections ------------------------------------------------------
    for case in cfg.get("inject", []) or []:
        INJECTORS[case](ds, rng)

    for name in TABLES:
        ds.table(name).sort(key=lambda r, n=name: tuple(r[k] for k in SORT_KEYS[n]))
    return ds


# --------------------------------------------------------------------------- injectors


def _inject_duplicate_order_snapshot(ds: Dataset, rng: random.Random) -> None:
    src = ds.orders[0]
    ds.orders.append(dict(src))
    ds.injected.append({"case": "duplicate_order_snapshot", "order_id": src["order_id"]})


def _inject_conflicting_order_snapshot(ds: Dataset, rng: random.Random) -> None:
    src = next(r for r in ds.orders if r["status"] == "completed")
    bad = dict(src)
    bad["status"] = "cancelled"  # same order_id/updated_at/source_sequence, different content
    bad["record_hash"] = order_record_hash(bad)
    ds.orders.append(bad)
    ds.injected.append({"case": "conflicting_order_snapshot", "order_id": src["order_id"]})


def _inject_missing_customer_fk(ds: Dataset, rng: random.Random) -> None:
    src = ds.orders[1]
    bad = dict(src)
    bad["order_id"] = "O9999991"
    bad["customer_id"] = "C999999"
    bad["source_sequence"] = max(r["source_sequence"] for r in ds.orders) + 1
    bad["record_hash"] = order_record_hash(bad)
    ds.orders.append(bad)
    ds.order_items.append(
        {
            "order_item_id": "I99999991",
            "order_id": bad["order_id"],
            "product_id": ds.products[0]["product_id"],
            "quantity": 1,
            "unit_price": ds.products[0]["list_price"],
        }
    )
    ds.injected.append({"case": "missing_customer_fk", "order_id": bad["order_id"]})


def _inject_refund_over_item_value(ds: Dataset, rng: random.Random) -> None:
    completed = {r["order_id"] for r in ds.orders if r["status"] == "completed"}
    item = next(i for i in ds.order_items if i["order_id"] in completed)
    item_amount = int(item["unit_price"].replace(".", "")) * int(item["quantity"])
    ds.refunds.append(
        {
            "refund_id": "R9999991",
            "order_item_id": item["order_item_id"],
            "refunded_at": "2026-02-28T00:00:00Z",
            "amount": cents_to_str(item_amount * 3),
            "status": "succeeded",
        }
    )
    ds.injected.append({"case": "refund_over_item_value", "order_item_id": item["order_item_id"]})


def _inject_negative_amount(ds: Dataset, rng: random.Random) -> None:
    src = ds.order_items[0]
    ds.order_items.append(
        {
            "order_item_id": "I99999992",
            "order_id": src["order_id"],
            "product_id": src["product_id"],
            "quantity": 1,
            "unit_price": "-10.00",
        }
    )
    ds.injected.append({"case": "negative_amount", "order_item_id": "I99999992"})


def _inject_duplicate_refund_delivery(ds: Dataset, rng: random.Random) -> None:
    src = ds.refunds[0]
    ds.refunds.append(dict(src))
    ds.injected.append({"case": "duplicate_refund_delivery", "refund_id": src["refund_id"]})


INJECTORS = {
    "duplicate_order_snapshot": _inject_duplicate_order_snapshot,
    "conflicting_order_snapshot": _inject_conflicting_order_snapshot,
    "missing_customer_fk": _inject_missing_customer_fk,
    "refund_over_item_value": _inject_refund_over_item_value,
    "negative_amount": _inject_negative_amount,
    "duplicate_refund_delivery": _inject_duplicate_refund_delivery,
}


# --------------------------------------------------------------------------- output


def write(ds: Dataset, out_dir: Path, cfg: dict[str, Any]) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    for name in TABLES:
        path = out_dir / f"{name}.csv"
        with open(path, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=COLUMNS[name], lineterminator="\n")
            w.writeheader()
            for row in ds.table(name):
                w.writerow({k: row[k] for k in COLUMNS[name]})

    manifest = {
        "generator_version": 1,
        "profile": cfg.get("profile"),
        "seed": cfg["seed"],
        "base_date": cfg["base_date"],
        "days": cfg["days"],
        "currency": cfg["currency"],
        "timezone": "UTC",
        "row_counts": {name: len(ds.table(name)) for name in TABLES},
        "injected": ds.injected,
        "files": {
            name: hashlib.sha256((out_dir / f"{name}.csv").read_bytes()).hexdigest()
            for name in TABLES
        },
    }
    with open(out_dir / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)
        f.write("\n")
    return manifest

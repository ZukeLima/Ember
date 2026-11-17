"""US-01 acceptance: deterministic output, clean-fixture contracts, dirty-fixture cases."""

from __future__ import annotations

import csv
import json
import re
from collections import Counter
from pathlib import Path

import pytest

from ember.config import load_profile
from ember.generate import TABLES, generate, write

UTC_TS = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def _read(out: Path, name: str) -> list[dict]:
    with open(out / f"{name}.csv", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


@pytest.fixture(scope="module")
def clean(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("clean")
    cfg = load_profile("tiny")
    write(generate(cfg), out, cfg)
    return out


@pytest.fixture(scope="module")
def dirty(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("dirty")
    cfg = load_profile("dirty")
    cfg["row_counts"] = {"customers": 30, "products": 10, "orders": 80}
    write(generate(cfg), out, cfg)
    return out


# ---------------------------------------------------------------- determinism


def test_same_seed_is_byte_identical(tmp_path: Path):
    cfg = load_profile("tiny")
    a, b = tmp_path / "a", tmp_path / "b"
    write(generate(cfg), a, cfg)
    write(generate(cfg), b, cfg)
    for name in TABLES:
        assert (a / f"{name}.csv").read_bytes() == (b / f"{name}.csv").read_bytes(), name
    assert (a / "manifest.json").read_text() == (b / "manifest.json").read_text()


def test_different_seed_changes_output(tmp_path: Path):
    cfg = load_profile("tiny")
    a = tmp_path / "a"
    write(generate(cfg), a, cfg)
    cfg["seed"] = cfg["seed"] + 1
    b = tmp_path / "b"
    write(generate(cfg), b, cfg)
    assert (a / "orders.csv").read_bytes() != (b / "orders.csv").read_bytes()


def test_files_are_sorted_by_primary_key(clean: Path):
    for name, key in {
        "customers": "customer_id",
        "products": "product_id",
        "order_items": "order_item_id",
        "refunds": "refund_id",
    }.items():
        ids = [r[key] for r in _read(clean, name)]
        assert ids == sorted(ids), name
    orders = [(r["order_id"], int(r["source_sequence"])) for r in _read(clean, "orders")]
    assert orders == sorted(orders)


# ---------------------------------------------------------------- clean contracts


def test_clean_primary_keys_unique(clean: Path):
    for name, key in {
        "customers": "customer_id",
        "products": "product_id",
        "order_items": "order_item_id",
        "refunds": "refund_id",
    }.items():
        ids = [r[key] for r in _read(clean, name)]
        assert len(ids) == len(set(ids)), f"duplicate {key} in {name}"


def test_clean_order_snapshots_dedupe_to_one_latest(clean: Path):
    """orders is a snapshot table: multiple rows per order_id are allowed, but
    (order_id, updated_at, source_sequence) must be unique and the max row unique."""
    rows = _read(clean, "orders")
    keys = [(r["order_id"], r["updated_at"], r["source_sequence"]) for r in rows]
    assert len(keys) == len(set(keys))
    seqs = [int(r["source_sequence"]) for r in rows]
    assert len(seqs) == len(set(seqs)), "source_sequence must be globally unique"
    hashes = Counter(r["record_hash"] for r in rows)
    assert all(n == 1 for n in hashes.values())
    late = Counter(r["order_id"] for r in rows)
    assert any(n > 1 for n in late.values()), "fixture must contain late status updates"


def test_clean_foreign_keys_valid(clean: Path):
    customers = {r["customer_id"] for r in _read(clean, "customers")}
    products = {r["product_id"] for r in _read(clean, "products")}
    orders = {r["order_id"] for r in _read(clean, "orders")}
    items = {r["order_item_id"] for r in _read(clean, "order_items")}
    assert all(r["customer_id"] in customers for r in _read(clean, "orders"))
    for r in _read(clean, "order_items"):
        assert r["order_id"] in orders and r["product_id"] in products
    assert all(r["order_item_id"] in items for r in _read(clean, "refunds"))


def test_clean_amounts_and_quantities(clean: Path):
    money = re.compile(r"^\d+\.\d{2}$")
    for r in _read(clean, "products"):
        assert money.match(r["list_price"])
    for r in _read(clean, "order_items"):
        assert int(r["quantity"]) > 0
        assert money.match(r["unit_price"])
    for r in _read(clean, "refunds"):
        assert money.match(r["amount"])


def test_clean_refunds_never_exceed_item_value(clean: Path):
    items = {r["order_item_id"]: r for r in _read(clean, "order_items")}
    refunded = Counter()
    for r in _read(clean, "refunds"):
        if r["status"] == "succeeded":
            refunded[r["order_item_id"]] += int(r["amount"].replace(".", ""))
    for item_id, total in refunded.items():
        it = items[item_id]
        assert total <= int(it["unit_price"].replace(".", "")) * int(it["quantity"]), item_id


def test_clean_has_partial_refunds(clean: Path):
    per_item = Counter(r["order_item_id"] for r in _read(clean, "refunds"))
    assert any(n >= 2 for n in per_item.values()), "fixture must contain two partial refunds"


def test_timestamps_are_utc(clean: Path):
    for name, cols in {
        "customers": ["signup_at"],
        "orders": ["created_at", "updated_at"],
        "refunds": ["refunded_at"],
    }.items():
        for r in _read(clean, name):
            for c in cols:
                assert UTC_TS.match(r[c]), (name, c, r[c])


def test_clean_manifest(clean: Path):
    m = json.loads((clean / "manifest.json").read_text())
    assert m["injected"] == []
    assert m["timezone"] == "UTC" and m["currency"] == "BRL"
    assert set(m["row_counts"]) == set(TABLES)


# ---------------------------------------------------------------- dirty fixture


def test_dirty_manifest_lists_every_case(dirty: Path):
    m = json.loads((dirty / "manifest.json").read_text())
    cases = {c["case"] for c in m["injected"]}
    assert cases == {
        "duplicate_order_snapshot",
        "conflicting_order_snapshot",
        "missing_customer_fk",
        "refund_over_item_value",
        "negative_amount",
        "duplicate_refund_delivery",
    }


def test_dirty_contains_duplicate_and_conflicting_snapshots(dirty: Path):
    rows = _read(dirty, "orders")
    full = Counter(tuple(r.values()) for r in rows)
    assert any(n == 2 for n in full.values()), "exact duplicate snapshot expected"
    key = Counter((r["order_id"], r["updated_at"], r["source_sequence"]) for r in rows)
    conflicting = [k for k, n in key.items() if n >= 2]
    assert conflicting

    # at least one of those keys has two different hashes → a real conflict
    def hashes_for(k):
        return {
            r["record_hash"]
            for r in rows
            if (r["order_id"], r["updated_at"], r["source_sequence"]) == k
        }

    assert any(len(hashes_for(k)) > 1 for k in conflicting)


def test_dirty_contains_missing_fk_and_bad_amounts(dirty: Path):
    customers = {r["customer_id"] for r in _read(dirty, "customers")}
    assert any(r["customer_id"] not in customers for r in _read(dirty, "orders"))
    assert any(r["unit_price"].startswith("-") for r in _read(dirty, "order_items"))
    items = {r["order_item_id"]: r for r in _read(dirty, "order_items")}
    over = [
        r
        for r in _read(dirty, "refunds")
        if int(r["amount"].replace(".", ""))
        > int(items[r["order_item_id"]]["unit_price"].replace(".", ""))
        * int(items[r["order_item_id"]]["quantity"])
    ]
    assert over
    refund_ids = Counter(r["refund_id"] for r in _read(dirty, "refunds"))
    assert any(n == 2 for n in refund_ids.values())

"""Raw ingestion into DuckDB (US-02).

Each fixture directory is a *batch*. Every row loaded carries:
  * `_ingested_at`   : UTC timestamp of the load
  * `_source_id`     : logical source name (e.g. "synthetic")
  * `_batch_id`      : sha256 over the batch's file contents (from manifest)

Idempotency rule
----------------
`_batch_id` is content-addressed. Re-running ingestion on an unchanged directory
finds the batch already loaded and does nothing (status "skipped"). A batch with
different content is appended; raw tables are append-only and never deduplicated
here; deduplication is dbt's job (staging), using the deterministic rule in
docs/data-contracts.md. This keeps raw a faithful record of what was delivered.

A run artifact (JSON) is written next to the database so freshness, row counts
and status are inspectable without opening the DB.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb

from ember.generate import COLUMNS, TABLES

RAW_SCHEMA = "raw"

# Column types in raw: keep everything as delivered (VARCHAR), except integers.
# Casting to DECIMAL/TIMESTAMP is a staging concern so that a bad value fails
# a contract test instead of crashing the load.
RAW_TYPES: dict[str, dict[str, str]] = {
    "customers": {"customer_id": "VARCHAR", "signup_at": "VARCHAR", "segment": "VARCHAR"},
    "products": {
        "product_id": "VARCHAR",
        "category": "VARCHAR",
        "name": "VARCHAR",
        "list_price": "VARCHAR",
    },
    "orders": {
        "order_id": "VARCHAR",
        "customer_id": "VARCHAR",
        "created_at": "VARCHAR",
        "status": "VARCHAR",
        "updated_at": "VARCHAR",
        "source_sequence": "BIGINT",
        "record_hash": "VARCHAR",
    },
    "order_items": {
        "order_item_id": "VARCHAR",
        "order_id": "VARCHAR",
        "product_id": "VARCHAR",
        "quantity": "BIGINT",
        "unit_price": "VARCHAR",
    },
    "refunds": {
        "refund_id": "VARCHAR",
        "order_item_id": "VARCHAR",
        "refunded_at": "VARCHAR",
        "amount": "VARCHAR",
        "status": "VARCHAR",
    },
}

META_COLUMNS = {
    "_ingested_at": "TIMESTAMP",
    "_source_id": "VARCHAR",
    "_batch_id": "VARCHAR",
}


def batch_id_for(src_dir: Path) -> str:
    """Content hash of the five CSVs (order-independent of manifest formatting)."""
    h = hashlib.sha256()
    for name in TABLES:
        h.update(name.encode())
        h.update((src_dir / f"{name}.csv").read_bytes())
    return h.hexdigest()[:32]


def _ensure_schema(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(f"CREATE SCHEMA IF NOT EXISTS {RAW_SCHEMA}")
    for name in TABLES:
        cols = {**RAW_TYPES[name], **META_COLUMNS}
        ddl = ", ".join(f"{c} {t}" for c, t in cols.items())
        con.execute(f"CREATE TABLE IF NOT EXISTS {RAW_SCHEMA}.{name} ({ddl})")
    con.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {RAW_SCHEMA}._batches (
            batch_id VARCHAR PRIMARY KEY,
            source_id VARCHAR,
            src_dir VARCHAR,
            ingested_at TIMESTAMP,
            row_counts JSON
        )
        """
    )


def ingest(
    src_dir: Path,
    db_path: Path,
    source_id: str = "synthetic",
    artifact_path: Path | None = None,
) -> dict[str, Any]:
    src_dir = Path(src_dir)
    db_path = Path(db_path)
    artifact_path = artifact_path or db_path.with_name("last_run.json")
    missing = [n for n in TABLES if not (src_dir / f"{n}.csv").exists()]
    if missing:
        raise FileNotFoundError(f"fixture {src_dir} is missing: {missing}")

    batch_id = batch_id_for(src_dir)
    started = datetime.now(UTC)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect(str(db_path))
    try:
        _ensure_schema(con)
        already = con.execute(
            f"SELECT 1 FROM {RAW_SCHEMA}._batches WHERE batch_id = ?", [batch_id]
        ).fetchone()
        if already:
            result = _result("skipped", batch_id, source_id, src_dir, started, con)
            result["message"] = "batch already ingested; nothing to do"
            _write_artifact(artifact_path, result)
            return result

        con.execute("BEGIN")
        counts: dict[str, int] = {}
        for name in TABLES:
            cols = COLUMNS[name]
            col_types = {c: RAW_TYPES[name][c] for c in cols}
            types_sql = ", ".join(f"'{c}': '{t}'" for c, t in col_types.items())
            col_list = ", ".join(cols)
            con.execute(
                f"""
                INSERT INTO {RAW_SCHEMA}.{name} ({col_list}, _ingested_at, _source_id, _batch_id)
                SELECT {col_list}, ?, ?, ?
                FROM read_csv(?, header = true, columns = {{{types_sql}}},
                              nullstr = '', all_varchar = false)
                """,
                [started.replace(tzinfo=None), source_id, batch_id, str(src_dir / f"{name}.csv")],
            )
            counts[name] = con.execute(
                f"SELECT count(*) FROM {RAW_SCHEMA}.{name} WHERE _batch_id = ?", [batch_id]
            ).fetchone()[0]
        con.execute(
            f"INSERT INTO {RAW_SCHEMA}._batches VALUES (?, ?, ?, ?, ?)",
            [batch_id, source_id, str(src_dir), started.replace(tzinfo=None), json.dumps(counts)],
        )
        con.execute("COMMIT")
        result = _result("ok", batch_id, source_id, src_dir, started, con)
        result["batch_row_counts"] = counts
    except Exception as exc:  # noqa: BLE001, we want the artifact to record the failure
        try:
            con.execute("ROLLBACK")
        except duckdb.Error:
            pass
        result = {
            "status": "failed",
            "stage": "ingest",
            "batch_id": batch_id,
            "source_id": source_id,
            "src_dir": str(src_dir),
            "started_at": started.isoformat(),
            "error": f"{type(exc).__name__}: {exc}",
        }
        _write_artifact(artifact_path, result)
        raise
    finally:
        con.close()

    _write_artifact(artifact_path, result)
    return result


def _result(
    status: str,
    batch_id: str,
    source_id: str,
    src_dir: Path,
    started: datetime,
    con: duckdb.DuckDBPyConnection,
) -> dict[str, Any]:
    totals = {
        name: con.execute(f"SELECT count(*) FROM {RAW_SCHEMA}.{name}").fetchone()[0]
        for name in TABLES
    }
    n_batches = con.execute(f"SELECT count(*) FROM {RAW_SCHEMA}._batches").fetchone()[0]
    return {
        "status": status,
        "stage": "ingest",
        "batch_id": batch_id,
        "source_id": source_id,
        "src_dir": str(src_dir),
        "started_at": started.isoformat(),
        "finished_at": datetime.now(UTC).isoformat(),
        "raw_row_counts": totals,
        "batches_loaded": n_batches,
    }


def _write_artifact(path: Path, result: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, sort_keys=True)
        f.write("\n")

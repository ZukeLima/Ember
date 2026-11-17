"""Pipeline orchestration: ingest → dbt build → publish (ADR-005 gate).

Publication model
-----------------
dbt builds everything into the *working* database. Only if `dbt build` succeeds
(no critical test failure) are the marts copied into a separate *published*
DuckDB file, which the dashboard opens read-only. The copy is written to a temp
file and atomically renamed, so:

* a critical failure leaves the previous published file untouched
  (last known-good), and
* a dashboard holding the old file open keeps working while a new one lands.

A run artifact (`last_run.json`, next to the working DB) records every stage,
test status, failing tests with sample offending records, and row counts.
"""

from __future__ import annotations

import json
import os
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb

from ember.config import PROJECT_ROOT
from ember.ingest import ingest

ANALYTICS_DIR = PROJECT_ROOT / "analytics"
PUBLISHED_TABLES = (
    "dim_customer",
    "dim_product",
    "fct_order_item",
    "fct_refund",
    "mart_daily_sales",
    "mart_kpi_total",
)


# --------------------------------------------------------------------------- dbt


def run_dbt(
    db_path: Path,
    target_path: Path | None = None,
    full_refresh: bool = True,
) -> dict[str, Any]:
    """Run `dbt build` in-process and summarize target/run_results.json."""
    from dbt.cli.main import dbtRunner

    target_path = target_path or ANALYTICS_DIR / "target"
    os.environ["EMBER_DB"] = str(Path(db_path).resolve())
    args = [
        "build",
        "--project-dir",
        str(ANALYTICS_DIR),
        "--profiles-dir",
        str(ANALYTICS_DIR),
        "--target-path",
        str(target_path),
        "--log-path",
        str(target_path / "logs"),
        "--quiet",
    ]
    if full_refresh:
        args.append("--full-refresh")
    res = dbtRunner().invoke(args)

    summary: dict[str, Any] = {
        "success": bool(res.success),
        "failures": [],
        "warnings": [],
        "models_built": 0,
        "tests_run": 0,
    }
    if res.exception is not None:
        summary["error"] = f"{type(res.exception).__name__}: {res.exception}"
    results_file = target_path / "run_results.json"
    if results_file.exists():
        rr = json.loads(results_file.read_text())
        for r in rr.get("results", []):
            uid: str = r.get("unique_id", "")
            status = r.get("status")
            if uid.startswith("model.") and status == "success":
                summary["models_built"] += 1
            if uid.startswith("test."):
                summary["tests_run"] += 1
                if status == "fail" or status == "error":
                    summary["failures"].append(
                        {
                            "test": uid.split(".")[2],
                            "status": status,
                            "failures": r.get("failures"),
                            "message": (r.get("message") or "")[:300],
                        }
                    )
                elif status == "warn":
                    summary["warnings"].append(
                        {"test": uid.split(".")[2], "failures": r.get("failures")}
                    )
    return summary


def failing_records(db_path: Path, failures: list[dict[str, Any]], limit: int = 5) -> dict:
    """Pull a sample of offending rows for each failed test from dq_failures."""
    out: dict[str, list[dict[str, Any]]] = {}
    # dbt (in-process) may still hold this file open; a read_only connection
    # would conflict with that configuration, so open it the same way dbt did.
    con = duckdb.connect(str(db_path))
    try:
        tables = {
            r[0]
            for r in con.execute(
                "select table_name from information_schema.tables where table_schema='dq_failures'"
            ).fetchall()
        }
        for f in failures:
            name = f["test"]
            match = next((t for t in tables if t == name or t.startswith(name[:40])), None)
            if match is None:
                continue
            cur = con.execute(f'select * from dq_failures."{match}" limit {int(limit)}')
            cols = [d[0] for d in cur.description]
            out[name] = [dict(zip(cols, row, strict=True)) for row in cur.fetchall()]
    finally:
        con.close()
    return json.loads(json.dumps(out, default=str))


# --------------------------------------------------------------------------- publish


def publish(db_path: Path, published_path: Path, run_info: dict[str, Any]) -> dict[str, int]:
    """Copy marts into a fresh DuckDB file and atomically replace published_path."""
    published_path = Path(published_path)
    published_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = published_path.with_name(published_path.name + ".tmp")
    for p in (tmp, tmp.with_name(tmp.name + ".wal")):
        if p.exists():
            p.unlink()

    counts: dict[str, int] = {}
    con = duckdb.connect(str(db_path))
    try:
        con.execute(f"ATTACH '{tmp}' AS pub")
        con.execute("CREATE SCHEMA IF NOT EXISTS pub.marts")
        con.execute("CREATE SCHEMA IF NOT EXISTS pub.meta")
        for t in PUBLISHED_TABLES:
            con.execute(f"CREATE TABLE pub.marts.{t} AS SELECT * FROM marts.{t}")
            counts[t] = con.execute(f"SELECT count(*) FROM pub.marts.{t}").fetchone()[0]
        con.execute(
            "CREATE TABLE pub.meta.run AS SELECT ?::TIMESTAMP AS published_at, ?::JSON AS run_info",
            [datetime.now(UTC).replace(tzinfo=None), json.dumps(run_info, default=str)],
        )
        con.execute("DETACH pub")
    finally:
        con.close()
    os.replace(tmp, published_path)
    return counts


# --------------------------------------------------------------------------- orchestration


def build(
    src_dir: Path,
    db_path: Path,
    published_path: Path | None = None,
    artifact_path: Path | None = None,
    source_id: str = "synthetic",
    target_path: Path | None = None,
) -> dict[str, Any]:
    db_path = Path(db_path)
    published_path = Path(published_path or db_path.with_name("published.duckdb"))
    artifact_path = Path(artifact_path or db_path.with_name("last_run.json"))
    started = datetime.now(UTC)
    run: dict[str, Any] = {
        "started_at": started.isoformat(),
        "src_dir": str(src_dir),
        "db_path": str(db_path),
        "published_path": str(published_path),
        "stages": {},
    }

    # 1 · ingest ----------------------------------------------------------
    ing = ingest(src_dir, db_path, source_id=source_id, artifact_path=artifact_path)
    run["stages"]["ingest"] = {
        "status": ing["status"],
        "batch_id": ing["batch_id"],
        "raw_row_counts": ing["raw_row_counts"],
        "batches_loaded": ing["batches_loaded"],
    }

    # 2 · dbt build (models + critical tests) ------------------------------
    dbt = run_dbt(db_path, target_path=target_path)
    run["stages"]["dbt"] = dbt
    if not dbt["success"]:
        run["status"] = "failed"
        run["test_status"] = "critical_failure"
        run["failing_records"] = failing_records(db_path, dbt["failures"])
        run["message"] = (
            f"{len(dbt['failures'])} critical test(s) failed; marts NOT published "
            f"(ADR-005). Last known-good remains at {published_path}"
            if published_path.exists()
            else f"{len(dbt['failures'])} critical test(s) failed; nothing published."
        )
        run["finished_at"] = datetime.now(UTC).isoformat()
        _write(artifact_path, run)
        return run

    # 3 · publish ----------------------------------------------------------
    run["test_status"] = "warnings" if dbt["warnings"] else "all_critical_passed"
    counts = publish(
        db_path, published_path, {"batch_id": ing["batch_id"], "src_dir": str(src_dir)}
    )
    run["stages"]["publish"] = {"status": "ok", "row_counts": counts}
    run["status"] = "ok"
    run["last_successful_run_at"] = datetime.now(UTC).isoformat()
    run["finished_at"] = run["last_successful_run_at"]
    _write(artifact_path, run)
    return run


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=True, default=str)
        f.write("\n")


def reset_workdir(db_path: Path) -> None:
    """Delete the working DB (and its WAL) so a build starts from scratch."""
    for p in (db_path, db_path.with_name(db_path.name + ".wal")):
        if p.exists():
            p.unlink()
    target = ANALYTICS_DIR / "target"
    if target.exists():
        shutil.rmtree(target, ignore_errors=True)

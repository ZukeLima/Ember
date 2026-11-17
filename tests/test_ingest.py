"""US-02 acceptance: metadata columns, idempotent replay, run artifact."""

from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pytest

from ember.config import load_profile
from ember.generate import TABLES, generate, write
from ember.ingest import batch_id_for, ingest


@pytest.fixture
def fixture_dir(tmp_path: Path) -> Path:
    out = tmp_path / "tiny"
    cfg = load_profile("tiny")
    write(generate(cfg), out, cfg)
    return out


def test_ingest_loads_every_table_with_metadata(fixture_dir: Path, tmp_path: Path):
    db = tmp_path / "t.duckdb"
    result = ingest(fixture_dir, db)
    assert result["status"] == "ok"
    manifest = json.loads((fixture_dir / "manifest.json").read_text())
    assert result["batch_row_counts"] == manifest["row_counts"]

    con = duckdb.connect(str(db), read_only=True)
    for name in TABLES:
        n_null = con.execute(
            f"SELECT count(*) FROM raw.{name} "
            "WHERE _ingested_at IS NULL OR _source_id IS NULL OR _batch_id IS NULL"
        ).fetchone()[0]
        assert n_null == 0, name
    assert con.execute("SELECT DISTINCT _source_id FROM raw.orders").fetchall() == [("synthetic",)]
    # integers typed, money kept as delivered text (cast happens in staging)
    types = {r[0]: r[1] for r in con.execute("DESCRIBE raw.order_items").fetchall()}
    assert types["quantity"] == "BIGINT" and types["unit_price"] == "VARCHAR"
    con.close()


def test_replay_of_same_batch_is_noop(fixture_dir: Path, tmp_path: Path):
    db = tmp_path / "t.duckdb"
    first = ingest(fixture_dir, db)
    second = ingest(fixture_dir, db)
    assert second["status"] == "skipped"
    assert second["raw_row_counts"] == first["raw_row_counts"]
    assert second["batches_loaded"] == 1


def test_changed_batch_is_appended_not_merged(fixture_dir: Path, tmp_path: Path):
    db = tmp_path / "t.duckdb"
    ingest(fixture_dir, db)
    # deliver a second batch whose content differs → new batch_id → appended
    other = tmp_path / "other"
    cfg = load_profile("tiny")
    cfg["seed"] = 99
    write(generate(cfg), other, cfg)
    assert batch_id_for(other) != batch_id_for(fixture_dir)
    result = ingest(other, db)
    assert result["status"] == "ok" and result["batches_loaded"] == 2
    con = duckdb.connect(str(db), read_only=True)
    n_batches = con.execute("SELECT count(DISTINCT _batch_id) FROM raw.customers").fetchone()[0]
    assert n_batches == 2
    con.close()


def test_run_artifact_written(fixture_dir: Path, tmp_path: Path):
    db = tmp_path / "t.duckdb"
    ingest(fixture_dir, db)
    artifact = json.loads((tmp_path / "last_run.json").read_text())
    assert artifact["status"] == "ok"
    assert set(artifact["raw_row_counts"]) == set(TABLES)
    assert artifact["finished_at"].endswith("+00:00")


def test_missing_file_fails_before_touching_db(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        ingest(tmp_path / "nope", tmp_path / "t.duckdb")
    assert not (tmp_path / "t.duckdb").exists()

"""Command-line entrypoints: `ember generate`, `ember ingest`."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ember.config import PROJECT_ROOT, load_profile


def cmd_generate(args: argparse.Namespace) -> int:
    from ember.generate import generate, write

    cfg = load_profile(args.profile)
    if args.seed is not None:
        cfg["seed"] = args.seed
    out = Path(args.out) if args.out else PROJECT_ROOT / "data" / "generated" / args.profile
    ds = generate(cfg)
    manifest = write(ds, out, cfg)
    print(f"[generate] profile={args.profile} seed={cfg['seed']} → {out}")
    for name, n in manifest["row_counts"].items():
        print(f"  {name:12s} {n:>7d}")
    if manifest["injected"]:
        print(f"  injected: {[c['case'] for c in manifest['injected']]}")
    return 0


def cmd_ingest(args: argparse.Namespace) -> int:
    from ember.ingest import ingest

    src = Path(args.src)
    db = Path(args.db) if args.db else PROJECT_ROOT / "data" / "ember.duckdb"
    result = ingest(src_dir=src, db_path=db, source_id=args.source_id)
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "ok" else 1


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="ember")
    sub = p.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("generate", help="generate a synthetic fixture")
    g.add_argument("--profile", default="clean", help="clean | tiny | dirty (config/fixtures.yml)")
    g.add_argument("--seed", type=int, default=None, help="override the profile seed")
    g.add_argument("--out", default=None, help="output directory")
    g.set_defaults(fn=cmd_generate)

    i = sub.add_parser("ingest", help="load a fixture directory into DuckDB raw schema")
    i.add_argument("--src", required=True, help="fixture directory with the five CSVs")
    i.add_argument("--db", default=None, help="DuckDB file (default data/ember.duckdb)")
    i.add_argument("--source-id", default="synthetic", help="logical source identifier")
    i.set_defaults(fn=cmd_ingest)

    b = sub.add_parser("build", help="ingest → dbt build → publish (full pipeline)")
    b.add_argument("--src", required=True, help="fixture directory with the five CSVs")
    b.add_argument("--db", default=None, help="working DuckDB file (default data/ember.duckdb)")
    b.add_argument(
        "--published", default=None, help="published DuckDB file (default data/published.duckdb)"
    )
    b.add_argument("--source-id", default="synthetic")
    b.add_argument("--fresh", action="store_true", help="delete the working DB before building")
    b.set_defaults(fn=cmd_build)

    args = p.parse_args(argv)
    return args.fn(args)


def cmd_build(args: argparse.Namespace) -> int:
    from ember.pipeline import build, reset_workdir

    db = Path(args.db) if args.db else PROJECT_ROOT / "data" / "ember.duckdb"
    if args.fresh:
        reset_workdir(db)
    run = build(
        src_dir=Path(args.src),
        db_path=db,
        published_path=Path(args.published) if args.published else None,
        source_id=args.source_id,
    )
    dbt = run["stages"]["dbt"]
    print(f"[build] status={run['status']} test_status={run.get('test_status')}")
    ing = run["stages"]["ingest"]
    print(f"  ingest : {ing['status']} batch={ing['batch_id'][:12]}")
    print(
        f"  dbt    : models={dbt['models_built']} tests={dbt['tests_run']} "
        f"failed={len(dbt['failures'])} warned={len(dbt['warnings'])}"
    )
    for f in dbt["failures"]:
        print(f"    ✗ {f['test']} ({f['failures']} rows)")
        for rec in run.get("failing_records", {}).get(f["test"], [])[:3]:
            print(f"        {rec}")
    if run["status"] == "ok":
        print(f"  publish: {run['published_path']} {run['stages']['publish']['row_counts']}")
    else:
        print(f"  {run['message']}")
    return 0 if run["status"] == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())

# Runbook

Source: Blueprint v0.1, sections 6 and 7.

How changes are made, how the pipeline is gated in CI, what to do when it breaks,
and which risks and decisions are still open.

## Engineering standards

| Topic | Rule |
|---|---|
| Branches | `feature/<story-id>-short-name` |
| Pull requests contain | Problem, implementation, tests, screenshots if UI changes, and data-contract effects |
| Breaking changes | Treat dataset/metric changes as breaking changes requiring documentation |

## CI pipeline (proposed)

1. Install pinned Python/dbt dependencies.
2. Generate a tiny fixed-seed fixture.
3. Run Python unit tests and ingestion into an isolated DuckDB file.
4. Run `dbt parse` / `build` / `test` on fixture data.
5. Run reconciliation assertions and validate run artifacts.
6. Fail on critical violations; upload sanitized diagnostic artifacts if appropriate.

No secrets should be needed for the MVP. Generated datasets, DuckDB files, cache
directories and potential personal data must be excluded from Git.

## Setup

Prerequisite: [`uv`](https://docs.astral.sh/uv/) (`pip install uv` works). It
installs Python 3.12 and every pinned dependency from `uv.lock`.

```bash
uv sync
uv run ember generate --profile clean                  # data/generated/clean/*.csv + manifest.json
uv run ember build --src data/generated/clean --fresh  # data/ember.duckdb → data/published.duckdb
uv run streamlit run dashboard/app.py
```

| Command | What it does |
|---|---|
| `ember generate --profile {clean,tiny,dirty} [--seed N] [--out DIR]` | Deterministic fixture + manifest |
| `ember ingest --src DIR [--db FILE]` | Load one batch into `raw.*` (content-addressed, idempotent) |
| `ember build --src DIR [--db FILE] [--published FILE] [--fresh]` | ingest → `dbt build` → publish gate; exit 1 on critical failure |
| `cd analytics && DBT_PROFILES_DIR=. uv run dbt build` | Run dbt directly (`EMBER_DB` selects the file) |

Files produced (all git-ignored):

| File | Purpose |
|---|---|
| `data/ember.duckdb` | Working DB: `raw`, `staging`, `intermediate`, `marts`, `dq_failures` |
| `data/published.duckdb` | Read-only snapshot for the dashboard: `marts.*` + `meta.run` |
| `data/last_run.json` | Run artifact: stages, test status, failing tests with sample rows, row counts |
| `analytics/target/` | dbt artifacts (`run_results.json`, compiled SQL) |

Environment variables: `EMBER_DB` (dbt target file), `EMBER_PUBLISHED`,
`EMBER_RUN_ARTIFACT` (dashboard inputs), `EMBER_STALE_AFTER_HOURS` (default 24).

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `build` exits 1, "critical test(s) failed" | Data violates a contract | Read the listed tests and sample rows; full detail in `dq_failures.<test>` inside the working DB; fix the source or the contract *intentionally*, rebuild |
| `ingest` says `skipped` | Same batch content already loaded | Expected; change the data or use `--fresh` to start over |
| `Can't open a connection to same database file with a different configuration` | Another process has the working DB open with a different mode | Close the other connection (e.g. a DuckDB CLI) and rerun |
| Dashboard shows "Nothing published yet" | No successful build | Run `ember build` on a clean fixture |
| Dashboard shows "Stale" | Last successful run older than 24 h | Rebuild, or adjust `EMBER_STALE_AFTER_HOURS` |
| Dashboard shows "Failure · invalid data" | Last build failed; figures are the previous snapshot | Fix the data, rebuild; the badge returns to Healthy |

## Operational runbook

| Event | Detection | Response |
|---|---|---|
| Input schema drifts | Contract test failure | Halt publication, inspect changed fields and update contract intentionally |
| Duplicate replay | Key uniqueness / result comparison | Resolve stable source identity; re-run deterministic load |
| Late status update | Snapshot `updated_at` greater than prior | Full-refresh affected model, rerun reconciliation |
| Quality gate fails | CI and dashboard status | Keep last known-good results or block visualization, inspect failing records |
| Database locked/unavailable | Connection failure | Stop concurrent writer; rerun from idempotent ingestion stage |

## Security / data handling

- Use synthetic customers with no real email/phone/CPF/CNPJ.
- Do not copy proprietary employer data, analytics exports or brand assets into
  this public repository.
- Store no authentication tokens in code.

## Risk register

| Risk / decision | Impact | Mitigation or owner decision |
|---|---|---|
| Financial metrics are ambiguous | Misleading dashboard | Confirm status, refund and date semantics before coding |
| Streaming/incremental complexity grows | MVP never ships | Start deterministic batch and full refresh |
| Synthetic data looks unrealistic | Low credibility of the results | Include edge-case fixtures and explain generator distributions |
| DuckDB concurrent dashboard + pipeline access | File contention | Separate read-only published snapshot or serialize writes; test actual runtime |

The two product decisions to lock for v0.2 (domain, demo) are listed in
[product.md](product.md#open-decisions-to-lock-for-v02).

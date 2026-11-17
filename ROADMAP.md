# Roadmap

Delivery plan derived from the v0.1 blueprint (`docs/blueprint/`). Each step states what it
delivers and how it is verified. Critical path, as defined by the blueprint:

`metric definitions → source contracts → staging → marts → dashboard`

CI and documentation run alongside every sprint, not at the end.

Legend: `[x]` done, `[ ]` open

---

## Step 0: Decisions

The blueprint's recommended options were adopted as the v0.1 baseline. Changing any of the
financial semantics is a breaking change and requires a new ADR.

- [x] Domain: fictional e-commerce
- [x] Demo: local reproducibility
- [x] Financial semantics (`docs/metrics.md`): only `completed` orders are eligible; only
      succeeded refunds on eligible items count; `net_sales = eligible_gross − refunded_amount`
      at 2 dp in BRL/UTC; order-cohort time
- [x] ADR-001 … ADR-005 recorded as *Accepted*

---

## Sprint 1: Foundation

Demo: deterministic rerun and invalid-record detection.

### Step 1: Repository bootstrap
- [x] Pinned environment (`pyproject.toml`, `uv.lock`), `.gitignore`
- [x] `config/generator.yml` (seed, base date, row counts, distributions) and
      `config/fixtures.yml` (clean, tiny, demo, dirty)
- [x] `ember` CLI; `uv sync && uv run pytest` green on a clean checkout

### Step 2 (US-01): Deterministic synthetic generator
- [x] Five CSV sources plus `manifest.json` with per-file hashes
- [x] Order snapshots carry `updated_at`, `source_sequence`, `record_hash`
- [x] Dirty profile injects six violations, each listed in the manifest
- [x] Tests: byte-identical output per seed, key integrity, refund caps, UTC timestamps

### Step 3 (US-02): Raw ingestion
- [x] Append-only `raw.*` with `_ingested_at`, `_source_id`, content-hash `_batch_id`
- [x] Unchanged batch → no-op; changed batch → append
- [x] Run artifact (`last_run.json`)

### Step 4 (US-03): dbt staging and source contracts
- [x] dbt project on DuckDB, no secrets
- [x] Contract tests on sources and staging (unique, not_null, relationships, accepted_values, non_negative, positive)
- [x] Deterministic deduplication: hash collapses replays → max `updated_at` → max `source_sequence` → tie is a failure
- [x] Missing segment → `unknown` (warning)
- [x] Clean fixture passes; dirty fixture fails and stores offending rows in `dq_failures.*`

---

## Sprint 2: Trusted metrics

Demo: a changed order status updates metrics without duplicates.

### Step 5 (US-04): Dimensional marts
- [x] `dim_customer`, `dim_product`, `fct_order_item` (latest status, `is_eligible`), `fct_refund` (`is_recognized`)
- [x] `int_item_refunds` aggregates refunds to item grain before joining (no fan-out)
- [x] `mart_daily_sales` (date × product), `mart_kpi_total`
- [x] Full-refresh materialization (ADR-004)

### Step 6 (US-05): Financial reconciliation
- [x] `assert_net_sales_reconciles` across facts, daily mart and KPI total (±0.01)
- [x] `assert_refunds_within_item_value`, `assert_completed_orders_counted_as_orders`, `assert_aov_null_when_no_orders`

### Step 7 (US-06): Quality gate
- [x] `ember build`: ingest → dbt build → publish only when every critical test passed (ADR-005)
- [x] Separate read-only `published.duckdb`, atomic swap, last known-good preserved on failure
- [x] Failure report names the test and the offending rows; exit code 1

### Step 8: Data-contract scenarios
- [x] Nine scenarios from `docs/data-contracts.md` as end-to-end tests (plus exact-duplicate acceptance)

### Step 9 (US-10): Historical correction (P2)
- [x] Covered by scenarios 2 (late cancellation) and 8 (late refund)

---

## Sprint 3: Product surface

Demo: fresh install, test failure, recovery and KPI drill-down.

### Step 10 (US-07): Dashboard
- [x] Reads only `published.duckdb` and `last_run.json`; data layer filters and sums at declared grain
- [x] Freshness badge, quality chip, five KPI cards, date/category/product filters, daily chart, category breakdown
- [x] States: loading, no data for the current filters, stale, and critical failure with the last known-good snapshot
- [x] Tooltips quote the metric dictionary; pt-BR currency; explicit UTC
- [x] Tests: unfiltered queries equal `mart_kpi_total`; every state renders under `AppTest`
- [x] Visual v2: desktop and mobile layouts, what-if dialog (hypothetical, never alters published KPIs)

### Step 11 (US-08): Continuous integration
- [x] Workflow: lint → unit tests → clean pipeline → artifact validation → diagnostics upload
- [x] Job: nine scenarios
- [x] Job: dirty fixture must fail and publish nothing
- [ ] First run on GitHub

### Step 12 (US-09): Documentation
- [x] README with development map, architecture, lineage, gate output and screenshots
- [x] Product, architecture, data contracts, metrics, design system, runbook, ADRs
- [ ] Narrated demo (failure → recovery → restatement)

---

## Release checklist (from the blueprint)

- [x] Product decisions approved
- [x] Metric dictionary and source contracts implemented as tests
- [x] All P0 stories accepted (US-01 … US-06)
- [x] Full rebuild from a clean checkout
- [x] Intentional failing-fixture test documented and automated
- [x] Empty and error states validated by tests
- [x] README with architecture, trade-offs, limitations and screenshots
- [ ] CI green on GitHub

## Open items

1. Push to GitHub and confirm the CI workflow.
2. Narrated demo of failure → recovery → late-refund restatement.
3. v0.2 candidate: incremental materialization of `fct_order_item`, only after the scenarios
   prove replay safety (ADR-004).
4. Reconcile `docs/design-system.md` with the v2 visual, or record the departure as an ADR.

## Working agreements (from `docs/runbook.md`)

- Branches: `feature/<story-id>-short-name`
- Pull requests state the problem, implementation, tests, screenshots for UI changes, and data-contract effects
- Any dataset or metric change is a breaking change and requires documentation
- Definition of Done: merged, verified locally, automated test added, docs updated, CI green, demo evidence captured

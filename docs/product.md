# Product

Source: Blueprint v0.1, sections 1 and 2.

Why Ember exists, who it serves, what the MVP must prove, and how delivery is sliced.

## 1. Executive brief (PRD)

### Problem

An e-commerce operation has customer, order, item, payment and refund data, but its
teams cannot safely compare revenue and conversion metrics because records may be
duplicated, statuses change after purchase, and KPI definitions differ.

### Product vision

Deliver a small, trustworthy analytics platform in which revenue can be traced from
source records through tested transformation models to a dashboard with documented
definitions and freshness.

### Users and jobs-to-be-done

| Persona | Job | Evidence of success |
|---|---|---|
| Business analyst | Analyze sales by day, product and customer segment | Consistent metrics across dashboard and SQL |
| Finance stakeholder | Reconcile approved sales, cancellations and refunds | Every aggregate can be explained at order level |
| Analytics engineer | Safely rerun and change transformations | Deterministic pipeline, tests, clear lineage and runbook |

### Goals (MVP)

1. Reproducible ingestion of synthetic data into local DuckDB.
2. Tested dbt staging and dimensional marts.
3. Explicit financial metric contracts and reconciliation.
4. Dashboard with date/product filters, freshness status and quality warnings.
5. CI that validates the project from a clean checkout.
6. Documentation of trade-offs, lineage and recovery steps.

### Non-goals (MVP)

- Real-time streaming, Kubernetes, paid cloud infrastructure or login/roles.
- Production-grade personal-data handling or a public multi-tenant service.
- ML recommendations, marketing attribution or mobile app.
- Payment processing and operational order management.

### Success metrics and release gates

| Metric | MVP target / verification |
|---|---|
| Reproducibility | A documented command sequence creates the whole environment from clean checkout |
| Referential integrity | All accepted order items reference a valid order; invalid records are quarantined or stop publication |
| Idempotency | Running ingestion + transformation twice with unchanged inputs yields the same business results |
| Financial reconciliation | Net revenue equals eligible item revenue minus recognized refunds, within currency rounding precision |
| Quality gate | CI fails for critical contract violations and passes with clean fixtures |
| Observability | Last successful run, row counts and test status are inspectable |

No numeric latency or throughput SLO is committed until the sample data volume and
target machine are measured.

## 2. Product scope and delivery

### MVP user stories

| ID | Priority | Story | Acceptance criteria |
|---|---|---|---|
| US-01 | P0 | As an engineer, I want deterministic synthetic source data | A fixed seed produces identical files; includes orders, customers, products, order_items and refunds |
| US-02 | P0 | As an engineer, I want to load raw data safely | Each source has ingestion timestamp, source identifier and batch ID; retries do not silently duplicate business keys |
| US-03 | P0 | As an analyst, I want validated staging models | Types, normalization, deduplication and business keys documented; dbt tests run |
| US-04 | P0 | As an analyst, I want a dimensional mart | Facts and dimensions define grain, joins and slowly changing attributes policy |
| US-05 | P0 | As Finance, I want trustworthy revenue | Gross, cancelled, refunded and net measures have SQL-level reconciliation tests |
| US-06 | P0 | As an engineer, I want failures to be visible | A critical test fails the pipeline; error message points to failing model and records |
| US-07 | P1 | As a stakeholder, I want to explore KPIs | Dashboard supports date/product filters; shows KPIs and daily trend without duplicate aggregation |
| US-08 | P1 | As an engineer, I want CI validation | Pull request workflow installs dependencies and runs lint/build/test on sample data |
| US-09 | P1 | As a new contributor, I want a runbook | Setup, architecture, troubleshooting, data dictionary and ADRs exist |
| US-10 | P2 | As an analyst, I want a historical correction demo | Late cancellation/refund updates results correctly after reprocessing |

### Definition of Ready

Every story has a scenario, input/output example, grain and dependencies, explicit
acceptance tests and known edge cases. Financial story definitions must be signed
off before implementation.

### Definition of Done

Implementation merged, local verification run, automated test added, docs updated,
CI green and demo evidence captured. **A pretty dashboard without validated models
is not done.**

### Suggested 3-sprint plan

Timeboxes are estimates.

| Sprint | Theme | Scope | Demo |
|---|---|---|---|
| 1 (2 to 3 days) | Foundation | Repo bootstrap, generator, raw load, dbt staging, source contracts | Deterministic rerun and invalid-record detection |
| 2 (3 to 4 days) | Trusted metrics | Dimensional models, cancellations/refunds, reconciliation, tests and reprocessing | Changed order status updates metrics without duplicates |
| 3 (2 to 3 days) | Product surface | Streamlit dashboard, freshness, CI, README, ADRs | Fresh install, test failure, recovery and KPI drill-down |

### Dependencies / critical path

Metric definitions → Synthetic source contracts → Staging → Marts → Dashboard.

CI and documentation are continuous tracks, not a final-day task.

## 7. First implementation ticket

**US-01: Deterministic synthetic data generator and fixtures**

- **Task:** Build deterministic synthetic data generator and fixtures.
- **Inputs:** Configurable seed, base date and row counts.
- **Outputs:** `customers`, `products`, `orders`, `order_items`, `refunds`, with a
  documented schema and a fixture containing duplicates, partial refunds, late
  updates and invalid foreign keys.
- **Acceptance:** Same seed/config → byte-identical sorted output; tests assert
  uniqueness in the canonical clean fixture and explicitly verify invalid fixtures;
  timestamps use UTC; no sensitive real data.
- **Out of scope:** dbt models, dashboard, cloud hosting.

## Release checklist

- [ ] Product decisions approved
- [ ] Metric dictionary and source contracts reviewed
- [ ] All P0 stories accepted
- [ ] Full rebuild works from clean checkout
- [ ] CI green; intentional failing-fixture test documented
- [ ] Screens and empty/error states validated
- [ ] README includes demo, architecture, trade-offs and known limitations

## Product decisions

Adopted for v0.1 (the blueprint's recommended options). The product owner may
revisit them; changing the financial semantics is a breaking change.

| # | Decision | Options | Adopted |
|---|---|---|---|
| 1 | Domain | Fictional e-commerce or digital analytics / A/B experimentation | **Fictional e-commerce** |
| 2 | Demo | Local reproducibility or hosted dashboard | **Local reproducibility** |

Financial semantics (status, refund and date rules) are fixed in
[metrics.md](metrics.md) and [ADR-003](adr/ADR-003-order-cohort-time.md).

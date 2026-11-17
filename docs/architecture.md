# Architecture

Source: Blueprint v0.1, section 3.

Python owns generation and raw ingestion, dbt owns transformations and data-quality
contracts, Streamlit only presents what dbt has published.

## Data flow

```
Synthetic source      Python          DuckDB        dbt           dbt core
  CSV/Parquet   ──▶  ingestion  ──▶   raw    ──▶  staging  ──▶   marts   ──▶  Streamlit
                                                     │              │
                                                     └── dbt tests & reconciliation ──▶ CI quality gate
 ◀──── owned by Python ────▶ ◀──────── owned by dbt ────────▶  ◀ presentation ▶  ◀ automation ▶
```

## Technology decisions

| Concern | Decision | Why | Trade-off |
|---|---|---|---|
| Language | Python + SQL | Focus on transformation and testability | Two execution contexts |
| Analytical database | DuckDB file | Local, fast setup, low cost | Not a multi-user serving database |
| Transformations | dbt Core + DuckDB adapter | Model lineage, tests, macros, documentation | Adapter/version compatibility must be pinned |
| Dashboard | Streamlit | Quick interactive evidence | Fewer controls over UI than a dedicated front-end |
| Automation | GitHub Actions | Visible PR quality gate | CI workflow requires isolated setup |
| Packaging | `pyproject.toml` + pinned lock/dependencies | Reproducibility | Dependency maintenance |

## Architecture boundaries

- **Python** owns synthetic generation and raw ingestion.
- **dbt** owns transformations and data-quality contracts.
- **Streamlit** only reads published marts and must not redefine business formulas.

## Repository layout

```
ember/
├── README.md
├── pyproject.toml
├── .github/workflows/ci.yml
├── config/
├── data/                 # synthetic fixtures only; generated files ignored
├── scripts/              # generation and ingestion entrypoints
├── analytics/
│   ├── dbt_project.yml
│   ├── models/
│   │   ├── sources/
│   │   ├── staging/
│   │   ├── intermediate/
│   │   └── marts/
│   ├── macros/
│   ├── seeds/
│   └── tests/
├── dashboard/
├── tests/                # Python unit/integration tests
└── docs/
    ├── product.md
    ├── architecture.md
    ├── data-contracts.md
    ├── metrics.md
    ├── design-system.md
    ├── runbook.md
    └── adr/
```

Implemented layout differs slightly: Python entrypoints live in the `ember/`
package (`ember` CLI) instead of `scripts/`, and `tests/scenarios/` holds the
nine end-to-end cases. Keep the project small: introduce folders only when their
contents exist.

## ADR index

| ADR | Status | Decision |
|---|---|---|
| [ADR-001](adr/ADR-001-duckdb-local.md) | Accepted | DuckDB locally instead of cloud warehouse |
| [ADR-002](adr/ADR-002-dbt-owns-business-logic.md) | Accepted | dbt owns business logic; dashboard is presentation only |
| [ADR-003](adr/ADR-003-order-cohort-time.md) | Accepted | Financial aggregates use order-cohort time, with restatement from late refunds |
| [ADR-004](adr/ADR-004-full-refresh-first.md) | Accepted | Full-refresh first; incremental when verified |
| [ADR-005](adr/ADR-005-critical-checks-block-publication.md) | Accepted | Failed critical checks block publication |

## Publication mechanism (ADR-005 in practice)

`ember build` runs `dbt build` against the working database. Only when it
succeeds are the six published tables copied into a fresh DuckDB file that
atomically replaces `data/published.duckdb` (`meta.run` records when and from
which batch). The dashboard opens that file read-only, so pipeline and dashboard
never contend for the same writer, and a failed build leaves the previous
snapshot, clearly labelled as *not current*, in place.

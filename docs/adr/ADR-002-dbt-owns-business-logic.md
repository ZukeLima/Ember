# ADR-002: dbt owns business logic; dashboard is presentation only

**Status:** Accepted

**Date:** 2026-11-15

## Context

Teams cannot compare metrics when KPI definitions differ between SQL and the
dashboard. A single source of truth for formulas is a core product goal.

## Decision

All business formulas (eligibility, refunds, net sales, order counts, AOV) are
implemented once, in dbt models and tests. Streamlit reads published marts and
renders them. The UI never computes a metric from raw or staging tables and never
redefines a formula; tooltips quote `docs/metrics.md`.

## Consequences

- (+) Dashboard and SQL agree by construction; metrics are testable in CI.
- (−) Any new KPI requires a dbt model change and tests before it can be shown.
- Filtering in the dashboard must operate on marts at their declared grain
  (`mart_daily_sales` = date × product) to avoid re-aggregation errors.

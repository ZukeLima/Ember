# ADR-001: DuckDB locally instead of cloud warehouse

**Status:** Accepted

**Date:** 2026-11-15

## Context

The MVP must be reproducible by another developer from a clean checkout, at zero
infrastructure cost, with no secrets. Data volume is synthetic and small.

## Decision

Use a single local DuckDB file as the analytical database for raw, staging and
marts. No cloud warehouse.

## Consequences

- (+) Local, fast setup, no cost, trivially reproducible in CI.
- (−) Not a multi-user serving database; dashboard and pipeline may contend for
  the file. Mitigation: publish a read-only snapshot for the dashboard or serialize
  writes (see risk register).
- Adapter/version compatibility (dbt-duckdb) must be pinned.

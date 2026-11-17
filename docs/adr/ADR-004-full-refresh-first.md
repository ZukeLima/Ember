# ADR-004: Full-refresh first; incremental when verified

**Status:** Accepted

**Date:** 2026-11-15

## Context

Late status updates, partial refunds and replayed batches make incremental
materialization error-prone. The MVP's data volume does not require it.

## Decision

All dbt models are materialized as full-refresh (`table`/`view`) for the first
release. A model may be switched to `incremental` only after automated tests prove
that late updates, deletions and replay produce the same result as a full rebuild.

## Consequences

- (+) Correctness is easy to reason about; replay is trivially idempotent.
- (−) Build time grows with data; acceptable for synthetic volumes.
- Incremental processing is recorded as an optimization, not a requirement.

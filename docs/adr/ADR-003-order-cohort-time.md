# ADR-003: Financial aggregates use order-cohort time, with restatement from late refunds

**Status:** Accepted (v0.1 default; product owner may revisit)

**Date:** 2026-11-15

## Context

Refunds arrive after the order. Reporting them by refund date (cashflow view) or by
original order date (cohort view) gives different daily figures. The choice is a
material business decision and must be fixed before models are written.

## Decision

Default reporting is **order-cohort**: a refund adjusts the net sales of the
original order's date. Historical days may therefore be restated when late refunds
arrive. A refund-cashflow view by refund date is out of scope for the MVP.

## Consequences

- (+) Net sales per order date is always reconcilable to the orders of that date.
- (−) Past numbers change; the dashboard must say so explicitly ("order-cohort
  view", restatement note) and the pipeline must support full reprocessing.
- Test scenario 8 (late refund corrects original date) enforces this.

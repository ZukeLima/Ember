# ADR-005: Failed critical checks block publication

**Status:** Accepted

**Date:** 2026-11-15

## Context

Showing unvalidated numbers as facts is the primary failure mode the product
exists to prevent.

## Decision

Data-quality tests are classified as **critical**, **warning** or **accepted**
(see `docs/data-contracts.md`). Any critical failure (duplicate keys after dedupe,
missing required foreign keys, negative amounts, reconciliation mismatch) fails
the build and prevents marts from being published. Warnings are reported and do not
block.

## Consequences

- (+) The dashboard can only ever show figures that passed every critical check.
- (−) A single bad record can block the whole publication; the error message must
  point to the failing model and records so recovery is fast.
- The dashboard shows a "critical failure" state (KPIs blocked, or last
  known-good snapshot clearly labeled with its run timestamp).
- CI includes a documented test with a deliberately invalid fixture that is
  expected to fail.

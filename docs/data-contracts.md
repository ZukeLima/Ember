# Data contracts

Source: Blueprint v0.1, section 4.

Source contracts, dimensional models and the quality rules that decide whether
anything gets published. Metric definitions live in [metrics.md](metrics.md).

> **Status:** implemented as dbt contracts (`analytics/models/**/*.yml`,
> `analytics/tests/`) and verified end-to-end by `tests/scenarios/`.

## Source contracts

### Synthetic source tables

| Entity | Grain / primary key | Required fields | Important edge case |
|---|---|---|---|
| `customers` | 1 row/customer; `customer_id` | customer_id, signup_at, segment | Missing segment allowed and labeled `unknown` |
| `products` | 1 row/product; `product_id` | product_id, category, list_price | Product description changes |
| `orders` | latest snapshot/order; `order_id` | order_id, customer_id, created_at, status, updated_at | Status changes after order creation |
| `order_items` | 1 row/item; `order_item_id` | order_item_id, order_id, product_id, quantity, unit_price | Multiple items per order; no double-counting |
| `refunds` | 1 row/refund transaction; `refund_id` | refund_id, order_item_id, refunded_at, amount, status | Partial refunds and repeated delivery |

### Contract assumptions

- Monetary fields are decimal with two places in a single currency (**BRL**).
- Timestamps are stored in **UTC**.
- All business IDs are strings.
- `quantity > 0`; unit price and refund amount are nonnegative.
- Refunds are attached to **items** to support correct allocation.
- Order snapshots carry `updated_at`, `source_sequence` and a raw-record hash
  (required by the deduplication rule below). The synthetic generator must emit them.

> **Modeling gap to settle before code.** The MVP does not model payment
> authorization, taxes, shipping, discounts or chargebacks. Therefore its
> `gross_revenue` is *eligible merchandise sales* rather than accounting revenue
> recognized under a formal standard.

## Dimensional model

### Proposed marts

| Model | Grain | Measures / attributes |
|---|---|---|
| `dim_customer` | customer_id | signup_date, segment |
| `dim_product` | product_id | category, product metadata |
| `fct_order_item` | order_item_id | order_id, customer_id, product_id, order_date, quantity, item_amount, order_status |
| `fct_refund` | refund_id | order_item_id, refund_date, refund_amount, refund_status |
| `mart_daily_sales` | date × product_id | eligible_gross, refunded_amount, net_sales, orders_count |

> **Join warning.** Never join order-item facts directly to multiple refunds and
> then sum item amounts; that fanout inflates gross sales. First aggregate refunds
> to item grain, or calculate measures in separate aggregates and join at their
> declared common grain.

## Data-quality policy

### Severity and outcome

| Severity | Conditions | Outcome |
|---|---|---|
| **Critical** | Duplicate primary keys after dedupe, missing required foreign keys, negative amounts, financial reconciliation mismatch | Fail build and do not publish marts |
| **Warning** | Missing optional segment, delayed batch, unexpected but parseable status | Report warning; map optional values to `unknown` |
| **Accepted** | Out-of-order deliveries with newer `updated_at`, valid partial refunds | Deterministic upsert/rebuild |

### Deterministic deduplication

For source order snapshots:

1. Collapse exact replays: rows with the same `record_hash` are one record
   (`int_order_snapshots`).
2. Per `order_id`, pick max `updated_at`, then max `source_sequence` (`stg_orders`).
3. If two rows still share (`order_id`, `updated_at`, `source_sequence`) but have
   different content (different hash), the load is **rejected** by
   `assert_no_conflicting_order_snapshots` rather than silently choosing a row.

Entity tables (`customers`, `products`, `order_items`, `refunds`) keep the rows
from the most recent batch that delivered each key, then collapse exact
duplicates; a key delivered twice in one batch with different content fails the
`unique` contract.

### Incremental implementation choice

First implement full-refresh materialization and verify correctness. Only switch a
model to incremental after tests prove late updates, deletions and replay are
handled. Incremental processing is an optimization, not a requirement for the first
release.

## Test scenarios

Nine cases the models must pass; each is an automated end-to-end test in
`tests/scenarios/test_scenarios.py` (ingest → dbt build → publish on a throw-away DB):

| # | Scenario | Expected |
|---|---|---|
| 1 | Duplicated input batch | Same final counts/sums after replay |
| 2 | Order transitions from `completed` to `cancelled` | Its contribution disappears on reprocess |
| 3 | One order with three items | Order count stays one |
| 4 | One item with two partial refunds | Gross counted once, both valid refunds counted |
| 5 | Refund greater than item value | Quality gate fails |
| 6 | Missing customer reference | Quality gate fails |
| 7 | Zero completed orders | AOV is NULL, not division error |
| 8 | Late refund | Original order date's net sales is corrected |
| 9 | Two conflicting snapshots at identical ordering keys | Load rejected explicitly |

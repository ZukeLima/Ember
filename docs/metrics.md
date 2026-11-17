# Metrics

Source: Blueprint v0.1, section 4.

The metric dictionary. The dashboard quotes these definitions verbatim in tooltips
and never redefines a formula.

> **Status:** adopted as the v0.1 default and implemented in `analytics/models/marts/`
> (`fct_order_item.is_eligible`, `fct_refund.is_recognized`, `mart_daily_sales`,
> `mart_kpi_total`). Changing any definition is a breaking change.

## Metric dictionary

| Metric | Definition | Exclusions / notes |
|---|---|---|
| `eligible_gross` | Sum(`quantity * unit_price`) for order items whose **latest** order status is `completed` | `pending` / `cancelled` excluded |
| `refunded_amount` | Sum of successful refunds linked to eligible completed order items | Pending/failed refunds excluded; cap check against eligible item value |
| `net_sales` | `eligible_gross - refunded_amount` | Financial precision fixed at 2 decimal places |
| `completed_orders` | Count distinct completed `order_id` | Never count order items as orders |
| `average_order_value` | `net_sales / completed_orders` | NULL if denominator zero |

## Time semantics: a material business decision

The default dashboard is **order-cohort reporting**: refunds adjust the original
order's date, so historical net sales may change as late refunds arrive.

A refund-cashflow view by refund date is explicitly **out of scope** for MVP.

Recorded as [ADR-003](adr/ADR-003-order-cohort-time.md).

## Presentation rules

- Currency: BRL, formatted pt-BR (`R$ 1.234,56`), tabular numerals, right-aligned.
- Timezone: UTC, labeled explicitly on every date axis and timestamp.
- Order counts are **not** summed across categories, because one order can contain
  items from several of them.
- Empty results show explanatory states, never `R$ 0,00` disguised as sales.

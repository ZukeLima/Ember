-- Critical (docs/metrics.md): completed_orders counts distinct order_id, never
-- order items. Compare mart_kpi_total against the order table directly.
with expected as (
    select count(distinct o.order_id) as n
    from {{ ref('stg_orders') }} as o
    where o.status = 'completed'
      and exists (select 1 from {{ ref('stg_order_items') }} as i where i.order_id = o.order_id)
),

item_rows as (
    select count(*) as n from {{ ref('fct_order_item') }} where is_eligible
)

select k.completed_orders, e.n as expected_orders, i.n as eligible_item_rows
from {{ ref('mart_kpi_total') }} as k, expected as e, item_rows as i
where k.completed_orders <> e.n

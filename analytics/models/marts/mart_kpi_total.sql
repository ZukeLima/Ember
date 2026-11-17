{# Single row: the five headline metrics over ALL published data, computed
   straight from the metric dictionary (docs/metrics.md). Used by reconciliation
   tests and by the dashboard's unfiltered state. #}

with items as (
    select order_id, order_item_id, item_amount
    from {{ ref('fct_order_item') }}
    where is_eligible
),

totals as (
    select
        cast(coalesce(sum(i.item_amount), 0) as decimal(12, 2)) as eligible_gross,
        cast(coalesce(sum(r.recognized_refund_amount), 0) as decimal(12, 2)) as refunded_amount,
        count(distinct i.order_id) as completed_orders
    from items as i
    left join {{ ref('int_item_refunds') }} as r on r.order_item_id = i.order_item_id
)

select
    eligible_gross,
    refunded_amount,
    cast(eligible_gross - refunded_amount as decimal(12, 2)) as net_sales,
    completed_orders,
    -- NULL, never a division error, when there are no completed orders
    cast((eligible_gross - refunded_amount) / nullif(completed_orders, 0) as decimal(12, 2))
        as average_order_value
from totals

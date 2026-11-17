{# Grain: one row per order item, carrying the order's LATEST status.
   `is_eligible` encodes the metric dictionary: only `completed` orders count
   toward eligible_gross (docs/metrics.md). #}

select
    i.order_item_id,
    i.order_id,
    o.customer_id,
    i.product_id,
    cast(o.created_at as date) as order_date,      -- UTC; order-cohort key (ADR-003)
    o.created_at as order_created_at,
    o.updated_at as order_updated_at,
    i.quantity,
    i.unit_price,
    i.item_amount,
    o.status as order_status,
    o.status = 'completed' as is_eligible
from {{ ref('stg_order_items') }} as i
inner join {{ ref('stg_orders') }} as o on o.order_id = i.order_id

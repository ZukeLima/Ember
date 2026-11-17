{# Grain: one row per refund transaction. `is_recognized` encodes the metric
   dictionary: only succeeded refunds on eligible (completed) items reduce
   net sales. Refund rows carry the ORIGINAL order_date (order-cohort, ADR-003). #}

select
    r.refund_id,
    r.order_item_id,
    i.order_id,
    i.product_id,
    i.order_date,
    cast(r.refunded_at as date) as refund_date,
    r.refunded_at,
    r.refund_amount,
    r.refund_status,
    (r.refund_status = 'succeeded' and i.is_eligible) as is_recognized
from {{ ref('stg_refunds') }} as r
inner join {{ ref('fct_order_item') }} as i on i.order_item_id = r.order_item_id

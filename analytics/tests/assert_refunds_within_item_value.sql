-- Critical. Successful refunds on an item must not exceed the item's value
-- (docs/metrics.md: cap check; scenario 5).
with refunded as (
    select order_item_id, sum(refund_amount) as refunded_amount
    from {{ ref('stg_refunds') }}
    where refund_status = 'succeeded'
    group by 1
)
select
    i.order_item_id,
    i.item_amount,
    r.refunded_amount
from {{ ref('stg_order_items') }} as i
inner join refunded as r on r.order_item_id = i.order_item_id
where r.refunded_amount > i.item_amount

{# Grain: order_date × product_id (order-cohort view, ADR-003).
   orders_count is distinct within the row; it is NOT additive across products
   because one order can contain several products. #}

with items as (
    select
        order_date,
        product_id,
        order_id,
        order_item_id,
        item_amount
    from {{ ref('fct_order_item') }}
    where is_eligible
),

joined as (
    select
        i.order_date,
        i.product_id,
        i.order_id,
        i.item_amount,
        coalesce(r.recognized_refund_amount, 0) as refunded_amount
    from items as i
    left join {{ ref('int_item_refunds') }} as r on r.order_item_id = i.order_item_id
)

select
    order_date,
    product_id,
    cast(sum(item_amount) as decimal(12, 2)) as eligible_gross,
    cast(sum(refunded_amount) as decimal(12, 2)) as refunded_amount,
    cast(sum(item_amount) - sum(refunded_amount) as decimal(12, 2)) as net_sales,
    count(distinct order_id) as orders_count
from joined
group by 1, 2

{# Refunds aggregated to ITEM grain before any join to items, so that an item
   with two partial refunds never fans out (docs/data-contracts.md join warning). #}

select
    order_item_id,
    cast(sum(refund_amount) as decimal(12, 2)) as recognized_refund_amount,
    count(*) as recognized_refund_count
from {{ ref('fct_refund') }}
where is_recognized
group by 1

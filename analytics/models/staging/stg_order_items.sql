with latest as (
    {{ latest_batch_rows(source('raw', 'order_items'), 'order_item_id',
                         ['order_item_id', 'order_id', 'product_id', 'quantity', 'unit_price']) }}
)

select
    order_item_id,
    order_id,
    product_id,
    quantity,
    {{ to_money('unit_price') }} as unit_price,
    cast(quantity * {{ to_money('unit_price') }} as decimal(12, 2)) as item_amount,
    _batch_id
from latest

with latest as (
    {{ latest_batch_rows(source('raw', 'products'), 'product_id',
                         ['product_id', 'category', 'name', 'list_price']) }}
)

select
    product_id,
    category,
    name as product_name,
    {{ to_money('list_price') }} as list_price,
    _batch_id
from latest

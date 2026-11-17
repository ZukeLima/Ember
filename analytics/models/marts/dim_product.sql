select
    product_id,
    category,
    product_name,
    list_price
from {{ ref('stg_products') }}

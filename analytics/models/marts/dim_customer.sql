select
    customer_id,
    cast(signup_at as date) as signup_date,
    signup_at,
    segment
from {{ ref('stg_customers') }}

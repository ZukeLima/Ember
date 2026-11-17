with latest as (
    {{ latest_batch_rows(source('raw', 'customers'), 'customer_id',
                         ['customer_id', 'signup_at', 'segment']) }}
)

select
    customer_id,
    {{ to_utc_ts('signup_at') }} as signup_at,
    -- missing optional segment is a warning, mapped to 'unknown' (policy)
    coalesce(nullif(trim(segment), ''), 'unknown') as segment,
    _batch_id
from latest

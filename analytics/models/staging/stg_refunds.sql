with latest as (
    {{ latest_batch_rows(source('raw', 'refunds'), 'refund_id',
                         ['refund_id', 'order_item_id', 'refunded_at', 'amount', 'status']) }}
)

select
    refund_id,
    order_item_id,
    {{ to_utc_ts('refunded_at') }} as refunded_at,
    {{ to_money('amount') }} as refund_amount,
    lower(trim(status)) as refund_status,
    _batch_id
from latest

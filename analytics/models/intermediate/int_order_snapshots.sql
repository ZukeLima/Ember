{# All distinct order snapshots ever delivered, typed. Exact replays (same
   record_hash) collapse to one row here. Conflicting snapshots (same
   (order_id, updated_at, source_sequence) but different record_hash) survive
   and are caught by the singular test assert_no_conflicting_order_snapshots. #}

with snapshots as (
    select distinct
        order_id,
        customer_id,
        created_at,
        status,
        updated_at,
        source_sequence,
        record_hash
    from {{ source('raw', 'orders') }}
)

select
    order_id,
    customer_id,
    {{ to_utc_ts('created_at') }} as created_at,
    lower(trim(status)) as status,
    {{ to_utc_ts('updated_at') }} as updated_at,
    source_sequence,
    record_hash
from snapshots

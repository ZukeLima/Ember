{# Latest snapshot per order (docs/data-contracts.md "Deterministic deduplication"):
   max updated_at, then max source_sequence. Ties beyond that are conflicts and
   are rejected upstream by assert_no_conflicting_order_snapshots. #}

select
    order_id,
    customer_id,
    created_at,
    status,
    updated_at,
    source_sequence,
    record_hash
from {{ ref('int_order_snapshots') }}
qualify row_number() over (
    partition by order_id
    order by updated_at desc, source_sequence desc
) = 1

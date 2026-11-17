-- Critical. Two snapshots of the same order with identical ordering keys
-- (updated_at, source_sequence) but different content: the dedupe rule cannot
-- choose, so the load is rejected (docs/data-contracts.md, scenario 9).
select
    order_id,
    updated_at,
    source_sequence,
    count(distinct record_hash) as conflicting_versions
from {{ ref('int_order_snapshots') }}
group by 1, 2, 3
having count(distinct record_hash) > 1

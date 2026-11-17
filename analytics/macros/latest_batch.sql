{# For entity tables (1 row per key), keep only rows from the most recent batch
   that delivered that key, then collapse exact duplicates. A key delivered twice
   *within* one batch with different content survives as two rows and fails the
   `unique` contract test; that is intentional (critical, do not guess). #}
{% macro latest_batch_rows(source_relation, key, columns) -%}
    with ranked as (
        select
            {{ columns | join(', ') }},
            _batch_id,
            dense_rank() over (
                partition by {{ key }}
                order by _ingested_at desc, _batch_id desc
            ) as batch_rank
        from {{ source_relation }}
    )
    select distinct {{ columns | join(', ') }}, _batch_id
    from ranked
    where batch_rank = 1
{%- endmacro %}

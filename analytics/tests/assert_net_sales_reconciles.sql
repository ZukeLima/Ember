-- Critical (US-05). net_sales published in mart_daily_sales must equal
-- eligible item revenue minus recognized refunds, computed independently from
-- the facts, within currency rounding (0.01).
with from_facts as (
    select
        sum(case when is_eligible then item_amount else 0 end) as eligible_gross,
        (select coalesce(sum(refund_amount), 0) from {{ ref('fct_refund') }} where is_recognized)
            as refunded_amount
    from {{ ref('fct_order_item') }}
),

from_mart as (
    select
        coalesce(sum(eligible_gross), 0) as eligible_gross,
        coalesce(sum(refunded_amount), 0) as refunded_amount,
        coalesce(sum(net_sales), 0) as net_sales
    from {{ ref('mart_daily_sales') }}
),

from_kpi as (
    select eligible_gross, refunded_amount, net_sales from {{ ref('mart_kpi_total') }}
)

select
    f.eligible_gross as facts_gross,
    m.eligible_gross as mart_gross,
    k.eligible_gross as kpi_gross,
    f.refunded_amount as facts_refunds,
    m.refunded_amount as mart_refunds,
    k.refunded_amount as kpi_refunds,
    m.net_sales as mart_net,
    k.net_sales as kpi_net
from from_facts as f, from_mart as m, from_kpi as k
where abs(f.eligible_gross - m.eligible_gross) > 0.01
   or abs(f.refunded_amount - m.refunded_amount) > 0.01
   or abs(m.net_sales - (f.eligible_gross - f.refunded_amount)) > 0.01
   or abs(k.eligible_gross - f.eligible_gross) > 0.01
   or abs(k.refunded_amount - f.refunded_amount) > 0.01
   or abs(k.net_sales - m.net_sales) > 0.01

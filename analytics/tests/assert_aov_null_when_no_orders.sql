-- Critical (scenario 7): average_order_value must be NULL when there are no
-- completed orders and equal net_sales / completed_orders otherwise.
select *
from {{ ref('mart_kpi_total') }}
where (completed_orders = 0 and average_order_value is not null)
   or (completed_orders > 0
       and abs(average_order_value - net_sales / completed_orders) > 0.01)

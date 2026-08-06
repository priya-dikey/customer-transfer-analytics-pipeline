with staging_total as (
    select sum(send_amount_gbp) as v from {{ ref('stg_transfers') }}
),
mart_total as (
    select sum(monetary_gbp) as v from {{ ref('dim_customer_rfm') }}
)
select s.v as staging_v, m.v as mart_v
from staging_total s
cross join mart_total m
where abs(s.v - m.v) > 0.01

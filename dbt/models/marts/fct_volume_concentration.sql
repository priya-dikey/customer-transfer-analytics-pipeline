with customers as (
    select
        customer_id,
        monetary_gbp,
        percent_rank() over (order by monetary_gbp desc) as pct_rank
    from {{ ref('int_customer_metrics') }}
),

totals as (
    select
        count(*)            as n_customers,
        sum(monetary_gbp)   as total_volume_gbp
    from customers
)

select
    t.n_customers,
    round(t.total_volume_gbp, 2)                                as total_volume_gbp,
    round(100.0 * sum(case when c.pct_rank < 0.01 then c.monetary_gbp else 0 end)
          / t.total_volume_gbp, 1)                              as top_1pct_volume_share,
    round(100.0 * sum(case when c.pct_rank < 0.05 then c.monetary_gbp else 0 end)
          / t.total_volume_gbp, 1)                              as top_5pct_volume_share,
    round(100.0 * sum(case when c.pct_rank < 0.10 then c.monetary_gbp else 0 end)
          / t.total_volume_gbp, 1)                              as top_10pct_volume_share
from customers c
cross join totals t
group by t.n_customers, t.total_volume_gbp

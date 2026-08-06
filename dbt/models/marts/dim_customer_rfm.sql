with scored as (
    select
        *,
        ntile(5)  over (order by recency_days desc) as r_score,
        ntile(5)  over (order by frequency asc)     as f_score,
        ntile(5)  over (order by monetary_gbp asc)  as m_score,
        ntile(10) over (order by monetary_gbp desc) as vol_decile
    from {{ ref('int_customer_metrics') }}
)
select
    customer_id, first_transfer_date, last_transfer_date, recency_days,
    frequency, monetary_gbp, avg_send_gbp,
    dest_currency as top_currency,
    r_score, f_score, m_score,
    (vol_decile = 1) as is_high_value_top_decile,
    case
        when r_score >= 4 and f_score >= 4 and m_score >= 4 then 'Champions'
        when m_score >= 4 or f_score >= 4                   then 'Loyal'
        when r_score <= 2 and (f_score >= 3 or m_score >= 3) then 'At Risk'
        when r_score <= 2                                   then 'Hibernating'
        else 'Regular'
    end as rfm_segment
from scored
select
    dayofmonth(transfer_date)      as day_of_month,
    count(*)                       as n_transfers,
    round(sum(send_amount_gbp), 2) as total_volume_gbp,
    round(avg(send_amount_gbp), 2) as avg_transfer_gbp
from {{ ref('stg_transfers') }}
group by 1
order by 1
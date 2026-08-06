select
    corridor,
    source_country,
    dest_country,
    dest_currency,
    count(*)                       as n_transfers,
    count(distinct customer_id)    as n_senders,
    round(sum(send_amount_gbp), 2) as total_volume_gbp
from {{ ref('stg_transfers') }}
group by 1, 2, 3, 4
order by total_volume_gbp desc
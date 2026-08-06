select
    isodow(transfer_date)          as iso_dow,     
    isodow(transfer_date) || '-' || dayname(transfer_date) as day_name,    
    isodow(transfer_date) in (6,7) as is_weekend,
    count(*)                       as n_transfers,
    round(sum(send_amount_gbp), 2) as total_volume_gbp
from {{ ref('stg_transfers') }}
group by 1, 2, 3
order by 1
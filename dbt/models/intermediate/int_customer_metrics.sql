with per_customer as (
    select
        customer_id,
        min(transfer_date)          as first_transfer_date,
        max(transfer_date)          as last_transfer_date,
        count(distinct transfer_id) as frequency,
        sum(send_amount_gbp)        as monetary_gbp,
        avg(send_amount_gbp)        as avg_send_gbp,
        max(dest_currency)          as dest_currency  -- one corridor per sender, so this is just their currency
    from {{ ref('stg_transfers') }}
    group by customer_id
)
select
    *,
    (select max(transfer_date) from {{ ref('stg_transfers') }}) - last_transfer_date as recency_days
from per_customer
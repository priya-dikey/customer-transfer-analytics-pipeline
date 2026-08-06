select
    cast(transfer_id      as varchar) as transfer_id,
    cast(customer_id      as varchar) as customer_id,
    cast(transfer_ts      as date)    as transfer_date,
    cast(source_country   as varchar) as source_country,
    cast(dest_country     as varchar) as dest_country,
    cast(corridor         as varchar) as corridor,
    cast(dest_currency    as varchar) as dest_currency,
    cast(send_amount_gbp  as double)  as send_amount_gbp,
    cast(fee_gbp          as double)  as fee_gbp
from {{ source('raw', 'fct_transfers') }}
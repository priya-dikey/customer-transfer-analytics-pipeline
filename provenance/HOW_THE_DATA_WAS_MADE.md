# How the data was made

The files in `../output/` (`fct_transfers.csv`, `dim_corridor.csv`, `dim_fx.csv`,
`transfers.duckdb`) are already generated. This folder holds the scripts that
produced them and documents the method. Running anything here is only needed
to regenerate the data from scratch.

## Real vs synthetic

- **Real:** customer identity, repeat behaviour, timing, monetary distribution
  — from the Online Retail dataset (UK gift retailer, ~540k line items).
- **Synthetic:** corridor (source → destination), FX mid-rate, spread, fee.

## Augmentation logic (`augment_transfers.py`)

1. **Clean** — drop cancellations, rows with no customer, non-positive amounts.
2. **Regrain** — roll line items up to one invoice = one transfer; keep the
   real invoice total as `send_amount_gbp`.
3. **Corridor** — source country is the real `Country`. Destination is
   assigned per customer (a sender always remits to the same country), drawn
   from weighted remittance corridors, independently of amount.
4. **FX** — each destination currency has a static mid-rate; each corridor a
   spread. `customer_rate = mid_rate × (1 − spread)`,
   `recipient_amount = send_amount_gbp × customer_rate`.
5. **Fee** — `fee = max(min_fee, fee_pct × send_amount)`, per-corridor values
   derived deterministically from the corridor name.

## Validation result

- 18,532 transfers, 4,338 senders, 152 corridors.
- 34.4% of senders have exactly one transfer.
- Top 10% of senders drive 61.3% of total volume.

## Regenerating the data

```bash
pip install -r provenance/requirements-augment.txt
python provenance/augment_transfers.py --input online_retail.csv --outdir output --duckdb
```

Base data: Online Retail (UCI / mirrors). Non-commercial use only, per the
dataset donor's terms.


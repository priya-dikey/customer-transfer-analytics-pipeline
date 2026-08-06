# Customer Segmentation and Value Concentration Analysis

An end to end analytics pipeline that segments customers and measures how
concentrated value is among the highest value senders. Built on a
transfer themed dataset with dbt, DuckDB, and Superset.

**Headline:** the top 10% of senders account for 61.4% of total volume.

## Data

Behavioural data is real: customer identities, repeat behaviour, transaction
timing, and monetary values come from a UK retail dataset (~540K transactions).
A synthetic layer adds a corridor, destination currency, FX spread, and fee to
each transaction to model a cross border money transfer product.

- Real (basis for all insights): segmentation, monetary distribution, value concentration.
- Synthetic (mechanics only): corridor, currency, FX, fee. Assigned independently
  of behaviour, so corridor and currency patterns are artifacts of the assignment,
  not findings.

## Stack

- dbt: layered modelling (staging to intermediate to marts) with tests
- DuckDB: local analytical warehouse
- Superset: dashboard

## Pipeline

```
raw tables (DuckDB)
  staging       stg_transfers             clean and type, one row per transfer
  intermediate  int_customer_metrics      aggregate to one row per customer (RFM)
  marts         dim_customer_rfm          RFM scores, segment, high value flag
                fct_volume_concentration  top 1/5/10% volume share
                fct_corridor_summary      corridor and currency demand
                fct_seasonality_*         time patterns
```

## Results

- Value concentration: top 1% of senders drive ~32% of volume, top 10% drive 61.4%.
- Segments: five RFM segments (Champions, Loyal, Regular, At Risk, Hibernating).
  Groups are fairly balanced by headcount but Champions dominate by volume. The
  count versus value gap is the concentration story.

## Validation

Validation runs as dbt tests:

- Source: not null and unique on raw keys.
- Model: unique and not null customer grain, accepted values on 1 to 5 RFM scores,
  accepted range on concentration shares.
- Reconciliation: total volume in the customer mart equals total volume in
  staging (no rows lost or double counted in aggregation).

## Dashboard

Interactive Superset dashboard (screenshots in docs/):

- Top 10% volume share: the 61.4% headline metric.
- Customers by Volume and Customer segments: count versus value contrast across segments.
- High Value Senders: top decile drill down (customer 12346 is a single transfer
  GBP 77K outlier, flagged as a data quality check).

## Extended marts (capability, not findings)

Corridor, currency, and time based marts are demonstrations, not insights on this data:

- Corridor and currency demand reflects the synthetic assignment. On real transfer
  data the same marts would surface true demand and inform capital allocation
  decisions.
- Seasonality checks returned no genuine signal: the month end decline is a
  short month calendar artifact and the weekday view is skewed by the source
  retailer not trading Saturdays. On real transfer data the same models would
  detect payday and workweek patterns.

## Run

Data is pre generated; no Python step is required.

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cd dbt && dbt deps && DBT_PROFILES_DIR=$(pwd) dbt build
```

Connect Superset to output/transfers.duckdb to view or rebuild the charts.

## Limitations

- Synthetic corridor, FX, and currency layer: those dimensions are mechanics only.
- Static illustrative FX rates, not a live feed.
- ~34% of senders are single transaction, so low frequency RFM quintiles are
  approximate (NTILE splits ties across buckets).

<img width="682" height="463" alt="Screenshot 2026-08-06 at 10 25 07 AM" src="https://github.com/user-attachments/assets/afec2b07-3d74-4070-ba3d-639d9b7d3cd1" />
<img width="1390" height="816" alt="Screenshot 2026-08-06 at 10 24 52 AM (2)" src="https://github.com/user-attachments/assets/6a725aa9-4169-49f9-865d-a45aabc7f94c" />
<img width="1393" height="448" alt="Screenshot 2026-08-06 at 10 25 01 AM" src="https://github.com/user-attachments/assets/6cc47539-5973-4f70-853b-8a1d577b08cc" />

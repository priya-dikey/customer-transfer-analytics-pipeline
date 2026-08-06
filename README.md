# Customer Analytics & Value Segmentation

Identifying the small cohort of senders that drives an outsized share of transfer
volume, and profiling what distinguishes them — themed on a cross-border
money-transfer product.

---

## Data preparation

The dataset in `output/` is pre-generated. The project runs on dbt against
DuckDB.

- `output/transfers.duckdb` — 
- `output/fct_transfers.csv` — one row per transfer (18,532). Real amounts,
  synthetic corridor/FX/fee.
- `output/dim_corridor.csv` — 152 corridors with fee %, floor, spread.
- `output/dim_fx.csv` — 15 currencies with GBP mid-rate.

How the data was made is documented in `provenance/HOW_THE_DATA_WAS_MADE.md`.

## What's real vs synthetic

- **Real** — customer identity, repeat behaviour, timing, monetary distribution.
- **Synthetic** — corridor, FX rate, spread, fee. Corridor is assigned
  independently of amount.

---

## Project structure

```
high_value_segmentation/
├── README.md                 
├── requirements.txt          
├── output/                   
│   ├── transfers.duckdb
│   ├── fct_transfers.csv
│   ├── dim_corridor.csv
│   └── dim_fx.csv
├── dbt/                      
│   ├── dbt_project.yml
│   ├── profiles.yml          
│   ├── packages.yml
│   ├── models/
│   │   ├── staging/          
│   │   ├── intermediate/     
│   │   └── marts/            
│   └── tests/               
└── provenance/               
    ├── HOW_THE_DATA_WAS_MADE.md
    ├── augment_transfers.py
    ├── load_to_warehouse.py
    └── requirements-augment.txt
```

## dbt model DAG

```
source: fct_transfers, dim_corridor, dim_fx   (in output/transfers.duckdb)
   └─ stg_transfers            
        └─ int_customer_metrics   
             ├─ dim_customer_rfm         
             └─ fct_volume_concentration  
```

---

## Run

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# run the pipeline
cd dbt
dbt deps                            
DBT_PROFILES_DIR=$(pwd) dbt build  
```


## Validation / tests

- Source tests (`_sources.yml`): 
- Mart tests (`_marts.yml`): 
- Reconciliation (`tests/assert_monetary_reconciles.sql`)

## Limitations

- Synthetic corridor/FX/fee -> corridor-level amount analysis is mechanics.
- Static illustrative FX rates, not a live feed.
- 34.4% of senders are one-timers, so low-frequency RFM quintiles are lumpy.
- NTILE splits tied values across buckets, so score boundaries are approximate
  where values cluster.

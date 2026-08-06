"""
augment_transfers.py
====================
Reshapes the Online Retail II dataset (UCI) into a transfer-style fact table
and adds a synthetic cross-border layer: source->destination corridor, FX
mid-rate + spread, and a fee.

Real: customer identity, repeat behaviour, timing, monetary distribution.
Synthetic: corridor, FX mid-rate, spread, fee.

Corridors are assigned per customer, independently of send amount, so
corridor does not drive transfer size in this dataset.

INPUT
-----
Online Retail II, from https://archive.ics.uci.edu/dataset/502/online+retail+ii
.xlsx (two sheets) or .csv. Expected columns (Online Retail I names also
accepted):
    Invoice, StockCode, Description, Quantity, InvoiceDate, Price,
    Customer ID, Country

OUTPUT (written to --outdir, default ./output)
    fct_transfers.csv   one row per transfer, real + synthetic columns
    dim_corridor.csv    corridor reference: currency, fee %, min fee, spread
    dim_fx.csv          currency -> GBP mid-rate (as-of label)
    transfers.duckdb    (optional, --duckdb) same three tables, loaded

USAGE
    python augment_transfers.py --input online_retail_II.xlsx
    python augment_transfers.py --input online_retail_II.csv --duckdb
"""

from __future__ import annotations
import argparse
import hashlib
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Synthetic parameters
# ---------------------------------------------------------------------------
SEED = 42

# Online Retail II is GBP-priced; every send_amount is treated as GBP.
BASE_CURRENCY = "GBP"

# Static illustrative mid-market rates (destination currency per 1 GBP), not live.
FX_AS_OF = "2024-01-01 (illustrative, static)"
CURRENCY_RATES_PER_GBP = {
    "GBP": 1.00, "EUR": 1.17, "USD": 1.27, "INR": 105.0, "NGN": 1150.0,
    "PKR": 355.0, "PLN": 5.05, "PHP": 71.0, "BDT": 139.0, "KES": 200.0,
    "RON": 5.80, "AUD": 1.93, "ZAR": 23.5, "GHS": 15.5, "LKR": 400.0,
}

COUNTRY_CURRENCY = {
    "India": "INR", "Nigeria": "NGN", "Pakistan": "PKR", "Poland": "PLN",
    "Philippines": "PHP", "Bangladesh": "BDT", "Kenya": "KES", "Romania": "RON",
    "France": "EUR", "Germany": "EUR", "Spain": "EUR", "Portugal": "EUR",
    "Italy": "EUR", "Netherlands": "EUR", "Ireland": "EUR", "USA": "USD",
    "Australia": "AUD", "South Africa": "ZAR", "Ghana": "GHS", "Sri Lanka": "LKR",
    "United Kingdom": "GBP",
}

# Destination weights by SOURCE country (real remittance corridors, approx).
# Sources not listed fall back to GLOBAL_FALLBACK.
DEST_BY_SOURCE = {
    "United Kingdom": {
        "India": 0.18, "Nigeria": 0.12, "Poland": 0.12, "Pakistan": 0.10,
        "France": 0.08, "Germany": 0.07, "Philippines": 0.06, "Bangladesh": 0.06,
        "Romania": 0.06, "Kenya": 0.05, "USA": 0.05, "Ghana": 0.05,
    },
    "EIRE": {"India": 0.15, "Poland": 0.20, "Romania": 0.15, "Nigeria": 0.12,
             "USA": 0.10, "Philippines": 0.10, "Pakistan": 0.08, "Ghana": 0.10},
    "Germany": {"Poland": 0.22, "Romania": 0.18, "India": 0.14, "USA": 0.12,
                "Philippines": 0.10, "Nigeria": 0.12, "Ghana": 0.12},
    "France": {"India": 0.16, "Portugal": 0.20, "Romania": 0.16, "USA": 0.12,
               "Philippines": 0.12, "Nigeria": 0.12, "Ghana": 0.12},
}
GLOBAL_FALLBACK = {
    "India": 0.20, "Nigeria": 0.15, "Philippines": 0.15, "Pakistan": 0.12,
    "Poland": 0.10, "USA": 0.10, "Bangladesh": 0.10, "Kenya": 0.08,
}

# Per-corridor fee/spread bands; actual value drawn deterministically per
# corridor name, recorded in dim_corridor.
FEE_PCT_RANGE = (0.004, 0.012)     # fee as fraction of send amount
MIN_FEE_GBP_RANGE = (0.50, 2.00)   # floor fee in GBP
FX_SPREAD_RANGE = (0.004, 0.015)   # provider margin vs mid-market


# ---------------------------------------------------------------------------
# Load + clean the REAL data
# ---------------------------------------------------------------------------
def _rename_columns(df: pd.DataFrame) -> pd.DataFrame:
    mapping = {
        "InvoiceNo": "invoice", "Invoice": "invoice",
        "UnitPrice": "price", "Price": "price",
        "Customer ID": "customer_id", "CustomerID": "customer_id",
        "InvoiceDate": "invoice_date", "Quantity": "quantity",
        "Country": "country", "StockCode": "stock_code",
        "Description": "description",
    }
    return df.rename(columns={k: v for k, v in mapping.items() if k in df.columns})


def load_raw(path: Path) -> pd.DataFrame:
    if path.suffix.lower() in (".xlsx", ".xls"):
        # Online Retail II ships as one workbook with two yearly sheets.
        sheets = pd.read_excel(path, sheet_name=None)
        df = pd.concat(sheets.values(), ignore_index=True)
    else:
        df = pd.read_csv(path, encoding="ISO-8859-1")
    df = _rename_columns(df)
    required = {"invoice", "price", "customer_id", "invoice_date",
                "quantity", "country"}
    missing = required - set(df.columns)
    if missing:
        sys.exit(f"ERROR: input is missing expected columns: {sorted(missing)}")
    return df


def clean_transactions(df: pd.DataFrame) -> pd.DataFrame:
    """Line-level cleaning rules."""
    n0 = len(df)
    df = df.copy()
    df["invoice"] = df["invoice"].astype(str)
    df["invoice_date"] = pd.to_datetime(df["invoice_date"], errors="coerce")

    # Cleaning rules:
    # 1. drop rows with no customer -> cannot attribute a transfer to a sender
    df = df[df["customer_id"].notna()]
    # 2. drop cancellations: invoice numbers prefixed 'C' are returns
    df = df[~df["invoice"].str.upper().str.startswith("C")]
    # 3. drop non-positive quantity or price -> not a valid send
    df = df[(df["quantity"] > 0) & (df["price"] > 0)]
    # 4. drop rows with an unparseable date
    df = df[df["invoice_date"].notna()]

    df["customer_id"] = df["customer_id"].astype(float).astype(int).astype(str)
    df["line_amount_gbp"] = (df["quantity"] * df["price"]).round(2)

    print(f"[clean] line rows: {n0:,} -> {len(df):,} "
          f"({n0 - len(df):,} dropped)")
    return df


def aggregate_to_transfers(df: pd.DataFrame) -> pd.DataFrame:
    """One transfer == one invoice (a basket), the natural transfer grain."""
    transfers = (
        df.groupby("invoice")
          .agg(customer_id=("customer_id", "first"),
               transfer_ts=("invoice_date", "min"),
               source_country=("country", "first"),
               send_amount_gbp=("line_amount_gbp", "sum"),
               n_line_items=("line_amount_gbp", "size"))
          .reset_index()
          .rename(columns={"invoice": "transfer_id"})
    )
    transfers["send_amount_gbp"] = transfers["send_amount_gbp"].round(2)
    print(f"[grain] transfers (invoices): {len(transfers):,} | "
          f"unique senders: {transfers['customer_id'].nunique():,}")
    return transfers


# ---------------------------------------------------------------------------
# SYNTHETIC corridor / FX / fee layer
# ---------------------------------------------------------------------------
def _stable_uniform(key: str, lo: float, hi: float) -> float:
    """Deterministic draw in [lo, hi] from a string key (stable across runs)."""
    h = int(hashlib.md5(f"{SEED}:{key}".encode()).hexdigest(), 16)
    return lo + (h % 10_000) / 10_000 * (hi - lo)


def _weighted_choice(rng: np.random.Generator, weights: dict[str, float]) -> str:
    keys = list(weights)
    w = np.array([weights[k] for k in keys], dtype=float)
    w = w / w.sum()
    return keys[rng.choice(len(keys), p=w)]


def assign_corridors(transfers: pd.DataFrame) -> pd.DataFrame:
    """Assign ONE destination per customer (consistent corridor per sender)."""
    rng = np.random.default_rng(SEED)
    # first source country seen per customer anchors their corridor origin
    cust_source = (transfers.sort_values("transfer_ts")
                            .groupby("customer_id")["source_country"].first())
    dest_by_cust = {}
    for cust, src in cust_source.sort_index().items():
        weights = DEST_BY_SOURCE.get(src, GLOBAL_FALLBACK)
        dest_by_cust[cust] = _weighted_choice(rng, weights)

    transfers = transfers.copy()
    transfers["dest_country"] = transfers["customer_id"].map(dest_by_cust)
    transfers["dest_currency"] = transfers["dest_country"].map(COUNTRY_CURRENCY)
    transfers["send_currency"] = BASE_CURRENCY
    transfers["corridor"] = (transfers["source_country"].astype(str)
                             + " -> " + transfers["dest_country"])
    return transfers


def build_corridor_dim(transfers: pd.DataFrame) -> pd.DataFrame:
    dim = (transfers[["corridor", "source_country", "dest_country",
                      "dest_currency"]]
           .drop_duplicates().reset_index(drop=True))
    dim["fee_pct"] = dim["corridor"].map(
        lambda c: round(_stable_uniform("fee:" + c, *FEE_PCT_RANGE), 4))
    dim["min_fee_gbp"] = dim["corridor"].map(
        lambda c: round(_stable_uniform("min:" + c, *MIN_FEE_GBP_RANGE), 2))
    dim["fx_spread"] = dim["corridor"].map(
        lambda c: round(_stable_uniform("spr:" + c, *FX_SPREAD_RANGE), 4))
    return dim


def apply_fx_and_fees(transfers: pd.DataFrame,
                      dim: pd.DataFrame) -> pd.DataFrame:
    t = transfers.merge(
        dim[["corridor", "fee_pct", "min_fee_gbp", "fx_spread"]],
        on="corridor", how="left")

    t["fx_mid_rate"] = t["dest_currency"].map(CURRENCY_RATES_PER_GBP)
    # customer receives a rate worse than mid by the provider spread
    t["customer_rate"] = (t["fx_mid_rate"] * (1 - t["fx_spread"])).round(6)

    # fee = max(floor, pct * amount); recipient gets amount * customer_rate
    t["fee_gbp"] = np.maximum(
        t["min_fee_gbp"], (t["fee_pct"] * t["send_amount_gbp"])).round(2)
    t["total_cost_gbp"] = (t["send_amount_gbp"] + t["fee_gbp"]).round(2)
    t["recipient_amount"] = (t["send_amount_gbp"] * t["customer_rate"]).round(2)
    # implied FX margin the provider earns in GBP terms = send * spread
    t["fx_margin_gbp"] = (t["send_amount_gbp"] * t["fx_spread"]).round(2)
    return t


# ---------------------------------------------------------------------------
# Validation / profiling, printed on every run
# ---------------------------------------------------------------------------
def profile(t: pd.DataFrame) -> None:
    print("\n" + "=" * 62)
    print("VALIDATION / PROFILING SUMMARY")
    print("=" * 62)

    # RFM frequency scoring requires repeat senders.
    per_cust = t.groupby("customer_id").size()
    single = (per_cust == 1).mean() * 100
    print("\nTransfers per sender:")
    print(f"  senders                : {per_cust.size:,}")
    print(f"  median transfers/sender: {per_cust.median():.0f}")
    print(f"  p90 transfers/sender   : {per_cust.quantile(0.90):.0f}")
    print(f"  max transfers/sender   : {per_cust.max():,}")
    print(f"  % senders with exactly 1: {single:.1f}%")

    # top-decile volume share
    vol = t.groupby("customer_id")["send_amount_gbp"].sum().sort_values(
        ascending=False)
    top_decile_cut = max(1, int(len(vol) * 0.10))
    share = vol.iloc[:top_decile_cut].sum() / vol.sum() * 100
    print(f"\nVolume concentration:")
    print(f"  top 10% of senders drive {share:.1f}% of total volume")

    # integrity checks
    print("\nIntegrity checks:")
    print(f"  null corridor rows     : {t['corridor'].isna().sum()}")
    print(f"  null fx rate rows      : {t['fx_mid_rate'].isna().sum()}")
    print(f"  fee < floor violations : {(t['fee_gbp'] < t['min_fee_gbp']).sum()}")
    print(f"  negative amounts       : {(t['send_amount_gbp'] <= 0).sum()}")
    print(f"  fee as % of send (med) : "
          f"{(t['fee_gbp'] / t['send_amount_gbp'] * 100).median():.2f}%")

    # corridor is independent of amount, by construction
    print("\nTop corridors by transfer count:")
    top = t["corridor"].value_counts().head(8)
    for corr, n in top.items():
        med = t.loc[t["corridor"] == corr, "send_amount_gbp"].median()
        print(f"  {corr:<34} {n:>7,} transfers | median GBP {med:>8.2f}")
    print("  median send is flat across corridors by construction.")


# ---------------------------------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", required=True,
                    help="path to Online Retail II .xlsx or .csv")
    ap.add_argument("--outdir", default="output", help="output directory")
    ap.add_argument("--duckdb", action="store_true",
                    help="also load the tables into transfers.duckdb")
    args = ap.parse_args()

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    raw = load_raw(Path(args.input))
    clean = clean_transactions(raw)
    transfers = aggregate_to_transfers(clean)
    transfers = assign_corridors(transfers)
    dim_corridor = build_corridor_dim(transfers)
    fct = apply_fx_and_fees(transfers, dim_corridor)

    dim_fx = (pd.DataFrame({"currency": list(CURRENCY_RATES_PER_GBP),
                            "gbp_mid_rate": list(CURRENCY_RATES_PER_GBP.values())})
              .assign(as_of=FX_AS_OF))

    profile(fct)  # includes fee_pct / min_fee_gbp columns

    col_order = ["transfer_id", "customer_id", "transfer_ts", "source_country",
                 "dest_country", "corridor", "send_currency", "dest_currency",
                 "send_amount_gbp", "fee_gbp", "total_cost_gbp", "fx_mid_rate",
                 "fx_spread", "customer_rate", "recipient_amount",
                 "fx_margin_gbp", "n_line_items"]
    fct = fct[col_order]

    fct.to_csv(outdir / "fct_transfers.csv", index=False)
    dim_corridor.to_csv(outdir / "dim_corridor.csv", index=False)
    dim_fx.to_csv(outdir / "dim_fx.csv", index=False)
    print(f"\n[write] {outdir/'fct_transfers.csv'}  ({len(fct):,} rows)")
    print(f"[write] {outdir/'dim_corridor.csv'}  ({len(dim_corridor):,} rows)")
    print(f"[write] {outdir/'dim_fx.csv'}  ({len(dim_fx):,} rows)")

    if args.duckdb:
        import duckdb
        con = duckdb.connect(str(outdir / "transfers.duckdb"))
        con.register("fct", fct)
        con.register("dc", dim_corridor)
        con.register("dfx", dim_fx)
        con.execute("CREATE OR REPLACE TABLE fct_transfers AS SELECT * FROM fct")
        con.execute("CREATE OR REPLACE TABLE dim_corridor AS SELECT * FROM dc")
        con.execute("CREATE OR REPLACE TABLE dim_fx AS SELECT * FROM dfx")
        con.close()
        print(f"[write] {outdir/'transfers.duckdb'}  (3 tables)")


if __name__ == "__main__":
    main()

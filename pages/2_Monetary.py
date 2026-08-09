"""SBP monetary, market-rate and credit indicators."""
from __future__ import annotations
# Streamlit executes this file as a top-level script, so it puts only the main
# script's own directory on sys.path — the repository root is absent and
# `import dashboard.lib` fails with ModuleNotFoundError. The failure surfaces as a
# traceback rendered inside the running app rather than as a non-zero exit or a
# bad HTTP status, so it survives both an import-based test harness (which runs
# from the repo root, where the import happens to work) and a curl check on the
# root URL (which only fetches Streamlit's shell HTML). The path is therefore
# fixed explicitly here, before any first-party import.
import sys as _sys
from pathlib import Path as _Path

_ROOT = _Path(__file__).resolve().parents[2]
if str(_ROOT) not in _sys.path:
    _sys.path.insert(0, str(_ROOT))


import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from dashboard.lib import apply_theme, date_window, download_data, filtered_long, get_series, inject_css, line_chart, source_expander, yoy

st.set_page_config(page_title="Monetary | PIDE Macro", page_icon="▦", layout="wide")
inject_css()
st.title("Monetary conditions")
st.write(
    "Monetary indicators connect the SBP policy stance to money, bank credit and market borrowing costs. Policy rates set the stance, while KIBOR, T-bill yields and lending/deposit rates show transmission through financial markets and bank balance sheets."
)
st.caption("Publisher basis shown: State Bank of Pakistan (SBP). All rates are percentages; monetary aggregates and credit are million PKR.")
start, end = date_window("monetary_dates")

st.subheader("Policy stance and the policy-rate corridor")
policy = ["SBP Policy Rate (target)", "SBP Repo Rate (floor)", "SBP Reverse Repo Rate (ceiling)"]
# These are the actual policy-rate corridor series.  The similarly named
# sbp_interest_rate_corridor dataset records standing-facility usage, not rates.
line_chart(get_series(policy, start, end), "Policy target, floor and ceiling", "%", "SBP · policy and repo rate history", step=True)
st.info("Important distinction: the chart above is the policy-rate corridor from `sbp_interest_rates`. The `sbp_interest_rate_corridor` dataset below records standing-facility **usage** (amounts and institution counts), not the policy rate.")

st.subheader("Money, deposits and private-sector credit")
transform = st.radio("Monetary-aggregate display", ["Level", "YoY change"], horizontal=True)
aggregates = ["Currency in Circulation", "Total Deposits with Banks1", "a. Credit to Private Sector*"]
agg = get_series(aggregates, start, end)
shown = agg if transform == "Level" else yoy(agg)
line_chart(shown, "Currency, deposits and private-sector credit", "million PKR" if transform == "Level" else "% YoY", "SBP · Broad Money (M2) components and affecting factors")
st.caption("The archived headline M2 series ends in 2012. The current component labels are shown without stitching old and new labels into a synthetic M2 line.")

st.subheader("Interbank and Treasury-bill yields")
rates = ["KIBOR 1-month", "KIBOR 3-month", "KIBOR 6-month", "T-bill 3-month cut-off yield", "T-bill 6-month cut-off yield", "T-bill 12-month cut-off yield"]
line_chart(get_series(rates, start, end), "KIBOR and T-bill cut-off yields", "%", "SBP · interest rates and auction yields")

st.subheader("Bank lending and deposit rates")
bank_rates = ["Lending rate — fresh (marginal) (PKR, all banks)", "Lending rate — outstanding (stocks) (PKR, all banks)", "Deposit rate — fresh (marginal) (PKR, all banks)", "Deposit rate — outstanding (stocks) (PKR, all banks)"]
line_chart(get_series(bank_rates, start, end), "PKR lending and deposit rates", "%", "SBP · banking-sector weighted rates")

st.subheader("Standing-facility usage")
usage_amount = get_series(["Ceiling — Amount", "Floor — Amount"], start, end)
usage_count = get_series(["Ceiling — Institutions", "Floor — Institutions"], start, end)
c1, c2 = st.columns(2)
with c1:
    line_chart(usage_amount, "Standing-facility amount used", "million PKR", "SBP · interest-rate corridor usage")
with c2:
    line_chart(usage_count, "Institutions using standing facilities", "Institution count", "SBP · interest-rate corridor usage")

st.warning("Borrower categories labelled “(ISIC rev. 4 basis)” in `sbp_credit_loans_by_borrower` are not comparable with unsuffixed pre-2019 categories because SBP reclassified borrowers. This page does not join them into a single line.")
sources = ["sbp_interest_rates", "sbp_broad_money_m2", "sbp_interest_rate_corridor", "sbp_credit_loans_by_borrower"]
source_expander(sources)
download_data(filtered_long(source_ids=sources, start=start, end=end), "pide_monetary_filtered.csv")

"""Home page for the PIDE Macroeconomic Indicator Dashboard."""
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

_ROOT = _Path(__file__).resolve().parents[1]
if str(_ROOT) not in _sys.path:
    _sys.path.insert(0, str(_ROOT))


import pandas as pd
import streamlit as st

from dashboard.lib import (
    date_window, download_data, filtered_long, inject_css, kpi_card, line_chart,
    load_index, load_manifest, resolve_sdmx_code, series_unit, source_expander,
)

st.set_page_config(page_title="PIDE Macro Dashboard", page_icon="▦", layout="wide", initial_sidebar_state="expanded")
inject_css()

st.title("PIDE Macroeconomic Indicator Dashboard")
st.write(
    "A policy-facing view of Pakistan's official macroeconomic releases. The cards show the latest published observation and its same-period-year-earlier change; charts retain the underlying release frequency so economists can assess timing, scale and source basis before drawing conclusions."
)
st.caption("Publisher basis: PBS for prices and customs trade; SBP for monetary, external and national-accounts series.")
start, end = date_window("overview_dates")

st.subheader("Latest official readings")
general_balance = resolve_sdmx_code("mof_general_govt_operations_sdmx", "PAK_GGO_BBIG_XDC")
# Every name below is an exact match in series_index.csv.
#
# The remittances card uses SBP's own published 'Total' row. The corridor rows are
# NOT summed to produce it: they nest (Abu Dhabi, Dubai and Sharjah sit inside
# U.A.E.; individual EU members sit inside 'EU Countries') and the list carries
# both 'Bahrain' and the publisher's older misspelling 'Behrain', so adding them
# would double-count. Where the publisher states an aggregate, the aggregate is
# read from the source rather than reconstructed.
cards = [
    ("Headline CPI inflation", "National — inflation", "{:,.1f}%", "PBS national CPI year-on-year inflation."),
    ("SBP policy rate", "SBP Policy Rate (target)", "{:,.2f}%", "The policy target is a dated decision series, not a monthly average."),
    ("Total liquid FX reserves", "Total liquid FX reserves", "{:,.0f}", "SBP plus banking-system liquid foreign-exchange reserves, million USD."),
    ("Trade balance — BOP", "Balance of Trade [a-c]", "{:,.0f}", "SBP balance-of-payments basis; do not compare directly with customs-basis trade."),
    ("Broad money (M2)", "Broad Money (M2) (A+B+C)", "{:,.0f}", "SBP broad money stock, million PKR. Components basis (currency + other deposits with SBP + total bank deposits)."),
    ("Workers' remittances", "Total", "{:,.0f}", "SBP total monthly workers' remittances, million USD. Publisher's own total; corridor rows nest and are not summed.", "sbp_workers_remittances"),
    ("Annual GDP growth", "GDP Growth Rate (%)", "{:,.1f}%", "SBP annual national-accounts GDP growth rate."),
    ("General-govt budget balance", general_balance or "", "{:,.0f}", "MoF consolidated federal-plus-provincial budget balance, million PKR; data lag to 2025 Q1."),
]
for row in [cards[:4], cards[4:]]:
    cols = st.columns(4 if len(row) == 4 else 3)
    for col, spec in zip(cols, row):
        with col:
            kpi_card(*spec)

st.subheader("Key series at a glance")
small_multiples = [
    ("National CPI inflation", ["National — inflation"], "% YoY", "PBS · national CPI inflation"),
    ("Total liquid FX reserves", ["Total liquid FX reserves"], "million USD", "SBP · liquid foreign-exchange reserves"),
    ("Trade balance — BOP basis", ["Balance of Trade [a-c]"], "million USD", "SBP · balance-of-payments basis"),
    ("GDP growth", ["GDP Growth Rate (%)"], "% YoY", "SBP · annual national accounts"),
]
for left, right in zip(small_multiples[::2], small_multiples[1::2]):
    c1, c2 = st.columns(2)
    for container, item in ((c1, left), (c2, right)):
        with container:
            names = item[1]
            data = filtered_long(names=names, start=start, end=end)
            wide = data.pivot(index="date", columns="series", values="value") if not data.empty else pd.DataFrame()
            line_chart(wide, item[0], item[2], item[3])

st.subheader("Data freshness")
manifest = load_manifest()
index = load_index()
records = []
for source_id, details in manifest.get("sources", {}).items():
    idx = index[index["source_id"].eq(source_id)]
    records.append({
        "Dataset": source_id,
        "Publisher": str(details.get("publisher", idx["publisher"].iloc[0] if not idx.empty else "" )).upper(),
        "Data fetched at (UTC)": details.get("fetched_at", "not available"),
        "Status": details.get("status", "not available"),
        "Official page": details.get("page", idx["page"].iloc[0] if not idx.empty else ""),
    })
if records:
    freshness = pd.DataFrame(records).sort_values(["Publisher", "Dataset"])
    st.dataframe(freshness, hide_index=True, width="stretch", column_config={"Official page": st.column_config.LinkColumn("Official page")})
else:
    st.info("Manifest freshness metadata are not available.")

used_sources = ["pbs_cpi_historical", "sbp_interest_rates", "sbp_forex_reserves", "sbp_balance_of_trade", "sbp_workers_remittances", "sbp_broad_money_m2", "sbp_gdp_annual", "mof_general_govt_operations_sdmx"]
source_expander(used_sources)
download_data(filtered_long(source_ids=used_sources, start=start, end=end), "pide_macro_overview_filtered.csv")

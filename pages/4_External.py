"""SBP and PBS external-sector indicators, with basis separation."""
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


import streamlit as st

from dashboard.lib import date_window, download_data, filtered_long, get_series, inject_css, line_chart, resolve_sdmx_code, source_expander, yoy

st.set_page_config(page_title="External | PIDE Macro", page_icon="▦", layout="wide")
inject_css()
st.title("External sector")
st.write(
    "External indicators show the flow of goods, workers' remittances and foreign-exchange liquidity that shape Pakistan's balance-of-payments pressures. Trade series are presented on their original publication basis because customs and balance-of-payments statistics answer different questions."
)
st.caption("Publisher basis shown: SBP for BOP trade, remittances and reserves; PBS for customs trade. These bases are never combined.")
start, end = date_window("external_dates")
mode = st.radio("Trade and exchange-rate display", ["Level", "YoY change"], horizontal=True)

st.subheader("Trade — balance-of-payments basis")
st.warning("SBP trade is **BOP basis**. It is not plotted with, summed with, or substituted for PBS customs-basis trade.")
bop = ["Exports (BOP) Value [a]", "Imports (BOP) Value [c]", "Balance of Trade [a-c]"]
bop_data = get_series(bop, start, end)
line_chart(bop_data if mode == "Level" else yoy(bop_data), "SBP trade: BOP basis", "million USD" if mode == "Level" else "% YoY", "SBP · external sector data, balance-of-payments basis")

st.subheader("Trade — customs basis")
st.warning("PBS trade is **customs basis**. It is shown separately and must not be combined with the SBP BOP-basis chart above.")
customs = ["Exports (goods)", "Imports (goods)", "Balance of Trade (goods)"]
customs_data = get_series(customs, start, end)
line_chart(customs_data if mode == "Level" else yoy(customs_data), "PBS goods trade: customs basis", "million USD" if mode == "Level" else "% YoY", "PBS · external trade statistics, customs basis")

st.subheader("Long-run merchandise trade — customs basis, national currency")
st.warning("The PBS SDMX merchandise trade series is **customs basis in million PKR**. It is separate from the PBS summary spreadsheet (**customs basis in million USD**) and SBP BOP trade (**million USD**); the three releases are never combined, summed, or placed on the same axis.")
long_customs = [
    resolve_sdmx_code("pbs_merchandise_trade_sdmx", "TXG_FOB_XDC"),
    resolve_sdmx_code("pbs_merchandise_trade_sdmx", "TMG_CIF_XDC"),
]
line_chart(get_series([name for name in long_customs if name], start, end), "PBS merchandise trade: long customs history", "million PKR", "PBS SDMX · merchandise trade, customs basis")

st.subheader("Workers' remittances by corridor")
remit = ["Saudi Arabia", "U.A.E.", "U.K.", "USA", "Other GCC Countries"]
line_chart(get_series(remit, start, end), "Monthly remittances by selected corridor", "million USD", "SBP · workers' remittances")

st.subheader("Liquid foreign-exchange reserves")
reserves = ["Reserves with SBP", "Reserves with banks", "Total liquid FX reserves"]
line_chart(get_series(reserves, start, end), "Foreign-exchange reserves", "million USD", "SBP · liquid foreign-exchange reserves")

st.subheader("REER and NEER")
st.error("Discontinued series: SBP REER/NEER publication in this master ends in **2023-12**. The chart is intentionally not extended or flat-lined beyond that date.")
reer = get_series(["REER", "NEER"], start, end)
line_chart(reer if mode == "Level" else yoy(reer), "Real and nominal effective exchange rates", "Index (2010 = 100)" if mode == "Level" else "% YoY", "SBP · REER/NEER (last published 2023-12)")

sources = ["sbp_balance_of_trade", "pbs_trade_summary_monthly", "pbs_merchandise_trade_sdmx", "sbp_workers_remittances", "sbp_forex_reserves", "sbp_reer_neer"]
source_expander(sources)
download_data(filtered_long(source_ids=sources, start=start, end=end), "pide_external_filtered.csv")

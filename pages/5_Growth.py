"""National-account growth data included in the validated master."""
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

from dashboard.lib import date_window, download_data, filtered_long, get_series, inject_css, line_chart, resolve_sdmx_code, source_expander

st.set_page_config(page_title="Growth | PIDE Macro", page_icon="▦", layout="wide")
inject_css()
st.title("Growth and production")
st.write(
    "Growth indicators describe the scale and sectoral composition of economic activity. Annual national accounts provide the fiscal-year overview, while quarterly sector growth offers a more timely read on agriculture, industry and services."
)
st.caption("Publisher basis shown: State Bank of Pakistan (SBP), reproducing official national-accounts series.")
start, end = date_window("growth_dates")

st.subheader("Annual GDP growth and sectoral levels")
line_chart(get_series(["GDP Growth Rate (%)"], start, end), "Annual GDP growth", "% YoY", "SBP · annual national accounts")
annual_sectors = ["Agriculture, Forestry and Fishing ( 1 to 4 )", "Industrial Activities ( 1 to 4 )", "Services ( 1 to 10)"]
line_chart(get_series(annual_sectors, start, end), "Annual sectoral gross value added", "million PKR (constant 2015-16)", "SBP · annual national accounts")

st.subheader("Quarterly sector growth")
quarterly_growth = ["Agriculture Sector (1 to 4) — growth", "Industrial Sector (1 to 4) — growth", "Services Sector (1 to 10) — growth"]
line_chart(get_series(quarterly_growth, start, end), "Quarterly sector growth", "% YoY", "SBP · quarterly national accounts")

st.subheader("PBS quarterly national accounts: nominal GDP")
pbs_nominal_gdp = resolve_sdmx_code("pbs_quarterly_national_accounts_sdmx", "NGDP_FY_XDC")
line_chart(get_series([pbs_nominal_gdp] if pbs_nominal_gdp else [], start, end), "Quarterly GDP — nominal", "million PKR (nominal)", "PBS SDMX · quarterly national accounts")
st.warning("Basis note: PBS SDMX quarterly GDP is nominal national currency, while the SBP quarterly workbook series above is at constant 2015-16 basic prices. Both are valid releases but measure different price bases, so they are not compared directly or plotted on a shared axis.")

st.subheader("Large-scale manufacturing coverage")
st.info("The master table does not include the separate monthly LSM production snapshot by design. It does contain national-accounts large-scale manufacturing, which is shown below as a sectoral value-added measure—not as an LSM production index.")
lsm_proxy = ["i. Large Scale — growth", "i. Large Scale — level"]
# Level and growth have different units, so they are rendered in separate charts.
c1, c2 = st.columns(2)
with c1:
    line_chart(get_series([lsm_proxy[0]], start, end), "Large-scale manufacturing: quarterly growth", "% YoY", "SBP · quarterly national accounts")
with c2:
    line_chart(get_series([lsm_proxy[1]], start, end), "Large-scale manufacturing: quarterly level", "million PKR (constant basic prices)", "SBP · quarterly national accounts")

sources = ["sbp_gdp_annual", "sbp_gdp_quarterly", "pbs_quarterly_national_accounts_sdmx"]
source_expander(sources)
download_data(filtered_long(source_ids=sources, start=start, end=end), "pide_growth_filtered.csv")

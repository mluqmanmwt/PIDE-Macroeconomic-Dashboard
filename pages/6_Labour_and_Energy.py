"""Official PBS SDMX labour and energy indicators, with clear coverage limits."""
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
import streamlit as st

from dashboard.lib import date_window, download_data, filtered_long, get_series, inject_css, line_chart, resolve_sdmx_code, source_expander

st.set_page_config(page_title="Labour and Energy | PIDE Macro", page_icon="▦", layout="wide")
inject_css()
# A 10-year default window would start in 2016 and, because PBS stopped
# refreshing the labour feed after the 2020-21 Labour Force Survey, would leave
# only five annual points visible while silently hiding the 1991-2015 history.
# The window is widened here rather than globally: every other page tracks a
# live series where a recent window is the right default.
st.title("Labour and energy")
st.write(
    "Labour-market participation, employment and unemployment describe household access to work, while domestic energy production and electricity generation indicate important capacity and supply-side conditions. The page uses the currently available PBS SDMX releases and makes their publication cut-offs explicit."
)
st.caption("Publisher basis shown: Pakistan Bureau of Statistics (PBS) SDMX. Labour data are annual fiscal-year observations; energy data are monthly production/generation indicators.")
start, end = date_window("labour_energy_dates", default_years=40)

st.subheader("Labour market")
labor_force = resolve_sdmx_code("pbs_labour_sdmx", "LLF_PE_FY_NUM")
employment = resolve_sdmx_code("pbs_labour_sdmx", "LE_PE_FY_NUM")
unemployment = resolve_sdmx_code("pbs_labour_sdmx", "LU_PE_FY_NUM")
labour_names = [name for name in [labor_force, employment, unemployment] if name]
labour = get_series(labour_names, start, end)
line_chart(labour, "Labour force, employment and unemployment", "million persons", "PBS SDMX · Labour Force Survey indicators")
if labor_force and unemployment and labor_force in labour.columns and unemployment in labour.columns:
    derived_rate = (labour[unemployment] / labour[labor_force] * 100).to_frame("Derived unemployment rate (unemployed ÷ labour force)")
    derived_rate.attrs["frequencies"] = {"Derived unemployment rate (unemployed ÷ labour force)": "annual"}
    line_chart(derived_rate, "Derived unemployment rate", "%", "Derived from PBS SDMX unemployment ÷ labour force; not a separately published rate")
st.error("Discontinued labour feed: PBS SDMX labour observations end in fiscal year 2020–21 (2021-06). PBS has not refreshed this SDMX Labour Force Survey feed since that release; the chart is not extended or flat-lined beyond its last observation.")

st.subheader("Energy production and electricity generation")
total_electricity = resolve_sdmx_code("pbs_energy_sdmx", "PAK_ORSI_EG_GWH")
thermal = resolve_sdmx_code("pbs_energy_sdmx", "PAK_ORSI_T_GWH")
hydel = resolve_sdmx_code("pbs_energy_sdmx", "PAK_ORSI_H_GWH")
nuclear = resolve_sdmx_code("pbs_energy_sdmx", "PAK_ORSI_N_GWH")
alternate = resolve_sdmx_code("pbs_energy_sdmx", "PAK_ORSI_AE_GWH")
line_chart(get_series([name for name in [total_electricity, thermal, hydel, nuclear, alternate] if name], start, end), "Electricity generation", "GWh", "PBS SDMX · industrial production / electricity generation")

crude = resolve_sdmx_code("pbs_energy_sdmx", "AOMPC_BBL")
gas = resolve_sdmx_code("pbs_energy_sdmx", "PAK_ORSI_NG_1000FC")
c1, c2 = st.columns(2)
with c1:
    line_chart(get_series([crude] if crude else [], start, end), "Crude-oil production", "thousand barrels", "PBS SDMX · crude-oil production")
with c2:
    line_chart(get_series([gas] if gas else [], start, end), "Natural-gas production", "thousand units", "PBS SDMX · natural-gas production")
st.info("NEPRA and OGRA regulatory datasets (tariffs, sales, sectoral consumption and regulatory measures) remain PDF-only or blocked in the current pipeline. They are not substituted with estimates here.")

sources = ["pbs_labour_sdmx", "pbs_energy_sdmx"]
source_expander(sources)
download_data(filtered_long(source_ids=sources, start=start, end=end), "pide_labour_energy_filtered.csv")

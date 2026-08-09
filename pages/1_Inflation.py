"""PBS inflation indicators."""
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

from dashboard.lib import date_window, download_data, filtered_long, get_series, inject_css, line_chart, load_index, resolve_sdmx_code, source_expander, yoy

st.set_page_config(page_title="Inflation | PIDE Macro", page_icon="▦", layout="wide")
inject_css()
st.title("Inflation")
st.write(
    "Inflation indicators show how quickly consumer prices are changing and where price pressure is concentrated. National CPI is the headline policy measure; the weekly Sensitive Price Indicator (SPI) is a faster, narrower signal that can help nowcast food-price pressures between monthly CPI releases."
)
st.caption("Publisher basis shown: Pakistan Bureau of Statistics (PBS). CPI and SPI are distinct official price instruments, not interchangeable baskets.")
start, end = date_window("inflation_dates")
mode = st.radio("Display", ["Level (index)", "Year-over-year change"], horizontal=True)

cpi_levels = ["National — index", "UCPI — index", "RPI — index"]
cpi_published_yoy = ["National — inflation", "UCPI — inflation", "RPI — inflation"]
if mode == "Level (index)":
    cpi = get_series(cpi_levels, start, end)
    cpi_title, unit = "PBS headline price indices", "Index (base varies in historical release)"
else:
    # PBS publishes explicit historical inflation rates.  Using those avoids
    # presenting a recomputation as an official CPI release when the base changed.
    cpi = get_series(cpi_published_yoy, start, end)
    cpi_title, unit = "PBS published headline inflation", "% YoY"
line_chart(cpi, cpi_title, unit, "PBS · CPI/RPI historical price-statistics release")
st.caption("UCPI is the PBS Urban CPI series and RPI is the Rural Price Index series available in the validated master; they should be interpreted using PBS's own coverage definitions.")

st.subheader("Food, non-food and core coverage")
st.write(
    "The validated SDMX extract contains COICOP division indices and weights, including Food and non-alcoholic beverages (division 01). It does not contain a pre-built official core-inflation or non-food aggregate series, so this dashboard does not construct one from components.")
food = resolve_sdmx_code("pbs_cpi_sdmx", "PCPI_CP_01_IX")
food_weight = resolve_sdmx_code("pbs_cpi_sdmx", "PCPI_CP_01_WT")
c1, c2 = st.columns(2)
with c1:
    data = get_series([food] if food else [], start, end)
    displayed = data if mode == "Level (index)" else yoy(data)
    line_chart(displayed, "Food and non-alcoholic beverages", "Index" if mode == "Level (index)" else "% YoY", "PBS SDMX · COICOP division 01")
with c2:
    weights = get_series([food_weight] if food_weight else [], start, end)
    line_chart(weights, "CPI basket weight: food and non-alcoholic beverages", "PBS-published weight", "PBS SDMX · COICOP division 01 weight")

st.subheader("Wholesale / producer prices")
wpi_names = load_index().loc[lambda x: x["source_id"].eq("pbs_producer_prices_sdmx"), "series"].tolist()
wpi = get_series(wpi_names, start, end)
wpi_shown = wpi if mode == "Level (index)" else yoy(wpi)
line_chart(wpi_shown, "PBS wholesale price index (WPI/PPI)", "Index" if mode == "Level (index)" else "% YoY", "PBS SDMX · wholesale/producer price indices")
st.caption("This is the machine-readable PBS WPI/PPI coverage; it is a producer/wholesale-price measure, not a CPI substitute.")

st.subheader("Weekly SPI: fast-moving price signal")
spi_mode = st.radio("SPI display", ["SPI index", "SPI published YoY"], horizontal=True)
spi_name = "SPI Combined — index" if spi_mode == "SPI index" else "SPI Combined — % change YoY"
spi_unit = "Index (2015-16 = 100)" if spi_mode == "SPI index" else "% YoY"
line_chart(get_series([spi_name], start, end), f"{spi_mode} — combined basket", spi_unit, "PBS · weekly Sensitive Price Indicator")

sources = ["pbs_cpi_historical", "pbs_cpi_sdmx", "pbs_producer_prices_sdmx", "pbs_spi_weekly"]
source_expander(sources)
download_data(filtered_long(source_ids=sources, start=start, end=end), "pide_inflation_filtered.csv")

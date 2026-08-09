"""MoF general-government operations and SBP domestic debt coverage."""
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


import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from dashboard.lib import (
    apply_theme, date_window, download_data, filtered_long, get_series, inject_css,
    line_chart, resolve_sdmx_code, short_labels, source_expander, yoy,
)

st.set_page_config(page_title="Fiscal | PIDE Macro", page_icon="▦", layout="wide")
inject_css()
st.title("Fiscal operations and domestic debt")
st.write(
    "Fiscal indicators show the consolidated public-sector resource position and the domestic financing structure behind it. General-government operations combine federal and provincial government; domestic debt shows the instruments through which government financing is held in the local market."
)
st.caption("Publisher basis shown: Ministry of Finance (MoF) for general-government operations, and State Bank of Pakistan (SBP) for domestic debt. Values are million PKR for operations and billion PKR for debt.")
start, end = date_window("fiscal_dates")

st.subheader("Consolidated general-government operations")
# The sawtooth in these series is not noise and not a parsing artefact: the
# Ministry of Finance reports fiscal operations CUMULATIVELY from 1 July, so each
# value is the fiscal-year-to-date total and the series resets every July. Read as
# if it were a quarterly flow it would suggest revenue collapsing every summer.
st.warning(
    "**Cumulative series.** Ministry of Finance fiscal operations are reported as "
    "fiscal-year-to-date totals, restarting each July. The repeating rise-and-reset "
    "pattern is the reporting convention, not a quarterly collapse. Differencing "
    "consecutive quarters within one fiscal year gives the flow for that quarter."
)
st.info(
    "**Publication lag.** This feed currently ends at January-March 2025. It is the "
    "only machine-readable fiscal source the Government of Pakistan publishes; more "
    "recent fiscal outturns exist only in Ministry of Finance and FBR PDFs."
)
revenue = resolve_sdmx_code("mof_general_govt_operations_sdmx", "PAK_GGO_RG_R_XDC")
expenditure = resolve_sdmx_code("mof_general_govt_operations_sdmx", "PAK_GGO_E_XDC")
balance = resolve_sdmx_code("mof_general_govt_operations_sdmx", "PAK_GGO_BBIG_XDC")
flows = [item for item in [revenue, expenditure] if item]
line = get_series(flows, start, end)
if line.empty:
    st.info("General-government revenue and expenditure are not available for the selected dates.")
else:
    fig = go.Figure()
    labels = short_labels([str(col) for col in line.columns])
    for i, col in enumerate(line.columns):
        fig.add_trace(go.Scatter(x=line.index, y=line[col], name=labels[str(col)], meta=f"Full series: {col}", hovertemplate="%{x|%Y-%m-%d}<br>%{y:,.0f}<br>%{meta}<extra>%{fullData.name}</extra>", mode="lines", line={"width": 2.5}))
    fig.update_layout(title="General-government revenue and expenditure", hovermode="x unified")
    fig.update_xaxes(rangeslider={"visible": True})
    fig.update_yaxes(title_text="million PKR", tickformat=",.0f")
    apply_theme(fig)
    st.plotly_chart(fig, width="stretch", config={"displaylogo": False})
    st.caption("MoF · consolidated general-government operations · [official fiscal operations page](https://www.finance.gov.pk/fiscal_operations.html)")

balance_data = get_series([balance] if balance else [], start, end)
line_chart(balance_data, "Budget balance including grants", "million PKR", "MoF · general-government operations; negative values indicate a deficit")
st.warning("Coverage and consolidation note: the machine-readable general-government feed currently ends at Jan–Mar 2025. Do **not** add `mof_central_govt_operations_sdmx` to it: general government already consolidates federal and provincial government, so summing central-government figures would double-count. FBR collection releases, PSDP releases and budget documents remain PDF-first in this pipeline.")

st.subheader("Domestic debt by instrument")
view = st.radio("Debt display", ["Level", "YoY change"], horizontal=True)
components = ["I. Permanent Debt (1+2+3+4)", "II. Floating Debt", "III. Unfunded Debt", "IV. Foreign Currency Loans4", "V. Naya Pakistan Certificates6"]
wide = get_series(components, start, end)
plot_data = wide if view == "Level" else yoy(wide)
if plot_data.empty or plot_data.dropna(how="all").empty:
    st.info("Domestic-debt components are not available for the selected dates.")
else:
    fig = go.Figure()
    labels = short_labels([str(col) for col in plot_data.columns])
    for col in plot_data.columns:
        fig.add_trace(go.Scatter(x=plot_data.index, y=plot_data[col], name=labels[str(col)], mode="lines", stackgroup="debt" if view == "Level" else None, line={"width": 1.5}))
    fig.update_layout(title="Domestic debt composition" if view == "Level" else "Domestic debt components: year-over-year change", hovermode="x unified")
    fig.update_xaxes(rangeslider={"visible": True})
    fig.update_yaxes(title_text="billion PKR" if view == "Level" else "% YoY", tickformat=",.0f")
    apply_theme(fig)
    st.plotly_chart(fig, width="stretch", config={"displaylogo": False})
    st.caption("SBP · Government Domestic Debt and Liabilities; components are displayed as published.")

st.subheader("Latest published debt composition")
if view == "Level" and not wide.empty:
    latest_date = wide.dropna(how="all").index.max()
    latest_row = wide.loc[latest_date].dropna().reset_index()
    latest_row.columns = ["Instrument", "billion PKR"]
    if not latest_row.empty:
        tree = px.treemap(latest_row, path=["Instrument"], values="billion PKR", color="billion PKR", color_continuous_scale="Tealgrn", title=f"Composition at {latest_date.date()}")
        apply_theme(tree)
        st.plotly_chart(tree, width="stretch", config={"displaylogo": False})
        st.caption("SBP · latest available month; treemap uses only components reported for that month.")
else:
    st.caption("Switch to Level to view the latest-month composition treemap.")

sources = ["mof_general_govt_operations_sdmx", "mof_central_govt_operations_sdmx", "sbp_domestic_debt"]
source_expander(sources)
download_data(filtered_long(source_ids=sources, start=start, end=end), "pide_fiscal_filtered.csv")

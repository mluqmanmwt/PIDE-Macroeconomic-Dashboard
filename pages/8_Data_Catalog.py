"""Catalog, provenance and validation reporting for dashboard users."""
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

from dashboard.lib import apply_theme, date_window, download_data, filtered_long, inject_css, load_index, load_validation, source_expander

st.set_page_config(page_title="Data Catalog | PIDE Macro", page_icon="▦", layout="wide")
inject_css()
st.title("Data catalog and quality checks")
st.write(
    "The catalog documents what is actually available to the dashboard: publisher, official page, frequency, unit and observed coverage. It is designed to make source choice and data limitations visible before an indicator is used in analysis or briefing material."
)
st.caption("Publisher basis shown: all official datasets currently indexed from PBS and SBP; the catalog does not infer additional coverage.")
start, end = date_window("catalog_dates")
index = load_index().copy()

st.subheader("Search the full series catalog")
query = st.text_input("Search by series, dataset, theme or publisher")
view = index.copy()
if query:
    mask = pd.Series(False, index=view.index)
    for col in ["series", "source_id", "dataset", "publisher", "theme", "unit", "frequency"]:
        mask |= view[col].astype(str).str.contains(query, case=False, na=False)
    view = view[mask]
view = view.sort_values(["source_id", "series"])
st.caption(f"Showing {len(view):,} of {len(index):,} indexed entries.")
st.dataframe(
    view[["source_id", "dataset", "publisher", "theme", "series", "unit", "frequency", "start", "end", "n_obs", "page"]],
    hide_index=True,
    width="stretch",
    height=520,
    column_config={"page": st.column_config.LinkColumn("Official page")},
)

st.subheader("Coverage by official dataset")
coverage = index.groupby("source_id", as_index=False).agg(start=("start", "min"), end=("end", "max"), series=("series", "size"), publisher=("publisher", "first"))
coverage = coverage.sort_values("start")
fig = go.Figure()
for row in coverage.itertuples():
    fig.add_trace(go.Scatter(x=[row.start, row.end], y=[row.source_id, row.source_id], mode="lines+markers", line={"width": 12}, marker={"size": 7}, name=row.source_id, showlegend=False, hovertemplate=f"{row.source_id}<br>%{{x|%Y-%m-%d}}<extra></extra>"))
fig.update_layout(title="Observed date coverage", height=max(420, 35 * len(coverage) + 150))
fig.update_xaxes(title_text="Observation date")
fig.update_yaxes(title_text="Dataset", categoryorder="array", categoryarray=coverage["source_id"].tolist())
apply_theme(fig)
st.plotly_chart(fig, width="stretch", config={"displaylogo": False})
st.dataframe(coverage, hide_index=True, width="stretch")

st.subheader("Validation report")
validation = load_validation()
if validation.empty:
    st.success("No validation findings were recorded.")
else:
    st.dataframe(validation, hide_index=True, width="stretch")

source_expander(index["source_id"].unique().tolist())
download_data(filtered_long(start=start, end=end), "pide_catalog_date_filtered_master.csv", "Download all observations in selected date range (CSV)")

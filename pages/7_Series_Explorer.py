"""Flexible, unit-safe explorer for every indexed official series."""
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

from dashboard.lib import date_window, download_data, filtered_long, inject_css, line_chart, load_index, source_expander, yoy

st.set_page_config(page_title="Series Explorer | PIDE Macro", page_icon="▦", layout="wide")
inject_css()
st.title("Series explorer")
st.write(
    "Explore every indexed official series without losing track of its source, frequency or unit. The explorer separates different units into separate charts unless you explicitly normalize series to a common starting value."
)
st.caption("Publisher basis shown: filterable official PBS and SBP datasets. Series names are resolved against the live catalog before data are displayed.")
start, end = date_window("explorer_dates")
index = load_index().copy()

with st.sidebar:
    st.markdown("### Catalog filters")
    theme_choices = sorted(index["theme"].dropna().unique())
    source_choices = sorted(index["source_id"].unique())
    frequency_choices = sorted(index["frequency"].dropna().unique())
    selected_themes = st.multiselect("Theme", theme_choices, default=theme_choices, key="explorer_themes")
    selected_sources = st.multiselect("Dataset", source_choices, default=source_choices, key="explorer_sources")
    selected_freqs = st.multiselect("Frequency", frequency_choices, default=frequency_choices, key="explorer_freqs")
    search = st.text_input("Search series names", key="explorer_search")

catalog = index[index["theme"].isin(selected_themes) & index["source_id"].isin(selected_sources) & index["frequency"].isin(selected_freqs)].copy()
if search:
    catalog = catalog[catalog["series"].str.contains(search, case=False, na=False)]
catalog = catalog.sort_values(["source_id", "series"])
# Source-qualified labels avoid silently merging the few identical literal series
# names that occur in different SBP tables (notably several forms of “Others”).
catalog["label"] = catalog.apply(lambda r: f"{r.source_id} | {r.series} [{r.unit}; {r.frequency}]", axis=1)
st.caption(f"{len(catalog):,} catalog entries match the filters ({len(index):,} indexed entries total). Select up to 20 for legible overlays.")
_options = catalog["label"].tolist()
# The explorer opens with two headline series already plotted. An empty chart area
# on arrival gives no indication of what the control does or what the data look
# like, and the catalog runs to well over a thousand entries, so an unseeded
# multiselect asks the reader to guess a series name before seeing anything. The
# defaults are intersected with the live options because a default that is absent
# from the option list raises, and the option list shrinks as filters are applied.
_preferred = [
    "pbs_cpi_historical | National — inflation",
    "sbp_interest_rates | SBP Policy Rate (target)",
]
# Matched on the exact "source | series" prefix followed by the unit bracket, not
# a bare startswith: 'National — inflation' is also a prefix of
# 'National — inflation (FY average)', so a loose match picked the annual variant
# and returned two CPI series instead of one CPI series and the policy rate.
_defaults = [o for pref in _preferred for o in _options if o.startswith(pref + " [")]
selected_labels = st.multiselect(
    "Series", options=_options, default=_defaults,
    max_selections=20, placeholder="Search and select series",
)
selection = catalog[catalog["label"].isin(selected_labels)].copy()
transform = st.radio("Transformation", ["Level", "YoY change", "Normalize first observation to 100"], horizontal=True)

if selection.empty:
    st.info("Select one or more indexed series to begin. The catalog filters above are applied before the selection list.")
    output = pd.DataFrame(columns=["date", "series", "value", "unit", "source_id", "frequency"])
else:
    frames = []
    for row in selection.itertuples():
        piece = filtered_long(source_ids=[row.source_id], names=[row.series], start=start, end=end)
        # Give traces a source-qualified name only after extracting raw data; CSV
        # exports retain official literal series names and source_id exactly.
        piece["trace_label"] = f"{row.source_id} | {row.series}"
        frames.append(piece)
    output = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if output.empty:
        st.info("No observations are available for the selected dates.")
    elif transform == "Normalize first observation to 100":
        normalized = output.sort_values("date").copy()
        normalized["plot_value"] = normalized.groupby("trace_label")["value"].transform(lambda s: (s / s.dropna().iloc[0] * 100) if not s.dropna().empty else s)
        wide = normalized.pivot(index="date", columns="trace_label", values="plot_value")
        line_chart(wide, "Normalized comparison", "Index (first selected observation = 100)", "Official sources as selected above")
    else:
        # Unit-safe default: every different unit receives its own y-axis/chart.
        # Users can normalize intentionally when they want a dimensionless overlay.
        for unit, group in output.groupby("unit", dropna=False):
            wide = group.pivot(index="date", columns="trace_label", values="value")
            if transform == "YoY change":
                freqs = group.drop_duplicates("trace_label").set_index("trace_label")["frequency"].to_dict()
                wide.attrs["frequencies"] = freqs
                wide = yoy(wide)
            line_chart(wide, f"Selected series — {unit}", "% YoY" if transform == "YoY change" else str(unit), "Official sources as selected above")

source_expander(selection["source_id"].tolist() if not selection.empty else [])
download_data(output.drop(columns=["trace_label", "plot_value"], errors="ignore"), "pide_series_explorer_filtered.csv")

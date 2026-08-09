"""Cross-Indicator Analysis page for the PIDE Macroeconomic Dashboard.

Provides:
- Indicator comparison
- Normalized trend comparison
- Scatter plot
- Correlation coefficient
- Correlation matrix
- CSV download

All data are read from the validated master table through dashboard.lib.
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

# ---------------------------------------------------------------------------
# Make repository root importable when Streamlit executes this page directly.
# ---------------------------------------------------------------------------

_ROOT = _Path(__file__).resolve().parents[2]

if str(_ROOT) not in _sys.path:
    _sys.path.insert(0, str(_ROOT))


import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from dashboard.lib import (
    apply_theme,
    date_window,
    download_data,
    filtered_long,
    inject_css,
    load_index,
    load_master,
    source_expander,
)


# ---------------------------------------------------------------------------
# Page configuration
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Cross-Indicator Analysis | PIDE Macro Dashboard",
    page_icon="◎",
    layout="wide",
    initial_sidebar_state="expanded",
)

inject_css()


# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------

st.title("Cross-Indicator Analysis")

st.write(
    "Explore statistical relationships between Pakistan's macroeconomic "
    "indicators using the validated PIDE master dataset. Select indicators "
    "to compare their trends, examine pairwise relationships, and calculate "
    "correlations."
)

st.info(
    "Correlation measures statistical association between series. "
    "It does not establish economic causality."
)


# ---------------------------------------------------------------------------
# Load metadata/data safely
# ---------------------------------------------------------------------------

try:
    index = load_index()
    master = load_master()
except Exception as exc:
    st.error("The validated dashboard data could not be loaded.")
    st.exception(exc)
    st.stop()


if index.empty or master.empty:
    st.warning(
        "No validated indicator data are currently available. "
        "Run the ETL pipeline first."
    )
    st.stop()


# ---------------------------------------------------------------------------
# Available series
# ---------------------------------------------------------------------------

available_series = (
    index["series"]
    .dropna()
    .astype(str)
    .drop_duplicates()
    .tolist()
)

if not available_series:
    st.warning("No indexed series are available.")
    st.stop()


# ---------------------------------------------------------------------------
# Date range
# ---------------------------------------------------------------------------

start, end = date_window(
    "cross_indicator_dates",
    default_years=10,
)


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _unit_for_series(series_name: str) -> str:
    """Return the indexed unit for a series."""

    rows = index[index["series"].eq(series_name)]

    if rows.empty:
        return ""

    value = rows["unit"].dropna()

    if value.empty:
        return ""

    return str(value.iloc[0])


def _frequency_for_series(series_name: str) -> str:
    """Return the indexed frequency for a series."""

    rows = index[index["series"].eq(series_name)]

    if rows.empty:
        return ""

    value = rows["frequency"].dropna()

    if value.empty:
        return ""

    return str(value.iloc[0])


def _series_frame(names: list[str]) -> pd.DataFrame:
    """Return a date-indexed wide dataframe for selected indicators."""

    if not names:
        return pd.DataFrame()

    data = filtered_long(
        names=names,
        start=start,
        end=end,
    )

    if data.empty:
        return pd.DataFrame()

    data = data.dropna(subset=["date", "value"])

    if data.empty:
        return pd.DataFrame()

    wide = (
        data.pivot_table(
            index="date",
            columns="series",
            values="value",
            aggfunc="last",
        )
        .sort_index()
    )

    return wide


def _normalize_to_100(data: pd.DataFrame) -> pd.DataFrame:
    """Normalize every selected series to 100 at its first valid observation."""

    result = pd.DataFrame(index=data.index)

    for column in data.columns:
        series = pd.to_numeric(data[column], errors="coerce").dropna()

        if series.empty:
            result[column] = np.nan
            continue

        first = float(series.iloc[0])

        if first == 0:
            result[column] = np.nan
        else:
            result[column] = data[column] / first * 100

    return result


def _display_name(name: str) -> str:
    """Create a compact display label while preserving the actual series name."""

    raw = str(name)

    if " | " in raw:
        prefix, remainder = raw.split(" | ", 1)
        return f"{prefix} | {remainder}"

    return raw


def _correlation_label(value: float) -> str:
    """Return a simple interpretation of correlation magnitude."""

    absolute = abs(value)

    if absolute >= 0.80:
        strength = "very strong"
    elif absolute >= 0.60:
        strength = "strong"
    elif absolute >= 0.40:
        strength = "moderate"
    elif absolute >= 0.20:
        strength = "weak"
    else:
        strength = "very weak"

    direction = "positive" if value > 0 else "negative"

    if value == 0:
        direction = "no"

    return f"{strength} {direction} association"


def _build_normalized_chart(data: pd.DataFrame) -> go.Figure:
    """Build normalized comparison chart."""

    fig = go.Figure()

    for column in data.columns:
        fig.add_trace(
            go.Scatter(
                x=data.index,
                y=data[column],
                mode="lines",
                name=_display_name(column),
                hovertemplate=(
                    "%{x|%Y-%m-%d}"
                    "<br>Index: %{y:.2f}"
                    "<extra>%{fullData.name}</extra>"
                ),
            )
        )

    fig.update_layout(
        title="Normalized Indicator Trends",
        xaxis={
            "title": "Date",
            "rangeslider": {"visible": True},
            "type": "date",
        },
        yaxis={
            "title": "Index (first available observation = 100)",
        },
    )

    return apply_theme(fig)


def _build_scatter(
    data: pd.DataFrame,
    x_name: str,
    y_name: str,
) -> tuple[go.Figure, pd.DataFrame]:
    """Build scatter plot using overlapping observations only."""

    pair = data[[x_name, y_name]].dropna().copy()

    pair = pair.sort_index()

    fig = go.Figure()

    fig.add_trace(
        go.Scatter(
            x=pair[x_name],
            y=pair[y_name],
            mode="markers",
            marker={
                "size": 8,
                "opacity": 0.75,
            },
            text=pair.index.strftime("%Y-%m-%d"),
            hovertemplate=(
                "Date: %{text}"
                "<br>X: %{x:,.2f}"
                "<br>Y: %{y:,.2f}"
                "<extra></extra>"
            ),
            name="Observations",
        )
    )

    # Add an ordinary least-squares trend line when enough observations exist.
    if len(pair) >= 3:
        x_values = pair[x_name].astype(float).to_numpy()
        y_values = pair[y_name].astype(float).to_numpy()

        valid = np.isfinite(x_values) & np.isfinite(y_values)

        x_values = x_values[valid]
        y_values = y_values[valid]

        if len(x_values) >= 3 and np.ptp(x_values) != 0:
            slope, intercept = np.polyfit(x_values, y_values, 1)

            x_line = np.linspace(
                float(x_values.min()),
                float(x_values.max()),
                100,
            )

            y_line = slope * x_line + intercept

            fig.add_trace(
                go.Scatter(
                    x=x_line,
                    y=y_line,
                    mode="lines",
                    name="Linear trend",
                    line={
                        "dash": "dash",
                        "width": 2,
                    },
                    hoverinfo="skip",
                )
            )

    fig.update_layout(
        title=f"{_display_name(y_name)} vs {_display_name(x_name)}",
        xaxis_title=_display_name(x_name),
        yaxis_title=_display_name(y_name),
    )

    return apply_theme(fig), pair


# ---------------------------------------------------------------------------
# Section 1 — Pairwise comparison
# ---------------------------------------------------------------------------

st.subheader("1. Compare Two Indicators")

default_a = (
    "National — inflation"
    if "National — inflation" in available_series
    else available_series[0]
)

remaining = [x for x in available_series if x != default_a]

default_b = (
    "Broad Money (M2) (A+B+C)"
    if "Broad Money (M2) (A+B+C)" in remaining
    else remaining[0] if remaining else default_a
)

col1, col2 = st.columns(2)

with col1:
    indicator_a = st.selectbox(
        "Indicator A",
        options=available_series,
        index=available_series.index(default_a),
        key="cross_indicator_a",
    )

with col2:
    indicator_b = st.selectbox(
        "Indicator B",
        options=available_series,
        index=(
            available_series.index(default_b)
            if default_b in available_series
            else 0
        ),
        key="cross_indicator_b",
    )


if indicator_a == indicator_b:
    st.warning("Please select two different indicators.")

else:
    comparison = _series_frame(
        [indicator_a, indicator_b]
    )

    if comparison.empty:
        st.warning(
            "No overlapping observations were found for the selected "
            "indicators and date range."
        )

    else:
        # ---------------------------------------------------------------
        # Basic information
        # ---------------------------------------------------------------

        info1, info2, info3, info4 = st.columns(4)

        overlap = comparison[[indicator_a, indicator_b]].dropna()

        with info1:
            st.metric(
                "Overlapping observations",
                f"{len(overlap):,}",
            )

        with info2:
            st.metric(
                "Indicator A unit",
                _unit_for_series(indicator_a) or "n.a.",
            )

        with info3:
            st.metric(
                "Indicator B unit",
                _unit_for_series(indicator_b) or "n.a.",
            )

        with info4:
            st.metric(
                "Frequency",
                _frequency_for_series(indicator_a) or "n.a.",
            )

        # ---------------------------------------------------------------
        # Normalized trend chart
        # ---------------------------------------------------------------

        st.markdown("### Relative Trend Comparison")

        st.caption(
            "Both series are rebased to 100 at their first overlapping "
            "observation. This allows indicators with different units "
            "and scales to be compared visually."
        )

        normalized = _normalize_to_100(comparison)

        fig = _build_normalized_chart(normalized)

        st.plotly_chart(
            fig,
            width="stretch",
            config={"displaylogo": False},
        )

        # ---------------------------------------------------------------
        # Scatter plot
        # ---------------------------------------------------------------

        st.markdown("### Pairwise Relationship")

        scatter_fig, pair = _build_scatter(
            comparison,
            indicator_a,
            indicator_b,
        )

        if len(pair) >= 2:
            correlation = pair[indicator_a].corr(pair[indicator_b])

            c1, c2 = st.columns(2)

            with c1:
                st.metric(
                    "Pearson correlation",
                    f"{correlation:.3f}"
                    if pd.notna(correlation)
                    else "n.a.",
                )

            with c2:
                if pd.notna(correlation):
                    st.metric(
                        "Interpretation",
                        _correlation_label(float(correlation)),
                    )
                else:
                    st.metric(
                        "Interpretation",
                        "Not available",
                    )

        st.plotly_chart(
            scatter_fig,
            width="stretch",
            config={"displaylogo": False},
        )

        st.caption(
            "The dashed line is a simple linear trend for visual guidance. "
            "It is not an econometric model."
        )

        # ---------------------------------------------------------------
        # Pairwise data table
        # ---------------------------------------------------------------

        with st.expander("View overlapping observations"):
            table = pair.reset_index()

            table["date"] = pd.to_datetime(
                table["date"]
            ).dt.strftime("%Y-%m-%d")

            st.dataframe(
                table,
                hide_index=True,
                width="stretch",
            )

            download_data(
                pair.reset_index(),
                "pide_cross_indicator_pair.csv",
                "Download pairwise observations (CSV)",
            )


# ---------------------------------------------------------------------------
# Section 2 — Correlation matrix
# ---------------------------------------------------------------------------

st.divider()

st.subheader("2. Correlation Matrix")

st.write(
    "Select several indicators to calculate Pearson correlations using "
    "only dates where each pair has overlapping observations."
)

max_matrix_series = min(12, len(available_series))

default_matrix = []

preferred_matrix = [
    "National — inflation",
    "SBP Policy Rate (target)",
    "Broad Money (M2) (A+B+C)",
    "Total liquid FX reserves",
    "Balance of Trade [a-c]",
    "GDP Growth Rate (%)",
    "Total",
]

for candidate in preferred_matrix:
    if candidate in available_series and candidate not in default_matrix:
        default_matrix.append(candidate)

if len(default_matrix) < 2:
    default_matrix = available_series[:max_matrix_series]

matrix_series = st.multiselect(
    "Indicators for correlation matrix",
    options=available_series,
    default=default_matrix[:max_matrix_series],
    max_selections=max_matrix_series,
    key="correlation_matrix_series",
)


if len(matrix_series) < 2:
    st.info("Select at least two indicators.")

else:
    matrix_data = _series_frame(matrix_series)

    if matrix_data.empty:
        st.warning("No data are available for the selected indicators.")

    else:
        correlation_matrix = matrix_data.corr(
            method="pearson",
            min_periods=2,
        )

        # ---------------------------------------------------------------
        # Heatmap
        # ---------------------------------------------------------------

        fig = go.Figure(
            data=go.Heatmap(
                z=correlation_matrix.values,
                x=[
                    _display_name(x)
                    for x in correlation_matrix.columns
                ],
                y=[
                    _display_name(x)
                    for x in correlation_matrix.index
                ],
                zmin=-1,
                zmax=1,
                text=np.round(
                    correlation_matrix.values,
                    2,
                ),
                texttemplate="%{text}",
                hovertemplate=(
                    "%{x}"
                    "<br>%{y}"
                    "<br>Correlation: %{z:.3f}"
                    "<extra></extra>"
                ),
                colorbar={
                    "title": "r",
                },
            )
        )

        fig.update_layout(
            title="Pearson Correlation Matrix",
            xaxis={
                "tickangle": -35,
            },
            yaxis={
                "autorange": "reversed",
            },
            height=max(
                450,
                100 + len(matrix_series) * 45,
            ),
        )

        fig = apply_theme(fig)

        st.plotly_chart(
            fig,
            width="stretch",
            config={"displaylogo": False},
        )

        # ---------------------------------------------------------------
        # Correlation table
        # ---------------------------------------------------------------

        st.markdown("### Correlation Values")

        display_matrix = correlation_matrix.copy()

        display_matrix.columns = [
            _display_name(x)
            for x in display_matrix.columns
        ]

        display_matrix.index = [
            _display_name(x)
            for x in display_matrix.index
        ]

        st.dataframe(
            display_matrix.style.format(
                "{:.3f}",
                na_rep="—",
            ),
            width="stretch",
        )

        # ---------------------------------------------------------------
        # Download matrix
        # ---------------------------------------------------------------

        matrix_download = correlation_matrix.reset_index()

        matrix_download = matrix_download.rename(
            columns={
                matrix_download.columns[0]: "series"
            }
        )

        download_data(
            matrix_download,
            "pide_correlation_matrix.csv",
            "Download correlation matrix (CSV)",
        )


# ---------------------------------------------------------------------------
# Methodology
# ---------------------------------------------------------------------------

st.divider()

with st.expander("Methodology and interpretation"):
    st.markdown(
        """
### How this page calculates relationships

**Normalized comparison**

Each series is rebased to 100 at its first available observation in the
selected overlapping period:

- 100 = starting observation
- Above 100 = increase relative to the starting observation
- Below 100 = decrease relative to the starting observation

This is a visual comparison rather than a change in the original data.

### Pearson correlation

The correlation coefficient ranges from **-1 to +1**:

- **+1** — perfect positive linear association
- **0** — no linear association
- **-1** — perfect negative linear association

Only overlapping non-missing observations are used for each pair.

### Important limitation

Correlation does **not** demonstrate causation. Economic interpretation should
consider timing, frequency, structural breaks, policy changes, seasonality,
and other relevant variables.
"""
    )


# ---------------------------------------------------------------------------
# Sources
# ---------------------------------------------------------------------------

st.divider()

source_ids = (
    index[
        index["series"].isin(
            matrix_series
            if len(matrix_series) >= 2
            else [indicator_a, indicator_b]
        )
    ]["source_id"]
    .dropna()
    .drop_duplicates()
    .tolist()
)

if source_ids:
    source_expander(source_ids)
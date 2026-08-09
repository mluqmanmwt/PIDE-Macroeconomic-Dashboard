"""Policy Context page for the PIDE Macroeconomic Indicator Dashboard.

This page provides:
- Latest SBP policy rate
- Historical policy-rate chart
- Inflation vs policy-rate comparison
- Verified policy-event annotations
- Policy-event timeline
- Source information
- CSV downloads

Important:
The SBP policy rate is an irregular decision-date series, while CPI inflation
is normally monthly. Therefore, the comparison uses the latest known policy
rate on or before each inflation observation date.

Policy events are NEVER inferred from the macroeconomic data. They are loaded
only from:

    data/metadata/policy_events.csv
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

# ---------------------------------------------------------------------------
# Repository root
# ---------------------------------------------------------------------------

_ROOT = _Path(__file__).resolve().parents[2]

if str(_ROOT) not in _sys.path:
    _sys.path.insert(0, str(_ROOT))


# ---------------------------------------------------------------------------
# Third-party imports
# ---------------------------------------------------------------------------

import pandas as pd
import plotly.graph_objects as go
import streamlit as st


# ---------------------------------------------------------------------------
# Dashboard utilities
# ---------------------------------------------------------------------------

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
# Streamlit configuration
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Policy Context | PIDE Macro Dashboard",
    page_icon="◈",
    layout="wide",
    initial_sidebar_state="expanded",
)

inject_css()


# ===========================================================================
# Helper functions
# ===========================================================================


def _find_series(candidates: list[str]) -> str | None:
    """Return the first exact series name available in series_index.csv."""

    try:
        index = load_index()
    except Exception:
        return None

    if index.empty or "series" not in index.columns:
        return None

    available = set(
        index["series"]
        .dropna()
        .astype(str)
    )

    for candidate in candidates:
        if candidate in available:
            return candidate

    return None


def _series_unit(series_name: str) -> str:
    """Return the unit for an indexed series."""

    try:
        index = load_index()
    except Exception:
        return ""

    rows = index[index["series"].eq(series_name)]

    if rows.empty:
        return ""

    if "unit" not in rows.columns:
        return ""

    units = rows["unit"].dropna()

    if units.empty:
        return ""

    return str(units.iloc[0])


def _series_source(series_name: str) -> str:
    """Return the source_id for an indexed series."""

    try:
        index = load_index()
    except Exception:
        return ""

    rows = index[index["series"].eq(series_name)]

    if rows.empty:
        return ""

    if "source_id" not in rows.columns:
        return ""

    return str(rows.iloc[0]["source_id"])


def _display_name(series_name: str) -> str:
    """Create a readable chart label without changing the actual series name."""

    raw = str(series_name)

    if " | " in raw:
        prefix, remainder = raw.split(" | ", 1)
        return f"{prefix} | {remainder}"

    return raw


def _load_policy_events() -> pd.DataFrame:
    """Load optional verified policy events.

    Required columns:

        date
        event_type
        title
        description
        source
    """

    path = _ROOT / "data" / "metadata" / "policy_events.csv"

    if not path.exists():
        return pd.DataFrame()

    try:
        events = pd.read_csv(path)
    except Exception as exc:
        st.warning(
            "The policy_events.csv file exists but could not be read."
        )
        st.caption(str(exc))
        return pd.DataFrame()

    required_columns = {
        "date",
        "event_type",
        "title",
        "description",
        "source",
    }

    missing = required_columns.difference(events.columns)

    if missing:
        st.warning(
            "policy_events.csv is missing required columns: "
            + ", ".join(sorted(missing))
        )
        return pd.DataFrame()

    events = events.copy()

    events["date"] = pd.to_datetime(
        events["date"],
        errors="coerce",
    )

    events = events.dropna(subset=["date"])

    for column in (
        "event_type",
        "title",
        "description",
        "source",
    ):
        events[column] = (
            events[column]
            .fillna("")
            .astype(str)
        )

    return (
        events
        .sort_values("date")
        .reset_index(drop=True)
    )


def _prepare_series(
    series_name: str,
    start: pd.Timestamp | None = None,
    end: pd.Timestamp | None = None,
) -> pd.DataFrame:
    """Return a clean date/value dataframe for one exact series."""

    data = filtered_long(
        names=[series_name],
        start=start,
        end=end,
    )

    if data.empty:
        return pd.DataFrame(
            columns=[
                "date",
                "value",
            ]
        )

    data = data[
        [
            "date",
            "value",
        ]
    ].copy()

    data["date"] = pd.to_datetime(
        data["date"],
        errors="coerce",
    )

    data["value"] = pd.to_numeric(
        data["value"],
        errors="coerce",
    )

    data = data.dropna(
        subset=[
            "date",
            "value",
        ]
    )

    return (
        data
        .sort_values("date")
        .drop_duplicates(
            subset=["date"],
            keep="last",
        )
        .reset_index(drop=True)
    )


def _policy_rate_chart(
    policy_data: pd.DataFrame,
    policy_series: str,
    events: pd.DataFrame,
) -> go.Figure:
    """Create the historical policy-rate chart."""

    fig = go.Figure()

    fig.add_trace(
        go.Scatter(
            x=policy_data["date"],
            y=policy_data["value"],
            mode="lines+markers",
            name=_display_name(policy_series),
            line={
                "width": 2.5,
            },
            marker={
                "size": 5,
            },
            hovertemplate=(
                "%{x|%Y-%m-%d}"
                "<br>Policy rate: %{y:.2f}%"
                "<extra></extra>"
            ),
        )
    )

    # Verified policy events
    if not events.empty:

        min_date = policy_data["date"].min()
        max_date = policy_data["date"].max()

        for _, event in events.iterrows():

            event_date = pd.Timestamp(event["date"])

            if event_date < min_date or event_date > max_date:
                continue

            fig.add_vline(
                x=event_date,
                line_width=1,
                line_dash="dot",
                opacity=0.65,
            )

            fig.add_annotation(
                x=event_date,
                y=1,
                yref="paper",
                text=str(event["title"]),
                showarrow=False,
                textangle=-90,
                yanchor="top",
                xanchor="left",
                font={
                    "size": 9,
                },
            )

    fig.update_layout(
        title="SBP Policy Rate",
        xaxis={
            "title": "Date",
            "type": "date",
            "rangeslider": {
                "visible": True,
            },
        },
        yaxis={
            "title": _series_unit(policy_series) or "Policy Rate (%)",
        },
    )

    return apply_theme(fig)


def _build_aligned_inflation_policy_data(
    inflation_series: str,
    policy_series: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> pd.DataFrame:
    """Align inflation observations with the latest applicable policy rate.

    Example:

        Inflation date: 2026-04-01
        Policy decision: 2026-04-28

    The April inflation observation cannot use the April 28 rate if that rate
    was announced after the inflation observation. Therefore, merge_asof with
    direction='backward' selects the latest policy rate available ON or BEFORE
    each inflation observation.

    The returned dataframe ALWAYS has these normalized columns:

        date
        inflation
        policy_rate

    This prevents the KeyError caused by trying to access the original series
    name after the data had already been normalized.
    """

    # -----------------------------------------------------------------------
    # Inflation data
    # -----------------------------------------------------------------------

    inflation_data = _prepare_series(
        inflation_series,
        start=start,
        end=end,
    )

    if inflation_data.empty:
        return pd.DataFrame(
            columns=[
                "date",
                "inflation",
                "policy_rate",
            ]
        )

    inflation_data = inflation_data.rename(
        columns={
            "value": "inflation",
        }
    )

    # -----------------------------------------------------------------------
    # Policy-rate data
    #
    # IMPORTANT:
    # We intentionally do NOT restrict policy data to "start" here.
    #
    # Suppose the selected period starts at 2020-01-01, but the previous
    # policy-rate decision was 2019-12-20. That 2019-12-20 rate is still the
    # applicable rate for January 2020.
    # -----------------------------------------------------------------------

    policy_data = _prepare_series(
        policy_series,
        end=end,
    )

    if policy_data.empty:
        return pd.DataFrame(
            columns=[
                "date",
                "inflation",
                "policy_rate",
            ]
        )

    policy_data = policy_data.rename(
        columns={
            "value": "policy_rate",
        }
    )

    # -----------------------------------------------------------------------
    # Sort before merge_asof
    # -----------------------------------------------------------------------

    inflation_data = inflation_data.sort_values("date")
    policy_data = policy_data.sort_values("date")

    # -----------------------------------------------------------------------
    # Latest policy rate available on or before inflation date
    # -----------------------------------------------------------------------

    aligned = pd.merge_asof(
        inflation_data[
            [
                "date",
                "inflation",
            ]
        ],
        policy_data[
            [
                "date",
                "policy_rate",
            ]
        ],
        on="date",
        direction="backward",
    )

    aligned = aligned.dropna(
        subset=[
            "inflation",
            "policy_rate",
        ]
    )

    if aligned.empty:
        return pd.DataFrame(
            columns=[
                "date",
                "inflation",
                "policy_rate",
            ]
        )

    return (
        aligned
        .sort_values("date")
        .reset_index(drop=True)
    )


def _inflation_policy_chart(
    data: pd.DataFrame,
    inflation_series: str,
    policy_series: str,
    events: pd.DataFrame,
) -> go.Figure:
    """Create inflation vs policy-rate chart.

    IMPORTANT:
    `data` is the normalized dataframe produced by
    `_build_aligned_inflation_policy_data()`.

    Therefore its columns are:

        date
        inflation
        policy_rate

    We must NOT access:
        data[inflation_series]
        data[policy_series]

    because those are the original series names, not the normalized column
    names.
    """

    fig = go.Figure()

    # -----------------------------------------------------------------------
    # Inflation
    # -----------------------------------------------------------------------

    fig.add_trace(
        go.Scatter(
            x=data["date"],
            y=data["inflation"],
            mode="lines+markers",
            name=_display_name(inflation_series),
            line={
                "width": 2.5,
            },
            marker={
                "size": 4,
            },
            hovertemplate=(
                "%{x|%Y-%m-%d}"
                "<br>Inflation: %{y:.2f}%"
                "<extra></extra>"
            ),
        )
    )

    # -----------------------------------------------------------------------
    # Policy rate
    # -----------------------------------------------------------------------

    fig.add_trace(
        go.Scatter(
            x=data["date"],
            y=data["policy_rate"],
            mode="lines",
            name=_display_name(policy_series),
            yaxis="y2",
            line={
                "width": 2.5,
                "dash": "dash",
            },
            hovertemplate=(
                "%{x|%Y-%m-%d}"
                "<br>Policy rate: %{y:.2f}%"
                "<extra></extra>"
            ),
        )
    )

    # -----------------------------------------------------------------------
    # Verified policy events
    # -----------------------------------------------------------------------

    if not events.empty:

        min_date = data["date"].min()
        max_date = data["date"].max()

        for _, event in events.iterrows():

            event_date = pd.Timestamp(event["date"])

            if event_date < min_date or event_date > max_date:
                continue

            fig.add_vline(
                x=event_date,
                line_width=1,
                line_dash="dot",
                opacity=0.5,
            )

            fig.add_annotation(
                x=event_date,
                y=1,
                yref="paper",
                text=str(event["title"]),
                showarrow=False,
                textangle=-90,
                yanchor="top",
                xanchor="left",
                font={
                    "size": 8,
                },
            )

    # -----------------------------------------------------------------------
    # Layout
    # -----------------------------------------------------------------------

    fig.update_layout(
        title="Inflation vs Policy Rate",
        xaxis={
            "title": "Date",
            "type": "date",
            "rangeslider": {
                "visible": True,
            },
        },
        yaxis={
            "title": _series_unit(inflation_series) or "Inflation (%)",
            "side": "left",
        },
        yaxis2={
            "title": _series_unit(policy_series) or "Policy Rate (%)",
            "overlaying": "y",
            "side": "right",
        },
    )

    return apply_theme(fig)


def _events_table(events: pd.DataFrame) -> pd.DataFrame:
    """Prepare policy events for Streamlit display."""

    if events.empty:
        return pd.DataFrame()

    output = events.copy()

    output["Date"] = output["date"].dt.strftime(
        "%Y-%m-%d"
    )

    output["Event Type"] = output["event_type"]
    output["Title"] = output["title"]
    output["Description"] = output["description"]
    output["Official Source"] = output["source"]

    return output[
        [
            "Date",
            "Event Type",
            "Title",
            "Description",
            "Official Source",
        ]
    ]


# ===========================================================================
# PAGE HEADER
# ===========================================================================

st.title("Policy Context")

st.write(
    "Place major monetary and fiscal policy events alongside Pakistan's "
    "macroeconomic indicators to help researchers interpret changes in "
    "inflation and other series."
)

st.caption(
    "Policy events shown on this page are based only on verified official "
    "announcements. The dashboard does not invent or infer policy events "
    "from the data."
)


# ===========================================================================
# LOAD CORE DATA
# ===========================================================================

try:

    index = load_index()
    master = load_master()

except Exception as exc:

    st.error(
        "The validated macroeconomic data could not be loaded."
    )

    st.exception(exc)

    st.stop()


if index.empty:

    st.warning(
        "series_index.csv is empty. No indexed indicators are available."
    )

    st.stop()


if master.empty:

    st.warning(
        "macro_master.parquet is empty. No validated observations are available."
    )

    st.stop()


# ===========================================================================
# DATE RANGE
# ===========================================================================

start, end = date_window(
    "policy_context_dates",
    default_years=10,
)


# ===========================================================================
# FIND REQUIRED INDICATORS
# ===========================================================================

policy_rate_series = _find_series(
    [
        "SBP Policy Rate (target)",
        "SBP Policy Rate",
        "Policy Rate",
    ]
)

inflation_series = _find_series(
    [
        "National — inflation",
        "National CPI inflation",
        "CPI Inflation",
    ]
)


# ===========================================================================
# LOAD VERIFIED EVENTS
# ===========================================================================

policy_events = _load_policy_events()

if not policy_events.empty:

    events_in_window = policy_events[
        (policy_events["date"] >= start)
        & (policy_events["date"] <= end)
    ].copy()

else:

    events_in_window = pd.DataFrame()


# ===========================================================================
# 1. MONETARY POLICY
# ===========================================================================

st.subheader("1. Monetary Policy")


if policy_rate_series is None:

    st.warning(
        "The SBP policy-rate series could not be found in "
        "data/metadata/series_index.csv."
    )

else:

    policy_data = _prepare_series(
        policy_rate_series,
        start=start,
        end=end,
    )

    if policy_data.empty:

        st.info(
            "No policy-rate observations are available for the "
            "selected date range."
        )

    else:

        latest_policy = policy_data.iloc[-1]

        col1, col2, col3 = st.columns(3)

        with col1:

            st.metric(
                "Latest policy rate",
                f"{latest_policy['value']:,.2f}%",
            )

        with col2:

            st.metric(
                "Latest observation",
                pd.Timestamp(
                    latest_policy["date"]
                ).strftime("%Y-%m-%d"),
            )

        with col3:

            st.metric(
                "Unit",
                _series_unit(policy_rate_series) or "%",
            )

        policy_fig = _policy_rate_chart(
            policy_data=policy_data,
            policy_series=policy_rate_series,
            events=events_in_window,
        )

        st.plotly_chart(
            policy_fig,
            width="stretch",
            config={
                "displaylogo": False,
            },
        )

        st.caption(
            "Policy rate observations are taken directly from the "
            "validated master dataset."
        )


# ===========================================================================
# 2. INFLATION VS POLICY RATE
# ===========================================================================

st.divider()

st.subheader("2. Inflation and Monetary Policy")


if inflation_series is None:

    st.warning(
        "The national inflation series could not be found in "
        "data/metadata/series_index.csv."
    )

elif policy_rate_series is None:

    st.warning(
        "The SBP policy-rate series could not be found in "
        "data/metadata/series_index.csv."
    )

else:

    aligned_data = _build_aligned_inflation_policy_data(
        inflation_series=inflation_series,
        policy_series=policy_rate_series,
        start=start,
        end=end,
    )

    if aligned_data.empty:

        st.info(
            "There are no aligned inflation and policy-rate observations "
            "for the selected date range."
        )

    else:

        inflation_policy_fig = _inflation_policy_chart(
            data=aligned_data,
            inflation_series=inflation_series,
            policy_series=policy_rate_series,
            events=events_in_window,
        )

        st.plotly_chart(
            inflation_policy_fig,
            width="stretch",
            config={
                "displaylogo": False,
            },
        )

        st.caption(
            "Inflation is normally reported monthly, while the SBP policy "
            "rate is recorded on decision dates. Each inflation observation "
            "is therefore matched with the latest policy rate available on "
            "or before that date."
        )

        # ---------------------------------------------------------------
        # Aligned data table
        # ---------------------------------------------------------------

        with st.expander(
            "View aligned inflation and policy-rate data",
            expanded=False,
        ):

            table = aligned_data.copy()

            table["date"] = pd.to_datetime(
                table["date"]
            ).dt.strftime("%Y-%m-%d")

            table = table.rename(
                columns={
                    "date": "Date",
                    "inflation": "Inflation (%)",
                    "policy_rate": "Policy Rate (%)",
                }
            )

            st.dataframe(
                table,
                hide_index=True,
                width="stretch",
            )


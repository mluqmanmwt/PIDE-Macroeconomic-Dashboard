"""Shared utilities for the PIDE Macroeconomic Indicator Dashboard.

The app reads only the validated master table and its ETL metadata.  Helpers
resolve series against the index before plotting so a partial ETL run degrades
into an explicit empty state rather than a broken page.
"""
from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from typing import Callable, Iterable, Sequence

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
MASTER_PATH = DATA_DIR / "processed" / "macro_master.parquet"
INDEX_PATH = DATA_DIR / "metadata" / "series_index.csv"
MANIFEST_PATH = DATA_DIR / "metadata" / "manifest.json"
VALIDATION_PATH = DATA_DIR / "metadata" / "validation_report.csv"
CACHE_TTL = 15 * 60

# Pakistan-inspired but restrained.  The darker green and charcoal remain clear
# on projectors; warm amber/red are reserved for genuinely distinct data lines.
PALETTE = ["#0B5D4B", "#176B87", "#C17A19", "#9E3D35", "#6B5B95", "#2F7F73", "#765D45", "#B04A5A"]


def _mtime(path: Path) -> float:
    """Expose the file timestamp to cached functions, invalidating after ETL."""
    return path.stat().st_mtime


@st.cache_data(ttl=CACHE_TTL, show_spinner="Loading validated macro data…")
def _read_master(_: float) -> pd.DataFrame:
    df = pd.read_parquet(MASTER_PATH)
    df["date"] = pd.to_datetime(df["date"])
    return df


def load_master() -> pd.DataFrame:
    """Return the validated tidy master table; refresh automatically after ETL."""
    return _read_master(_mtime(MASTER_PATH))


@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def _read_index(_: float) -> pd.DataFrame:
    df = pd.read_csv(INDEX_PATH)
    for col in ("start", "end"):
        df[col] = pd.to_datetime(df[col], errors="coerce")
    return df


def load_index() -> pd.DataFrame:
    return _read_index(_mtime(INDEX_PATH))


@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def _read_manifest(_: float) -> dict:
    with MANIFEST_PATH.open(encoding="utf-8") as fh:
        return json.load(fh)


def load_manifest() -> dict:
    return _read_manifest(_mtime(MANIFEST_PATH))


@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def _read_validation(_: float) -> pd.DataFrame:
    return pd.read_csv(VALIDATION_PATH)


def load_validation() -> pd.DataFrame:
    return _read_validation(_mtime(VALIDATION_PATH))


def existing_names(names: Iterable[str]) -> list[str]:
    """Keep only exact strings that the current index verifies."""
    available = set(load_index()["series"])
    return [name for name in names if name in available]


def resolve_sdmx_code(source_id: str, code: str) -> str | None:
    """Resolve a verified full series name from a source-specific SDMX code.

    SDMX descriptors are intentionally retained verbatim in storage and
    exports.  Pages may use this helper to select a stable official code while
    still passing an exact full-name match to the master table.
    """
    pattern = re.escape(f"[{code}]")
    rows = load_index()
    match = rows[rows["source_id"].eq(source_id) & rows["series"].str.contains(pattern, regex=True, na=False)]
    return str(match["series"].iloc[0]) if not match.empty else None


def _code_suffix(series: str) -> str | None:
    match = re.search(r"\[([^\]]+)\]", series)
    return match.group(1) if match else None


# Longest legend entry that fits the chart width at the default layout.
_MAX_LABEL = 38


def _clip(label: str) -> str:
    """Shorten to the label budget on a word boundary, marking the elision.

    Truncating at a fixed character count cuts words in half ('Fishin…'), which
    reads as a rendering fault rather than as a deliberate abbreviation.
    """
    if len(label) <= _MAX_LABEL:
        return label
    cut = label[:_MAX_LABEL]
    if " " in cut[max(0, _MAX_LABEL - 14):]:
        cut = cut[:cut.rstrip().rfind(" ")]
    return cut.rstrip(" ·,;:-") + "\u2026"


def short_label(series: str) -> str:
    """Return a compact display label without ever changing the raw series name.

    SDMX descriptors can be several hundred characters long.  A useful legend
    normally needs the meaningful terminal hierarchy (for example “Revenue and
    grants · Revenue”), not repeated concepts such as National Currency or
    SDMX's base-period annotation.  The full official descriptor remains in
    hover text, catalog tables, and CSV exports.
    """
    raw = re.sub(r"\s+", " ", str(series)).strip()
    without_code = re.sub(r"\s*\[[^\]]+\]", "", raw)
    without_metadata = re.sub(r"\s*\(BASE_PER=[^)]+\)", "", without_code, flags=re.IGNORECASE)
    # SBP appends a classification range to sector names ('( 1 to 3 )'), which
    # identifies the aggregate but means nothing to a reader of the legend.
    without_metadata = re.sub(r"\s*\(\s*\d+\s+to\s+\d+\s*\)", "", without_metadata)

    # Comma-splitting only makes sense for SDMX descriptors, where commas separate
    # levels of a concept hierarchy. Ordinary published names also contain commas
    # that are part of the name itself: splitting 'Agriculture, Forestry and
    # Fishing' produced the nonsense 'Agriculture · Forestry and Fishin…'. SDMX
    # descriptors are identified by their trailing [CODE] and their depth, so
    # anything shallower is left exactly as published.
    parts = [re.sub(r"\s+", " ", part).strip(" /") for part in without_metadata.split(",")]
    is_sdmx_descriptor = raw != without_code or len(parts) >= 4
    if not is_sdmx_descriptor:
        label = without_metadata.strip()
        return (label if len(label) <= _MAX_LABEL
                else _clip(label))
    # Boilerplate that every indicator in a feed repeats carries no information
    # in a legend where all the lines share it.
    ignored = {
        "national currency", "fiscal year", "number of", "index",
        "nominal", "real", "value", "by central product classification (cpc) version 2.1",
        "pakistan definition", "persons", "perso", "domestic currency",
        "general government operations", "central government operations",
        "labor markets", "labour markets", "prices", "external trade",
        "national accounts", "monetary", "seasonally adjusted",
    }
    meaningful = [part for part in parts if part and part.lower() not in ignored]
    if not meaningful:
        # Everything was boilerplate, so fall back to the tail of the raw text
        # rather than returning nothing.
        meaningful = [part for part in parts if part][-2:] or [raw]

    # Two segments, not three. A horizontal Plotly legend does not ellipsize: it
    # runs past the plotting area and the last entry is clipped mid-word, which
    # is how 'Unemployment, Persons' rendered as 'Unemployment · Perso'.
    label = " \u00b7 ".join(meaningful[-2:])
    return label if len(label) <= _MAX_LABEL else _clip(label)


def short_labels(series_names: Sequence[str]) -> dict[str, str]:
    """Create collision-safe display labels for a collection of raw names."""
    labels: dict[str, str] = {}
    for name in series_names:
        prefix, raw = (str(name).split(" | ", 1) if " | " in str(name) else ("", str(name)))
        compact = short_label(raw)
        labels[str(name)] = f"{prefix} | {compact}" if prefix else compact
    counts = pd.Series(list(labels.values())).value_counts()
    for name, label in list(labels.items()):
        if counts[label] > 1:
            code = _code_suffix(str(name))
            # Reattaching the official code is explicit and stable; it prevents
            # two different SDMX lines from becoming indistinguishable in a legend.
            labels[name] = f"{label} [{code}]" if code else f"{label} — {name}"
    return labels


def get_series(names: Sequence[str], start=None, end=None) -> pd.DataFrame:
    """Fetch exact indexed series as a date × series wide frame.

    Literal series names are intentionally required.  The catalog has a few
    duplicate names across sources (for example ``Others``), so thematic pages
    never use ambiguous labels.  ``pivot_table`` is defensive for an occasional
    duplicate observation in an upstream file, not an interpolation method.
    """
    valid = existing_names(names)
    if not valid:
        return pd.DataFrame(index=pd.DatetimeIndex([], name="date"))
    df = load_master()
    out = df[df["series"].isin(valid)].copy()
    if start is not None:
        out = out[out["date"] >= pd.Timestamp(start)]
    if end is not None:
        out = out[out["date"] <= pd.Timestamp(end)]
    if out.empty:
        return pd.DataFrame(index=pd.DatetimeIndex([], name="date"))
    wide = out.pivot_table(index="date", columns="series", values="value", aggfunc="last").sort_index()
    frequencies = (
        out.sort_values("date").groupby("series")["frequency"].agg(lambda x: x.dropna().iloc[-1] if not x.dropna().empty else "monthly")
    )
    wide.attrs["frequencies"] = frequencies.to_dict()
    wide.attrs["units"] = out.groupby("series")["unit"].agg(lambda x: x.dropna().iloc[-1] if not x.dropna().empty else "").to_dict()
    return wide


def filtered_long(source_ids: Sequence[str] | None = None, names: Sequence[str] | None = None, start=None, end=None) -> pd.DataFrame:
    """Return exact raw observations for CSV download and source-specific work."""
    df = load_master()
    if source_ids:
        df = df[df["source_id"].isin(source_ids)]
    if names:
        df = df[df["series"].isin(existing_names(names))]
    if start is not None:
        df = df[df["date"] >= pd.Timestamp(start)]
    if end is not None:
        df = df[df["date"] <= pd.Timestamp(end)]
    return df.sort_values(["date", "source_id", "series"]).reset_index(drop=True)


def latest(series_name: str):
    """Return (date, value, unit) for the latest available observation, or None."""
    data = filtered_long(names=[series_name])
    if data.empty:
        return None
    row = data.dropna(subset=["value"]).sort_values("date").iloc[-1]
    return pd.Timestamp(row["date"]), float(row["value"]), str(row["unit"])


def _periods_for_frequency(frequency: str) -> int:
    return {"monthly": 12, "quarterly": 4, "annual": 1, "weekly": 52, "daily": 365}.get(str(frequency).lower(), 1)


def yoy(df: pd.DataFrame) -> pd.DataFrame:
    """Calculate percent change against the same observation period a year earlier.

    This intentionally uses the published frequency rather than a generic
    12-row shift: quarterly and annual data would otherwise be misinterpreted.
    Irregular policy/auction data lack a reliable annual period and are left as
    missing rather than manufacturing a comparison.
    """
    if df.empty:
        return df.copy()
    freqs = df.attrs.get("frequencies", {})
    result = pd.DataFrame(index=df.index)
    for col in df.columns:
        freq = str(freqs.get(col, "monthly")).lower()
        if freq == "irregular":
            result[col] = pd.NA
        else:
            result[col] = df[col].pct_change(periods=_periods_for_frequency(freq), fill_method=None) * 100
    result.attrs = df.attrs.copy()
    result.attrs["units"] = {col: "% YoY" for col in result.columns}
    return result


def _format_value(value: float, fmt: str | Callable[[float], str]) -> str:
    if callable(fmt):
        return fmt(value)
    try:
        return fmt.format(value)
    except (ValueError, KeyError):
        return f"{value:,.2f}"


def kpi_card(label: str, series_name: str, fmt: str | Callable[[float], str],
             help_text: str, source_id: str | None = None) -> None:
    """Render a resilient latest-value KPI with annual-period comparison.

    ``source_id`` pins the card to one dataset. Several official series carry
    short, generic names ('Total', 'Others') that are unique today but would
    silently start averaging two different indicators together if a future
    release introduced the same label in another dataset.
    """
    data = filtered_long(names=[series_name],
                         source_ids=[source_id] if source_id else None)
    if data.empty or series_name not in set(load_index()["series"]):
        st.metric(label, "n.a.", help=help_text)
        return
    data = data.dropna(subset=["value"]).sort_values("date")
    if data.empty:
        st.metric(label, "n.a.", help=help_text)
        return
    last = data.iloc[-1]
    freq = str(last["frequency"]).lower()
    prior = None
    if freq != "irregular":
        n = _periods_for_frequency(freq)
        if len(data) > n:
            prior = float(data.iloc[-(n + 1)]["value"])
    delta = None if prior is None else float(last["value"]) - prior
    # The delta is formatted to match the magnitude of the level it sits under. A
    # fixed two decimals prints '+4,592,093.02' beside a million-rupee stock,
    # where the pretend precision is noise, while rounding to whole numbers would
    # erase a rate change of half a point. Percentage-unit series get 'pp' so a
    # change in a rate is not misread as a percentage change of that rate.
    unit = str(last["unit"]).strip()
    if delta is None:
        delta_text = None
    else:
        if abs(delta) >= 1_000:
            body = f"{delta:+,.0f}"
        elif abs(delta) >= 10:
            body = f"{delta:+,.1f}"
        else:
            body = f"{delta:+,.2f}"
        suffix = " pp" if unit in {"%", "% YoY", "percent"} else ""
        delta_text = f"{body}{suffix} vs year earlier"
    st.metric(label, _format_value(float(last["value"]), fmt), delta=delta_text, help=help_text)
    st.caption(f"Latest: {pd.Timestamp(last['date']).date()} · {last['unit']}")


def apply_theme(fig: go.Figure) -> go.Figure:
    """Apply projector-friendly, low-ink Plotly defaults consistently."""
    fig.update_layout(
        template="plotly_white",
        colorway=PALETTE,
        paper_bgcolor="#FFFFFF",
        plot_bgcolor="#FFFFFF",
        font={"family": "Source Sans 3, Arial, sans-serif", "color": "#202B32", "size": 13},
        title={"font": {"size": 18, "color": "#163B34"}, "x": 0.01, "xanchor": "left",
               "y": 0.97, "yanchor": "top"},
        hovermode="x unified",
        hoverlabel={"bgcolor": "#173E36", "font_color": "#FFFFFF"},
        # Generous top margin because the legend occupies its own band above the
        # plot and may wrap to a second row; the charts carry a range slider, so
        # there is no usable space for a legend below the x-axis.
        margin={"l": 54, "r": 28, "t": 92, "b": 48},
        # entrywidthmode/entrywidth give every legend entry a fixed share of the
        # figure width, which is what makes a horizontal legend WRAP onto another
        # row. Without it Plotly lays all entries on one line and simply clips
        # whatever runs past the plotting area, truncating the last label
        # mid-word ('Revenue' rendered as 'Revenu').
        legend={
            "orientation": "h", "yanchor": "bottom", "y": 1.0, "x": 0,
            "xanchor": "left", "font": {"size": 11},
            "entrywidthmode": "fraction", "entrywidth": 0.33,
            "bgcolor": "rgba(0,0,0,0)", "borderwidth": 0,
        },
    )
    fig.update_xaxes(showgrid=False, linecolor="#C9D3D1", tickfont={"size": 12})
    fig.update_yaxes(gridcolor="#E6ECEA", zerolinecolor="#C9D3D1", tickfont={"size": 12})
    return fig


def _tick_format(values: pd.Series) -> str:
    """Pick a tick format with enough precision for the range actually plotted.

    A fixed ',.0f' rounds every tick to a whole number, so a series confined to a
    narrow band - an unemployment rate moving between 5.9 and 7.1 - renders its
    axis as 6, 6, 6, 7, 7 and reads as a broken chart rather than a small range.
    """
    clean = pd.to_numeric(pd.Series(values).dropna(), errors="coerce").dropna()
    if clean.empty:
        return ",.0f"
    spread = float(clean.max() - clean.min())
    if spread == 0:
        spread = abs(float(clean.iloc[0])) or 1.0
    if spread >= 20:
        return ",.0f"
    if spread >= 2:
        return ",.1f"
    return ",.2f"


def fy_shading(fig: go.Figure) -> go.Figure:
    """Lightly shade July–June fiscal years without obscuring the observations."""
    years = pd.date_range("2000-07-01", pd.Timestamp.today() + pd.DateOffset(years=1), freq="YS-JUL")
    for i, start in enumerate(years):
        if i % 2 == 0:
            fig.add_vrect(x0=start, x1=start + pd.DateOffset(years=1), fillcolor="#0B5D4B", opacity=0.035, line_width=0, layer="below")
    return fig


def line_chart(df: pd.DataFrame, title: str, unit: str, source_note: str, *, step: bool = False, fy: bool = False) -> go.Figure | None:
    """Render a standardized line chart and an attributable official-source caption."""
    if df.empty or df.dropna(how="all").empty:
        st.info("Not available for the selected dates.")
        return None
    fig = go.Figure()
    display = short_labels([str(col) for col in df.columns])
    for i, col in enumerate(df.columns):
        full_name = str(col)
        fig.add_trace(
            go.Scatter(
                x=df.index,
                y=df[col],
                name=display[full_name],
                meta=f"Full series: {full_name}",
                hovertemplate="%{x|%Y-%m-%d}<br>%{y:,.2f}<br>%{meta}<extra>%{fullData.name}</extra>",
                mode="lines",
                line={"width": 2.4, "color": PALETTE[i % len(PALETTE)], "shape": "hv" if step else "linear"},
            )
        )
    fig.update_layout(title=title, xaxis={"rangeslider": {"visible": True}, "type": "date"})
    fig.update_yaxes(title_text=unit)
    apply_theme(fig)
    fig.update_yaxes(tickformat=_tick_format(df.stack(future_stack=True)))
    if fy:
        fy_shading(fig)
    st.plotly_chart(fig, width="stretch", config={"displaylogo": False})
    # Keep every chart attributable at the point of interpretation.  Explorer
    # traces are source-qualified labels, whereas thematic charts use literal
    # series names, so support both forms when looking up official page URLs.
    literal_names = list(df.columns)
    qualified_sources = [str(col).split(" | ", 1)[0] for col in literal_names if " | " in str(col)]
    catalog = load_index()
    matched = catalog[catalog["series"].isin(literal_names) | catalog["source_id"].isin(qualified_sources)]
    urls = matched["page"].dropna().drop_duplicates().tolist()
    links = " · ".join(f"[official source page]({url})" for url in urls)
    st.caption(f"{source_note}{' · ' + links if links else ''}")
    return fig


def date_window(key: str, *, default_years: int = 10) -> tuple[pd.Timestamp, pd.Timestamp]:
    """Shared date selector constrained to the actual master-table coverage."""
    master = load_master()
    max_date = pd.Timestamp(master["date"].max()).normalize()
    min_date = pd.Timestamp(master["date"].min()).normalize()
    start = max(min_date, max_date - pd.DateOffset(years=default_years))
    st.sidebar.caption("Charts are clipped to this window.")
    selected = st.sidebar.date_input(
        "Date range",
        value=(start.date(), max_date.date()),
        min_value=min_date.date(), max_value=max_date.date(), key=key,
    )
    if not isinstance(selected, tuple) or len(selected) != 2:
        return start, max_date
    return pd.Timestamp(selected[0]), pd.Timestamp(selected[1])


def source_expander(source_ids: Sequence[str]) -> None:
    """Show publisher and official dataset page for every dataset used on a page."""
    idx = load_index()
    meta = idx[idx["source_id"].isin(source_ids)].drop_duplicates("source_id")
    with st.expander("Sources", expanded=False):
        if meta.empty:
            st.write("No indexed source is available for this view.")
        else:
            for row in meta.sort_values("source_id").itertuples():
                st.markdown(f"- **{row.source_id}** — {str(row.publisher).upper()} · [official dataset page]({row.page})")


def download_data(df: pd.DataFrame, filename: str, label: str = "Download filtered data (CSV)") -> None:
    """Offer the exact post-filter observations, never chart-only approximations."""
    export = df.copy()
    if "date" in export.columns:
        export["date"] = pd.to_datetime(export["date"]).dt.strftime("%Y-%m-%d")
    st.download_button(label, data=export.to_csv(index=False).encode("utf-8"), file_name=filename, mime="text/csv")


def series_unit(name: str, default: str = "Value") -> str:
    row = load_index()[load_index()["series"].eq(name)]
    return str(row["unit"].iloc[0]) if not row.empty else default


def inject_css() -> None:
    """Compact, accessible polish that keeps Streamlit controls familiar."""
    st.markdown(
        """<style>
        @import url('https://fonts.googleapis.com/css2?family=Source+Sans+3:wght@400;600;700&family=Source+Serif+4:opsz,wght@8..60,600&display=swap');
        .stApp { background: #f7f8f6; color: #202B32; }
        [data-testid="stSidebar"] { background: #173E36; }
        /* Light-on-dark for sidebar chrome, but NOT for form controls. A blanket
           `*` rule here also recolours the text inside the date picker, which
           keeps its white background - producing white-on-white input text that
           looks like an empty, broken widget. Inputs are therefore excluded and
           given explicit dark text. */
        [data-testid="stSidebar"] *:not(input):not(textarea):not(select) { color: #F6F8F5 !important; }
        [data-testid="stSidebar"] input,
        [data-testid="stSidebar"] textarea,
        [data-testid="stSidebar"] [data-baseweb="select"] * { color: #202B32 !important; }
        [data-testid="stSidebar"] [data-baseweb="input"],
        [data-testid="stSidebar"] [data-baseweb="select"] > div { background: #FFFFFF; }
        h1 { font-family: 'Source Serif 4', Georgia, serif; color: #163B34; letter-spacing: -0.015em; }
        h2, h3 { color: #163B34; }
        [data-testid="stMetric"] { background: #FFFFFF; border: 1px solid #D9E2DF; border-radius: 8px; padding: 0.8rem 0.9rem; min-height: 124px; }
        [data-testid="stMetricLabel"] { color: #53635F; font-weight: 700; }
        [data-testid="stMetricValue"] { color: #163B34; font-variant-numeric: tabular-nums; }
        .stDownloadButton button { border-color: #0B5D4B; color: #0B5D4B; font-weight: 600; }
        .stDownloadButton button:hover { background: #0B5D4B; color: #FFFFFF; }
        p, li { font-size: 1rem; }
        </style>""",
        unsafe_allow_html=True,
    )

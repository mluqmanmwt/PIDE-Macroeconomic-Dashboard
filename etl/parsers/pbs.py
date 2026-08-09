"""
Parsers for Pakistan Bureau of Statistics files.

PBS spreadsheets are cleaner than SBP's but still carry banner rows and
merged headers. The historical CPI workbook is the single most valuable
inflation file on any GoP site — four sheets covering indices and inflation
rates on both the 2007-08 and 2015-16 bases.
"""

from __future__ import annotations

import re
import warnings
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", category=UserWarning, module="openpyxl")

TIDY_COLS = ["date", "series", "value", "unit", "source_id", "frequency"]


def _num(x):
    if pd.isna(x):
        return np.nan
    if isinstance(x, (int, float, np.number)):
        return float(x)
    s = re.sub(r"[^\d.\-]", "", str(x).replace(",", ""))
    try:
        return float(s) if s not in {"", "-", "."} else np.nan
    except ValueError:
        return np.nan


MIN_DATE = pd.Timestamp("1947-01-01")
MAX_DATE = pd.Timestamp("2100-12-31")


def _tidy(recs, source_id, unit, freq) -> pd.DataFrame:
    df = pd.DataFrame(recs)
    if df.empty:
        return pd.DataFrame(columns=TIDY_COLS)
    # `_unit` lets a parser set the unit per record. The SPI table mixes index
    # levels and percentage changes in one block, and tagging them all "index"
    # would make a -0.35% weekly change look like an impossible negative index.
    if "_unit" in df.columns:
        df["unit"] = df["_unit"].fillna(unit)
    else:
        df["unit"] = unit
    df["source_id"], df["frequency"] = source_id, freq
    df = df[TIDY_COLS].dropna(subset=["value"])
    d = pd.to_datetime(df["date"], errors="coerce")
    df["date"] = d.where((d >= MIN_DATE) & (d <= MAX_DATE))
    return df.dropna(subset=["date"]).sort_values(["series", "date"]).reset_index(drop=True)


def parse_pbs_cpi_historical(path: Path) -> pd.DataFrame:
    """indices_and_growth_rates_historical.xlsx

    Sheets
      'Historical Indices'              2007-08 + 2015-16 base, to Aug 2019
      'Historical Indices 2015-16'      2015-16 base, Sep 2019 onward (current)
      'Historical Inflation Rate'       YoY %, older
      'Historical Inflation Rat2015-16' YoY %, current

    Layout: row 2 is the header (Year | Month | National | UCPI | RPI | WPI ...).
    Rows where Month is blank are fiscal-year averages — we tag those separately
    rather than dropping them, because policymakers ask for FY averages.
    """
    frames = []
    xl = pd.ExcelFile(path)
    spec = {
        "Historical Indices": ("index (base varies)", "index"),
        "Historical Indices 2015-16": ("index (2015-16 = 100)", "index"),
        "Historical Inflation Rate": ("% YoY", "inflation"),
        "Historical Inflation Rat2015-16": ("% YoY", "inflation"),
    }
    for sheet, (unit, kind) in spec.items():
        if sheet not in xl.sheet_names:
            continue
        df = xl.parse(sheet, header=None)

        hdr = None
        for i in range(min(8, len(df))):
            row = [str(v).strip().lower() for v in df.iloc[i].tolist()]
            if "year" in row and "month" in row:
                hdr = i
                break
        if hdr is None:
            continue

        header = [str(v).strip() for v in df.iloc[hdr].tolist()]
        year_col, month_col = header.index("Year"), header.index("Month")
        value_cols = {c: re.sub(r"\s+", " ", header[c])
                      for c in range(month_col + 1, len(header))
                      if header[c] and header[c].lower() != "nan"}

        recs = []
        for r in range(hdr + 1, len(df)):
            y_raw, m_raw = df.iat[r, year_col], df.iat[r, month_col]
            if pd.isna(y_raw):
                continue
            y_str = str(y_raw).strip()

            if pd.isna(m_raw) or str(m_raw).strip() == "":
                # fiscal-year average row, e.g. '2016-17'
                m = re.search(r"(\d{4})\s*-\s*(\d{2,4})", y_str)
                if not m:
                    continue
                date = pd.Timestamp(year=int(m.group(1)) + 1, month=6, day=30)
                suffix = " (FY average)"
            else:
                try:
                    year, month = int(float(y_str)), int(float(m_raw))
                except (ValueError, TypeError):
                    continue
                if not 1 <= month <= 12:
                    continue
                date = pd.Timestamp(year=year, month=month, day=1) + pd.offsets.MonthEnd(0)
                suffix = ""

            for c, name in value_cols.items():
                recs.append({"date": date,
                             "series": f"{name} — {kind}{suffix}",
                             "value": _num(df.iat[r, c])})
        frames.append(_tidy(recs, "pbs_cpi_historical", unit, "monthly"))

    if not frames:
        return pd.DataFrame(columns=TIDY_COLS)
    out = pd.concat(frames, ignore_index=True)
    return out.drop_duplicates(subset=["date", "series"], keep="last")


def parse_pbs_spi(path: Path) -> pd.DataFrame:
    """3.-SPI-Report-DD.MM.YYYY.xlsx — weekly Sensitive Price Indicator.

    Page 1 carries the headline table: one row per expenditure quintile plus a
    'Combined' row, with five numeric columns — the current week's index, the
    previous week's index, the same week a year earlier, and the WoW and YoY
    percentage changes.

    The week-ending date is taken from the filename, which is the authoritative
    identifier PBS itself uses; the in-sheet header carries the same date but is
    wrapped across newlines and formatted inconsistently.

    Each weekly file is a single observation, so a real SPI history is built by
    accumulating snapshots — see `etl/transform.py`, which unions every dated
    snapshot under data/raw/pbs/ rather than only the latest pointer.
    """
    m = re.search(r"(\d{2})[.\-](\d{2})[.\-](\d{4})", path.name)
    if not m:
        return pd.DataFrame(columns=TIDY_COLS)
    week = pd.Timestamp(year=int(m.group(3)), month=int(m.group(2)), day=int(m.group(1)))

    df = pd.ExcelFile(path).parse("Page 1", header=None)

    hdr = None
    for r in range(len(df)):
        if any("Expenditure Group" in str(v) for v in df.iloc[r].tolist()):
            hdr = r
            break
    if hdr is None:
        return pd.DataFrame(columns=TIDY_COLS)

    label_col = next(c for c in range(df.shape[1])
                     if "Expenditure Group" in str(df.iat[hdr, c]))

    measures = ["index", "index previous week", "index year ago",
                "% change WoW", "% change YoY"]

    recs = []
    for r in range(hdr + 1, min(hdr + 12, len(df))):
        label = df.iat[r, label_col]
        if pd.isna(label) or not str(label).strip():
            break
        group = re.sub(r"\s+", " ", str(label)).strip()
        vals = [_num(v) for v in df.iloc[r, label_col + 1:].tolist()]
        vals = [v for v in vals if not pd.isna(v)]
        for name, val in zip(measures, vals):
            recs.append({"date": week, "series": f"SPI {group} — {name}",
                         "value": val,
                         "_unit": "%" if name.startswith("%") else "index (2015-16 = 100)"})

    return _tidy(recs, "pbs_spi_weekly", "index (2015-16 = 100)", "weekly")


def parse_pbs_spi_history(paths: list[Path]) -> pd.DataFrame:
    """Union every weekly SPI snapshot on disk into one continuous series."""
    frames = [parse_pbs_spi(p) for p in sorted(paths)]
    frames = [f for f in frames if not f.empty]
    if not frames:
        return pd.DataFrame(columns=TIDY_COLS)
    out = pd.concat(frames, ignore_index=True)
    return (out.drop_duplicates(subset=["date", "series"], keep="last")
               .sort_values(["series", "date"]).reset_index(drop=True))


def _classify_trade_row(label: str) -> str | None:
    """Map a PBS trade line-item label to a canonical series name.

    Labels are not stable across the goods and services workbooks or across
    months — the same concept appears as 'Exports', 'Exports of Services' and
    'Balance of Trade (Trade Deficit)'. Prefix matching on a normalised label
    keeps all three variants pointing at one series.
    """
    low = label.lower()
    if low.startswith("balance of trade"):
        return "Balance of Trade"
    if low.startswith("exports"):
        return "Exports"
    if low.startswith("imports"):
        return "Imports"
    return None


def parse_pbs_trade_summary(path: Path, source_id: str = "pbs_trade_summary_monthly"
                            ) -> pd.DataFrame:
    """Summary-<Month>-<YYYY>.xlsx / Services-Summary-<Month>-<YYYY>.xlsx.

    PBS trade is reported on a CUSTOMS basis and must never be mixed with SBP's
    BOP-basis trade series — the two differ by coverage and valuation.

    Sheet layout: three stacked tables, each introduced by a 'Table-N:' row.
      Table-1  current month vs previous month
      Table-2  current month vs same month last year
      Table-3  cumulative July-to-date, current FY vs previous FY

    Every table repeats the same three line items in two currencies (Rs. million
    and US$ million), so column position alone is ambiguous. We read the currency
    sub-header row beneath each table's period row to bind values correctly, and
    only emit the current-period USD figures as the monthly observation — the
    comparison columns are the same series at earlier dates and are emitted at
    their own dates instead of as separate series.
    """
    # Reference month comes from the publisher's own filename, which survives in
    # the snapshot name. PBS is inconsistent here — 'Summary-July-2026.xlsx',
    # 'Summary-_October-2025.xlsx', 'Revised-Summary-April-2025.xlsx' and
    # 'Summary-June-2026-1.xlsx' all occur — so the separators are kept loose.
    m = re.search(r"Summary[-_ ]+([A-Za-z]+)[-_ ]+(\d{2,4})", path.name)
    if not m:
        return pd.DataFrame(columns=TIDY_COLS)
    yr = int(m.group(2)) if len(m.group(2)) == 4 else 2000 + int(m.group(2))
    try:
        month_end = pd.Timestamp(f"{m.group(1)} 1, {yr}") + pd.offsets.MonthEnd(0)
    except Exception:  # noqa: BLE001
        return pd.DataFrame(columns=TIDY_COLS)

    df = pd.read_excel(path, sheet_name=0, header=None)
    kind = "services" if "services" in path.name.lower() else "goods"

    # Locate each 'Series' header row; the currency row sits 1-2 rows below it.
    blocks = [r for r in range(len(df)) if str(df.iat[r, 0]).strip() == "Series"]

    recs = []
    for bi, hr in enumerate(blocks):
        cur_row = None
        for rr in range(hr + 1, min(hr + 4, len(df))):
            row = [str(v).strip() for v in df.iloc[rr].tolist()]
            if "Rs." in row and "$" in row:
                cur_row = rr
                break
        if cur_row is None:
            continue
        usd_cols = [c for c in range(df.shape[1])
                    if str(df.iat[cur_row, c]).strip() == "$"]
        if not usd_cols:
            continue

        # Only Table-1 and Table-2 are monthly; Table-3 is cumulative FY-to-date.
        cumulative = bi >= 2
        # First $ column = current period, later ones = comparison periods.
        for ci, c in enumerate(usd_cols):
            if cumulative:
                if ci > 0:
                    continue
                date, suffix = month_end, " (cumulative Jul-to-date)"
            else:
                if ci > 0:
                    continue  # comparison periods arrive via their own monthly file
                date, suffix = month_end, ""

            for r in range(cur_row + 1, min(cur_row + 8, len(df))):
                label = re.sub(r"\s+", " ", str(df.iat[r, 0])).strip()
                item = _classify_trade_row(label)
                if item is None:
                    continue
                recs.append({"date": date,
                             "series": f"{item} ({kind}){suffix}",
                             "value": _num(df.iat[r, c])})
            break

    out = _tidy(recs, source_id, "million USD", "monthly")
    return out.drop_duplicates(subset=["date", "series"], keep="first")


def parse_pbs_services_summary(path: Path) -> pd.DataFrame:
    return parse_pbs_trade_summary(path, source_id="pbs_trade_services_summary")


# ---------------------------------------------------------------------------
# SDMX 2.1
# ---------------------------------------------------------------------------
# Several Government of Pakistan bodies publish SDMX 2.1 StructureSpecificData
# messages as plain static XML with no key and no session. These are the only
# genuinely machine-readable feeds the government offers for fiscal operations,
# producer prices, labour and energy, so they carry disproportionate weight in
# this pipeline.
#
# Period convention. Pakistan's fiscal year runs July to June, and the national
# accounts and fiscal feeds are published on fiscal quarters, not calendar ones:
# FY2026 Q1 is Jul-Sep 2025 and Q3 is Jan-Mar 2026. This was confirmed against
# the independently parsed SBP quarterly national accounts file, which starts at
# 2015-09-30 and ends 2026-03-31 — exactly matching QNAG's 2016-Q1 to 2026-Q3
# under the fiscal reading and off by two quarters under the calendar reading.
# Reading these as calendar quarters would shift every observation by six months
# and silently misdate every turning point in the series.
_SDMX_QUARTER_END = {"1": (9, 1), "2": (12, 1), "3": (3, 0), "4": (6, 0)}

# UNIT_MULT is an SDMX power-of-ten scaling factor. It is reported rather than
# applied: rescaling to absolute units would turn readable "million PKR" figures
# into 13-digit numbers, and the dashboard formats by unit string.
_SDMX_MULT = {"0": "", "3": "thousand ", "6": "million ", "9": "billion "}

# Trailing tokens of the INDICATOR code carry the unit of measure.
_SDMX_UNIT_SUFFIX = {
    "WT": "weight (%)",         # CPI basket weight, constant by design
    "XDC": "{m}PKR",            # domestic currency
    "USD": "{m}USD",
    "IX": "index",
    "PC": "%",
    "PT": "%",
    "NUM": "{m}number",
    "BBL": "{m}barrels",
    "MT": "{m}metric tonnes",
    "KWH": "{m}kWh",
    "GWH": "GWh",
}


def _sdmx_period(token: str, freq: str) -> pd.Timestamp | None:
    """Convert an SDMX TIME_PERIOD into the period-END date.

    Period end, not period start, so that a quarterly and a monthly series can be
    plotted on one time axis without the quarterly one appearing to lead by three
    months.
    """
    t = str(token).strip()

    m = re.fullmatch(r"(\d{4})[-]?Q([1-4])", t, re.I)
    if m:
        year, q = int(m.group(1)), m.group(2)
        month, back = _SDMX_QUARTER_END[q]
        return pd.Timestamp(year=year - back, month=month, day=1) + pd.offsets.MonthEnd(0)

    m = re.fullmatch(r"(\d{4})-(\d{1,2})", t)
    if m:
        year, month = int(m.group(1)), int(m.group(2))
        if 1 <= month <= 12:
            return pd.Timestamp(year=year, month=month, day=1) + pd.offsets.MonthEnd(0)

    m = re.fullmatch(r"(\d{4})M(\d{1,2})", t, re.I)
    if m:
        return pd.Timestamp(year=int(m.group(1)), month=int(m.group(2)), day=1) \
            + pd.offsets.MonthEnd(0)

    if re.fullmatch(r"\d{4}", t):
        # A bare year on a GoP feed is a fiscal year ending 30 June. Dating it to
        # 31 December would place it six months later than it belongs.
        return pd.Timestamp(year=int(t), month=6, day=30)

    d = pd.to_datetime(t, errors="coerce")
    return None if pd.isna(d) else pd.Timestamp(d)


def _sdmx_unit(indicator: str, unit_mult: str) -> str:
    mult = _SDMX_MULT.get(str(unit_mult).strip(), "")
    for token in reversed(re.split(r"[_\W]+", str(indicator).upper())):
        if token in _SDMX_UNIT_SUFFIX:
            return _SDMX_UNIT_SUFFIX[token].format(m=mult)
    return (mult + "units").strip() if mult else "n.a."


_SDMX_FREQ = {"M": "monthly", "Q": "quarterly", "A": "annual", "W": "weekly", "D": "daily"}

# GoP SDMX messages carry only opaque IMF ECOFIN indicator codes such as
# 'PAK_GGO_RG_XDC' and no <Name> elements, which would leave a policy reader
# unable to tell revenue from expenditure. The codes come from the IMF ECOFIN
# data structure definition that the files themselves reference in their
# xsi:schemaLocation, so the official labels are read from a cached extract of
# that codelist. The label is presentation only — every value still comes from
# the Government of Pakistan feed. Codes that resolved ambiguously were excluded
# from the cache rather than guessed at.
_LABEL_FILE = Path(__file__).resolve().parents[2] / "data" / "metadata" / "sdmx_indicator_labels.csv"


@lru_cache(maxsize=1)
def _sdmx_labels() -> dict[str, str]:
    if not _LABEL_FILE.exists():
        return {}
    df = pd.read_csv(_LABEL_FILE)
    return dict(zip(df["indicator"].astype(str), df["label"].astype(str)))


def parse_sdmx(path: Path, source_id: str) -> pd.DataFrame:
    """Parse any GoP SDMX 2.1 StructureSpecificData message into the tidy contract.

    Observations are ``<Obs TIME_PERIOD OBS_VALUE/>`` nested in ``<Series>``
    elements whose attributes hold the dimension values. The series name is built
    from INDICATOR plus any dimension that actually varies within the file —
    including constant dimensions such as REF_AREA=PK would add noise to every
    label without distinguishing anything.
    """
    import xml.etree.ElementTree as ET

    blocks = [e for e in ET.parse(path).iter() if e.tag.endswith("Series")]
    if not blocks:
        return pd.DataFrame(columns=TIDY_COLS)

    ignore = {"INDICATOR", "UNIT_MULT", "DATA_DOMAIN", "COUNTERPART_AREA",
              "TIME_FORMAT", "OBS_STATUS"}
    varying = {
        k for k in {k for b in blocks for k in b.attrib}
        if k not in ignore and len({b.attrib.get(k) for b in blocks}) > 1
    }

    recs: list[dict] = []
    freqs: set[str] = set()
    for block in blocks:
        a = block.attrib
        indicator = a.get("INDICATOR") or a.get("DATA_DOMAIN") or "unknown"
        freq = _SDMX_FREQ.get(str(a.get("FREQ", "")).upper(), "monthly")
        freqs.add(freq)
        unit = _sdmx_unit(indicator, a.get("UNIT_MULT", "0"))

        qualifiers = [f"{k}={a[k]}" for k in sorted(varying) if a.get(k) and k != "FREQ"]
        label = _sdmx_labels().get(indicator)
        # The raw code is retained alongside the label so a user can trace any
        # series back to the exact indicator in the publisher's file.
        name = f"{label} [{indicator}]" if label else indicator
        if qualifiers:
            name += f" ({', '.join(qualifiers)})"

        for obs in block:
            if not obs.tag.endswith("Obs"):
                continue
            value = obs.attrib.get("OBS_VALUE")
            if value in (None, ""):
                continue
            date = _sdmx_period(obs.attrib.get("TIME_PERIOD", ""), freq)
            if date is None:
                continue
            recs.append({"date": date, "series": name, "value": _num(value),
                         "_unit": unit, "_freq": freq})

    if not recs:
        return pd.DataFrame(columns=TIDY_COLS)

    # A single SDMX file can mix frequencies, so frequency is carried per record
    # and the file-level default is only a fallback.
    out = _tidy(recs, source_id, "n.a.", "monthly" if len(freqs) != 1 else freqs.pop())
    per_record = pd.DataFrame(recs)["_freq"]
    if per_record.nunique() > 1:
        out["frequency"] = per_record.values[: len(out)]
    return out.drop_duplicates(subset=["date", "series"], keep="last").reset_index(drop=True)


def parse_sdmx_generic(path: Path) -> pd.DataFrame:
    """Back-compatible entry point for the PBS CPI SDMX feed."""
    return parse_sdmx(path, "pbs_cpi_sdmx")


def parse_sdmx_mof_ggo(path: Path) -> pd.DataFrame:
    return parse_sdmx(path, "mof_general_govt_operations_sdmx")


def parse_sdmx_mof_cgo(path: Path) -> pd.DataFrame:
    return parse_sdmx(path, "mof_central_govt_operations_sdmx")


def parse_sdmx_pbs_trade(path: Path) -> pd.DataFrame:
    return parse_sdmx(path, "pbs_merchandise_trade_sdmx")


def parse_sdmx_pbs_qna(path: Path) -> pd.DataFrame:
    return parse_sdmx(path, "pbs_quarterly_national_accounts_sdmx")


def parse_sdmx_pbs_ppi(path: Path) -> pd.DataFrame:
    return parse_sdmx(path, "pbs_producer_prices_sdmx")


def parse_sdmx_pbs_energy(path: Path) -> pd.DataFrame:
    return parse_sdmx(path, "pbs_energy_sdmx")


def parse_sdmx_pbs_labour(path: Path) -> pd.DataFrame:
    return parse_sdmx(path, "pbs_labour_sdmx")

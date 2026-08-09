"""
Parsers for State Bank of Pakistan Excel archives.

SBP workbooks are formatted for human reading, not machines:
  * 3-6 rows of title/unit banner before the real header
  * a blank spacer column at position 0 (sometimes two)
  * dates as *columns* (wide layout) in remittances, M2, GDP
  * multiple sheets split by fiscal-year era with inconsistent names
  * footnote rows ("P: Provisional", "--") mixed into the data block

Every function here returns a TIDY long frame with a consistent contract:

    date | series | value | unit | source_id | frequency

so the dashboard can concatenate anything without special-casing.
"""

from __future__ import annotations

import re
from datetime import date, datetime
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", category=UserWarning, module="openpyxl")

TIDY_COLS = ["date", "series", "value", "unit", "source_id", "frequency"]


# --------------------------------------------------------------------------- helpers
def _read(path: Path, sheet=0) -> pd.DataFrame:
    return pd.read_excel(path, sheet_name=sheet, header=None)


def _drop_empty(df: pd.DataFrame) -> pd.DataFrame:
    return df.dropna(axis=0, how="all").dropna(axis=1, how="all")


def _num(x):
    """Coerce SBP cell values to float. '--', 'P', 'n.a.', '1,234' all appear."""
    if pd.isna(x):
        return np.nan
    if isinstance(x, (int, float, np.number)):
        return float(x)
    s = str(x).strip().replace(",", "")
    s = re.sub(r"[^\d.\-]", "", s)
    if s in {"", "-", ".", "--"}:
        return np.nan
    try:
        return float(s)
    except ValueError:
        return np.nan


def _fy_to_date(label) -> pd.Timestamp | None:
    """'2016-17' / 'FY 2016-17' -> 30 June 2017 (Pakistan fiscal year end).

    Only genuine strings are considered. A datetime such as 1970-07-01 stringifies
    to '1970-07-01 00:00:00', which a loose search would happily read as fiscal
    year 1970-07 — silently turning every monthly observation in a mixed
    annual/monthly sheet into a duplicate of the same June year-end.
    """
    if label is None or isinstance(label, (pd.Timestamp, datetime, date)) or pd.isna(label):
        return None
    if not isinstance(label, str):
        return None
    m = re.fullmatch(r"\s*(?:FY\s*)?(\d{4})\s*[-/]\s*(\d{2,4})\s*", label, re.I)
    if not m:
        return None
    start = int(m.group(1))
    if not 1947 <= start <= 2100:
        return None
    return pd.Timestamp(year=start + 1, month=6, day=30)


# Pakistan's first official statistics postdate 1947; anything outside this window
# is a misparsed header cell, a footnote, or a stray Excel serial number.
MIN_DATE = pd.Timestamp("1947-01-01")
MAX_DATE = pd.Timestamp("2100-12-31")


def _safe_dates(s: pd.Series) -> pd.Series:
    """Parse to datetime, clamping out-of-range values to NaT.

    Necessary because SBP sheets contain cells that pandas happily reads as
    year 182 or year 9999, which then overflow on concat.
    """
    out = pd.to_datetime(s, errors="coerce")
    return out.where((out >= MIN_DATE) & (out <= MAX_DATE))


def _tidy(records: list[dict], source_id: str, unit: str, freq: str) -> pd.DataFrame:
    df = pd.DataFrame(records)
    if df.empty:
        return pd.DataFrame(columns=TIDY_COLS)
    # A record may override the sheet-level unit via `_unit`. Needed whenever one
    # sheet mixes measures — e.g. GDP_table.xlsx carries a 'GDP Growth Rate (%)'
    # row among rows denominated in Rs million.
    if "_unit" in df.columns:
        df["unit"] = df["_unit"].fillna(unit)
    else:
        df["unit"] = unit
    df["source_id"] = source_id
    df["frequency"] = freq
    df = df[TIDY_COLS]
    df = df.dropna(subset=["value"])
    df["date"] = _safe_dates(df["date"])
    return df.dropna(subset=["date"]).sort_values(["series", "date"]).reset_index(drop=True)


_MONTH_RE = re.compile(
    r"^(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*[\s\-/]*(\d{2,4})$", re.I)


def _coerce_period(v) -> pd.Timestamp | None:
    """Turn an SBP column header into a month-end Timestamp.

    SBP mixes formats within a single header row. In Homeremit_Arch.xlsx the
    early columns are real datetimes while the recent ones are strings such as
    'Dec-24', 'June-25' and 'May-26R' (R = revised, P = provisional). Fiscal-year
    aggregate columns ('FY25') are deliberately rejected — they are not monthly
    observations and would corrupt a monthly series.
    """
    if pd.isna(v):
        return None
    if isinstance(v, (pd.Timestamp,)):
        d = pd.Timestamp(v)
        return d if MIN_DATE <= d <= MAX_DATE else None

    s = str(v).strip()
    if not s or re.fullmatch(r"FY\s*\d{2,4}", s, re.I):
        return None
    s = re.sub(r"\s*[\(\[]?[RPrp][\)\]]?$", "", s).strip()  # strip R / P markers

    m = _MONTH_RE.match(s)
    if m:
        month = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
                 "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11,
                 "dec": 12}[m.group(1).lower()[:3]]
        yr = int(m.group(2))
        yr = yr + 2000 if yr < 100 else yr
        return pd.Timestamp(year=yr, month=month, day=1) + pd.offsets.MonthEnd(0)

    d = pd.to_datetime(s, errors="coerce")
    if pd.isna(d) or not (MIN_DATE <= d <= MAX_DATE):
        return None
    return pd.Timestamp(d) + pd.offsets.MonthEnd(0)


def _melt_wide_by_date(df: pd.DataFrame, label_col: int, first_data_col: int,
                       header_row: int) -> list[dict]:
    """Generic 'labels down the side, periods across the top' unpivot."""
    col_dates = {}
    for c in range(first_data_col, df.shape[1]):
        d = _coerce_period(df.iat[header_row, c])
        if d is not None:
            col_dates[c] = d

    out = []
    for r in range(header_row + 1, len(df)):
        # The label is found by scanning every column left of the data
        # right-to-left, not by reading one fixed column. SBP indents component
        # rows one column further right than the aggregate rows that total them,
        # so a fixed label column silently drops the aggregates: the headline
        # 'Broad Money (M2) (A+B+C)' row sits a column to the left of the
        # components in every sheet from FY13 onward, which truncated the M2
        # total at 2012 while its components stayed current to 2026. Scanning
        # right-to-left also naturally prefers the descriptive text over the
        # single-letter section code that sits beside it.
        series = ""
        for c in range(min(label_col, first_data_col - 1), -1, -1):
            cell = df.iat[r, c]
            if pd.isna(cell):
                continue
            text = re.sub(r"\s+", " ", str(cell)).strip()
            # Section markers ('A', 'B.', '(i)', '1)') label a block rather than
            # a series, so they are not usable names on their own.
            if not text or re.fullmatch(r"[\(\)a-zA-Z0-9ivxIVX]{1,4}[\.\)]?", text):
                continue
            series = text
            break
        if not series:
            continue
        for c, d in col_dates.items():
            out.append({"date": d, "series": series, "value": _num(df.iat[r, c])})
    return out


# --------------------------------------------------------------------------- parsers
def parse_sbp_forex(path: Path) -> pd.DataFrame:
    """Forex_Arch.xlsx — sheets: Year-end / Month-end / Week-end.

    Layout: col1 = period, col2 = net reserves with SBP, col3 = with banks,
    col4 = total liquid FX reserves. Millions of US$.
    """
    frames = []
    xl = pd.ExcelFile(path)
    freq_map = {"Week-end": "weekly", "Month-end": "monthly", "Year-end": "annual"}
    for sheet, freq in freq_map.items():
        if sheet not in xl.sheet_names:
            continue
        df = _drop_empty(xl.parse(sheet, header=None)).reset_index(drop=True)
        hdr = None
        for i in range(min(15, len(df))):
            row = " ".join(str(v) for v in df.iloc[i].tolist())
            if "END PERIOD" in row.upper():
                hdr = i
                break
        if hdr is None:
            continue
        block = df.iloc[hdr + 1:].copy()
        cols = ["period", "sbp", "banks", "total"]
        block = block.iloc[:, :4]
        block.columns = cols

        recs = []
        for _, r in block.iterrows():
            per = r["period"]
            d = pd.to_datetime(per, errors="coerce")
            if pd.isna(d):
                d = _fy_to_date(per)
            if d is None or pd.isna(d):
                continue
            for name, col in [("Reserves with SBP", "sbp"),
                              ("Reserves with banks", "banks"),
                              ("Total liquid FX reserves", "total")]:
                recs.append({"date": d, "series": name, "value": _num(r[col])})
        frames.append(_tidy(recs, "sbp_forex_reserves", "million USD", freq))
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=TIDY_COLS)


def parse_sbp_remittances(path: Path) -> pd.DataFrame:
    """Homeremit_Arch.xlsx — country-wise workers' remittances, 1972-07 onward.

    Three era sheets, each wide (months across columns). Country labels sit in
    col 2, with a section marker in col 0 ('I.', 'II.') we ignore.
    """
    frames = []
    xl = pd.ExcelFile(path)
    for sheet in xl.sheet_names:
        df = xl.parse(sheet, header=None)
        hdr = None
        for i in range(min(12, len(df))):
            row = df.iloc[i]
            n_dates = sum(pd.notna(pd.to_datetime(v, errors="coerce")) for v in row)
            if n_dates >= 6:
                hdr = i
                break
        if hdr is None:
            continue
        first_data_col = next((c for c in range(df.shape[1])
                               if pd.notna(pd.to_datetime(df.iat[hdr, c], errors="coerce"))), 3)
        label_col = max(0, first_data_col - 1)
        recs = _melt_wide_by_date(df, label_col, first_data_col, hdr)
        frames.append(_tidy(recs, "sbp_workers_remittances", "million USD", "monthly"))
    if not frames:
        return pd.DataFrame(columns=TIDY_COLS)
    out = pd.concat(frames, ignore_index=True)
    return out.drop_duplicates(subset=["date", "series"], keep="last")


def parse_sbp_m2(path: Path) -> pd.DataFrame:
    """BroadMoney_M2_Arch.xls — one sheet per fiscal-year block, wide by month."""
    frames = []
    xl = pd.ExcelFile(path)
    for sheet in xl.sheet_names:
        df = xl.parse(sheet, header=None)
        hdr = None
        for i in range(min(10, len(df))):
            n_dates = sum(pd.notna(pd.to_datetime(v, errors="coerce")) for v in df.iloc[i])
            if n_dates >= 4:
                hdr = i
                break
        if hdr is None:
            continue
        first_data_col = next((c for c in range(df.shape[1])
                               if pd.notna(pd.to_datetime(df.iat[hdr, c], errors="coerce"))), 2)
        recs = _melt_wide_by_date(df, max(0, first_data_col - 1), first_data_col, hdr)
        frames.append(_tidy(recs, "sbp_broad_money_m2", "million PKR", "monthly"))
    if not frames:
        return pd.DataFrame(columns=TIDY_COLS)
    return pd.concat(frames, ignore_index=True).drop_duplicates(
        subset=["date", "series"], keep="last")


def parse_sbp_ir_corridor(path: Path) -> pd.DataFrame:
    """IR-Corridor-Hist.xls — daily access to SBP overnight facilities since 2009-08-13.

    Header spans two rows (Ceiling/Floor over Amount/Institutions).
    """
    df = _read(path, "Corridor")
    hdr = None
    for i in range(min(15, len(df))):
        if "Date" in [str(v).strip() for v in df.iloc[i].tolist()]:
            hdr = i
            break
    if hdr is None:
        return pd.DataFrame(columns=TIDY_COLS)

    date_col = next(c for c in range(df.shape[1]) if str(df.iat[hdr, c]).strip() == "Date")
    names = {}
    top = None
    for c in range(date_col + 1, df.shape[1]):
        t = df.iat[hdr, c]
        if pd.notna(t) and str(t).strip():
            top = str(t).strip()
        sub = df.iat[hdr + 1, c] if hdr + 1 < len(df) else None
        if pd.notna(sub) and str(sub).strip():
            names[c] = f"{top} — {str(sub).strip()}"

    recs = []
    for r in range(hdr + 2, len(df)):
        d = pd.to_datetime(df.iat[r, date_col], errors="coerce")
        if pd.isna(d):
            continue
        for c, name in names.items():
            recs.append({"date": d, "series": name, "value": _num(df.iat[r, c])})
    return _tidy(recs, "sbp_interest_rate_corridor", "million PKR / count", "daily")


def parse_sbp_balance_of_trade(path: Path) -> pd.DataFrame:
    """exp_import_BOP_Arch.xls — exports, imports and balance of trade, BOP basis.

    This is SBP's balance-of-payments measure of merchandise trade. It is NOT
    interchangeable with the PBS customs-basis series: the BOP figures are
    adjusted for coverage and valuation, so the two disagree every month by
    design.

    The sheet stacks two blocks under one header:
      * an ANNUAL block keyed by fiscal-year labels ('1970-71' … '2025-26')
      * a MONTHLY block keyed by real dates, starting July 1970

    Both blocks share one three-row header in which the measure name, the
    sub-measure and the algebraic column tag are spread across separate rows and
    merged cells, so column names are assembled by forward-filling row 1 and
    combining it with rows 2-3. Reading only the first non-empty header cell —
    the previous approach — collapsed 'Exports Value' and 'Exports Cumulative'
    onto the same name and produced thousands of duplicate observations.
    """
    df = _drop_empty(_read(path)).reset_index(drop=True)

    hdr = None
    for i in range(min(20, len(df))):
        row = " ".join(str(v) for v in df.iloc[i].tolist()).lower()
        if "period" in row and "export" in row:
            hdr = i
            break
    if hdr is None:
        return pd.DataFrame(columns=TIDY_COLS)

    period_col = next((c for c in range(df.shape[1])
                       if str(df.iat[hdr, c]).strip().lower() == "period"), 0)

    def cell(r, c):
        if r >= len(df):
            return ""
        v = df.iat[r, c]
        return "" if pd.isna(v) else re.sub(r"\s+", " ", str(v)).strip()

    # Row `hdr` carries the measure across merged cells — forward-fill it.
    # 'Growth Rate' appears as its own top-level heading under both Exports and
    # Imports, so the owning flow is tracked separately and prepended; otherwise
    # the export and import growth columns collide on one name.
    measures, current, flow = {}, "", ""
    for c in range(period_col + 1, df.shape[1]):
        top = cell(hdr, c)
        if top:
            current = top
            if not re.match(r"growth\s*rate", top, re.I):
                flow = top
        sub, tag = cell(hdr + 1, c), cell(hdr + 2, c)
        if not current and not sub:
            continue
        head = current
        if re.match(r"growth\s*rate", current, re.I) and flow:
            head = f"{flow} Growth Rate"
        name = " ".join(x for x in (head, sub) if x)
        if tag:
            name = f"{name} [{tag}]"
        measures[c] = name

    annual, monthly = [], []
    for r in range(hdr + 3, len(df)):
        raw = df.iat[r, period_col]
        if isinstance(raw, str) and re.match(r"^\s*(note|source|contact|designation|phone|email)",
                                             raw, re.I):
            break

        fy = _fy_to_date(raw)
        if fy is not None and not pd.isna(fy):
            bucket, date = annual, fy
        else:
            d = pd.to_datetime(raw, errors="coerce")
            if pd.isna(d) or not (MIN_DATE <= d <= MAX_DATE):
                continue
            bucket, date = monthly, pd.Timestamp(d) + pd.offsets.MonthEnd(0)

        for c, name in measures.items():
            bucket.append({"date": date, "series": name, "value": _num(df.iat[r, c])})

    frames = []
    if annual:
        frames.append(_tidy([{**x, "series": f"{x['series']} (annual)"} for x in annual],
                            "sbp_balance_of_trade", "million USD", "annual"))
    if monthly:
        frames.append(_tidy(monthly, "sbp_balance_of_trade", "million USD", "monthly"))
    if not frames:
        return pd.DataFrame(columns=TIDY_COLS)

    out = pd.concat(frames, ignore_index=True)
    # Growth-rate columns are percentages even though the sheet unit is USD.
    out.loc[out["series"].str.contains("Growth Rate", case=False), "unit"] = "%"
    return out


def parse_sbp_gdp_annual(path: Path) -> pd.DataFrame:
    """GDP_table.xlsx — sectors down, fiscal years across. Rs million + growth row."""
    df = _read(path, "Annual")
    hdr = None
    for i in range(min(12, len(df))):
        row = [str(v) for v in df.iloc[i].tolist()]
        if any("Sector" in v for v in row):
            hdr = i
            break
    if hdr is None:
        return pd.DataFrame(columns=TIDY_COLS)

    label_col = next(c for c in range(df.shape[1]) if "Sector" in str(df.iat[hdr, c]))
    year_cols = {c: _fy_to_date(df.iat[hdr, c]) for c in range(label_col + 1, df.shape[1])}
    year_cols = {c: d for c, d in year_cols.items() if d is not None}

    # The workbook states its price basis in the banner above the table.
    banner = " ".join(str(v) for i in range(hdr)
                      for v in df.iloc[i].tolist() if pd.notna(v))
    level_unit = "million PKR"
    if "constant" in banner.lower():
        m = re.search(r"constant[^)]*?(\d{4}-\d{2})", banner, re.I)
        level_unit = f"million PKR (constant {m.group(1)})" if m \
            else "million PKR (constant prices)"
    elif "current" in banner.lower():
        level_unit = "million PKR (current prices)"

    recs = []
    for r in range(hdr + 1, len(df)):
        label = df.iat[r, label_col]
        if pd.isna(label) or not str(label).strip():
            continue
        series = re.sub(r"\s+", " ", str(label)).strip()
        # Footnote and source rows sit below the table and have no numbers.
        if re.match(r"^(source|gva|od)\s*:", series, re.I):
            continue
        is_growth = "growth rate" in series.lower()
        unit = "% YoY" if is_growth else level_unit
        for c, d in year_cols.items():
            recs.append({"date": d, "series": series,
                         "value": _num(df.iat[r, c]), "_unit": unit})
    return _tidy(recs, "sbp_gdp_annual", level_unit, "annual")


def parse_sbp_gdp_quarterly(path: Path) -> pd.DataFrame:
    """QGDP.xlsx — sheets 'Quarterly' (levels) and 'Growth_Q'.

    Header is two rows: FY label on one row spanning four quarter columns.

    Both sheets use identical sector labels, so the measure is appended to the
    series name. Without it 'Crops' would exist twice at the same date — once as
    Rs 606,263 million and once as 1.70 percent — and any join or chart would
    silently pick whichever row came last.
    """
    frames = []
    xl = pd.ExcelFile(path)
    for sheet, unit, measure in [
            ("Quarterly", "million PKR (constant basic prices)", "level"),
            ("Growth_Q", "% YoY", "growth")]:
        if sheet not in xl.sheet_names:
            continue
        df = xl.parse(sheet, header=None)
        fy_row = q_row = None
        for i in range(min(12, len(df))):
            row = " ".join(str(v) for v in df.iloc[i].tolist())
            if re.search(r"FY\s*\d{4}", row):
                fy_row = i
            if re.search(r"\bQ1\b", row):
                q_row = i
                break
        if fy_row is None or q_row is None:
            continue
        label_col = next((c for c in range(df.shape[1])
                          if "Sector" in str(df.iat[fy_row, c])), 2)

        col_dates, cur_fy = {}, None
        for c in range(label_col + 1, df.shape[1]):
            fy = df.iat[fy_row, c]
            if pd.notna(fy) and re.search(r"\d{4}", str(fy)):
                cur_fy = str(fy)
            q = str(df.iat[q_row, c]).strip().upper()
            m = re.fullmatch(r"Q([1-4])", q)
            if cur_fy and m:
                y = int(re.search(r"(\d{4})", cur_fy).group(1))
                qn = int(m.group(1))
                # Pakistan FY starts in July: Q1 = Jul-Sep of start year
                month = {1: 9, 2: 12, 3: 3, 4: 6}[qn]
                year = y if qn <= 2 else y + 1
                col_dates[c] = pd.Timestamp(year=year, month=month, day=1) + pd.offsets.MonthEnd(0)

        recs = []
        for r in range(q_row + 1, len(df)):
            label = df.iat[r, label_col]
            if pd.isna(label) or not str(label).strip():
                continue
            series = re.sub(r"\s+", " ", str(label)).strip()
            if re.match(r"^(source|note|gva|od)\s*:", series, re.I):
                continue
            for c, d in col_dates.items():
                recs.append({"date": d, "series": f"{series} — {measure}",
                             "value": _num(df.iat[r, c])})
        frames.append(_tidy(recs, "sbp_gdp_quarterly", unit, "quarterly"))
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=TIDY_COLS)


def parse_sbp_lsm(path: Path) -> pd.DataFrame:
    """Productselect.xlsx — QIM of selected LSM items, base 2015-16.

    IMPORTANT: this workbook is NOT a time series. It is a single-vintage
    comparison snapshot — for each of ~97 LSM items it reports the QIM weight,
    the adjusted weight, cumulative Jul-<month> growth for the current and prior
    fiscal year, and the latest month's growth against the same month last year.

    Returned as a WIDE snapshot table (item x measure), not the tidy long format,
    because there is no meaningful single date to attach to a weight column.
    Use `pbs_qim_lsm` (PDF) or the Economic Survey manufacturing chapter for an
    actual LSM index history.
    """
    df = _read(path, "LSM_OP")
    hdr = None
    for i in range(min(15, len(df))):
        if any("Descriptions" in str(v) for v in df.iloc[i].tolist()):
            hdr = i
            break
    if hdr is None:
        return pd.DataFrame()

    label_col = next(c for c in range(df.shape[1]) if "Descriptions" in str(df.iat[hdr, c]))

    # Column labels live across the header row and the row beneath it.
    measures = {}
    for c in range(label_col + 1, df.shape[1]):
        parts = []
        for rr in (hdr - 1, hdr, hdr + 1):
            if 0 <= rr < len(df):
                v = df.iat[rr, c]
                if pd.notna(v) and str(v).strip():
                    parts.append(str(v).strip())
        if parts:
            measures[c] = " ".join(dict.fromkeys(parts))

    rows = []
    for r in range(hdr + 1, len(df)):
        label = df.iat[r, label_col]
        if pd.isna(label) or not str(label).strip():
            continue
        rec = {"item": re.sub(r"\s+", " ", str(label)).strip(),
               "code": str(df.iat[r, label_col - 1]).strip()
               if label_col > 0 and pd.notna(df.iat[r, label_col - 1]) else ""}
        for c, name in measures.items():
            rec[name] = _num(df.iat[r, c])
        rows.append(rec)

    out = pd.DataFrame(rows)
    out["source_id"] = "sbp_lsm_production"
    out["vintage"] = pd.Timestamp.today().normalize()
    return out


# --------------------------------------------------------------------------
# Structure of Interest Rates (sir.pdf)
# --------------------------------------------------------------------------
# SBP does not publish the policy rate as a spreadsheet anywhere. The only
# machine-readable official carrier is this fortnightly PDF, whose first page
# tabulates the reverse-repo (ceiling), repo (floor) and policy (target) rates
# by effective date, and whose later pages carry KIBOR monthly averages and
# weighted-average lending/deposit rates.
#
# Note this is a *current* structure table, not a full archive: page 1 starts at
# January 2023. Longer policy-rate history exists only in the Monetary Policy
# Statement archive as prose, so it is out of automated scope.

_MONS = "Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec"


def _dmy(tok: str) -> pd.Timestamp | None:
    """'24-Jan-23' -> Timestamp. Two-digit years are 20xx in this dataset."""
    m = re.fullmatch(rf"(\d{{1,2}})-({_MONS})-(\d{{2,4}})", tok.strip(), re.I)
    if not m:
        return None
    y = int(m.group(3))
    y += 2000 if y < 100 else 0
    try:
        return pd.Timestamp(f"{y}-{m.group(2).title()}-{int(m.group(1)):02d}")
    except ValueError:
        return None


def _my(tok: str) -> pd.Timestamp | None:
    """'Jul-25' -> month-end Timestamp."""
    m = re.fullmatch(rf"({_MONS})-(\d{{2,4}})", tok.strip(), re.I)
    if not m:
        return None
    y = int(m.group(2))
    y += 2000 if y < 100 else 0
    return pd.Timestamp(f"{y}-{m.group(1).title()}-01") + pd.offsets.MonthEnd(0)


def _f(tok: str) -> float:
    """Numeric cell. 'NA', 'R' (rejected) and 'N' (no auction) are real markers."""
    try:
        return float(tok.replace(",", ""))
    except ValueError:
        return np.nan


def parse_sbp_interest_rates(path: Path) -> pd.DataFrame:
    """sir.pdf — policy rate corridor, KIBOR and weighted-average bank rates."""
    import pdfplumber

    recs: list[dict] = []
    with pdfplumber.open(path) as pdf:
        pages = [p.extract_text() or "" for p in pdf.pages]

    # ---- Page 1: policy rate corridor, keyed by effective date -------------
    # Layout: <date> <reverse repo> <repo> <policy> <min deposit return> then a
    # second, independent EFS block with its own date. Only the first four
    # numbers belong to the corridor, so the row is truncated deliberately.
    if pages:
        corridor = ["SBP Reverse Repo Rate (ceiling)", "SBP Repo Rate (floor)",
                    "SBP Policy Rate (target)", "Minimum rate of return on saving deposits"]
        for line in pages[0].splitlines():
            toks = line.split()
            if not toks:
                continue
            d = _dmy(toks[0])
            if d is None:
                continue
            # Require all four rate cells to be numeric. A trailing footnote row
            # ("28-Apr-26 Over 3 years and upto 5 years 6.00 2.50 8.50") also
            # starts with a valid date, and lenient parsing would read its stray
            # '3' as a repo rate.
            vals = [_f(t) for t in toks[1:5]]
            if len(vals) < 4 or any(pd.isna(v) for v in vals):
                continue
            for name, v in zip(corridor, vals):
                recs.append({"date": d, "series": name, "value": v, "_freq": "irregular"})

    # ---- Page 2: T-bill auction yields (left) + KIBOR (right) -------------
    # One physical line carries two unrelated tables side by side. The right
    # block itself switches from "Monthly Average" to "Daily Rates" partway
    # down, and both use the same Mon-YY / DD-Mon-YY token shapes, so the mode
    # is tracked from the section heading rather than inferred from the token.
    if len(pages) > 1:
        tenors = ("1-month", "3-month", "6-month", "12-month")
        kibor_daily = False
        for line in pages[1].splitlines():
            if "Daily Rates" in line:
                kibor_daily = True
            toks = line.split()
            if not toks:
                continue

            # Left block: <auction date> then 4 cut-off + 4 weighted-average
            # yields. 'NA' (not available), 'R' (bids rejected) and 'N' (no bid
            # received) are the publisher's own markers and stay missing.
            d = _dmy(toks[0])
            if d is not None and len(toks) >= 9:
                for i, tenor in enumerate(tenors):
                    for label, off in (("cut-off", 1), ("weighted average", 5)):
                        v = _f(toks[off + i])
                        if not pd.isna(v):
                            recs.append({"date": d,
                                         "series": f"T-bill {tenor} {label} yield",
                                         "value": v, "_freq": "irregular"})

            # Right block: trailing <period> + exactly three KIBOR tenors.
            if len(toks) >= 4:
                tail = toks[-4:]
                vals = [_f(t) for t in tail[1:]]
                if not any(pd.isna(v) for v in vals):
                    if kibor_daily:
                        kd = _dmy(tail[0])
                        if kd is not None:
                            for tenor, v in zip(("1-month", "3-month", "6-month"), vals):
                                recs.append({"date": kd, "series": f"KIBOR {tenor}",
                                             "value": v, "_freq": "daily"})
                    else:
                        km = _my(tail[0])
                        if km is not None:
                            for tenor, v in zip(("1-month", "3-month", "6-month"), vals):
                                recs.append({"date": km,
                                             "series": f"KIBOR {tenor} (monthly average)",
                                             "value": v, "_freq": "monthly"})

    # ---- Page 6: weighted-average lending and deposit rates ----------------
    if len(pages) > 5:
        wa = ["Lending rate — fresh (marginal)", "Lending rate — outstanding (stocks)",
              "Deposit rate — fresh (marginal)", "Deposit rate — outstanding (stocks)"]
        for line in pages[5].splitlines():
            toks = line.split()
            if len(toks) < 5:
                continue
            d = _my(toks[0])
            if d is None:
                continue
            for name, t in zip(wa, toks[1:5]):
                v = _f(t)
                if not pd.isna(v):
                    recs.append({"date": d, "series": f"{name} (PKR, all banks)",
                                 "value": v, "_freq": "monthly"})

    if not recs:
        return pd.DataFrame(columns=TIDY_COLS)

    frames = []
    df = pd.DataFrame(recs)
    for freq, grp in df.groupby("_freq"):
        frames.append(_tidy(grp.drop(columns="_freq").to_dict("records"),
                            "sbp_interest_rates", "%", freq))
    out = pd.concat(frames, ignore_index=True)

    # Page 6 lists a fiscal-year column (Jun-17 … Jun-25) beside a rolling
    # monthly column, so the June observations appear twice with identical
    # values. Collapsing them is safe; a genuine conflict would survive.
    return out.drop_duplicates(subset=["date", "series"], keep="first").reset_index(drop=True)



def _dates_across(df: pd.DataFrame, min_dates: int = 3):
    """Locate a header row whose cells are dates, for label-down/date-across sheets.

    Returns ``(header_row, {column: month_end_date}, label_column)`` or None.
    Several SBP archives are laid out this way — instruments or borrower classes
    down the rows, reporting months across the columns — which is the transpose
    of the more common layout.
    """
    # _coerce_period, not pd.to_datetime: SBP header rows switch from real
    # datetimes to strings such as 'Jul-18' or 'Jun-26P' partway across, and a
    # plain to_datetime silently drops the string half — truncating what looks
    # like a complete series years before its actual end.
    for i in range(min(14, len(df))):
        found = {}
        for c in range(df.shape[1]):
            d = _coerce_period(df.iat[i, c])
            if d is not None:
                found[c] = d
        if len(found) >= min_dates:
            label_col = max((c for c in range(min(found)) ), default=0)
            return i, found, label_col
    return None


def _rows_from_wide(df: pd.DataFrame, hdr: int, date_cols: dict, label_col: int):
    """Yield tidy records from a label-down/date-across block."""
    for r in range(hdr + 1, len(df)):
        label = df.iat[r, label_col]
        if pd.isna(label) or not str(label).strip():
            continue
        name = re.sub(r"\s+", " ", str(label)).strip()
        if re.match(r"(note|source|contact|e-mail|ph\.|p=|r=|\*)", name, re.I):
            continue
        for c, d in date_cols.items():
            yield {"date": d, "series": name, "value": _num(df.iat[r, c])}


def parse_sbp_reer_neer(path: Path) -> pd.DataFrame:
    """neer-reer.xls — nominal and real effective exchange rate indices.

    Found via SBP's own JSON file catalog. Two stacked blocks share one header:
    fiscal-year averages first, then a 'Monthly Position' block.

    Two quirks matter. The day component of the early dates is junk (Jan-2013
    through Dec-2013 are all stored with day 12), so every date is snapped to
    month end — which recovers the correct month in every case. And the series
    is **discontinued**: SBP stopped updating it after December 2023, having
    rebased and spliced the index when PBS discontinued the RPI in July 2020.
    The dashboard must present it as a historical series, not a current one.
    """
    df = _drop_empty(_read(path)).reset_index(drop=True)

    hdr = next((i for i in range(min(15, len(df)))
                if "neer" in " ".join(str(v) for v in df.iloc[i]).lower()
                and "reer" in " ".join(str(v) for v in df.iloc[i]).lower()), None)
    if hdr is None:
        return pd.DataFrame(columns=TIDY_COLS)

    # Row `hdr` names the index columns; the row below names the two
    # percentage-change columns that sit under a merged 'Percentage Change'
    # banner. Both are wanted, and each pair must keep its own unit.
    cols: dict[int, tuple[str, str]] = {}
    for c in range(df.shape[1]):
        v = str(df.iat[hdr, c]).strip().upper()
        if v in ("NEER", "REER"):
            cols[c] = (v, "index (2010 = 100)")
    for c in range(df.shape[1]):
        v = str(df.iat[hdr + 1, c]).strip().upper() if hdr + 1 < len(df) else ""
        if v in ("NEER", "REER") and c not in cols:
            cols[c] = (f"{v} \u2014 change over previous period", "%")
    if not cols:
        return pd.DataFrame(columns=TIDY_COLS)

    period_col = next((c for c in range(df.shape[1])
                       if "month average" in str(df.iat[hdr, c]).lower()), 1)

    annual, monthly = [], []
    bucket = annual
    for r in range(hdr + 2, len(df)):
        # The 'Monthly Position' divider is not in the period column — SBP put it
        # in the NEER column — so the whole row has to be scanned for it.
        row_text = " ".join(str(v) for v in df.iloc[r].tolist() if pd.notna(v))
        if "monthly position" in row_text.lower():
            bucket = monthly
            continue
        raw = df.iat[r, period_col]
        if isinstance(raw, str):
            if re.match(r"\s*(note|source|contact|e-mail|ph\.|\*|P=|i+\.|iv\.|v\.)",
                        raw, re.I):
                break
            continue
        d = pd.to_datetime(raw, errors="coerce")
        if pd.isna(d) or not (MIN_DATE <= d <= MAX_DATE):
            continue
        d = pd.Timestamp(d) + pd.offsets.MonthEnd(0)
        for c, (name, unit) in cols.items():
            bucket.append({"date": d, "series": name,
                           "value": _num(df.iat[r, c]), "_unit": unit})

    frames = []
    if annual:
        frames.append(_tidy([{**x, "series": f"{x['series']} (fiscal-year average)"}
                             for x in annual], "sbp_reer_neer",
                            "index (2010 = 100)", "annual"))
    if monthly:
        frames.append(_tidy(monthly, "sbp_reer_neer", "index (2010 = 100)", "monthly"))
    if not frames:
        return pd.DataFrame(columns=TIDY_COLS)
    return pd.concat(frames, ignore_index=True)


def parse_sbp_credit_loans(path: Path) -> pd.DataFrame:
    """CreditLoans-arch.xls — credit and loans to the private sector.

    Three sheets, three different shapes, three different eras:

      * 'Pvt Sector Credit Jun 01 to 06'  periods DOWN the rows, 2001-06 to 2006-06
      * 'WEB COPY-Archive'                dates ACROSS the columns, 2006-06 onward
      * 'Archive ISIC 4'                  the same but reclassified to ISIC rev. 4

    The first two are read and stacked so the headline private-sector credit
    series runs unbroken from 2001. The ISIC sheet is read separately and its
    series are suffixed, because SBP's ISIC-4 reclassification means a borrower
    category with the same name is not the same aggregate before and after the
    switch; merging them silently would fabricate a break-free series.
    """
    book = pd.ExcelFile(path)
    recs: list[dict] = []

    for sheet in book.sheet_names:
        df = _drop_empty(book.parse(sheet, header=None)).reset_index(drop=True)
        if df.empty:
            continue
        isic = "isic" in sheet.lower()
        suffix = " (ISIC rev. 4 basis)" if isic else ""

        # Layout A: a 'Period' column with dates running down it.
        period_col = None
        hdr_a = None
        for i in range(min(14, len(df))):
            for c in range(df.shape[1]):
                if str(df.iat[i, c]).strip().lower() == "period":
                    hdr_a, period_col = i, c
                    break
            if hdr_a is not None:
                break

        if hdr_a is not None:
            labels = {}
            for c in range(period_col + 1, df.shape[1]):
                v = df.iat[hdr_a, c]
                if pd.notna(v) and str(v).strip():
                    labels[c] = re.sub(r"\s+", " ", str(v)).strip()
            for r in range(hdr_a + 1, len(df)):
                d = pd.to_datetime(df.iat[r, period_col], errors="coerce")
                if pd.isna(d) or not (MIN_DATE <= d <= MAX_DATE):
                    continue
                d = pd.Timestamp(d) + pd.offsets.MonthEnd(0)
                for c, name in labels.items():
                    recs.append({"date": d, "series": f"{name}{suffix}",
                                 "value": _num(df.iat[r, c])})
            continue

        # Layout B: dates across the header row.
        found = _dates_across(df)
        if found is None:
            continue
        hdr_b, date_cols, label_col = found
        for rec in _rows_from_wide(df, hdr_b, date_cols, label_col):
            rec["series"] = f"{rec['series']}{suffix}"
            recs.append(rec)

    if not recs:
        return pd.DataFrame(columns=TIDY_COLS)
    out = _tidy(recs, "sbp_credit_loans_by_borrower", "million PKR", "monthly")
    # The two non-ISIC sheets overlap at June 2006 with identical values.
    return out.drop_duplicates(subset=["date", "series"], keep="last").reset_index(drop=True)


def parse_sbp_domestic_debt(path: Path) -> pd.DataFrame:
    """D-Debt-Liabilities.xls — government domestic debt by instrument.

    Dates run across the columns and instruments down the rows. The workbook is
    split into era sheets because the instrument taxonomy changed in July 2022;
    every sheet whose header row carries dates is read, which also picks up the
    'DD (Outstanding)' summary sheet where its first column is a revision-marked
    label rather than a date.

    Values are BILLIONS of rupees here, unlike the millions used by most other
    SBP archives, so the unit is stated explicitly.
    """
    book = pd.ExcelFile(path)
    recs: list[dict] = []
    for sheet in book.sheet_names:
        df = _drop_empty(book.parse(sheet, header=None)).reset_index(drop=True)
        if df.empty:
            continue
        found = _dates_across(df)
        if found is None:
            continue
        recs.extend(_rows_from_wide(df, *found))

    if not recs:
        return pd.DataFrame(columns=TIDY_COLS)
    out = _tidy(recs, "sbp_domestic_debt", "billion PKR", "monthly")
    # Era sheets overlap at the boundary; the later sheet reflects the current
    # taxonomy and _tidy has already sorted, so the last value wins.
    return out.drop_duplicates(subset=["date", "series"], keep="last").reset_index(drop=True)

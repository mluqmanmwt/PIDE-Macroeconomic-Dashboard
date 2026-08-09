"""
Stage 3 — VALIDATE.

Data quality gates that run after every ETL cycle. The point is not to prove the
data is correct — only PBS and SBP can do that — but to catch the failure modes
that actually occur with GoP spreadsheets:

  * a parser silently returning an empty or collapsed table after a layout change
  * a series going stale because the publisher moved a file
  * duplicated (date, series) pairs from overlapping archive sheets
  * values that are obviously not the quantity they claim to be
    (a negative CPI index, a policy rate of 4,300, reserves of 1e12)

Failures are written to data/metadata/validation_report.csv and, for `error`
severity, exit non-zero so CI fails loudly rather than publishing bad numbers.

    python -m etl.validate
"""

from __future__ import annotations

import re
import sys

import pandas as pd

from .common import METADATA, PROCESSED, load_config, log

# Staleness budget per publication frequency, in days. Generous multiples of the
# nominal period because GoP releases routinely slip by a week or more.
STALENESS_DAYS = {"daily": 14, "weekly": 30, "monthly": 120,
                  "quarterly": 300, "annual": 800}

# Plausibility envelopes. Deliberately wide — these catch unit and parsing
# errors (a rate read as an index, millions read as units), not policy surprises.
RANGES = {
    "index": (0, 100_000),
    "%": (-100, 200),
    "million usd": (-100_000, 2_000_000),
    "million pkr": (-1e9, 1e11),
}


def _envelope(unit: str) -> tuple[float, float] | None:
    u = (unit or "").lower()
    for key, rng in RANGES.items():
        if key in u:
            return rng
    return None


def check(master: pd.DataFrame, sources: list) -> pd.DataFrame:
    by_id = {s.id: s for s in sources}
    today = pd.Timestamp.today().normalize()
    issues: list[dict] = []

    def add(sev, sid, series, kind, detail):
        issues.append({"severity": sev, "source_id": sid, "series": series,
                       "check": kind, "detail": detail})

    for sid, g in master.groupby("source_id"):
        src = by_id.get(sid)
        freq = (src.frequency if src else g["frequency"].iloc[0]) or "monthly"

        # --- coverage -------------------------------------------------------
        if len(g) < 5:
            add("error", sid, "", "too_few_rows",
                f"only {len(g)} row(s) parsed — likely a layout change upstream")

        # --- freshness ------------------------------------------------------
        # A discontinued series is permanently stale by definition. Flagging it
        # every run would train the reader to ignore staleness warnings, which
        # are the one signal that catches a publisher silently moving a file.
        budget = STALENESS_DAYS.get(freq, 120)
        age = (today - g["date"].max()).days
        if age > budget and not (src and getattr(src, "discontinued", False)):
            add("warning", sid, "", "stale",
                f"latest observation {g['date'].max().date()} is {age}d old "
                f"(budget {budget}d for {freq})")

        # --- duplicates -----------------------------------------------------
        dup = g.duplicated(subset=["date", "series"]).sum()
        if dup:
            add("error", sid, "", "duplicate_observations",
                f"{dup} duplicated (date, series) pair(s)")

        # --- plausibility ---------------------------------------------------
        for series, gs in g.groupby("series"):
            rng = _envelope(gs["unit"].iloc[0])
            if rng is None:
                continue
            bad = gs[(gs["value"] < rng[0]) | (gs["value"] > rng[1])]
            if len(bad):
                add("warning", sid, series, "out_of_range",
                    f"{len(bad)} value(s) outside {rng}; "
                    f"e.g. {bad['value'].iloc[0]:,.2f} on {bad['date'].iloc[0].date()}")

            # A constant series usually means one cell was broadcast across a row.
            # Basket weights are the legitimate exception: PBS republishes the same
            # CPI expenditure weight every month until the base year is revised.
            is_weight = bool(re.search(r"(_WT\b|weight)", series, re.I))
            if not is_weight and len(gs) > 12 and gs["value"].nunique() == 1:
                add("warning", sid, series, "constant_series",
                    f"all {len(gs)} observations equal {gs['value'].iloc[0]}")

    return pd.DataFrame(issues)


def run() -> pd.DataFrame:
    """Validate the master table, write the report and log a summary.

    Split out from `main` so the orchestrator can inspect the report itself
    rather than inferring outcomes from an exit code.
    """
    path = PROCESSED / "macro_master.parquet"
    if not path.exists():
        raise FileNotFoundError("macro_master.parquet missing — run etl.transform first")

    master = pd.read_parquet(path)
    _, sources = load_config()
    report = check(master, sources)

    out = METADATA / "validation_report.csv"
    report.to_csv(out, index=False)

    n_err = int((report["severity"] == "error").sum()) if len(report) else 0
    n_warn = int((report["severity"] == "warning").sum()) if len(report) else 0

    log.info("=" * 78)
    log.info("VALIDATION — %d dataset(s), %d series, %d observation(s)",
             master["source_id"].nunique(), master["series"].nunique(), len(master))
    log.info("  %d error(s), %d warning(s) -> %s", n_err, n_warn, out)

    if len(report):
        for (sid, chk, sev), g in report.groupby(["source_id", "check", "severity"]):
            lvl = log.error if sev == "error" else log.warning
            extra = f" (+{len(g) - 1} more series)" if len(g) > 1 else ""
            lvl("  [%s] %-26s %-22s %s%s", sev, sid, chk, g["detail"].iloc[0], extra)

    return report


def main(argv: list[str] | None = None) -> int:
    path = PROCESSED / "macro_master.parquet"
    if not path.exists():
        log.error("macro_master.parquet missing — run `python -m etl.transform` first")
        return 1

    master = pd.read_parquet(path)
    _, sources = load_config()
    report = check(master, sources)

    out = METADATA / "validation_report.csv"
    report.to_csv(out, index=False)

    n_err = int((report["severity"] == "error").sum()) if len(report) else 0
    n_warn = int((report["severity"] == "warning").sum()) if len(report) else 0

    log.info("=" * 78)
    log.info("VALIDATION — %d dataset(s), %d series, %d observation(s)",
             master["source_id"].nunique(), master["series"].nunique(), len(master))
    log.info("  %d error(s), %d warning(s) -> %s", n_err, n_warn, out)

    # Roll up by (source, check) so one bad sheet does not print 200 near-identical
    # lines and bury the errors that actually need attention.
    if len(report):
        for (sid, chk, sev), g in report.groupby(["source_id", "check", "severity"]):
            lvl = log.error if sev == "error" else log.warning
            extra = f" (+{len(g) - 1} more series)" if len(g) > 1 else ""
            lvl("  [%s] %-26s %-22s %s%s", sev, sid, chk, g["detail"].iloc[0], extra)

    return 1 if n_err else 0


if __name__ == "__main__":
    sys.exit(main())

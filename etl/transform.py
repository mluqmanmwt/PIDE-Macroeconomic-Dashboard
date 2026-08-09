"""
Stage 2 — TRANSFORM.

Reads `data/raw/<publisher>/<id>__latest.<fmt>`, runs the parser declared in
config/sources.yaml, and writes tidy long-format output to data/processed/.

Outputs
-------
data/processed/<source_id>.parquet     one tidy table per source
data/processed/<source_id>.csv         same, human-inspectable
data/processed/macro_master.parquet    every tidy series concatenated
data/metadata/series_index.csv         catalogue of every series the dashboard can plot

Tidy contract: date | series | value | unit | source_id | frequency

Usage
-----
    python -m etl.transform
    python -m etl.transform --id pbs_cpi_historical
"""

from __future__ import annotations

import argparse
import traceback
from pathlib import Path

import pandas as pd

from .common import METADATA, PROCESSED, RAW, load_config, log, select
from .parsers import pbs as pbs_parsers
from .parsers import sbp as sbp_parsers

REGISTRY = {
    # SBP
    "parse_sbp_forex": sbp_parsers.parse_sbp_forex,
    "parse_sbp_interest_rates": sbp_parsers.parse_sbp_interest_rates,
    "parse_sbp_reer_neer": sbp_parsers.parse_sbp_reer_neer,
    "parse_sbp_credit_loans": sbp_parsers.parse_sbp_credit_loans,
    "parse_sbp_domestic_debt": sbp_parsers.parse_sbp_domestic_debt,
    "parse_sbp_remittances": sbp_parsers.parse_sbp_remittances,
    "parse_sbp_m2": sbp_parsers.parse_sbp_m2,
    "parse_sbp_ir_corridor": sbp_parsers.parse_sbp_ir_corridor,
    "parse_sbp_balance_of_trade": sbp_parsers.parse_sbp_balance_of_trade,
    "parse_sbp_gdp_annual": sbp_parsers.parse_sbp_gdp_annual,
    "parse_sbp_gdp_quarterly": sbp_parsers.parse_sbp_gdp_quarterly,
    "parse_sbp_lsm": sbp_parsers.parse_sbp_lsm,
    # PBS
    "parse_pbs_cpi_historical": pbs_parsers.parse_pbs_cpi_historical,
    "parse_pbs_spi": pbs_parsers.parse_pbs_spi,
    "parse_pbs_trade_summary": pbs_parsers.parse_pbs_trade_summary,
    "parse_pbs_services_summary": pbs_parsers.parse_pbs_services_summary,
    "parse_sdmx_generic": pbs_parsers.parse_sdmx_generic,
    "parse_sdmx_mof_ggo": pbs_parsers.parse_sdmx_mof_ggo,
    "parse_sdmx_mof_cgo": pbs_parsers.parse_sdmx_mof_cgo,
    "parse_sdmx_pbs_trade": pbs_parsers.parse_sdmx_pbs_trade,
    "parse_sdmx_pbs_qna": pbs_parsers.parse_sdmx_pbs_qna,
    "parse_sdmx_pbs_ppi": pbs_parsers.parse_sdmx_pbs_ppi,
    "parse_sdmx_pbs_energy": pbs_parsers.parse_sdmx_pbs_energy,
    "parse_sdmx_pbs_labour": pbs_parsers.parse_sdmx_pbs_labour,
}

# Sources where each published file is a single-period release rather than a full
# history. For these we parse EVERY dated snapshot in data/raw/ and union the
# results, so the series grows by one observation per release instead of being
# overwritten. This is why raw snapshots are kept rather than replaced.
ACCUMULATING = {"pbs_spi_weekly", "pbs_trade_summary_monthly",
                "pbs_trade_services_summary"}


def latest_path(source) -> Path | None:
    p = RAW / source.publisher / f"{source.id}__latest.{source.fmt}"
    return p if p.exists() else None


def snapshots(source) -> list[Path]:
    """Every dated raw snapshot for a source, oldest first.

    The `__latest` pointer is excluded because it duplicates one of the dated
    files; including it would double-count the newest observation.
    """
    d = RAW / source.publisher
    return sorted(p for p in d.glob(f"{source.id}__*.{source.fmt}")
                  if "__latest" not in p.name)


def transform_one(source) -> pd.DataFrame | None:
    if not source.parser:
        return None
    fn = REGISTRY.get(source.parser)
    if fn is None:
        log.warning("no parser function registered: %s", source.parser)
        return None
    path = latest_path(source)
    if path is None:
        log.warning("raw file missing for %s — run `python -m etl.extract` first", source.id)
        return None

    try:
        if source.id in ACCUMULATING:
            snaps = snapshots(source)
            frames = []
            for p in snaps:
                try:
                    f = fn(p)
                except Exception:  # noqa: BLE001
                    continue
                if f is not None and not f.empty:
                    frames.append(f)
            df = (pd.concat(frames, ignore_index=True)
                    .drop_duplicates(subset=["date", "series"], keep="last")
                    .sort_values(["series", "date"])
                    .reset_index(drop=True)) if frames else None
            if df is not None:
                log.info("    (accumulated %d snapshot file(s))", len(frames))
        else:
            df = fn(path)
    except Exception:  # noqa: BLE001
        log.error("parser %s failed for %s:\n%s", source.parser, source.id,
                  traceback.format_exc(limit=3))
        return None

    if df is None or df.empty:
        log.warning("parser %s produced no rows for %s", source.parser, source.id)
        return None

    df.to_parquet(PROCESSED / f"{source.id}.parquet", index=False)
    df.to_csv(PROCESSED / f"{source.id}.csv", index=False)

    # A few sources (e.g. the LSM item snapshot) are legitimately wide tables
    # with no single date axis. Persist them, but keep them out of the tidy master.
    if not set(["date", "series", "value"]).issubset(df.columns):
        log.info("  ✓ %-32s %6d rows | wide snapshot table (excluded from master)",
                 source.id, len(df))
        return None

    log.info("  ✓ %-32s %6d rows | %4d series | %s → %s",
             source.id, len(df), df["series"].nunique(),
             df["date"].min().date(), df["date"].max().date())
    return df


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Tidy raw GoP files into long format")
    ap.add_argument("--id", nargs="*")
    ap.add_argument("--theme", nargs="*")
    args = ap.parse_args(argv)

    _, sources = load_config()
    targets = [s for s in select(sources, ids=args.id, themes=args.theme) if s.parser]

    log.info("=" * 78)
    log.info("PIDE Macro Dashboard — TRANSFORM | %d parseable source(s)", len(targets))
    log.info("=" * 78)

    frames, index_rows = [], []
    for s in targets:
        df = transform_one(s)
        if df is None:
            continue
        frames.append(df)
        for series, grp in df.groupby("series"):
            index_rows.append({
                "source_id": s.id, "dataset": s.name, "publisher": s.publisher,
                "theme": s.theme, "series": series,
                "unit": grp["unit"].iloc[0], "frequency": grp["frequency"].iloc[0],
                "start": grp["date"].min().date(), "end": grp["date"].max().date(),
                "n_obs": len(grp), "page": s.page,
            })

    if frames:
        master = pd.concat(frames, ignore_index=True)
        master.to_parquet(PROCESSED / "macro_master.parquet", index=False)
        pd.DataFrame(index_rows).sort_values(["theme", "source_id", "series"]) \
            .to_csv(METADATA / "series_index.csv", index=False)
        log.info("-" * 78)
        log.info("master: %d rows | %d series | %d datasets",
                 len(master), master["series"].nunique(), master["source_id"].nunique())
        return 0

    log.error("no data produced")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

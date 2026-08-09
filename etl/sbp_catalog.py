"""SBP file-library catalog.

SBP's Economic Data section is rendered client-side from three static JSON
documents. They are served from the ordinary asset host with no API key, no
session and no Cloudflare challenge, and between them they index roughly every
statistical file SBP publishes — title, publication date, frequency, direct
attachment URL and, crucially, the *cumulative archive* URL that carries the
full history rather than the latest vintage only.

That makes them a far better automation surface than parsing the site HTML:

  * URLs come from the publisher instead of being guessed, so a renamed file is
    picked up automatically rather than turning into a silent soft-404.
  * The publication date lets the pipeline decide whether a refetch is worth it.
  * New products appear in the catalog the moment SBP publishes them.

The catalog is therefore both a *discovery* mechanism for the extractor and a
standing inventory that feeds the data catalog in the docs.

Usage
-----
    python -m etl.sbp_catalog            # refresh and write the flat CSV
    python -m etl.sbp_catalog --grep reer
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import pandas as pd

from .common import METADATA, ROOT, Fetcher, load_config, log

CATALOGS = {
    "main": "https://www.sbp.org.pk/assets/dt_collection_75160/econmicMainDataNew.json",
    "real": "https://www.sbp.org.pk/assets/dt_collection_75160/econmicRealSectorData.json",
    "external": "https://www.sbp.org.pk/assets/dt_collection_75160/econmicExternoaSectorData.json",
}

OUT = METADATA / "sbp_file_catalog.csv"


def _rows(blob: dict, catalog: str):
    """Flatten {parent: {child: {frequency: {year: [entry, ...]}}}}."""
    for parent, children in (blob or {}).items():
        if not isinstance(children, dict):
            continue
        for child, freqs in children.items():
            if not isinstance(freqs, dict):
                continue
            for freq, years in freqs.items():
                if not isinstance(years, dict):
                    continue
                for year, entries in years.items():
                    for e in entries or []:
                        if not isinstance(e, dict):
                            continue
                        att = e.get("attachment") or {}
                        arc = e.get("commulative_archive") or {}
                        yield {
                            "catalog": catalog,
                            "parent": parent,
                            "child": child,
                            # SBP writes 'no-frequency' where the cadence is
                            # irregular; keep it as an explicit unknown.
                            "frequency": None if freq == "no-frequency" else freq,
                            "year": year,
                            "title": (e.get("title") or "").strip(),
                            "published": e.get("date"),
                            "file_name": att.get("file_name"),
                            "url": att.get("url"),
                            "fmt": (att.get("file_name") or "").rsplit(".", 1)[-1].lower() or None,
                            "bytes": att.get("file_size"),
                            # The archive file is what a time series actually
                            # needs; the primary attachment is often a single
                            # dated bulletin.
                            "archive_file_name": arc.get("file_name"),
                            "archive_url": arc.get("url"),
                        }


def refresh(fetcher: Fetcher | None = None) -> pd.DataFrame:
    """Download all three catalogs and return one flat table."""
    defaults, _ = load_config()
    fetcher = fetcher or Fetcher(defaults)

    rows: list[dict] = []
    for name, url in CATALOGS.items():
        try:
            blob = json.loads(fetcher.get(url).content.decode("utf-8", "replace"))
        except Exception as exc:  # a dead catalog must not kill the run
            log.warning("  sbp catalog %-9s unavailable: %s", name, exc)
            continue
        got = list(_rows(blob, name))
        log.info("  sbp catalog %-9s %4d entries", name, len(got))
        rows.extend(got)

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    df = df.sort_values(["parent", "child", "published"], na_position="first")
    df = df.drop_duplicates(subset=["url", "title", "year"], keep="last")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT, index=False)
    log.info("  -> %s (%d rows)", OUT.relative_to(ROOT), len(df))
    return df


def load() -> pd.DataFrame:
    """Read the cached catalog, refreshing it if absent."""
    if OUT.exists():
        return pd.read_csv(OUT)
    return refresh()


def find(pattern: str, field: str = "title") -> pd.DataFrame:
    """Case-insensitive regex lookup across the catalog."""
    df = load()
    if df.empty:
        return df
    cols = [field] if field != "any" else ["title", "child", "parent", "file_name"]
    mask = pd.Series(False, index=df.index)
    for c in cols:
        mask |= df[c].astype(str).str.contains(pattern, case=False, regex=True, na=False)
    return df[mask]


def resolve_url(pattern: str, prefer_archive: bool = True) -> str | None:
    """Best current URL for a product matched by title/child regex.

    `prefer_archive` returns the cumulative history file when SBP offers one,
    which is almost always what a time series wants.
    """
    hits = find(pattern, field="any")
    if hits.empty:
        return None
    hits = hits.sort_values("published", na_position="first")
    row = hits.iloc[-1]
    if prefer_archive and isinstance(row.get("archive_url"), str) and row["archive_url"]:
        return row["archive_url"]
    return row.get("url") or None


def main() -> int:
    ap = argparse.ArgumentParser(description="Refresh or query the SBP file catalog.")
    ap.add_argument("--grep", help="regex to search across title/child/parent/file name")
    ap.add_argument("--no-refresh", action="store_true", help="query the cached copy only")
    args = ap.parse_args()

    df = load() if args.no_refresh else refresh()
    if df.empty:
        log.error("catalog is empty")
        return 1

    if args.grep:
        hits = find(args.grep, field="any")
        log.info("%d match(es) for %r", len(hits), args.grep)
        for _, r in hits.iterrows():
            log.info("  %-58s %-10s %s", str(r["title"])[:58],
                     r["published"], r["archive_url"] or r["url"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

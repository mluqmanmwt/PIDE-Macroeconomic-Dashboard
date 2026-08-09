"""
Backfill historical snapshots for single-period PBS releases.

Some of the most useful PBS datasets are published as one file per period:

    3.-SPI-Report-06.08.2026.xlsx      one week
    Summary-July-2026.xlsx             one month of merchandise trade
    Services-Summary-June-2026.xlsx    one month of services trade

A normal ETL run only fetches the newest file, so a fresh clone of this repo
starts with a one-observation series. That is a cold-start problem, not a data
problem: PBS keeps the older files online and the WordPress media API will list
them. This module pages through that API and downloads every historical release
it can find, writing them as ordinary dated snapshots so `etl.transform` picks
them up through its normal accumulation path.

Run once after cloning, then never again:

    python -m etl.backfill --id pbs_spi_weekly --pages 12
    python -m etl.backfill --all
"""

from __future__ import annotations

import argparse
import re
from urllib.parse import unquote

from .common import (RAW, Fetcher, load_config, log, looks_like_html_error,
                     select, sha256_bytes, snapshot_name)
from .discover import PBS_MEDIA_API, _filter

BACKFILLABLE = ("pbs_spi_weekly", "pbs_trade_summary_monthly",
                "pbs_trade_services_summary")


def _media_page(fetcher: Fetcher, query: str, page: int, per_page: int = 100) -> list[dict]:
    r = fetcher.session.get(PBS_MEDIA_API,
                            params={"search": query, "per_page": per_page,
                                    "page": page, "orderby": "date", "order": "desc"},
                            timeout=fetcher.timeout)
    if r.status_code == 400:      # WordPress returns 400 past the last page
        return []
    r.raise_for_status()
    return r.json()


def backfill_source(fetcher: Fetcher, source, pages: int) -> int:
    if not source.query:
        log.warning("%s has no search query \u2014 cannot backfill", source.id)
        return 0

    out_dir = RAW / source.publisher
    out_dir.mkdir(parents=True, exist_ok=True)

    # Index what we already hold by the publisher's own filename, so re-running
    # backfill is cheap and idempotent rather than re-downloading everything.
    have = {m.group(1).lower()
            for p in out_dir.glob(f"{source.id}__*.{source.fmt}")
            if (m := re.search(r"__\d{8}__(.+)$", p.stem))}

    candidates: list[dict] = []
    for page in range(1, pages + 1):
        try:
            items = _media_page(fetcher, source.query, page)
        except Exception as exc:  # noqa: BLE001
            log.warning("[backfill] %s page %d failed: %s", source.id, page, exc)
            break
        if not items:
            break
        for m in items:
            url = m.get("source_url", "")
            if url.lower().endswith("." + source.fmt.lower()):
                candidates.append({"url": url, "date": m.get("date", "")[:10],
                                   "title": ""})

    candidates = _filter(candidates, source)
    log.info("[backfill] %s: %d historical file(s) listed", source.id, len(candidates))

    added = 0
    for c in candidates:
        stem = re.sub(r"\.[A-Za-z0-9]+$", "", unquote(c["url"].rsplit("/", 1)[-1]))
        stem = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("_")[:80]
        if stem.lower() in have:
            continue
        try:
            content = fetcher.get(c["url"]).content
        except Exception as exc:  # noqa: BLE001
            log.warning("  ! %s: %s", c["url"].rsplit("/", 1)[-1], exc)
            continue
        if looks_like_html_error(content, source.fmt):
            log.warning("  ! %s returned an HTML error page", c["url"].rsplit("/", 1)[-1])
            continue

        # Date the snapshot by the publisher's upload date, not today, so the
        # raw directory reflects when the data was actually released.
        stamp = (c["date"] or "").replace("-", "") or None
        snap = out_dir / snapshot_name(source.id, source.fmt, stamp=stamp, origin=c["url"])
        if snap.exists() and sha256_bytes(snap.read_bytes()) == sha256_bytes(content):
            continue
        snap.write_bytes(content)
        have.add(stem.lower())
        added += 1
        log.info("  + %s (%d bytes)", snap.name, len(content))

    log.info("[backfill] %s: %d new snapshot(s)", source.id, added)
    return added


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Backfill historical PBS period files")
    ap.add_argument("--id", nargs="*")
    ap.add_argument("--all", action="store_true")
    # --tier/--theme are accepted so this stage takes the same selectors as
    # extract and transform. The orchestrator forwards whatever filter the user
    # gave it; without these it had to be called bare, and argparse then aborted
    # the entire run from inside a stage that was meant to be non-fatal.
    ap.add_argument("--tier", nargs="*", type=int)
    ap.add_argument("--theme", nargs="*")
    ap.add_argument("--pages", type=int, default=6,
                    help="media-API pages to walk (100 items each)")
    args = ap.parse_args(argv)

    defaults, sources = load_config()
    if args.id:
        ids = list(args.id)
    elif args.tier or args.theme:
        # Only sources that actually have a period-file backfill rule are
        # candidates; a tier filter otherwise selects sources this stage
        # cannot act on and reports misleading work.
        ids = [s.id for s in sources
               if s.id in BACKFILLABLE
               and (not args.tier or s.tier in args.tier)
               and (not args.theme or s.theme in args.theme)]
        if not ids:
            log.info("no backfillable sources match the given filters; nothing to do")
            return 0
    elif args.all:
        ids = list(BACKFILLABLE)
    else:
        ap.error("pass --id <source>, --tier <n>, --theme <name>, or --all")

    fetcher = Fetcher(defaults)
    total = sum(backfill_source(fetcher, s, args.pages) for s in select(sources, ids=ids))
    log.info("=" * 78)
    log.info("backfill complete \u2014 %d new snapshot(s). Re-run `python -m etl.transform`.", total)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

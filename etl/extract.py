"""
Stage 1 — EXTRACT.

Download every registered source into data/raw/<publisher>/ with:
  * a dated snapshot  `<id>__YYYYMMDD.<fmt>`  (immutable history)
  * a stable pointer   `<id>__latest.<fmt>`    (what the dashboard reads)

Content-hash comparison means re-running daily costs almost nothing: unchanged
files are recorded as `unchanged` and the snapshot is not duplicated.

Usage
-----
    python -m etl.extract                      # everything
    python -m etl.extract --tier 1             # dashboard core only
    python -m etl.extract --theme inflation external
    python -m etl.extract --id sbp_forex_reserves pbs_cpi_historical
    python -m etl.extract --dry-run
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone

from .common import (RAW, Fetcher, RunRecord, load_config, load_manifest, log,
                     looks_like_html_error, record, save_manifest, select,
                     sha256_bytes, snapshot_name, write_latest)
from .discover import resolve


def extract_one(fetcher: Fetcher, source, manifest: dict, dry_run: bool = False) -> RunRecord:
    prev = manifest["sources"].get(source.id, {})
    candidates = resolve(fetcher, source)

    if not candidates:
        return RunRecord(
            source_id=source.id, name=source.name, publisher=source.publisher,
            theme=source.theme, tier=source.tier, status="skipped", page=source.page,
            error="no downloadable URL resolved (manual or browser-only source)",
        )

    url = candidates[0]["url"]

    if dry_run:
        return RunRecord(source_id=source.id, name=source.name, publisher=source.publisher,
                         theme=source.theme, tier=source.tier, status="dry-run",
                         url=url, page=source.page)

    try:
        resp = fetcher.get(url)
        content = resp.content
    except Exception as exc:  # noqa: BLE001
        return RunRecord(source_id=source.id, name=source.name, publisher=source.publisher,
                         theme=source.theme, tier=source.tier, status="failed",
                         url=url, page=source.page, error=str(exc)[:300])

    if looks_like_html_error(content, source.fmt):
        return RunRecord(source_id=source.id, name=source.name, publisher=source.publisher,
                         theme=source.theme, tier=source.tier, status="failed",
                         url=url, page=source.page,
                         error=f"server returned HTML/soft-404 instead of .{source.fmt} "
                               f"({len(content)} bytes)")

    digest = sha256_bytes(content)
    if prev.get("sha256") == digest:
        log.info("  = %-38s unchanged (%s)", source.id, digest[:10])
        rec = RunRecord(**{**prev,
                           "status": "unchanged",
                           "fetched_at": datetime.now(timezone.utc).isoformat()})
        return rec

    out_dir = RAW / source.publisher
    out_dir.mkdir(parents=True, exist_ok=True)
    snap = out_dir / snapshot_name(source.id, source.fmt, origin=url)
    snap.write_bytes(content)
    latest = write_latest(snap, source.id, source.fmt, source.publisher)

    log.info("  + %-38s %8d bytes -> %s", source.id, len(content), snap.name)
    return RunRecord(
        source_id=source.id, name=source.name, publisher=source.publisher,
        theme=source.theme, tier=source.tier, status="downloaded", url=url,
        page=source.page, path=str(snap.relative_to(RAW.parents[1])),
        latest_path=str(latest.relative_to(RAW.parents[1])),
        bytes=len(content), sha256=digest,
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Download official GoP macro datasets")
    ap.add_argument("--tier", nargs="*", type=int)
    ap.add_argument("--theme", nargs="*")
    ap.add_argument("--id", nargs="*")
    ap.add_argument("--publisher", nargs="*")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    defaults, sources = load_config()
    targets = select(sources, themes=args.theme, tiers=args.tier,
                     ids=args.id, publishers=args.publisher)

    log.info("=" * 78)
    log.info("PIDE Macro Dashboard — EXTRACT | %d source(s)", len(targets))
    log.info("=" * 78)

    fetcher = Fetcher(defaults)
    manifest = load_manifest()
    results: list[RunRecord] = []

    for s in targets:
        rec = extract_one(fetcher, s, manifest, dry_run=args.dry_run)
        results.append(rec)
        if not args.dry_run:
            record(manifest, rec)

    if not args.dry_run:
        manifest["runs"].append({
            "at": datetime.now(timezone.utc).isoformat(),
            "requested": len(targets),
            "downloaded": sum(r.status == "downloaded" for r in results),
            "unchanged": sum(r.status == "unchanged" for r in results),
            "skipped": sum(r.status == "skipped" for r in results),
            "failed": sum(r.status == "failed" for r in results),
        })
        manifest["runs"] = manifest["runs"][-60:]
        save_manifest(manifest)

    log.info("-" * 78)
    for status in ("downloaded", "unchanged", "skipped", "failed", "dry-run"):
        n = sum(r.status == status for r in results)
        if n:
            log.info("%-11s %3d", status, n)
    for r in results:
        if r.status == "failed":
            log.error("FAILED %-34s %s", r.source_id, r.error)

    # Non-zero exit only if a Tier-1 (dashboard-critical) source failed.
    critical = [r for r in results if r.status == "failed" and r.tier == 1]
    return 1 if critical else 0


if __name__ == "__main__":
    raise SystemExit(main())

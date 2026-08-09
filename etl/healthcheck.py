"""Probe every catalogued source URL and report what is actually being served.

Why this exists separately from `validate.py`
---------------------------------------------
`validate.py` inspects data that has already been parsed, so it can only see a
problem once a source is wired up and flowing. Most of this catalogue is not
flowing: of 75 catalogued sources, 24 have parsers. The remaining tier-2 and
tier-3 entries are research assets — someone will come back and wire them up —
and a URL that has quietly rotted in the meantime is expensive to rediscover.

This module answers a narrower question for every source, wired or not: does the
URL still return the kind of file the catalogue says it should?

It is deliberately non-destructive. Nothing is written to `data/raw/`, no
manifest is touched and no snapshot is taken. It can be run against production
data at any time without side effects.

Detection notes
---------------
Content type is judged by magic bytes rather than by the Content-Type header or
the HTTP status. This is not defensive over-engineering: `sbp.org.pk/ecodata/`
is a dead path that returns HTTP 200 with a ~204 KB HTML body, so a status-code
check alone reports it as healthy. Several PBS paths behave the same way after a
site migration.

Only the first chunk of each response is read. Some catalogued files are very
large — the NEPRA State of Industry report for 2025 is roughly 332 MB — and
downloading them in full to check a signature would make the job unusable.

Usage
-----
    python -m etl.healthcheck                  # every source with a static URL
    python -m etl.healthcheck --tier 1
    python -m etl.healthcheck --fail-on-error  # non-zero exit for CI
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone

from .common import METADATA, Fetcher, load_config, log

# Leading bytes that identify the formats this catalogue contains. Checked in
# order; the first match wins.
SIGNATURES: list[tuple[bytes, str]] = [
    (b"PK\x03\x04", "zip/xlsx/docx"),
    (b"\xd0\xcf\x11\xe0", "xls (OLE2)"),
    (b"%PDF-", "pdf"),
    (b"<?xml", "xml"),
    (b"\x1f\x8b", "gzip"),
]

# A response whose body starts with any of these is a web page, whatever the
# status line claims.
HTML_MARKERS = (b"<!doctype html", b"<html", b"<!DOCTYPE HTML")

# Which sniffed types are acceptable for each catalogued format. `xml` is allowed
# for spreadsheet formats because a few publishers serve SpreadsheetML.
COMPATIBLE: dict[str, set[str]] = {
    "xlsx": {"zip/xlsx/docx", "xml"},
    "xls": {"xls (OLE2)", "zip/xlsx/docx", "xml"},
    "pdf": {"pdf"},
    "xml": {"xml"},
    "zip": {"zip/xlsx/docx"},
    "csv": {"text"},
    "json": {"text"},
}


def _sniff(chunk: bytes) -> str:
    head = chunk[:512]
    if any(head.lstrip()[: len(m)].lower() == m.lower() for m in HTML_MARKERS):
        return "html"
    for sig, name in SIGNATURES:
        if chunk.startswith(sig):
            return name
    try:
        chunk.decode("utf-8")
        return "text"
    except UnicodeDecodeError:
        return "binary (unrecognised)"


def probe(source, fetcher: Fetcher) -> dict:
    """Fetch the first chunk of a source URL and classify what came back."""
    row = {
        "source_id": source.id,
        "tier": source.tier,
        "publisher": source.publisher,
        "theme": source.theme,
        "declared_format": source.fmt,
        "url": source.url or "",
        "status": "",
        "bytes_sampled": 0,
        "sniffed": "",
        "verdict": "",
        "detail": "",
    }

    if not source.url:
        # Discovery-based sources have no static URL to probe; their listing page
        # is resolved at extract time.
        row["verdict"] = "skipped"
        row["detail"] = f"no static url (discover={source.discover or 'none'})"
        return row

    try:
        # stream=True so a 332 MB PDF costs one chunk rather than the whole file.
        resp = fetcher.get(source.url, stream=True)
        row["status"] = str(resp.status_code)
        chunk = next(resp.iter_content(chunk_size=8192), b"")
        resp.close()
    except Exception as exc:  # noqa: BLE001 — a probe must never abort the sweep
        row["status"] = "error"
        row["verdict"] = "error"
        row["detail"] = f"{type(exc).__name__}: {exc}"[:200]
        return row

    row["bytes_sampled"] = len(chunk)
    sniffed = _sniff(chunk)
    row["sniffed"] = sniffed

    if not chunk:
        row["verdict"] = "error"
        row["detail"] = "empty response body"
        return row

    if sniffed == "html":
        # The important case: a 200 that is really an error page or a redirect to
        # a site-search result.
        row["verdict"] = "error"
        row["detail"] = ("served HTML where a "
                         f"{source.fmt} file was expected — likely a moved or "
                         "retired path returning a soft 404")
        return row

    allowed = COMPATIBLE.get(source.fmt.lower())
    if allowed and sniffed not in allowed:
        row["verdict"] = "warning"
        row["detail"] = f"expected {source.fmt}, got {sniffed}"
        return row

    row["verdict"] = "ok"
    return row


def run(tiers: list[int] | None = None, ids: list[str] | None = None):
    defaults, sources = load_config()
    if tiers:
        sources = [s for s in sources if s.tier in tiers]
    if ids:
        sources = [s for s in sources if s.id in ids]

    fetcher = Fetcher(defaults)
    log.info("=" * 78)
    log.info("SOURCE HEALTH CHECK — probing %d source(s)", len(sources))
    log.info("=" * 78)

    rows = []
    for source in sources:
        row = probe(source, fetcher)
        rows.append(row)
        marker = {"ok": "  ok   ", "warning": "  warn ",
                  "error": "  FAIL ", "skipped": "  --   "}[row["verdict"]]
        log.info("%s %-38s %-6s %s", marker, source.id, row["status"],
                 row["detail"] or row["sniffed"])

    out = METADATA / "source_health.csv"
    with out.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]) + ["checked_at"])
        writer.writeheader()
        stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        for row in rows:
            writer.writerow({**row, "checked_at": stamp})

    counts = {v: sum(1 for r in rows if r["verdict"] == v)
              for v in ("ok", "warning", "error", "skipped")}
    log.info("-" * 78)
    log.info("  %d ok | %d warning | %d error | %d skipped -> %s",
             counts["ok"], counts["warning"], counts["error"], counts["skipped"], out)
    return rows, counts


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Probe catalogued source URLs.")
    ap.add_argument("--tier", nargs="*", type=int)
    ap.add_argument("--id", nargs="*")
    ap.add_argument("--fail-on-error", action="store_true",
                    help="exit non-zero if any source is broken")
    args = ap.parse_args(argv)

    _, counts = run(args.tier, args.id)
    if args.fail_on_error and counts["error"]:
        log.error("%d source(s) unreachable or serving the wrong content type",
                  counts["error"])
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

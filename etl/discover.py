"""
Dynamic URL discovery strategies.

Not every official dataset lives at a fixed URL. This module resolves the
`discover:` strategies declared in config/sources.yaml into concrete download URLs.

Strategies
----------
pbs_media_search   PBS runs WordPress and exposes the *unauthenticated* REST API at
                   /wp-json/wp/v2/media. This is the single most reliable automation
                   surface on any GoP site: it returns JSON with source_url,
                   mime_type and upload date, and supports ?search=. It is how we
                   resolve dated filenames such as `3.-SPI-Report-06.08.2026.xlsx`
                   and `Summary-July-2026.xlsx` without guessing.

pbs_page_link_scan Parse a PBS landing page and return every spreadsheet/PDF link.

mof_link_scan      finance.gov.pk is static HTML; scan a page and match a path prefix
                   (e.g. `/fiscal/`, `/dpco/`, `/survey/chapter_`).

fbr_link_scan      FBR listing pages link to download1.fbr.gov.pk with opaque numeric
                   filename prefixes, so URLs cannot be constructed — scan instead.

nepra_link_scan    NEPRA publication pages link to relative PDF paths.

sbp_dated_asset    SBP daily PDFs follow `<name>-DD-<month>-YYYY.pdf`. Build the URL
                   for a given date and walk backwards until one resolves.

easydata_dataset   SBP EasyData is Oracle APEX with session-checksum-protected URLs.
                   Cannot be resolved server-side; returns None with an explanation.
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from urllib.parse import urljoin, unquote

from bs4 import BeautifulSoup

from .common import Fetcher, Source, log

PBS_MEDIA_API = "https://www.pbs.gov.pk/wp-json/wp/v2/media"

SPREADSHEET_MIME = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-excel",
    "text/csv",
)


# --------------------------------------------------------------------------- PBS
def pbs_media_search(fetcher: Fetcher, source: Source, limit: int = 12) -> list[dict]:
    """Return recent PBS media matching `source.query`, newest first."""
    params = {"search": source.query, "per_page": limit,
              "orderby": "date", "order": "desc"}
    r = fetcher.session.get(PBS_MEDIA_API, params=params, timeout=fetcher.timeout)
    r.raise_for_status()
    items = []
    for m in r.json():
        url = m.get("source_url", "")
        if not url.lower().endswith("." + source.fmt.lower()):
            continue
        items.append({
            "url": url,
            "date": m.get("date", "")[:10],
            "title": (m.get("title") or {}).get("rendered", ""),
            "mime": m.get("mime_type", ""),
        })
    log.info("[discover] pbs_media_search '%s' -> %d candidate(s)", source.query, len(items))
    return items


def pbs_page_link_scan(fetcher: Fetcher, source: Source) -> list[dict]:
    return _scan_page(fetcher, source.query or source.page,
                      exts=(source.fmt, "xlsx", "xls", "csv"))


# --------------------------------------------------------------------------- MoF
def mof_link_scan(fetcher: Fetcher, source: Source) -> list[dict]:
    """Scan a finance.gov.pk page for links whose path contains `source.query`."""
    html = fetcher.text(source.page)
    soup = BeautifulSoup(html, "html.parser")
    needle = (source.query or "").lower()
    out = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if needle and needle not in href.lower():
            continue
        if not href.lower().endswith((".pdf", ".zip", ".xlsx", ".xls")):
            continue
        out.append({"url": urljoin(source.page, href),
                    "title": a.get_text(" ", strip=True)[:120], "date": ""})
    out = _dedupe(out)
    log.info("[discover] mof_link_scan '%s' -> %d link(s)", source.query, len(out))
    return out


# --------------------------------------------------------------------------- FBR
def fbr_link_scan(fetcher: Fetcher, source: Source) -> list[dict]:
    """FBR listing pages -> download1.fbr.gov.pk PDF links.

    `source.query` is treated as a regex alternation, e.g. "YEARBOOK|Yearbook".
    """
    html = fetcher.text(source.page)
    soup = BeautifulSoup(html, "html.parser")
    pat = re.compile(source.query or ".", re.I)
    out = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not href.lower().endswith((".pdf", ".xlsx", ".xls")):
            continue
        if not pat.search(unquote(href)):
            continue
        out.append({"url": urljoin(source.page, href),
                    "title": a.get_text(" ", strip=True)[:120], "date": ""})
    out = _dedupe(out)
    log.info("[discover] fbr_link_scan '%s' -> %d link(s)", source.query, len(out))
    return out


# --------------------------------------------------------------------------- NEPRA
def nepra_link_scan(fetcher: Fetcher, source: Source) -> list[dict]:
    return _scan_page(fetcher, source.page, exts=("pdf",), needle=source.query)


def nepra_state_of_industry_url(year: int) -> str:
    """NEPRA's SOI URL is fully predictable — verified for 2024."""
    return ("https://nepra.org.pk/publications/State%20of%20Industry%20Reports/"
            f"State%20of%20Industry%20Report%20{year}.pdf")


# --------------------------------------------------------------------------- SBP
_MONTHS = ["january", "february", "march", "april", "may", "june",
           "july", "august", "september", "october", "november", "december"]


def sbp_dated_asset(fetcher: Fetcher, source: Source, lookback: int = 10) -> list[dict]:
    """Resolve SBP's dated daily assets, e.g.

        https://www.sbp.org.pk/assets/document/kibor-rates-06-august-2026.pdf

    Walks back day by day until one URL returns real content (SBP answers 200
    with site chrome for missing files, so we check the payload, not the status).
    """
    tmpl = source.query or ""
    base = "https://www.sbp.org.pk/assets/document/"
    today = date.today()
    for back in range(lookback):
        d = today - timedelta(days=back)
        name = (tmpl.replace("{d}", f"{d.day:02d}")
                    .replace("{month_lower}", _MONTHS[d.month - 1])
                    .replace("{yyyy}", str(d.year)))
        url = base + name
        try:
            r = fetcher.session.get(url, timeout=fetcher.timeout)
            if r.ok and r.content[:5] == b"%PDF-":
                log.info("[discover] sbp_dated_asset resolved %s", url)
                return [{"url": url, "date": d.isoformat(), "title": name}]
        except Exception:  # noqa: BLE001
            continue
    log.warning("[discover] sbp_dated_asset found nothing in last %d days", lookback)
    return []


def sbp_mps_scan(fetcher: Fetcher, source: Source) -> list[dict]:
    return _scan_page(fetcher, source.page, exts=("pdf",), needle="MPS")


def easydata_dataset(fetcher: Fetcher, source: Source) -> list[dict]:
    """SBP EasyData cannot be resolved with a plain HTTP client.

    Observed behaviour (verified):
      * https://easydata.sbp.org.pk/api/v1/*  -> HTTP 401 Unauthorized
        (an API namespace exists but is not public / needs a token)
      * Dataset deep links are Oracle APEX:
        /apex/f?p=10:211:<session>::NO:RP:P211_DATASET_TYPE_CODE,P211_PAGE_ID:<CODE>,210&cs=<checksum>
        Removing the `&cs=` checksum returns
        "Session state protection violation", so the URL is not constructible.

    Use etl/easydata_browser.py (Playwright) or download manually.
    """
    log.warning("[discover] easydata_dataset '%s' needs a browser session — see "
                "etl/easydata_browser.py", source.query)
    return []


# --------------------------------------------------------------------------- shared
def _scan_page(fetcher: Fetcher, page: str, exts: tuple[str, ...],
               needle: str | None = None) -> list[dict]:
    html = fetcher.text(page)
    soup = BeautifulSoup(html, "html.parser")
    exts = tuple("." + e.lower().lstrip(".") for e in exts)
    out = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not unquote(href).lower().endswith(exts):
            continue
        if needle and needle.lower() not in unquote(href).lower():
            continue
        out.append({"url": urljoin(page, href),
                    "title": a.get_text(" ", strip=True)[:120], "date": ""})
    return _dedupe(out)


def _dedupe(items: list[dict]) -> list[dict]:
    seen, out = set(), []
    for i in items:
        if i["url"] in seen:
            continue
        seen.add(i["url"])
        out.append(i)
    return out


STRATEGIES = {
    "pbs_media_search": pbs_media_search,
    "pbs_page_link_scan": pbs_page_link_scan,
    "mof_link_scan": mof_link_scan,
    "fbr_link_scan": fbr_link_scan,
    "nepra_link_scan": nepra_link_scan,
    "sbp_dated_asset": sbp_dated_asset,
    "sbp_mps_scan": sbp_mps_scan,
    "easydata_dataset": easydata_dataset,
}


def resolve(fetcher: Fetcher, source: Source) -> list[dict]:
    """Return candidate download URLs for a source, newest/best first."""
    if source.url:
        return [{"url": source.url, "date": "", "title": source.name}]
    if not source.discover:
        return []
    fn = STRATEGIES.get(source.discover)
    if fn is None:
        log.warning("[discover] unknown strategy '%s' for %s", source.discover, source.id)
        return []
    try:
        cands = fn(fetcher, source)
    except Exception as exc:  # noqa: BLE001
        log.error("[discover] %s failed for %s: %s", source.discover, source.id, exc)
        return []

    return _filter(cands, source)


def _filter(candidates: list[dict], source: Source) -> list[dict]:
    """Apply the source's `match` / `exclude` regexes to candidate URLs.

    Search-based discovery is fuzzy: PBS's media search for 'Summary-' happily
    returns 'Services-Summary-June-2026.xlsx', which is a different dataset with
    a different unit basis. Silently ingesting it would put services trade into
    a merchandise trade series, so filtering here is a correctness requirement.
    """
    out = candidates
    if source.match:
        rx = re.compile(source.match, re.I)
        out = [c for c in out if rx.search(unquote(c["url"]))]
    if source.exclude:
        rx = re.compile(source.exclude, re.I)
        out = [c for c in out if not rx.search(unquote(c["url"]))]
    if len(out) != len(candidates):
        log.info("[discover] %s: %d/%d candidate(s) kept after URL filter",
                 source.id, len(out), len(candidates))
    return out

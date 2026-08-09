"""
Shared ETL utilities: config loading, resilient HTTP, content-hash change detection,
and the run manifest.

Design principles
-----------------
1. Never overwrite raw data silently. Every download is hashed; if the hash is
   unchanged the file is skipped and the manifest records `unchanged`.
2. Every raw file is versioned into data/raw/<publisher>/ with an ISO snapshot
   date so a dashboard number can always be traced back to the file it came from.
3. All failures are non-fatal at the source level — one dead link must not kill
   the monthly run.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import shutil
import time
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlparse
from typing import Any, Iterable

import requests
import yaml

# --------------------------------------------------------------------------- paths
ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "sources.yaml"
RAW = ROOT / "data" / "raw"
INTERIM = ROOT / "data" / "interim"
PROCESSED = ROOT / "data" / "processed"
METADATA = ROOT / "data" / "metadata"
LOGS = ROOT / "logs"

for _p in (RAW, INTERIM, PROCESSED, METADATA, LOGS):
    _p.mkdir(parents=True, exist_ok=True)

MANIFEST_PATH = METADATA / "manifest.json"

# --------------------------------------------------------------------------- logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)-22s | %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOGS / f"etl_{datetime.now(timezone.utc):%Y%m%d}.log"),
    ],
)
log = logging.getLogger("etl")


# --------------------------------------------------------------------------- config
@dataclass
class Source:
    id: str
    name: str
    publisher: str
    theme: str
    page: str
    fmt: str
    frequency: str
    tier: int
    url: str | None = None
    discover: str | None = None
    query: str | None = None
    coverage: str | None = None
    parser: str | None = None
    notes: str | None = None
    # Optional regexes applied to discovered candidate URLs. `match` keeps only
    # URLs that match; `exclude` drops any that do. Needed because PBS filenames
    # overlap — a search for 'Summary-' also returns 'Services-Summary-'.
    match: str | None = None
    exclude: str | None = None
    # True when the publisher has stopped updating the file. Such a source is
    # still worth carrying for history but must not raise a staleness warning.
    discontinued: bool = False


def load_config(path: Path = CONFIG) -> tuple[dict, list[Source]]:
    with open(path, "r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    defaults = raw.get("defaults", {})
    sources = [Source(**s) for s in raw["sources"]]
    return defaults, sources


def select(sources: Iterable[Source], *, themes=None, tiers=None, ids=None,
           publishers=None) -> list[Source]:
    """Filter the registry."""
    out = []
    for s in sources:
        if themes and s.theme not in themes:
            continue
        if tiers and s.tier not in tiers:
            continue
        if ids and s.id not in ids:
            continue
        if publishers and s.publisher not in publishers:
            continue
        out.append(s)
    return out


# --------------------------------------------------------------------------- http
class Fetcher:
    """Session-based downloader with retries, backoff and a browser User-Agent.

    A realistic User-Agent is required: several GoP hosts reject the default
    python-requests agent, and www.ogra.org.pk rejects everything non-interactive.
    """

    #: Minimum seconds between consecutive requests to a host. sbp.org.pk sits
    #: behind Cloudflare and starts returning 403 to *every* request — including
    #: ones that succeeded seconds earlier — once a burst trips its rate limit,
    #: and the block outlives the process. Spacing requests out is the only
    #: reliable way to keep a full extract run from poisoning itself midway.
    HOST_INTERVAL = {
        "www.sbp.org.pk": 4.0,
        "sbp.org.pk": 4.0,
        "easydata.sbp.org.pk": 4.0,
    }
    DEFAULT_INTERVAL = 0.5

    def __init__(self, defaults: dict):
        self.timeout = defaults.get("timeout", 120)
        self.retries = defaults.get("retries", 3)
        self.backoff = defaults.get("backoff", 5)
        self._last_hit: dict[str, float] = {}
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": defaults.get("user_agent", "Mozilla/5.0"),
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
        })

    def _throttle(self, url: str) -> None:
        host = urlparse(url).netloc.lower()
        gap = self.HOST_INTERVAL.get(host, self.DEFAULT_INTERVAL)
        prev = self._last_hit.get(host)
        if prev is not None:
            wait = gap - (time.monotonic() - prev)
            if wait > 0:
                time.sleep(wait)
        self._last_hit[host] = time.monotonic()

    def get(self, url: str, *, binary: bool = True,
            stream: bool = False) -> requests.Response:
        """Fetch a URL with throttling and retry.

        `stream=True` returns the response before the body is read, so a caller
        that only needs the first few bytes — the health check sniffing magic
        bytes — does not have to download a 332 MB PDF to identify it. The caller
        owns closing the response in that case.
        """
        last = None
        for attempt in range(1, self.retries + 1):
            self._throttle(url)
            try:
                r = self.session.get(url, timeout=self.timeout,
                                     allow_redirects=True, stream=stream)
                r.raise_for_status()
                return r
            except Exception as exc:  # noqa: BLE001
                last = exc
                log.warning("attempt %d/%d failed for %s: %s",
                            attempt, self.retries, url, exc)
                if attempt < self.retries:
                    # A 403 from a rate limiter clears with time, not with a
                    # fast retry, so back off much harder than for a timeout.
                    status = getattr(getattr(exc, "response", None), "status_code", None)
                    penalty = 6 if status == 403 else 1
                    time.sleep(self.backoff * attempt * penalty)
        raise RuntimeError(f"all {self.retries} attempts failed for {url}") from last

    def text(self, url: str) -> str:
        return self.get(url).text


# --------------------------------------------------------------------------- helpers
def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def looks_like_html_error(content: bytes, expected_fmt: str) -> bool:
    """GoP servers frequently answer 200 OK with an HTML 404 page.

    pbs.gov.pk returns a ~200 KB styled 404 body, and sbp.org.pk serves its
    site chrome for missing assets. So a 200 status is NOT sufficient — we
    check that the payload actually looks like the format we asked for.
    """
    if expected_fmt in {"html", "xml"}:
        return False
    head = content[:2048].lstrip().lower()
    if head.startswith(b"<!doctype html") or head.startswith(b"<html"):
        return True
    if expected_fmt == "xlsx" and not content.startswith(b"PK"):
        return True
    if expected_fmt == "xls" and not content.startswith(b"\xd0\xcf\x11\xe0"):
        return True
    if expected_fmt == "pdf" and not content[:5] == b"%PDF-":
        return True
    return False


def snapshot_name(source_id: str, fmt: str, stamp: str | None = None,
                  origin: str | None = None) -> str:
    """Build the on-disk snapshot filename.

    The publisher's own filename is appended when available, because for several
    PBS releases the filename IS the metadata: `3.-SPI-Report-06.08.2026.xlsx`
    carries the week-ending date and `Summary-June-2026.xlsx` carries the
    reference month. Nothing inside those workbooks states the period in a
    machine-readable way, so discarding the origin filename would make the
    observation undateable.
    """
    stamp = stamp or datetime.now(timezone.utc).strftime("%Y%m%d")
    base = f"{source_id}__{stamp}"
    if origin:
        stem = re.sub(r"\.[A-Za-z0-9]+$", "", unquote(origin.rsplit("/", 1)[-1]))
        stem = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("_")[:80]
        if stem:
            base = f"{base}__{stem}"
    return f"{base}.{fmt}"


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


# --------------------------------------------------------------------------- manifest
@dataclass
class RunRecord:
    source_id: str
    name: str
    publisher: str
    theme: str
    tier: int
    status: str              # downloaded | unchanged | skipped | failed
    url: str | None = None
    page: str | None = None
    path: str | None = None
    latest_path: str | None = None
    bytes: int = 0
    sha256: str | None = None
    fetched_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    error: str | None = None


def load_manifest() -> dict[str, Any]:
    if MANIFEST_PATH.exists():
        return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    return {"runs": [], "sources": {}}


def save_manifest(manifest: dict[str, Any]) -> None:
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def record(manifest: dict, rec: RunRecord) -> None:
    manifest["sources"][rec.source_id] = asdict(rec)


def write_latest(src_path: Path, source_id: str, fmt: str, publisher: str) -> Path:
    """Maintain a stable `<id>__latest.<fmt>` pointer so the dashboard never
    has to guess which snapshot is current."""
    dest = RAW / publisher / f"{source_id}__latest.{fmt}"
    shutil.copy2(src_path, dest)
    return dest

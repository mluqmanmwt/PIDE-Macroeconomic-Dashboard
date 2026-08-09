# PIDE Macroeconomic Indicator Dashboard

A production macro-data pipeline and Streamlit dashboard for Pakistan, built in the PIDE research setting. It converts selected official Government of Pakistan and State Bank of Pakistan releases into a validated, traceable macro dataset for research economists and policy-facing analysis.

The current validated build contains **144,647 observations**, **1,209 unique literal series**, **23 datasets**, **0 errors**, and **3 legitimate warnings**. The dashboard does not replace the originating statistical release: it preserves source, unit, frequency, and observed coverage so economists can check the underlying definition before interpreting a chart.

## Quickstart

```bash
pip install -r requirements.txt
python -m etl.run_etl --tier 1
streamlit run dashboard/Overview.py
```

`python -m etl.run_etl --tier 1` is the normal production command. It runs, in order, SBP catalogue refresh, extraction, historical backfill where needed, transformation, and validation. It returns exit code **0** for success or warnings, and **1** for a failed stage or any validation error.

## Repository structure

| Directory / file | Purpose |
|---|---|
| `config/` | The authoritative source registry. `sources.yaml` records publisher, URLs, format, coverage, frequency, tier, discovery rule, and parser. |
| `etl/` | Catalogue refresh, resilient retrieval, discovery rules, backfill, parsers, transformation, validation, and the end-to-end runner. |
| `etl/parsers/` | Source-specific parsers for SBP/PBS spreadsheets, PDFs, and SDMX feeds. |
| `dashboard/` | Streamlit application, shared plotting/provenance helpers, and the nine built pages. |
| `data/raw/` | Versioned downloaded inputs. This is local acquisition evidence and is intentionally not committed. |
| `data/processed/` | Validated source-level Parquet/CSV files and the dashboard master table. Committed as a supervisor-readable deliverable. |
| `data/metadata/` | Manifest, validation report, source/series indexes, and the flattened SBP catalogue. Committed as a supervisor-readable deliverable. |
| `docs/` | Findings report, generated catalog, dashboard-page guide, and the catalog generator. |
| `logs/` | Run logs for local operations; not committed. |
| `.streamlit/config.toml` | Streamlit widget theme (green accent) and file-watch exclusions for `data/` and `logs/`. |
| `requirements.txt` | Python runtime dependencies. |

## Tidy data contract

Every parser emits the same long-form schema:

```text
date | series | value | unit | source_id | frequency
```

The transformation stage writes the combined table to `data/processed/macro_master.parquet` and writes a Parquet/CSV pair for each parsed source. `data/metadata/series_index.csv` is the human-readable index of every source-qualified series, including observed start/end dates and observation counts. The dashboard reads only validated processed output and its metadata, never raw publisher files.

## Source tiers

| Tier | Meaning | Operating rule |
|---|---|---|
| **1** | Fully automated dashboard core | Stable source/discovery path plus a parser and validation coverage. Eligible for scheduled refresh and dashboard display. |
| **2** | Automated download, semi-structured parse | The file can usually be acquired, but parsing or definition review needs more work. Do not promote it to a headline chart without validation and economist review. |
| **3** | PDF/manual reference | PDF-first, blocked, exceptionally large, or otherwise unsuitable for unattended extraction. Retain in the catalog and cite it, but do not imply live coverage. |

## Automation schedule

Use source frequency and publisher release timing rather than a single daily job:

- **Weekly:** run after the PBS SPI and SBP FX-reserves/M2 releases; retain the raw snapshot even when the chart history is unchanged.
- **Monthly:** refresh CPI, producer prices, trade, BOP, remittances, exchange-rate archives, bank-credit/money workbooks, and energy feeds.
- **Quarterly:** refresh national accounts, MoF SDMX fiscal operations, debt, and any approved semi-structured fiscal sources.
- **Annual / irregular:** refresh annual national accounts, labour references, NEPRA reports, and source registry notes after a methodology or layout change.
- **Every run:** review `data/metadata/validation_report.csv`, source freshness in `manifest.json`, and the Streamlit Data Catalog page before using a new result in a briefing.

The SBP catalogue refresh is first because its [official JSON library](https://www.sbp.org.pk/assets/dt_collection_75160/econmicMainDataNew.json) provides the publisher’s direct archive URLs. The fetcher serialises requests to [SBP Economic Data](https://www.sbp.org.pk/economic-data) and [SBP EasyData](https://easydata.sbp.org.pk/) with a four-second host interval and a longer penalty after a 403; do not parallelise those hosts.

## Add a new source

1. **Research the official source.** Confirm the publisher landing page, direct file/feed or approved discovery strategy, format, frequency, unit/definition, and historical coverage. Do not use third-party aggregators.
2. **Add one entry to `config/sources.yaml`.** Give it a stable `id`, `publisher`, `theme`, `page`, `url` or `discover`, `fmt`, `frequency`, `coverage`, `tier`, and `parser` field. Record source-specific traps in `notes`.
3. **Write the parser.** Add a function in `etl/parsers/sbp.py`, `etl/parsers/pbs.py`, or a new focused parser module. It must return the tidy contract exactly, use robust date/unit handling, and preserve the publisher’s series definition.
4. **Register the parser.** Add the function name to `REGISTRY` in `etl/transform.py`. A registry entry is required; a parser that is not registered will not enter the master table.
5. **Run a targeted acquisition and transform.** Use `python -m etl.extract --id <source_id>` and `python -m etl.transform --id <source_id>` during development, then inspect the source-level CSV/Parquet and series index.
6. **Validate the full Tier 1 set.** Run `python -m etl.run_etl --tier 1`; investigate errors before merging. Warnings require documented judgement, not automatic dismissal.
7. **Add user-facing treatment.** Update the generated catalog, source notes, and dashboard page only after the series resolves in the index and the unit/basis is clear.

## Critical basis warnings

> **Never merge these into a single series or shared-axis comparison without an explicit conversion/definition note.**
>
> - **Trade:** SBP trade is balance-of-payments (BOP) basis in million USD; PBS summary trade is customs basis in million USD; PBS SDMX trade is customs basis in million PKR. These are three different official measures.
> - **Fiscal consolidation:** MoF general government already consolidates federal and provincial government. Do **not** add central-government operations to it; that double-counts.
> - **GDP price basis:** PBS SDMX quarterly GDP is nominal; the SBP quarterly workbook is at constant 2015-16 basic prices. Both can be correct but are not directly comparable.
> - **Discontinued/stale series:** REER/NEER ends at 2023-12; PBS labour SDMX ends in 2021; MoF operations currently end 2025-03-31. Never extend these lines with a flat last value.
> - **Credit taxonomy:** SBP’s 2019 ISIC Rev. 4 reclassification makes same-named pre/post categories non-comparable; retain the suffixed series rather than stitching them.

## Troubleshooting

### SBP 403 / throttling

[SBP Economic Data](https://www.sbp.org.pk/economic-data) and [SBP EasyData](https://easydata.sbp.org.pk/) are Cloudflare-protected. A burst can return a 403 that lasts beyond the current process. Wait, then rerun serially; do not add parallel workers or repeatedly retry at the same rate. The pipeline’s fetcher already uses a browser-style user agent, a four-second per-host interval, retries, and a sixfold backoff after 403.

### Soft 404s and wrong file types

The legacy `sbp.org.pk/ecodata/` path can return HTTP 200 with an HTML body instead of the requested file. Use the official [SBP JSON catalogue](https://www.sbp.org.pk/assets/dt_collection_75160/econmicMainDataNew.json) archive URLs and retain magic-byte checks: `PK` for XLSX, `\xd0\xcf\x11\xe0` for XLS, and `%PDF-` for PDF. A successful HTTP status alone is not proof of a valid input.

### Publisher layout changes

If validation reports an empty, stale, collapsed, duplicated, or implausible series, stop and inspect the new raw file before changing the dashboard. Common causes are moved header rows, mixed datetime/string headers, a changed unit, extra footnotes, or a new fiscal-year block. Update the parser, add a regression fixture where practical, rerun validation, and document the change in the source registry notes.

### PBS vintage duplicates

PBS can retain multiple SDMX vintages (for example `CPI.xml` and a later [CPI-1.xml](https://www.pbs.gov.pk/wp-content/uploads/2020/07/CPI-1.xml)). Prefer the XML with the later `prepared` attribute and preserve the old snapshot for auditability.

### Legitimate current warnings

The current three warnings are expected: both MoF fiscal-operation feeds have a genuine publication lag to 2025-03-31, and one SBP credit borrower category is correctly zero throughout its reported range. Do not “fix” them by imputing observations or deleting the series.

## Verifying the dashboard actually renders

An HTTP 200 on the app root proves only that the Streamlit server started. Streamlit
renders client-side and reports a page-level exception as a traceback drawn *inside*
the running app, so a page that fails to import still returns 200 and still serves
Streamlit's shell HTML. An import test run from the repository root does not catch it
either, because the import that fails at runtime happens to succeed there.

Rendering is therefore checked in a real browser. `dashboard/verify_pages.py` performs
the import-level check; for visual verification, drive a headless browser over every
route and assert positively that charts exist:

```bash
streamlit run app.py --server.port 8512 --server.headless true &
python -m playwright install chromium      # first run only
python dashboard/verify_render.py          # screenshots + assertions
```

The checks that matter, and why each one exists:

| Check | Failure it catches |
|---|---|
| Page body scanned for `Traceback`, `SyntaxError`, `ModuleNotFoundError`, `KeyError` | A Streamlit exception renders as page text, not as a bad HTTP status. |
| Count of `svg.main-svg` elements per page | A page that raised before drawing anything still screenshots cleanly; absence of an error string is not evidence that anything rendered. |
| Rendered legend text width against the plot box | Plotly does not ellipsize a horizontal legend; it clips whatever overruns the plot, truncating the last label mid-word. |
| Whole-word match on `nan`, `None`, `null` | Substring matching fires on ordinary words — `inf` inside `inflation` flagged every page of a macro dashboard. |
| Failed-request URLs, excluding `_stcore/health` and `_stcore/host-config` | Streamlit resolves its own probes against the current page path on multipage apps, so those 404s appear on every subpage and are not app bugs. |

## Data licensing and attribution

All pipeline inputs are official Government of Pakistan, SBP, PBS, MoF, FBR, NEPRA, or OGRA statistics. Users must cite the **originating institution and official release/page** in any PIDE paper, policy note, chart, or external presentation. This repository records provenance and transforms official releases; it does not transfer ownership, reinterpret official methodology, or grant a broader licence than the publisher provides.

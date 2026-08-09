"""End-to-end pipeline runner: catalog -> extract -> backfill -> transform -> validate.

This is the entry point that scheduled automation calls. It exists so that CI has
one command with one exit code, and so the stages always run in an order that
respects their dependencies:

  1. ``sbp_catalog``  refresh SBP's own JSON file index, so URL changes on the
     publisher's side are picked up before anything is downloaded.
  2. ``extract``      download every selected source, with soft-404 detection
     and SHA-256 change detection.
  3. ``backfill``     for sources published as one file per period, walk the
     publisher's media index so history accumulates instead of being
     overwritten each month.
  4. ``transform``    parse every raw file into the tidy contract and build the
     master table the dashboard reads.
  5. ``validate``     assert freshness, uniqueness and plausibility.

Exit codes
----------
0   everything succeeded, or only warnings were raised
1   a stage failed, or validation raised at least one error

Warnings deliberately do not fail the run. Pakistani publishers revise and
re-release files constantly, and a pipeline that goes red on every revision
stops being read. Errors — a parser returning nothing, duplicated observations,
values outside a physically possible range — do fail it.

Usage
-----
    python -m etl.run_etl                      # full monthly run
    python -m etl.run_etl --tier 1             # dashboard core only
    python -m etl.run_etl --skip-backfill      # faster, for a quick refresh
    python -m etl.run_etl --theme inflation external
"""

from __future__ import annotations

import argparse
import time
import traceback
from datetime import datetime, timezone

from .common import METADATA, log


def _banner(title: str) -> None:
    log.info("=" * 78)
    log.info("STAGE  %s", title)
    log.info("=" * 78)


def main() -> int:
    ap = argparse.ArgumentParser(description="Run the full PIDE macro ETL pipeline.")
    ap.add_argument("--tier", nargs="*", type=int, default=[1],
                    help="source tiers to extract (default: 1)")
    ap.add_argument("--theme", nargs="*", help="restrict to these themes")
    ap.add_argument("--id", nargs="*", help="restrict to these source ids")
    ap.add_argument("--skip-catalog", action="store_true")
    ap.add_argument("--skip-backfill", action="store_true")
    ap.add_argument("--fail-on-warning", action="store_true",
                    help="treat validation warnings as failures too")
    args = ap.parse_args()

    started = time.monotonic()
    log.info("PIDE macroeconomic ETL — run started %s",
             datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))

    stages: list[tuple[str, str]] = []

    def run(name: str, fn) -> bool:
        _banner(name)
        try:
            fn()
        except SystemExit as exc:
            # argparse calls ap.error() -> SystemExit, which derives from
            # BaseException and so slips past `except Exception`. Left uncaught it
            # terminates the whole run at that stage, and because the stage was
            # meant to be non-fatal the pipeline appears to end quietly without
            # ever reaching transform or validate. Treat it as a stage failure.
            if exc.code not in (0, None):
                log.error("stage %s exited with status %s (bad arguments?)", name, exc.code)
                stages.append((name, "failed"))
                return False
        except Exception:
            log.error("stage %s failed:\n%s", name, traceback.format_exc())
            stages.append((name, "failed"))
            return False
        stages.append((name, "ok"))
        return True

    # --- 1. SBP file catalog ------------------------------------------------
    # Non-fatal: a stale cached catalog is better than aborting the run, and
    # every tier-1 source also carries an explicit URL as a fallback.
    if not args.skip_catalog:
        from . import sbp_catalog
        try:
            _banner("sbp_catalog")
            sbp_catalog.refresh()
            stages.append(("sbp_catalog", "ok"))
        except Exception:
            log.warning("sbp_catalog refresh failed; continuing with the cached copy")
            stages.append(("sbp_catalog", "skipped"))

    # --- 2. extract --------------------------------------------------------
    from . import extract
    ex_args = []
    if args.tier:
        ex_args += ["--tier", *[str(t) for t in args.tier]]
    if args.theme:
        ex_args += ["--theme", *args.theme]
    if args.id:
        ex_args += ["--id", *args.id]
    if not run("extract", lambda: extract.main(ex_args)):
        return 1

    # --- 3. backfill -------------------------------------------------------
    if not args.skip_backfill:
        from . import backfill
        # Non-fatal: backfill only deepens history. Losing it degrades the
        # charts but does not invalidate the current period.
        # backfill requires an explicit selector; calling it with no arguments
        # made argparse abort the run. Mirror the extract stage's filters so
        # `--tier 1` backfills exactly the sources it just extracted.
        bf_args = list(ex_args) if (args.tier or args.theme or args.id) else ["--all"]
        if not run("backfill", lambda: backfill.main(bf_args)):
            log.warning("backfill failed; continuing with the snapshots already on disk")

    # --- 4. transform ------------------------------------------------------
    from . import transform
    if not run("transform", lambda: transform.main([])):
        return 1

    # --- 5. validate -------------------------------------------------------
    from . import validate
    _banner("validate")
    try:
        report = validate.run()
    except Exception:
        log.error("validation failed to execute:\n%s", traceback.format_exc())
        return 1

    errors = int((report["severity"] == "error").sum()) if len(report) else 0
    warnings = int((report["severity"] == "warning").sum()) if len(report) else 0
    stages.append(("validate", f"{errors} error(s), {warnings} warning(s)"))

    # --- summary -----------------------------------------------------------
    log.info("=" * 78)
    log.info("RUN SUMMARY  (%.0fs)", time.monotonic() - started)
    for name, status in stages:
        log.info("  %-14s %s", name, status)
    log.info("  report       %s", (METADATA / "validation_report.csv"))
    log.info("=" * 78)

    if errors:
        log.error("FAILED — %d validation error(s)", errors)
        return 1
    if warnings and args.fail_on_warning:
        log.error("FAILED — %d validation warning(s) with --fail-on-warning", warnings)
        return 1
    log.info("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

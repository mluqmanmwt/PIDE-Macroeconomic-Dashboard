"""Verification harness: uses production helpers and production data, no stubs."""
from __future__ import annotations

import contextlib
import importlib.util
import io
from pathlib import Path

import pandas as pd

from dashboard.lib import existing_names, filtered_long, get_series, load_index, resolve_sdmx_code

ROOT = Path(__file__).resolve().parent


def code(source_id: str, indicator: str) -> str:
    """Resolve the exact full SDMX descriptor used by a page, failing visibly if absent."""
    name = resolve_sdmx_code(source_id, indicator)
    if not name:
        raise AssertionError(f"SDMX indicator {indicator} missing from {source_id}")
    return name


# This mirrors the default chart selections in each page.  Long SDMX names are
# resolved from their official code exactly as the UI does; no abbreviated
# display label is ever used as a data key.
PAGES = {
    "app.py": [
        "National — inflation", "SBP Policy Rate (target)", "Total liquid FX reserves", "Balance of Trade [a-c]", "Saudi Arabia", "Broad Money (M2) (A+B+C)", "GDP Growth Rate (%)",
        code("mof_general_govt_operations_sdmx", "PAK_GGO_BBIG_XDC"),
    ],
    "1_Inflation.py": [
        "National — index", "UCPI — index", "RPI — index", "National — inflation", "UCPI — inflation", "RPI — inflation", code("pbs_cpi_sdmx", "PCPI_CP_01_IX"), code("pbs_cpi_sdmx", "PCPI_CP_01_WT"), "SPI Combined — index", "SPI Combined — % change YoY",
        *load_index().loc[lambda x: x["source_id"].eq("pbs_producer_prices_sdmx"), "series"].tolist(),
    ],
    "2_Monetary.py": [
        "SBP Policy Rate (target)", "SBP Repo Rate (floor)", "SBP Reverse Repo Rate (ceiling)", "Currency in Circulation", "Total Deposits with Banks1", "a. Credit to Private Sector*", "KIBOR 1-month", "KIBOR 3-month", "KIBOR 6-month", "T-bill 3-month cut-off yield", "T-bill 6-month cut-off yield", "T-bill 12-month cut-off yield", "Lending rate — fresh (marginal) (PKR, all banks)", "Lending rate — outstanding (stocks) (PKR, all banks)", "Deposit rate — fresh (marginal) (PKR, all banks)", "Deposit rate — outstanding (stocks) (PKR, all banks)", "Ceiling — Amount", "Floor — Amount", "Ceiling — Institutions", "Floor — Institutions",
    ],
    "3_Fiscal.py": [
        code("mof_general_govt_operations_sdmx", "PAK_GGO_RG_R_XDC"), code("mof_general_govt_operations_sdmx", "PAK_GGO_E_XDC"), code("mof_general_govt_operations_sdmx", "PAK_GGO_BBIG_XDC"),
        "I. Permanent Debt (1+2+3+4)", "II. Floating Debt", "III. Unfunded Debt", "IV. Foreign Currency Loans4", "V. Naya Pakistan Certificates6",
    ],
    "4_External.py": [
        "Exports (BOP) Value [a]", "Imports (BOP) Value [c]", "Balance of Trade [a-c]", "Exports (goods)", "Imports (goods)", "Balance of Trade (goods)", "Saudi Arabia", "U.A.E.", "U.K.", "USA", "Other GCC Countries", "Reserves with SBP", "Reserves with banks", "Total liquid FX reserves", "REER", "NEER",
        code("pbs_merchandise_trade_sdmx", "TXG_FOB_XDC"), code("pbs_merchandise_trade_sdmx", "TMG_CIF_XDC"),
    ],
    "5_Growth.py": [
        "GDP Growth Rate (%)", "Agriculture, Forestry and Fishing ( 1 to 4 )", "Industrial Activities ( 1 to 4 )", "Services ( 1 to 10)", "Agriculture Sector (1 to 4) — growth", "Industrial Sector (1 to 4) — growth", "Services Sector (1 to 10) — growth", "i. Large Scale — growth", "i. Large Scale — level",
        code("pbs_quarterly_national_accounts_sdmx", "NGDP_FY_XDC"),
    ],
    "6_Labour_and_Energy.py": [
        code("pbs_labour_sdmx", "LLF_PE_FY_NUM"), code("pbs_labour_sdmx", "LE_PE_FY_NUM"), code("pbs_labour_sdmx", "LU_PE_FY_NUM"),
        code("pbs_energy_sdmx", "PAK_ORSI_EG_GWH"), code("pbs_energy_sdmx", "PAK_ORSI_T_GWH"), code("pbs_energy_sdmx", "PAK_ORSI_H_GWH"), code("pbs_energy_sdmx", "PAK_ORSI_N_GWH"), code("pbs_energy_sdmx", "PAK_ORSI_AE_GWH"), code("pbs_energy_sdmx", "AOMPC_BBL"), code("pbs_energy_sdmx", "PAK_ORSI_NG_1000FC"),
    ],
    "7_Series_Explorer.py": ["National — inflation", code("pbs_energy_sdmx", "PAK_ORSI_EG_GWH")],
    "8_Data_Catalog.py": ["National — inflation", code("mof_general_govt_operations_sdmx", "PAK_GGO_RG_R_XDC")],
}

reports = []
for filename, names in PAGES.items():
    missing = sorted(set(names) - set(existing_names(names)))
    wide = get_series(names)
    long = filtered_long(names=names)
    missing_master = sorted(set(names) - set(long["series"].unique()))
    resolved = int(long["series"].nunique()) if not long.empty else 0
    # Import the real page module, without patching Streamlit or its helpers.
    module_path = ROOT / (filename if filename == "app.py" else f"pages/{filename}")
    try:
        with contextlib.redirect_stderr(io.StringIO()):
            spec = importlib.util.spec_from_file_location(f"verify_{filename.replace('.', '_')}", module_path)
            module = importlib.util.module_from_spec(spec)
            assert spec and spec.loader
            spec.loader.exec_module(module)
        imported = "PASS"
    except Exception as exc:  # report all pages rather than stopping at one failure
        imported = f"FAIL: {type(exc).__name__}: {exc}"
    reports.append({"page": filename, "references": len(names), "absent_names": "; ".join(missing) or "none", "absent_from_master": "; ".join(missing_master) or "none", "resolved_series": resolved, "observations": len(long), "import": imported})

report = pd.DataFrame(reports)
print(report.to_string(index=False))
out = ROOT / "verification_report.csv"
report.to_csv(out, index=False)
if (report["absent_names"] != "none").any() or (report["absent_from_master"] != "none").any() or (report["resolved_series"] == 0).any() or report["import"].str.startswith("FAIL").any():
    raise SystemExit("Page verification failed; see dashboard/verification_report.csv")

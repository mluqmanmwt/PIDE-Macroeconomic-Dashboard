# Data Catalog

This catalog is generated from `config/sources.yaml` and `data/metadata/series_index.csv`; do not edit it by hand. Regenerate with `python docs/generate_catalog.py` after changing the registry or ETL outputs.

## Registry summary

- **Catalogued official sources:** 75
- **Sources by tier:** Tier 1 — 32; Tier 2 — 26; Tier 3 — 17
- **Sources by publisher:** FBR — 3; MOF — 8; NEPRA — 2; OGRA — 1; PBS — 19; SBP — 42
- **Observed-series fields:** `Series count` and `Observed range` are joined from the current series index. They describe parsed output, not necessarily the full historical coverage advertised by the publisher.

## How to read it

- **Official page** is the publisher landing page to cite in analysis.
- **Direct URL** is a stable file/feed URL where one is registered. “Dynamic discovery” means the extractor resolves a current link from the publisher's listing; “manual” means no unattended retrieval path is configured.
- **Parser** names the registered transformation function. A dash means the source is catalogued for research/reference but is not presently transformed into the master table.
- **Configured coverage** is the registry's source-level description; it is not overwritten by the observed range.

## Inflation

### Tier 1 — fully automated dashboard core

| ID | Name | Publisher | Format | Frequency | Configured coverage | Tier | Parser | Series count | Observed range | Official page | Direct URL |
|---|---|---|---|---|---|---:|---|---:|---|---|---|
| `pbs_cpi_historical` | CPI / RPI / WPI historical indices and inflation rates (base 2015-16) | PBS | xlsx | monthly | 2016-07 onward (2015-16 base); 2007-08 base series also included | 1 | `parse_pbs_cpi_historical` | 24 | 2017-06-30 to 2026-06-30 | [official page](https://www.pbs.gov.pk/price-statistics/) | [direct file/feed](https://www.pbs.gov.pk/wp-content/uploads/2020/07/indices_and_growth_rates_historical.xlsx) |
| `pbs_producer_prices_sdmx` | Wholesale / producer price index (PBS, SDMX) | PBS | xml | monthly | 2021-04 onward | 1 | `parse_sdmx_pbs_ppi` | 6 | 2021-04-30 to 2026-06-30 | [official page](https://www.pbs.gov.pk/price-statistics) | [direct file/feed](https://www.pbs.gov.pk/wp-content/uploads/2020/07/PPI.xml) |
| `pbs_spi_weekly` | Weekly Sensitive Price Indicator (SPI) report | PBS | xlsx | weekly | rolling; one file per week | 1 | `parse_pbs_spi` | 30 | 2025-04-30 to 2026-08-06 | [official page](https://www.pbs.gov.pk/spi) | Dynamic discovery: `pbs_media_search` (`SPI-Report`) |

### Tier 2 — automated download and semi-structured parse

| ID | Name | Publisher | Format | Frequency | Configured coverage | Tier | Parser | Series count | Observed range | Official page | Direct URL |
|---|---|---|---|---|---|---:|---|---:|---|---|---|
| `pbs_cpi_sdmx` | CPI SDMX 2.1 data message (IMF ECOFIN_DSD) | PBS | xml | monthly | see file | 2 | `parse_sdmx_generic` | 26 | 2022-07-31 to 2026-07-31 | [official page](https://www.pbs.gov.pk/cpi) | [direct file/feed](https://www.pbs.gov.pk/wp-content/uploads/2020/07/CPI-1.xml) |
| `pbs_spi_monthly_prices_annex` | SPI monthly average prices annexure | PBS | xlsx | monthly | rolling | 2 | — | — | — | [official page](https://www.pbs.gov.pk/price-statistics/) | [direct file/feed](https://www.pbs.gov.pk/wp-content/uploads/2020/07/SPI-Monthly-Prices-Annex-6.xlsx) |

### Tier 3 — PDF/manual reference sources

| ID | Name | Publisher | Format | Frequency | Configured coverage | Tier | Parser | Series count | Observed range | Official page | Direct URL |
|---|---|---|---|---|---|---:|---|---:|---|---|---|
| `pbs_cpi_urban_groupwise` | CPI urban group-wise cumulative indices | PBS | pdf | monthly | rolling | 3 | — | — | — | [official page](https://www.pbs.gov.pk/price-statistics/) | [direct file/feed](https://www.pbs.gov.pk/wp-content/uploads/2020/07/CpI-Urban-Groupwise-Cumulative-Indices.pdf) |
| `pbs_monthly_price_review` | Monthly Price Indices review (CPI press release) | PBS | pdf | monthly | rolling | 3 | — | — | — | [official page](https://www.pbs.gov.pk/price-statistics/) | Dynamic discovery: `pbs_media_search` (`Monthly-Review`) |
| `pbs_rpi_groupwise` | RPI (rural) group-wise cumulative indices | PBS | pdf | monthly | rolling | 3 | — | — | — | [official page](https://www.pbs.gov.pk/price-statistics/) | [direct file/feed](https://www.pbs.gov.pk/wp-content/uploads/2020/07/RPI-Gropwise-Cumulative-Indices.pdf) |

## Monetary

### Tier 1 — fully automated dashboard core

| ID | Name | Publisher | Format | Frequency | Configured coverage | Tier | Parser | Series count | Observed range | Official page | Direct URL |
|---|---|---|---|---|---|---:|---|---:|---|---|---|
| `sbp_broad_money_m2` | Broad Money (M2) — components and affecting factors | SBP | xls | weekly | 1969-06 onward | 1 | `parse_sbp_m2` | 60 | 1969-06-30 to 2026-07-31 | [official page](https://www.sbp.org.pk/ecodata/index2.asp) | [direct file/feed](https://www.sbp.org.pk/assets/document/BroadMoney_M2_Arch.xls) |
| `sbp_credit_loans_by_borrower` | Credit and loans to the private sector | SBP | xls | monthly | 2001-06 onward | 1 | `parse_sbp_credit_loans` | 519 | 2001-06-30 to 2026-06-30 | [official page](https://www.sbp.org.pk/economic-data) | [direct file/feed](https://www.sbp.org.pk/assets/document/CreditLoans-arch.xls) |
| `sbp_interest_rate_corridor` | SBP standing facility usage (ceiling / floor amounts and institutions) | SBP | xls | daily | 2009-08-13 onward | 1 | `parse_sbp_ir_corridor` | 4 | 2009-08-13 to 2026-08-07 | [official page](https://www.sbp.org.pk/ecodata/index2.asp) | [direct file/feed](https://www.sbp.org.pk/assets/document/IR-Corridor-Hist.xls) |
| `sbp_interest_rates` | Structure of interest rates (policy rate, KIBOR, lending/deposit rates) | SBP | pdf | fortnightly | policy rate 2023-01 onward; KIBOR and bank rates rolling ~12 months | 1 | `parse_sbp_interest_rates` | 22 | 2017-06-30 to 2026-07-31 | [official page](https://www.sbp.org.pk/ecodata/index2.asp) | [direct file/feed](https://www.sbp.org.pk/assets/document/sir.pdf) |
| `sbp_pib_auction_results` | Pakistan Investment Bonds auction results (cut-off yields) | SBP | xlsx | monthly | long archive | 1 | — | — | — | [official page](https://www.sbp.org.pk/ecodata/index2.asp) | [direct file/feed](https://www.sbp.org.pk/assets/document/Pakinvestbonds.xlsx) |

### Tier 2 — automated download and semi-structured parse

| ID | Name | Publisher | Format | Frequency | Configured coverage | Tier | Parser | Series count | Observed range | Official page | Direct URL |
|---|---|---|---|---|---|---:|---|---:|---|---|---|
| `sbp_depository_corporations_survey` | Depository Corporations Survey | SBP | xls | monthly | long archive | 2 | — | — | — | [official page](https://www.sbp.org.pk/ecodata/index2.asp) | [direct file/feed](https://www.sbp.org.pk/assets/document/DCsArch.xls) |
| `sbp_deposits_by_holder` | Deposits distributed by category of deposit holders | SBP | xls | monthly | long archive | 2 | — | — | — | [official page](https://www.sbp.org.pk/ecodata/index2.asp) | [direct file/feed](https://www.sbp.org.pk/assets/document/DDholders-Arc.xls) |
| `sbp_lending_deposit_rates` | Weighted average lending and deposit rates | SBP | xls | monthly | long archive | 2 | — | — | — | [official page](https://www.sbp.org.pk/ecodata/index2.asp) | [direct file/feed](https://www.sbp.org.pk/assets/document/Lendingdepositrates_Arch.xls) |
| `sbp_loans_by_type_of_finance` | Loans to private sector business by type of finance | SBP | xls | monthly | long archive | 2 | — | — | — | [official page](https://www.sbp.org.pk/ecodata/index2.asp) | [direct file/feed](https://www.sbp.org.pk/assets/document/By-type-of-finance-arch.xls) |
| `sbp_monetary_aggregates_m3` | Monetary Aggregates (M3) | SBP | xlsx | monthly | long archive | 2 | — | — | — | [official page](https://www.sbp.org.pk/ecodata/index2.asp) | [direct file/feed](https://www.sbp.org.pk/assets/document/M3-Arch.xlsx) |
| `sbp_omo_injections` | Open Market Operations history (injections) | SBP | xlsx | weekly | long archive | 2 | — | — | — | [official page](https://www.sbp.org.pk/ecodata/index2.asp) | [direct file/feed](https://www.sbp.org.pk/assets/document/OMO-Inject-Hist.xlsx) |
| `sbp_reserve_money` | Reserve Money (RM) | SBP | xls | weekly | long archive | 2 | — | — | — | [official page](https://www.sbp.org.pk/ecodata/index2.asp) | [direct file/feed](https://www.sbp.org.pk/assets/document/ReserveMoney_Arch.xls) |
| `sbp_tbill_auction_latest` | Market Treasury Bills — latest auction result | SBP | xlsx | fortnightly | latest auction only | 2 | — | — | — | [official page](https://www.sbp.org.pk/ecodata/index2.asp) | [direct file/feed](https://www.sbp.org.pk/assets/document/tb.xlsx) |

### Tier 3 — PDF/manual reference sources

| ID | Name | Publisher | Format | Frequency | Configured coverage | Tier | Parser | Series count | Observed range | Official page | Direct URL |
|---|---|---|---|---|---|---:|---|---:|---|---|---|
| `sbp_kibor_daily` | KIBOR rates (daily) | SBP | pdf | daily | daily snapshot only | 3 | — | — | — | [official page](https://www.sbp.org.pk/ecodata/index2.asp) | Dynamic discovery: `sbp_dated_asset` (`kibor-rates-{d}-{month_lower}-{yyyy}.pdf`) |
| `sbp_monetary_policy_statement` | Monetary Policy Statement (policy rate decision) | SBP | pdf | bimonthly | archive on page | 3 | — | — | — | [official page](https://www.sbp.org.pk/mpstatements/index.asp) | Dynamic discovery: `sbp_mps_scan` |

## Fiscal

### Tier 1 — fully automated dashboard core

| ID | Name | Publisher | Format | Frequency | Configured coverage | Tier | Parser | Series count | Observed range | Official page | Direct URL |
|---|---|---|---|---|---|---:|---|---:|---|---|---|
| `mof_central_govt_operations_sdmx` | Central Government Operations (Ministry of Finance, SDMX) | MOF | xml | quarterly | 2017-Q1 onward | 1 | `parse_sdmx_mof_cgo` | 64 | 2016-09-30 to 2025-03-31 | [official page](https://www.finance.gov.pk/fiscal_operations.html) | [direct file/feed](http://sdmx.finance.gov.pk/CGO_Pakistan.xml) |
| `mof_general_govt_operations_sdmx` | General Government Operations (Ministry of Finance, SDMX) | MOF | xml | quarterly | 2017-Q1 onward | 1 | `parse_sdmx_mof_ggo` | 59 | 2016-09-30 to 2025-03-31 | [official page](https://www.finance.gov.pk/fiscal_operations.html) | [direct file/feed](http://sdmx.finance.gov.pk/GGO_Pakistan.xml) |
| `sbp_central_govt_debt` | Central Government Debt | SBP | xls | monthly | long archive | 1 | — | — | — | [official page](https://www.sbp.org.pk/ecodata/index2.asp) | [direct file/feed](https://www.sbp.org.pk/assets/document/CenGovDebt-Archive.xls) |
| `sbp_debt_liabilities_summary` | Pakistan Debt and Liabilities — Summary | SBP | xls | quarterly | long archive | 1 | — | — | — | [official page](https://www.sbp.org.pk/ecodata/index2.asp) | [direct file/feed](https://www.sbp.org.pk/assets/document/Summary.xls) |
| `sbp_domestic_debt` | Government domestic debt and liabilities by instrument | SBP | xls | monthly | 2010-07 onward | 1 | `parse_sbp_domestic_debt` | 69 | 2010-06-30 to 2026-05-31 | [official page](https://www.sbp.org.pk/economic-data) | [direct file/feed](https://www.sbp.org.pk/assets/document/D-Debt-Liabilities.xls) |
| `sbp_external_debt_outstanding` | Pakistan's External Debt and Liabilities — Outstanding | SBP | xls | quarterly | long archive | 1 | — | — | — | [official page](https://www.sbp.org.pk/ecodata/index2.asp) | [direct file/feed](https://www.sbp.org.pk/assets/document/pakdebt_Arch.xls) |

### Tier 2 — automated download and semi-structured parse

| ID | Name | Publisher | Format | Frequency | Configured coverage | Tier | Parser | Series count | Observed range | Official page | Direct URL |
|---|---|---|---|---|---|---:|---|---:|---|---|---|
| `fbr_monthwise_taxwise_collection` | Month-wise / tax-wise net revenue collection | FBR | pdf | annual (one file per FY) | FY2003-04 onward | 2 | — | — | — | [official page](https://www.fbr.gov.pk/revenue-collections/142253/131355) | Dynamic discovery: `fbr_link_scan` (`MonthWise-TaxWiseNetCollection`) |
| `sbp_debt_liabilities_profile` | Pakistan Debt and Liabilities — Profile | SBP | xls | quarterly | long archive | 2 | — | — | — | [official page](https://www.sbp.org.pk/ecodata/index2.asp) | [direct file/feed](https://www.sbp.org.pk/assets/document/Profile.xls) |
| `sbp_external_debt_servicing` | Pakistan External Debt / Liabilities servicing | SBP | xls | quarterly | long archive | 2 | — | — | — | [official page](https://www.sbp.org.pk/ecodata/index2.asp) | [direct file/feed](https://www.sbp.org.pk/assets/document/pakdebtsvr_Arch.xls) |
| `sbp_national_savings` | Savings mobilised by National Saving Schemes | SBP | xls | monthly | long archive | 2 | — | — | — | [official page](https://www.sbp.org.pk/ecodata/index2.asp) | [direct file/feed](https://www.sbp.org.pk/assets/document/savings.xls) |
| `sbp_pse_domestic_debt` | Outstanding domestic debt of Public Sector Enterprises | SBP | xls | quarterly | long archive | 2 | — | — | — | [official page](https://www.sbp.org.pk/ecodata/index2.asp) | [direct file/feed](https://www.sbp.org.pk/assets/document/PSEs.xls) |

### Tier 3 — PDF/manual reference sources

| ID | Name | Publisher | Format | Frequency | Configured coverage | Tier | Parser | Series count | Observed range | Official page | Direct URL |
|---|---|---|---|---|---|---:|---|---:|---|---|---|
| `fbr_quarterly_reviews` | FBR Biannual / Quarterly Review | FBR | pdf | quarterly | multi-year | 3 | — | — | — | [official page](https://www.fbr.gov.pk/fbr-biannual-quarterly-reviews/142253/132077) | Dynamic discovery: `fbr_link_scan` (`Review`) |
| `fbr_year_books` | FBR Year Book (annual revenue performance) | FBR | pdf | annual | FY1986-87 onward | 3 | — | — | — | [official page](https://www.fbr.gov.pk/fbr-year-books/142253/132039) | Dynamic discovery: `fbr_link_scan` (`YEARBOOK\|Yearbook\|YearBook`) |
| `mof_budget_documents` | Federal Budget documents (Budget in Brief, Finance Bill) | MOF | pdf | annual | multi-year | 3 | — | — | — | [official page](https://www.finance.gov.pk/budget_main.html) | Dynamic discovery: `mof_link_scan` (`/budget/`) |
| `mof_debt_bulletins` | Debt Policy Coordination Office — debt bulletins and annual debt review | MOF | pdf | quarterly | 2015 onward | 3 | — | — | — | [official page](https://www.finance.gov.pk/dpco_publications.html) | Dynamic discovery: `mof_link_scan` (`/dpco/`) |
| `mof_economic_survey_chapters` | Pakistan Economic Survey — statistical chapters | MOF | pdf | annual | FY2025-26 edition; earlier editions at survey_2025.html, survey_2023.html | 3 | — | — | — | [official page](https://www.finance.gov.pk/survey_2026.html) | Dynamic discovery: `mof_link_scan` (`/survey/chapter_`) |
| `mof_economic_survey_supplement` | Pakistan Economic Survey — Statistical Supplement | MOF | zip | annual | FY2024-25 | 3 | — | — | — | [official page](https://www.finance.gov.pk/publications_latest.html) | [direct file/feed](https://www.finance.gov.pk/economic/supplement_2024-25.zip) |
| `mof_fiscal_operations` | Consolidated Federal and Provincial Fiscal Operations | MOF | pdf | quarterly | FY2013-14 onward (July_June_2013_14.pdf ... july_march_2025_26.pdf) | 3 | — | — | — | [official page](https://www.finance.gov.pk/fiscal_main.html) | Dynamic discovery: `mof_link_scan` (`/fiscal/`) |
| `mof_monthly_economic_update` | Monthly Economic Update and Outlook | MOF | pdf | monthly | rolling | 3 | — | — | — | [official page](https://www.finance.gov.pk/economic_update.html) | Dynamic discovery: `mof_link_scan` (`/economic/Monthly_Economic_Update`) |

## External

### Tier 1 — fully automated dashboard core

| ID | Name | Publisher | Format | Frequency | Configured coverage | Tier | Parser | Series count | Observed range | Official page | Direct URL |
|---|---|---|---|---|---|---:|---|---:|---|---|---|
| `pbs_merchandise_trade_sdmx` | Merchandise trade, monthly (PBS, SDMX) | PBS | xml | monthly | 2008-01 onward | 1 | `parse_sdmx_pbs_trade` | 63 | 2008-01-31 to 2026-05-31 | [official page](https://www.pbs.gov.pk/external-trade-statistics/) | [direct file/feed](https://www.pbs.gov.pk/wp-content/uploads/2020/07/MET.xml) |
| `pbs_trade_services_summary` | Monthly summary on trade in services (PBS) | PBS | xlsx | monthly | rolling | 1 | `parse_pbs_services_summary` | 6 | 2025-03-31 to 2026-06-30 | [official page](https://www.pbs.gov.pk/external-trade-statistics/) | Dynamic discovery: `pbs_media_search` (`Services-Summary`) |
| `pbs_trade_summary_monthly` | Monthly summary on merchandise trade (PBS) | PBS | xlsx | monthly | rolling | 1 | `parse_pbs_trade_summary` | 6 | 2025-04-30 to 2026-07-31 | [official page](https://www.pbs.gov.pk/external-trade-statistics/) | Dynamic discovery: `pbs_media_search` (`Summary-`) |
| `sbp_balance_of_trade` | Exports, imports and balance of trade (BOP basis) | SBP | xls | monthly | FY1970-71 onward | 1 | `parse_sbp_balance_of_trade` | 15 | 1970-07-31 to 2026-06-30 | [official page](https://www.sbp.org.pk/ecodata/index2.asp) | [direct file/feed](https://www.sbp.org.pk/assets/document/exp_import_BOP_Arch.xls) |
| `sbp_bop_summary` | Summary of Balance of Payments (BPM6) | SBP | xls | monthly | long archive | 1 | — | — | — | [official page](https://www.sbp.org.pk/ecodata/index2.asp) | [direct file/feed](https://www.sbp.org.pk/assets/document/Balancepayment_BPM6.xls) |
| `sbp_bop_summary_archive` | Summary Balance of Payments BPM6 — monthly archive | SBP | xlsx | monthly | long archive | 1 | — | — | — | [official page](https://www.sbp.org.pk/ecodata/index2.asp) | [direct file/feed](https://www.sbp.org.pk/assets/document/BPM6_Ach_M.xlsx) |
| `sbp_exchange_rate_daily` | Bank floating exchange rates — daily archive | SBP | xlsx | daily | long archive | 1 | — | — | — | [official page](https://www.sbp.org.pk/ecodata/index2.asp) | [direct file/feed](https://www.sbp.org.pk/assets/document/BFER_Daily_Arch.xlsx) |
| `sbp_exchange_rate_monthly` | Bank floating average exchange rates (monthly archive) | SBP | xls | monthly | long archive | 1 | — | — | — | [official page](https://www.sbp.org.pk/ecodata/index2.asp) | [direct file/feed](https://www.sbp.org.pk/assets/document/IBF_Arch.xls) |
| `sbp_fdi_summary` | Summary of foreign investment in Pakistan | SBP | xls | monthly | long archive | 1 | — | — | — | [official page](https://www.sbp.org.pk/ecodata/index2.asp) | [direct file/feed](https://www.sbp.org.pk/assets/document/FIS-FDI-Arch.xls) |
| `sbp_forex_reserves` | Liquid foreign exchange reserves (SBP + banks) | SBP | xlsx | weekly | FY1998-99 onward | 1 | `parse_sbp_forex` | 3 | 1999-06-30 to 2026-07-31 | [official page](https://www.sbp.org.pk/ecodata/index2.asp) | [direct file/feed](https://www.sbp.org.pk/assets/document/Forex_Arch.xlsx) |
| `sbp_reer_neer` | Nominal and real effective exchange rate indices (NEER / REER) | SBP | xls | monthly | 2013-01 to 2023-12 | 1 | `parse_sbp_reer_neer` | 8 | 2013-01-31 to 2023-12-31 | [official page](https://www.sbp.org.pk/economic-data) | [direct file/feed](https://www.sbp.org.pk/assets/document/neer-reer.xls) |
| `sbp_workers_remittances` | Country-wise workers' remittances | SBP | xlsx | monthly | 1972-07 onward | 1 | `parse_sbp_remittances` | 38 | 1972-07-31 to 2026-06-30 | [official page](https://www.sbp.org.pk/ecodata/index2.asp) | [direct file/feed](https://www.sbp.org.pk/assets/document/Homeremit_Arch.xlsx) |

### Tier 2 — automated download and semi-structured parse

| ID | Name | Publisher | Format | Frequency | Configured coverage | Tier | Parser | Series count | Observed range | Official page | Direct URL |
|---|---|---|---|---|---|---:|---|---:|---|---|---|
| `sbp_exports_by_commodity` | Export receipts by commodities and groups | SBP | xls | monthly | long archive | 2 | — | — | — | [official page](https://www.sbp.org.pk/ecodata/index2.asp) | [direct file/feed](https://www.sbp.org.pk/assets/document/Export_Receipts_by_Commodities_and_Groups_Arch.xls) |
| `sbp_exports_by_country` | Export receipts by all countries | SBP | xls | monthly | long archive | 2 | — | — | — | [official page](https://www.sbp.org.pk/ecodata/index2.asp) | [direct file/feed](https://www.sbp.org.pk/assets/document/Export_Receipts_by_all_Countries_Arch.xls) |
| `sbp_fdi_by_country_sector` | Foreign investment by countries and sectors | SBP | xls | monthly | long archive | 2 | — | — | — | [official page](https://www.sbp.org.pk/ecodata/index2.asp) | [direct file/feed](https://www.sbp.org.pk/assets/document/Netinflow.xls) |
| `sbp_imports_by_commodity` | Import payments by commodities and groups | SBP | xls | monthly | long archive | 2 | — | — | — | [official page](https://www.sbp.org.pk/ecodata/index2.asp) | [direct file/feed](https://www.sbp.org.pk/assets/document/Import_Payments_by_Commodities_and_Groups_Arch.xls) |
| `sbp_imports_by_country` | Import payments by all countries | SBP | xls | monthly | long archive | 2 | — | — | — | [official page](https://www.sbp.org.pk/ecodata/index2.asp) | [direct file/feed](https://www.sbp.org.pk/assets/document/Import_Payments_by_all_Countries_Arch.xls) |
| `sbp_official_reserve_assets` | Official Reserve Assets (SDDS template) | SBP | xlsx | monthly | long archive | 2 | — | — | — | [official page](https://www.sbp.org.pk/ecodata/index2.asp) | [direct file/feed](https://www.sbp.org.pk/assets/document/ORA_Arch.xlsx) |
| `sbp_trade_in_services` | Trade in services — detailed | SBP | xls | monthly | long archive | 2 | — | — | — | [official page](https://www.sbp.org.pk/ecodata/index2.asp) | [direct file/feed](https://www.sbp.org.pk/assets/document/TradeInServicesArch.xls) |

## Growth

### Tier 1 — fully automated dashboard core

| ID | Name | Publisher | Format | Frequency | Configured coverage | Tier | Parser | Series count | Observed range | Official page | Direct URL |
|---|---|---|---|---|---|---:|---|---:|---|---|---|
| `pbs_quarterly_national_accounts_sdmx` | Quarterly national accounts (PBS, SDMX) | PBS | xml | quarterly | 2016-Q1 onward | 1 | `parse_sdmx_pbs_qna` | 84 | 2015-09-30 to 2026-03-31 | [official page](https://www.pbs.gov.pk/national-accounts) | [direct file/feed](https://www.pbs.gov.pk/wp-content/uploads/2020/07/QNAG.xml) |
| `sbp_gdp_annual` | Gross Domestic Product of Pakistan (annual, by sector) | SBP | xlsx | annual | FY1999-2000 onward | 1 | `parse_sbp_gdp_annual` | 36 | 2000-06-30 to 2026-06-30 | [official page](https://www.sbp.org.pk/ecodata/index2.asp) | [direct file/feed](https://www.sbp.org.pk/assets/document/GDP_table.xlsx) |
| `sbp_gdp_quarterly` | Quarterly GDP (constant basic prices) and quarterly growth | SBP | xlsx | quarterly | FY2015-16 Q1 onward | 1 | `parse_sbp_gdp_quarterly` | 62 | 2015-09-30 to 2026-03-31 | [official page](https://www.sbp.org.pk/ecodata/index2.asp) | [direct file/feed](https://www.sbp.org.pk/assets/document/QGDP.xlsx) |
| `sbp_lsm_production` | Production of selected large-scale manufacturing items (QIM, base 2015-16) | SBP | xlsx | monthly | base 2015-16 | 1 | `parse_sbp_lsm` | — | — | [official page](https://www.sbp.org.pk/ecodata/index2.asp) | [direct file/feed](https://www.sbp.org.pk/assets/document/Productselect.xlsx) |

### Tier 2 — automated download and semi-structured parse

| ID | Name | Publisher | Format | Frequency | Configured coverage | Tier | Parser | Series count | Observed range | Official page | Direct URL |
|---|---|---|---|---|---|---:|---|---:|---|---|---|
| `pbs_agriculture_statistics` | Agriculture statistics and agricultural census tables | PBS | xlsx | annual | census tables TABLE-NO-1.1 .. 8.16 | 2 | — | — | — | [official page](https://www.pbs.gov.pk/agriculture-sector-of-pakistan-importance-role-key-statistics/) | Dynamic discovery: `pbs_page_link_scan` (`https://www.pbs.gov.pk/agriculture-sector-of-pakistan-importance-role-key-statistics/`) |
| `pbs_national_accounts` | National Accounts tables (base 2015-16) | PBS | xlsx | annual | base 2015-16 | 2 | — | — | — | [official page](https://www.pbs.gov.pk/national-accounts-2/) | Dynamic discovery: `pbs_page_link_scan` (`https://www.pbs.gov.pk/national-accounts-2/`) |

### Tier 3 — PDF/manual reference sources

| ID | Name | Publisher | Format | Frequency | Configured coverage | Tier | Parser | Series count | Observed range | Official page | Direct URL |
|---|---|---|---|---|---|---:|---|---:|---|---|---|
| `pbs_qim_lsm` | Quantum Index of Large Scale Manufacturing Industries (QIM) | PBS | pdf | monthly | base 2015-16 | 3 | — | — | — | [official page](https://www.pbs.gov.pk/pakistan-bureau-of-statistics-economic-statistics-production/) | Dynamic discovery: `pbs_media_search` (`QUANTUM-INDEX`) |

## Labour

### Tier 1 — fully automated dashboard core

| ID | Name | Publisher | Format | Frequency | Configured coverage | Tier | Parser | Series count | Observed range | Official page | Direct URL |
|---|---|---|---|---|---|---:|---|---:|---|---|---|
| `pbs_labour_sdmx` | Labour force indicators (PBS, SDMX) | PBS | xml | annual | 1991 to 2021 | 1 | `parse_sdmx_pbs_labour` | 3 | 1991-06-30 to 2021-06-30 | [official page](https://www.pbs.gov.pk/labour-force-statistics) | [direct file/feed](https://www.pbs.gov.pk/wp-content/uploads/2020/07/LMI.xml) |

### Tier 2 — automated download and semi-structured parse

| ID | Name | Publisher | Format | Frequency | Configured coverage | Tier | Parser | Series count | Observed range | Official page | Direct URL |
|---|---|---|---|---|---|---:|---|---:|---|---|---|
| `pbs_labour_force_survey` | Labour Force Survey (unemployment, LFP, employment by sector) | PBS | xlsx | annual | multi-round | 2 | — | — | — | [official page](https://www.pbs.gov.pk/labour-force-statistics/) | Dynamic discovery: `pbs_page_link_scan` (`https://www.pbs.gov.pk/labour-force-statistics/`) |
| `pbs_social_statistics` | PSLM / HIES and social statistics | PBS | xlsx | biennial | multi-round | 2 | — | — | — | [official page](https://www.pbs.gov.pk/social-statistics-2/) | Dynamic discovery: `pbs_page_link_scan` (`https://www.pbs.gov.pk/social-statistics-2/`) |

## Energy

### Tier 1 — fully automated dashboard core

| ID | Name | Publisher | Format | Frequency | Configured coverage | Tier | Parser | Series count | Observed range | Official page | Direct URL |
|---|---|---|---|---|---|---:|---|---:|---|---|---|
| `pbs_energy_sdmx` | Oil and energy indicators (PBS, SDMX) | PBS | xml | monthly | 2022-01 onward | 1 | `parse_sdmx_pbs_energy` | 7 | 2022-01-31 to 2026-04-30 | [official page](https://www.pbs.gov.pk/) | [direct file/feed](https://www.pbs.gov.pk/wp-content/uploads/2020/07/ORSI.xml) |

### Tier 3 — PDF/manual reference sources

| ID | Name | Publisher | Format | Frequency | Configured coverage | Tier | Parser | Series count | Observed range | Official page | Direct URL |
|---|---|---|---|---|---|---:|---|---:|---|---|---|
| `nepra_state_of_industry` | NEPRA State of Industry Report | NEPRA | pdf | annual | 2004 onward | 3 | — | — | — | [official page](https://nepra.org.pk/publications/State%20of%20Industry%20Reports.php) | [direct file/feed](https://nepra.org.pk/publications/State%20of%20Industry%20Reports/State%20of%20Industry%20Report%202024.pdf) |
| `nepra_tariff_determinations` | NEPRA tariff determinations | NEPRA | pdf | as issued | rolling | 3 | — | — | — | [official page](https://nepra.org.pk/) | Dynamic discovery: `nepra_link_scan` (`Tariff`) |
| `ogra_petroleum_industry_report` | OGRA State of the Regulated Petroleum Industry | OGRA | pdf | annual | multi-year | 3 | — | — | — | [official page](https://www.ogra.org.pk/) | Dynamic discovery: `manual` |


# Dashboard Pages

The application has nine built pages: the overview home page and eight numbered Streamlit pages. All pages read the validated master table and metadata, resolve displayed series against the live series index, expose source provenance, and offer filtered CSV downloads. They deliberately retain original release frequency; they do not convert irregular releases into false monthly precision.

## Built pages

| Page | What it shows | Important interpretation safeguards |
|---|---|---|
| **Home / Overview** | Latest published KPI cards for headline CPI, policy rate, liquid FX reserves, BOP trade balance, a remittance corridor, archived M2, annual GDP growth, and general-government balance; small-multiple trend charts; source fetch/status table. | Labels the M2 headline as archived, reports data freshness from the manifest, and identifies the MoF balance as lagged rather than current. |
| **Inflation** | Published national/urban/rural CPI levels or official YoY changes; food COICOP index and weight; WPI/PPI series; weekly SPI index or published YoY. The page uses PBS price-statistics material and the [CPI SDMX feed](https://www.pbs.gov.pk/wp-content/uploads/2020/07/CPI-1.xml). | CPI and SPI are explicitly different baskets. It does not manufacture a core-inflation or non-food aggregate because the current PBS SDMX extract does not publish a pre-built official aggregate. |
| **Monetary conditions** | SBP policy target, floor and ceiling; M2 components and private-sector credit; KIBOR/T-bill yields; bank lending/deposit rates; standing-facility amounts and institution counts. It relies on SBP releases such as [Structure of Interest Rates](https://www.sbp.org.pk/assets/document/sir.pdf) and [standing-facility history](https://www.sbp.org.pk/assets/document/IR-Corridor-Hist.xls). | Makes the crucial distinction that `IR-Corridor-Hist.xls` records standing-facility usage, not the policy rate. It does not stitch old and new M2 headline labels or pre/post-2019 credit categories. |
| **Fiscal operations and domestic debt** | Consolidated general-government revenue/expenditure/budget balance, domestic-debt components, and a latest-month debt-composition treemap. It uses the [MoF general-government feed](http://sdmx.finance.gov.pk/GGO_Pakistan.xml) and SBP domestic-debt archive. | States that the MoF feed ends in 2025-03-31 and warns against adding central-government values to general government, which would double-count. |
| **External sector** | SBP BOP trade, PBS customs trade summary, PBS long-run customs trade in PKR, selected remittance corridors, reserves, and historical REER/NEER. It uses the [SBP BOP trade archive](https://www.sbp.org.pk/assets/document/exp_import_BOP_Arch.xls), [PBS MET feed](https://www.pbs.gov.pk/wp-content/uploads/2020/07/MET.xml), and [SBP reserves archive](https://www.sbp.org.pk/assets/document/Forex_Arch.xlsx). | Shows BOP trade, customs trade in USD, and customs trade in PKR separately. Flags REER/NEER as discontinued after 2023-12. |
| **Growth and production** | Annual GDP growth and sectoral value added, SBP quarterly sector growth, PBS nominal quarterly GDP, and national-accounts large-scale-manufacturing value added. It uses [SBP annual GDP](https://www.sbp.org.pk/assets/document/GDP_table.xlsx), [SBP QGDP](https://www.sbp.org.pk/assets/document/QGDP.xlsx), and [PBS QNAG](https://www.pbs.gov.pk/wp-content/uploads/2020/07/QNAG.xml). | Separates PBS nominal GDP from SBP constant-2015-16 basic-price GDP; it does not display the unparsed LSM production snapshot as if it were already in the master. |
| **Labour and energy** | Labour force, employment, unemployment, a clearly labelled derived unemployment rate, electricity generation by source, crude-oil production, and natural-gas production. It reads the [PBS labour feed](https://www.pbs.gov.pk/wp-content/uploads/2020/07/LMI.xml) and [PBS energy feed](https://www.pbs.gov.pk/wp-content/uploads/2020/07/ORSI.xml). | Shows labour as historical context only because the SDMX feed ends in 2021. States that NEPRA/OGRA regulatory information is not replaced with estimates. |
| **Series Explorer** | Filterable access to every indexed series by theme, dataset, and frequency; exact-series selection; levels, YoY change, or normalisation; unit-separated plots and CSV export. | Source-qualifies labels to avoid merging identical literal labels from different datasets. Different units are separated unless the user intentionally normalises them. |
| **Data Catalog and quality checks** | Searchable series index, source-level observed date-coverage timeline, current validation report, source provenance, and date-filtered master download. | Reports only observed parsed coverage, not assumed coverage. It makes warnings available to dashboard users instead of treating validation as an internal-only process. |

## Recommended next pages and interactive visualisations

The following are deliberately separated into (A) features that can be built from data already in the pipeline, (B) features that need an approved enhancement, and (C) features that require data not yet available in machine-readable form.

### A. Build now from existing pipeline data

#### 1. Monetary Policy Committee decision brief

Create a concise page designed for the week of an MPC decision: the latest policy target/floor/ceiling, KIBOR and T-bill curve, lending/deposit spread, money/credit growth, headline CPI, food CPI/SPI signal, reserves, trade, remittances, and a release/freshness panel. The current policy-rate extract comes from [SBP Structure of Interest Rates](https://www.sbp.org.pk/assets/document/sir.pdf); the page can also link to the official [Monetary Policy Statements archive](https://www.sbp.org.pk/mpstatements/index.asp) for the decision text. Use observation dates and “last published” labels—not a fabricated real-time policy reaction function.

**Interaction:** a decision-date selector that freezes the available-data vintage and an “as-of” table. This is especially useful in ex-post policy evaluation because it reduces hindsight bias.

#### 2. Inflation decomposition and contributions to YoY

Build a COICOP contribution chart from the CPI group indices and publisher-supplied weights in [CPI-1.xml](https://www.pbs.gov.pk/wp-content/uploads/2020/07/CPI-1.xml). Start with a method panel that shows the formula, base period, treatment of changing weights, and reconciliation gap versus published headline CPI. Show group contributions, food/non-food views, and a current-vs-year-ago basket-weight table.

**Interaction:** selectable groups, contribution waterfall, cumulative contribution view, and a “published versus derived” diagnostics panel. This is implementable now, but must be released only after economist review validates the aggregation against the official headline measure.

#### 3. External-vulnerability monitor

Use the existing [SBP reserves archive](https://www.sbp.org.pk/assets/document/Forex_Arch.xlsx), [BOP trade archive](https://www.sbp.org.pk/assets/document/exp_import_BOP_Arch.xls), and [remittances archive](https://www.sbp.org.pk/assets/document/Homeremit_Arch.xlsx) to display reserves, trade deficit, selected remittance corridors, and a clearly labelled **derived** reserves-in-months-of-imports proxy. The ratio should specify whether the denominator is a trailing three- or twelve-month average and whether it uses BOP imports; it must not be mixed with PBS customs trade.

**Interaction:** rolling-window selector, reserve component toggle (SBP / banks / total), a remittance-corridor share chart, and threshold bands that are visibly user-defined rather than official policy thresholds.

#### 4. Fiscal-lag tracker

Turn the known MoF publication lag into a dashboard page rather than a footnote. Use the [GGO feed](http://sdmx.finance.gov.pk/GGO_Pakistan.xml) and [CGO feed](http://sdmx.finance.gov.pk/CGO_Pakistan.xml) to show the latest observation date, days since latest observation, expected quarterly cadence, and a chart shaded after the last confirmed period. Separate central and general government and display a prominent “do not sum” consolidation note.

**Interaction:** a release-calendar strip, source-freshness history from the manifest, and an alert card if lag exceeds the validation budget. It makes the 16-month lag explicit, avoiding false claims about current fiscal conditions.

#### 5. Weekly SPI-to-monthly CPI nowcast

Use existing weekly SPI and published monthly CPI to build an **experimental** nowcast page. The purpose is not to replace the PBS CPI release but to give a dated high-frequency food-price signal between releases. Start with simple, documented models and a real-time back-test window; do not present coefficients as structural estimates.

**Interaction:** model choice (naive weekly change, distributed lag, rolling regression), training-end-date selector, fan chart, and error history. Label all output “PIDE experimental nowcast; not an official statistic.”

#### 6. Automated “what changed this month?” page

Compare two completed pipeline snapshots using raw-file hashes, manifest statuses, series-index coverage, and latest observations. Highlight new releases, revised historical values, newly added/removed series, changed source files, and validation status. Every item should link back to the relevant official page already stored in metadata.

**Interaction:** previous-run selector, filter by publisher/theme/severity, and a downloadable change log. This is a high-leverage supervision tool because it exposes revisions before analysts reuse a chart.

#### 7. Scenario and sensitivity workbook-style page

Provide transparent, non-forecasting arithmetic tools: exchange-rate pass-through sensitivities, import-cost sensitivities, food-weight shocks, reserve cover under alternative import paths, and fiscal balance-to-GDP scaling where inputs are available. The data inputs can draw from existing CPI weights, trade, reserves, and GDP releases.

**Interaction:** sliders with an explicit assumptions panel, unit/basis lockouts, saved scenario labels, and a CSV export. Keep scenarios separate from official data and require a user-entered assumption; no slider should silently extrapolate unavailable fiscal or energy data.

### B. High-value enhancements with officially obtainable data

#### 8. LSM / production pulse

Add the PBS monthly QIM trend sheet after a parser and validation rule are written. PBS publishes the stable [Trend-sheet XLSX](https://www.pbs.gov.pk/wp-content/uploads/2020/07/Trend-sheet.xlsx), while the pipeline already has related national-accounts measures. A page could compare QIM level, YoY, cumulative growth, and sectoral GDP with clear frequency distinctions.

**Status:** requires a new Tier 1/2 parser and reconciliation with the existing SBP national-accounts LSM presentation; do not substitute the two measures.

#### 9. Current labour-market update

Add supervised extracts from the [LFS 2024-25 Annual Report](https://www.pbs.gov.pk/wp-content/uploads/2020/07/LFS-2024-25-Annual-Report.pdf) or its official tables to bridge the SDMX feed’s 2021 cutoff. The page should show survey-round dates, methodology comparability, unemployment/LFP/employment measures, and a large “not annual monthly data” label.

**Status:** requires PDF/table extraction and an economist-approved comparability check; not yet a machine-readable pipeline input.

#### 10. Fiscal revenue and expenditure tracker

Create a Tier 2 page from official FBR collection PDFs and MoF fiscal operations PDFs. Start with source-document tiles and manually reviewed tables; later automate where the layouts prove stable. The official [FBR Revenue Collections page](https://www.fbr.gov.pk/revenue-collections/142253/131355) is the starting point.

**Status:** requires PDF extraction and reconciliation. It must never use the lagged MoF SDMX feed to imply current federal revenue or PSDP releases.

### C. Desired but not currently machine-readable / blocked data

#### 11. Power-sector affordability and reliability page

A useful policy page would combine NEPRA generation mix, DISCO losses, recoveries, tariffs/FCA, circular-debt references, and fuel inputs. The official [NEPRA State of Industry Reports](https://nepra.org.pk/publications/State%20of%20Industry%20Reports.php) and tariff pages are the correct sources.

**Status:** needs supervised PDF extraction and a cache strategy for very large reports; not currently a live dashboard source.

#### 12. Petroleum, gas, and retail-price monitor

The ideal page would show OGRA notified prices, monthly petroleum sales, gas-price notifications, and the pass-through to CPI transport/fuel groups. OGRA’s [official site](https://www.ogra.org.pk/) is the appropriate source, but direct scripted retrieval is blocked and the desired monthly OCAC sales series was not located in machine-readable form.

**Status:** unavailable to scheduled ETL until an approved manual/rendered-browser acquisition process and a verified official sales source are established.

#### 13. Poverty, household welfare, and agriculture dashboard

A welfare page should show HIES/PSLM poverty indicators, real consumption, food insecurity, labour outcomes, and crop production. PBS publishes the relevant source families through its [social statistics](https://www.pbs.gov.pk/social-statistics-2/) and [agriculture statistics](https://www.pbs.gov.pk/agriculture-sector-of-pakistan-importance-role-key-statistics/) pages.

**Status:** standalone poverty-headcount and crop-tonnage series were not located in machine-readable form. Treat this as a periodic report/survey-round dashboard, not a monthly nowcast, until official structured extracts are available.

## Product guardrails for all future pages

- Show the official source, unit, frequency, observed coverage, and last observation next to every decision-useful chart.
- Keep a derived metric visibly separate from a published official series, including formula and inputs.
- Disable or warn on comparisons across incompatible bases, currencies, price bases, or fiscal/calendar periods.
- Never carry forward a stale observation as a current value; use blank space, an end marker, and a lag notice.
- Version every methodology and expose revisions through the “what changed” page before incorporating them into briefing templates.

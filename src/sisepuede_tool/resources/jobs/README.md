# Jobs data

The Jobs page reads `data/`. The tables come from the process behind the
Egypt deck's jobs slides (Edmundo's Tableau workbook `Egypt_CaseStudy_261022`
and the R scripts in `r_original/`), ported to Python in
`services/jobs_service.py`. The port reproduces every table in `data/`: the
same rows and text, the numbers to 1e-9 (`tests/test_jobs_service.py`), except
the Tableau export's rounding of the forest investments (4e-8 billion USD).

## Rebuild from new runs

1. Run the pathways in the tool and download the Tableau zip (Results >
   Cost & benefits). Take its `cb_data.csv` (or the one in
   `ssp_egypt/ssp_modeling/tableau/data/tool_pathways`).
2. `python scripts/build_jobs_data.py --cb-data path/to/cb_data.csv`

This rewrites `data/`. The pathways are read from `strategy_code`: `PFLO:NDC`
and `PFLO:NDC2_0` (the tool's NDC2.0) as NDC, `PFLO:LEP` as LEP; `--pathway
CODE=NAME` names others. LEP is the low emissions pathway the baseline labour
market is changed by.

## Steps

| Step | Table | From | Was |
|---|---|---|---|
| 1 | `jobs_demand_egypt.csv`: jobs per million USD of each transformation, by EORA26 economic sector (direct, indirect, total) | `inputs/employment_results_sector_WB (Sector).csv` (input-output model, every country), Egypt's rows, `Strategy` split into `ssp_sector` and `ssp_transformation_name` | `r_original/#create jobs table for Egypt.r` |
| 2 | `total_jobs_multiplier.csv`: jobs per million USD by economic sector and SSP sector | step 1: `Total_Jobs` **summed** over the transformations of each SSP sector (`EN` left out) | Tableau export (Total job demand) |
| 3 | `technical_cost.csv`: investments, billion USD, by pathway, sector and year | `cb_data.csv`: −sum of the `technical_cost` rows of 12 sectors (`soil` left out), from 2023; zeros kept | Tableau export, from its `cb_data` extract |
| 4 | `direct_jobs_overtime_ippc_detail.csv`, `direct_jobs_overtime.csv`: jobs by year | multiplier × investment × 1e3, by the script's SSP sector → investment sector crosswalk | `r_original/create job time series_2026_05_29.r` |
| 5 | `total_jobs_overtime.csv`: Baseline, Low Emissions (reallocation), Low Emissions-Expansionary | baseline = working-age population × participation (0.45 → 0.48) × (1 − unemployment, 0.099 → 0.08) × sector share; LEP's jobs added, then rescaled to the baseline total (reallocation) or not (expansionary) | same script |

`inputs/` holds the other inputs as Edmundo gave them: UN WPP 2024-based
working-age population (2022–2050) and Egypt's employment shares by EORA26
sector (CAPMAS 2024, adds to 100).

## Kept as the process has them (to review)

- Step 2 sums the coefficients of a sector's transformations (e.g. 8 in
  transport), and step 4 multiplies that sum by the sector's whole investment.
- The crosswalk of step 4 has `LULUCF` where the multiplier says `Land Use`, so
  land use gets no investment; `CCS` and `Livestock` have none in step 3.
- The participation and unemployment rates of step 5 are the script's; the
  deck's baseline slide quotes 44.2% → 48% and 6.6% → 5%.
- `data/` now holds the tables from the Tableau extract of 2026-10-22. The
  `cb_data.csv` of ssp_egypt of 2026-10-23 gives other NDC investments in power.

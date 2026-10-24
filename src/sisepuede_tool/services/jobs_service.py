"""Jobs: the labour demand of the pathways' investments, and how it changes
Egypt's baseline jobs (Jobs page).

The page reads the CSVs in resources/jobs/data. They are built from the
pathways' technical costs (the tool's cb_data.csv, Tableau download) by
build(), a port of the process the Egypt deck's jobs slides came from, step by
step (resources/jobs/README.md):

1. jobs_demand_egypt.csv: jobs per million USD of each transformation, by
   EORA26 economic sector (direct, indirect, total), from the input-output
   model's employment_results_sector_WB (Sector).csv, Egypt's rows
   (r_original/#create jobs table for Egypt.r).
2. total_jobs_multiplier.csv: jobs per million USD by economic sector and SSP
   sector, the sum of Total_Jobs over the sector's transformations (as the
   Tableau workbook exports it).
3. technical_cost.csv: investments by pathway, IPCC-style sector and year
   (billion USD), -sum of the cb_data technical_cost rows of each sector, from
   FIRST_YEAR (as the Tableau workbook exports it).
4. direct_jobs_overtime*.csv and total_jobs_overtime.csv: multiplier x
   investment by year, and the baseline labour market with the low emissions
   pathway's jobs reallocated ("Low Emissions") or added
   ("Low Emissions-Expansionary") (r_original/create job time series_2026_05_29.r).

The numbers are kept as the process gives them; step 2 sums the coefficients
of the transformations of a sector, as the workbook does.
"""

import csv
import functools
import pathlib
from typing import Dict, Optional, Union

import numpy as np
import pandas as pd

from sisepuede_tool import config

JOBS_DIR = config.SISEPUEDE_TOOL_PACKAGE_DIR / "resources" / "jobs"
INPUTS_DIR = JOBS_DIR / "inputs"
DATA_DIR = JOBS_DIR / "data"

IO_RESULTS = "employment_results_sector_WB (Sector).csv"
POPULATION = "egypt_working_age_2022_2050_wpp2024_anchored_estimate.csv"
SECTOR_SHARES = "Egypt_employment_Fermi_breakdown_by_sector.csv"

COUNTRY = "EGY"
FIRST_YEAR = 2023  # first year of the investments (technical_cost.csv)
LOW_EMISSIONS = "LEP"  # the pathway the baseline labour market is changed by

# baseline labour market, 2022-2050, linear between the two ends
YEARS = (2022, 2050)
LABOR_FORCE_PARTICIPATION = (0.45, 0.48)
UNEMPLOYMENT_RATE = (0.099, 0.08)

# cb_data strategy_code -> pathway (the notebook runs' codes and the tool's)
PATHWAYS = {"PFLO:NDC": "NDC", "PFLO:NDC2_0": "NDC", "PFLO:LEP": "LEP"}

# jobs_demand ssp_sector -> SSP sector of the multiplier (the workbook's aliases;
# EN, the energy-sector-wide transformations, has none and is left out)
SSP_SECTORS = {
    "SCOE": "Buildings", "CCSQ": "CCS", "AGRC": "Crops", "FRST": "Forest", "FGTV": "Fugitive Emissions",
    "IPPU": "IPPU", "INEN": "Industrial Energy", "LNDU": "Land Use", "WALI": "Liquid Waste", "LVST": "Livestock",
    "LSMM": "Livestock Manure Management", "ENTC": "Power Industry", "WASO": "Solid Waste",
    "TRNS": "Transportation", "TRWW": "Wastewater treatment",
}

# cb_data sector -> investment sector (the workbook's aliases; soil has none)
COST_SECTORS = {
    "agrc": "AG - Crops", "lsmm": "AG - Livestock (manure)", "scoe": "EN - Building", "fgtv": "EN - Fugitive emissions",
    "inen": "EN - Industrial combustion", "entc": "EN - Power Industry (entc)", "trns": "EN - Transportation",
    "ippu": "IN - Industrial processes", "lndu": "LULUCF - Forest land", "waso": "Waste - Solid waste",
    "wali": "Waste - Wastewater (liquid waste)", "trww": "Waste - Wastewater treatment (trww)",
}

# SSP sector of the multiplier -> investment sector (the R script's crosswalk,
# as it is: "LULUCF" matches no SSP sector, so Land Use has no investment)
CROSSWALK = {
    "Wastewater treatment": "Waste - Wastewater treatment (trww)", "Transportation": "EN - Transportation",
    "Solid Waste": "Waste - Solid waste", "Power Industry": "EN - Power Industry (entc)", "LULUCF": "LULUCF - Forest land",
    "Livestock Manure Management": "AG - Livestock (manure)", "Livestock": "AG - Livestock",
    "Liquid Waste": "Waste - Wastewater (liquid waste)", "IPPU": "IN - Industrial processes",
    "Industrial Energy": "EN - Industrial combustion", "Fugitive Emissions": "EN - Fugitive emissions",
    "Forest": "LULUCF - Forest land", "Crops": "AG - Crops", "CCS": "CCS", "Buildings": "EN - Building",
}

# the workbook's grouping of the SSP sectors (Jobs Over Time Energy-Non Energy)
ENERGY_SECTORS = ["Buildings", "CCS", "Fugitive Emissions", "Industrial Energy", "Power Industry", "Transportation"]

BASELINE = "Baseline"
REALLOCATION = "Low Emissions"
EXPANSIONARY = "Low Emissions-Expansionary"


# ---------------------------------------------------------------------------
# 1-3: jobs per million USD, investments
# ---------------------------------------------------------------------------

def jobs_demand(io_results: pd.DataFrame, country: str = COUNTRY) -> pd.DataFrame:
    """The country's rows of the input-output results, with the Strategy
    ('AGRC: Expand conservation agriculture') split into ssp_sector and
    ssp_transformation_name (its leading space kept), indexed by the row number
    in the file (1-based, as R writes it)."""
    df = io_results.copy()
    df.index = range(1, len(df) + 1)
    parts = df["Strategy"].astype(str).str.split(":")
    df["ssp_sector"] = parts.str[0]
    df["ssp_transformation_name"] = parts.str[1]
    return df[df["Country"] == country]


def multiplier(demand: pd.DataFrame) -> pd.DataFrame:
    """[Economic Sector, Ssp Sector, Total Jobs]: Total_Jobs summed over the
    transformations of each SSP sector (SSP_SECTORS), for every economic sector."""
    d = demand[demand["ssp_sector"].isin(SSP_SECTORS)]
    out = d.groupby(["Sector", "ssp_sector"], as_index=False)["Total_Jobs"].sum()
    out["ssp_sector"] = out["ssp_sector"].map(SSP_SECTORS)
    out.columns = ["Economic Sector", "Ssp Sector", "Total Jobs"]
    return out.sort_values(["Ssp Sector", "Economic Sector"], ascending=False).reset_index(drop=True)


def technical_cost(cb_data: pd.DataFrame, first_year: int = FIRST_YEAR, pathways: Optional[Dict[str, str]] = None) -> pd.DataFrame:
    """[Pathway, Year1, Sector, Investments]: investments (billion USD, > 0 =
    spent) by pathway (`pathways`: strategy_code -> name, default PATHWAYS),
    sector (COST_SECTORS) and year from `first_year`: -sum of the cb_data
    technical_cost rows (capex, opex, ...); years that sum to 0 are kept."""
    pathways = pathways or PATHWAYS
    d = cb_data[(cb_data["cb_type"] == "technical_cost") & cb_data["sector"].isin(COST_SECTORS)
                & cb_data["strategy_code"].isin(pathways) & (cb_data["Year"] >= first_year)]
    out = d.groupby(["strategy_code", "Year", "sector"], as_index=False)["value"].sum()
    out = pd.DataFrame({
        "Pathway": out["strategy_code"].map(pathways), "Year1": out["Year"].astype(int),
        "Sector": out["sector"].map(COST_SECTORS), "Investments": -out["value"],
    })
    return out.sort_values(["Pathway", "Sector", "Year1"], ascending=[True, True, False]).reset_index(drop=True)


# ---------------------------------------------------------------------------
# 4: jobs over time (create job time series_2026_05_29.r)
# ---------------------------------------------------------------------------

def _linear(ends) -> pd.Series:
    years = np.arange(YEARS[0], YEARS[1] + 1)
    return pd.Series(np.interp(years, YEARS, ends), index=years)


def direct_jobs(mult: pd.DataFrame, costs: pd.DataFrame) -> pd.DataFrame:
    """[Sector, Ssp.Sector, Economic.Sector, Total.Jobs, Pathway, Investments,
    Year] (direct_jobs_overtime_ippc_detail.csv): the jobs of each SSP sector's
    investment in each economic sector, multiplier (jobs per million USD) x
    investment (billion USD) x 1e3."""
    m = mult.rename(columns={"Economic Sector": "Economic.Sector", "Ssp Sector": "Ssp.Sector", "Total Jobs": "Total.Jobs"})
    walk = pd.DataFrame({"Ssp.Sector": list(CROSSWALK), "Sector": list(CROSSWALK.values())})
    m = m.merge(walk, on="Ssp.Sector")
    new = m.merge(costs, on="Sector")
    new["Total.Jobs"] = new["Total.Jobs"] * new["Investments"] * 1e3
    new = new.rename(columns={"Year1": "Year"})
    return new[["Sector", "Ssp.Sector", "Economic.Sector", "Total.Jobs", "Pathway", "Investments", "Year"]].sort_values(
        ["Sector", "Ssp.Sector", "Economic.Sector", "Pathway", "Year"]).reset_index(drop=True)


def direct_jobs_by_sector(detail: pd.DataFrame) -> pd.DataFrame:
    """[Economic.Sector, Pathway, Year, Total.Jobs] (direct_jobs_overtime.csv)."""
    out = detail.groupby(["Year", "Pathway", "Economic.Sector"], as_index=False)["Total.Jobs"].sum()
    return out[["Economic.Sector", "Pathway", "Year", "Total.Jobs"]]


def baseline_jobs(population: pd.DataFrame, shares: pd.DataFrame) -> pd.DataFrame:
    """[Economic.Sector, Year, Jobs, Pathway=Baseline]: working-age population
    (million) x labour force participation x (1 - unemployment) x the sector's
    share of employment."""
    pop = population.merge(_linear(LABOR_FORCE_PARTICIPATION).rename("labor_force_participation").rename_axis("Year").reset_index(), on="Year")
    u = _linear(UNEMPLOYMENT_RATE).rename("unemployment_rate").rename_axis("Year").reset_index()
    pct = shares[["Economic.Sector"]].assign(Pct=shares["Employment.Share...."] / 100)
    labor = pop.merge(pct, how="cross").merge(u, on="Year")
    labor["Jobs"] = labor["Working_Age_Population_M"] * labor["labor_force_participation"] * (1 - labor["unemployment_rate"]) * labor["Pct"] * 1e6
    return labor[["Economic.Sector", "Year", "Jobs"]].assign(Pathway=BASELINE)


def jobs_overtime(baseline: pd.DataFrame, direct: pd.DataFrame, population: pd.DataFrame, pathway: str = LOW_EMISSIONS) -> pd.DataFrame:
    """[Economic.Sector, Year, Jobs, Pathway] (total_jobs_overtime.csv): the
    baseline, then with `pathway`'s direct jobs either reallocated (Low
    Emissions: the same total jobs as the baseline, in the shares the added
    jobs give) or added (Low Emissions-Expansionary)."""
    d = direct[direct["Pathway"] == pathway][["Economic.Sector", "Year", "Total.Jobs"]]
    both = baseline[["Economic.Sector", "Year", "Jobs"]].merge(d, on=["Economic.Sector", "Year"])
    added = both["Jobs"] + both["Total.Jobs"]

    share = added / added.groupby(both["Year"]).transform("sum")
    lfp = _linear(LABOR_FORCE_PARTICIPATION)
    u = _linear(UNEMPLOYMENT_RATE)
    wap = population.set_index("Year")["Working_Age_Population_M"]
    year = both["Year"]
    realloc = both[["Economic.Sector", "Year"]].assign(
        Jobs=wap.reindex(year).to_numpy() * lfp.reindex(year).to_numpy() * (1 - u.reindex(year).to_numpy()) * share.to_numpy() * 1e6,
        Pathway=REALLOCATION,
    )
    expan = both[["Economic.Sector", "Year"]].assign(Jobs=added.to_numpy(), Pathway=EXPANSIONARY)
    out = pd.concat([baseline, realloc.sort_values(["Year", "Economic.Sector"]), expan.sort_values(["Economic.Sector", "Year"])], ignore_index=True)
    return out[["Economic.Sector", "Year", "Jobs", "Pathway"]]


# ---------------------------------------------------------------------------
# The whole process
# ---------------------------------------------------------------------------

FILES = {
    "jobs_demand": "jobs_demand_egypt.csv",
    "multiplier": "total_jobs_multiplier.csv",
    "technical_cost": "technical_cost.csv",
    "direct_detail": "direct_jobs_overtime_ippc_detail.csv",
    "direct": "direct_jobs_overtime.csv",
    "total": "total_jobs_overtime.csv",
}


def build(cb_data: pd.DataFrame, inputs_dir: Union[str, pathlib.Path] = INPUTS_DIR,
          pathways: Optional[Dict[str, str]] = None) -> Dict[str, pd.DataFrame]:
    """Every table of the process (keys of FILES) from the pathways' cb_data and
    the inputs (resources/jobs/inputs: input-output results, population,
    employment shares)."""
    inputs_dir = pathlib.Path(inputs_dir)
    demand = jobs_demand(pd.read_csv(inputs_dir / IO_RESULTS))
    mult = multiplier(demand)
    costs = technical_cost(cb_data, pathways=pathways)
    detail = direct_jobs(mult, costs)
    direct = direct_jobs_by_sector(detail)
    population = pd.read_csv(inputs_dir / POPULATION)
    base = baseline_jobs(population, pd.read_csv(inputs_dir / SECTOR_SHARES))
    return {
        "jobs_demand": demand, "multiplier": mult, "technical_cost": costs,
        "direct_detail": detail, "direct": direct, "total": jobs_overtime(base, direct, population),
    }


def write(tables: Dict[str, pd.DataFrame], out_dir: Union[str, pathlib.Path] = DATA_DIR) -> None:
    """The tables as the process writes them (R's write.csv: quoted text, 15
    significant digits; jobs_demand with its row numbers)."""
    out_dir = pathlib.Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for key, df in tables.items():
        path = out_dir / FILES[key]
        if key == "jobs_demand":
            df.rename_axis("").to_csv(path, quoting=csv.QUOTE_NONNUMERIC, float_format="%.15g")
        elif key in ("multiplier", "technical_cost"):  # exported by Tableau, unquoted
            df.to_csv(path, index=False, float_format="%.15g")
        else:
            df.to_csv(path, index=False, quoting=csv.QUOTE_NONNUMERIC, float_format="%.15g")
    load.cache_clear()


# ---------------------------------------------------------------------------
# The page's data
# ---------------------------------------------------------------------------

@functools.lru_cache(maxsize=1)
def load(data_dir: Union[str, pathlib.Path] = DATA_DIR) -> Dict[str, pd.DataFrame]:
    """The tables in `data_dir` (keys of FILES; missing files left out)."""
    data_dir = pathlib.Path(data_dir)
    return {k: pd.read_csv(data_dir / f) for k, f in FILES.items() if (data_dir / f).exists()}


def investment_group(ssp_sector: str) -> str:
    """'energy' or 'non_energy' investments (ENERGY_SECTORS)."""
    return "energy" if ssp_sector in ENERGY_SECTORS else "non_energy"

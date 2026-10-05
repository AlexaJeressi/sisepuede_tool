"""Emissions from a run's output, grouped for the results pages.

Two levels:
- by subsector: the model's own `emission_co2e_subsector_total_<abv>` fields;
- detail: every `emission_co2e_<gas>_<abv>_<category>` field labelled with a
  mid-level `detail` group (e.g. Transportation -> Road / Rail / Aviation) and a
  gas group (CO2 / CH4 / N2O / F-gases).

The detail rules, gas groups and double-counting exclusions are ported from
the Egypt repo (ssp_egypt, ssp_modeling/notebooks/shared_scripts/
tableau_postprocessing.py, branch btr_invent). With the double-counted fields
dropped, the detail fields add up to the subsector totals; a category that
matches no rule is labelled "Other" rather than dropped, so the totals still
add up.
"""

import functools
import re
from typing import Dict, Iterable, List, Optional, Tuple

import pandas as pd

YEAR_0 = 2015  # time_period 0

SUBSECTORS: Dict[str, Tuple[str, str]] = {
    "agrc": ("AFOLU", "Agriculture"),
    "frst": ("AFOLU", "Forest"),
    "lndu": ("AFOLU", "Land use"),
    "lsmm": ("AFOLU", "Manure management"),
    "lvst": ("AFOLU", "Livestock"),
    "soil": ("AFOLU", "Soil management"),
    "wali": ("Circular Economy", "Liquid waste"),
    "waso": ("Circular Economy", "Solid waste"),
    "trww": ("Circular Economy", "Wastewater treatment"),
    "ccsq": ("Energy", "Carbon capture"),
    "enfu": ("Energy", "Energy fuels"),
    "enst": ("Energy", "Energy storage"),
    "entc": ("Energy", "Electricity & fuel production"),
    "fgtv": ("Energy", "Fugitive emissions"),
    "inen": ("Energy", "Industrial energy"),
    "scoe": ("Energy", "Buildings & other combustion"),
    "trns": ("Energy", "Transportation"),
    "trde": ("Energy", "Transportation demand"),
    "ippu": ("IPPU", "Industrial processes (IPPU)"),
    "econ": ("Socioeconomic", "Economy"),
    "gnrl": ("Socioeconomic", "General"),
}

SECTOR_ORDER = ["Energy", "IPPU", "AFOLU", "Circular Economy"]

# ordered category prefixes (after stripping the accounting prefixes)
DETAIL_RULES: Dict[str, Tuple[Tuple[str, str], ...]] = {
    "agrc": (
        ("anaerobicdom_rice", "Rice cultivation"),
        ("biomass_burning", "Biomass burning"),
        ("residue_and_biomass_burning", "Biomass burning"),
        ("crop_residues", "Crop residues"),
        ("residue_", "Crop residues"),
        ("biomass_", "Crop biomass"),
        ("woody_biomass", "Crop biomass"),
    ),
    "ccsq": (("direct_air_capture", "Direct air capture"),),
    "entc": (
        ("generation_pp_", "Electricity generation"),
        ("mining_and_extraction_", "Fuel extraction"),
        ("processing_and_refinement_", "Fuel processing & refining"),
    ),
    "fgtv": (
        ("dtp_", "Distribution, transmission & processing"),
        ("flaring_", "Flaring"),
        ("venting_", "Venting"),
    ),
    "frst": (
        ("forest_fires", "Forest fires"),
        ("decomposition", "Forest decomposition"),
        ("fuelwood_removals", "Fuelwood removals"),
        ("harvested_wood_products", "Harvested wood products"),
        ("methane_", "Forest methane"),
        ("sequestration_", "Forest sequestration"),
    ),
    "inen": (
        ("recycled_", "Recycling"),
        ("agriculture_and_livestock", "Agriculture & livestock"),
        ("mining", "Mining"),
        ("cement", "Manufacturing"),
        ("chemicals", "Manufacturing"),
        ("electronics", "Manufacturing"),
        ("glass", "Manufacturing"),
        ("lime_and_carbonite", "Manufacturing"),
        ("metals", "Manufacturing"),
        ("other_product_manufacturing", "Manufacturing"),
        ("paper", "Manufacturing"),
        ("plastic", "Manufacturing"),
        ("rubber_and_leather", "Manufacturing"),
        ("textiles", "Manufacturing"),
        ("wood", "Manufacturing"),
    ),
    "ippu": (
        ("production_", "Industrial production"),
        ("product_use_", "Product use"),
    ),
    "lndu": (
        ("conversion_", "Land use conversion"),
        ("biomass_sequestration_", "Biomass sequestration"),
        ("drained_organic_soils_", "Drained organic soils"),
        ("wetlands", "Wetlands"),
    ),
    "lsmm": (
        ("direct_", "Manure N2O (direct)"),
        ("indirect_", "Manure N2O (indirect)"),
        ("anaerobic_digester", "Manure CH4"),
        ("anaerobic_lagoon", "Manure CH4"),
        ("composting", "Manure CH4"),
        ("daily_spread", "Manure CH4"),
        ("deep_bedding", "Manure CH4"),
        ("dry_lot", "Manure CH4"),
        ("incineration", "Manure CH4"),
        ("liquid_slurry", "Manure CH4"),
        ("paddock_pasture_range", "Manure CH4"),
        ("poultry_manure", "Manure CH4"),
        ("storage_solid", "Manure CH4"),
    ),
    "lvst": (("entferm_", "Enteric fermentation"),),
    "scoe": (
        ("residential", "Residential"),
        ("commercial_municipal", "Commercial & municipal"),
        ("other_se", "Other stationary"),
    ),
    "soil": (
        ("fertilizer", "Synthetic & organic inputs"),
        ("urea_use", "Synthetic & organic inputs"),
        ("lime_use", "Synthetic & organic inputs"),
        ("soc_mineral_soils", "Mineral soils"),
        ("mineral_soils", "Mineral soils"),
        ("organic_soils", "Organic soils"),
        ("paddock_pasture_range", "Grazing"),
    ),
    "trns": (
        ("road_", "Road"),
        ("public", "Road"),
        ("powered_bikes", "Road"),
        ("human_powered", "Non-motorised"),
        ("rail_", "Rail"),
        ("aviation", "Aviation"),
        ("water_borne", "Water-borne"),
    ),
    "trww": (
        ("treated_", "Treated wastewater"),
        ("untreated_", "Untreated wastewater"),
    ),
    "waso": (
        ("landfilled_", "Landfill"),
        ("open_dump_", "Open dump"),
        ("compost_", "Composting"),
        ("biogas_", "Anaerobic digestion"),
        ("incineration", "Incineration"),
    ),
}

# fields that restate others from another angle (summing them double counts):
# electricity re-attributed to the consuming sector, and the land-use
# "converted away from type" roll-ups of the <from>_to_<to> pairs. The installed
# sisepuede names the latter `conversion_{agb,bgb}_away_`.
DOUBLE_COUNTING_PATTERNS = (
    "_entc_generation_for_",
    "_lndu_conversion_away_",
    "_lndu_conversion_agb_away_",
    "_lndu_conversion_bgb_away_",
)
# biogenic CO2 that the model reports but leaves out of the subsector totals
# (checked against emission_co2e_subsector_total_* on an Egypt run)
EXCLUDED_PATTERNS = ("_co2_inen_bmass_", "_co2_scoe_bmass_")
_ACCOUNTING_PREFIXES = ("nbmass_", "bmass_", "fuel_")
_TOTAL_PREFIX = "emission_co2e_subsector_total_"
_FIELD_RE = re.compile(r"^emission_co2e_(?P<gas>.+?)_(?P<sub>" + "|".join(SUBSECTORS) + r")_(?P<cat>.+)$")

GAS_GROUPS = ["CO2", "CH4", "N2O", "F-gases"]


def gas_group(gas: str) -> str:
    g = str(gas).upper()
    return g if g in ("CO2", "CH4", "N2O") else "F-gases"


def subsector_label(abv: str) -> str:
    return SUBSECTORS.get(abv, ("", abv))[1]


def sector_of(abv: str) -> str:
    return SUBSECTORS.get(abv, ("Other", abv))[0]


def detail_of(abv: str, category: str) -> str:
    rules = DETAIL_RULES.get(abv)
    if not rules:
        return subsector_label(abv)
    for prefix in _ACCOUNTING_PREFIXES:
        if category.startswith(prefix):
            category = category[len(prefix) :]
            break
    for marker, label in rules:
        if category.startswith(marker):
            return label
    return "Other"


@functools.lru_cache(maxsize=8)
def _classify(fields: Tuple[str, ...]) -> pd.DataFrame:
    rows = []
    for f in fields:
        if not f.startswith("emission_co2e_") or f.startswith(_TOTAL_PREFIX):
            continue
        if any(p in f for p in DOUBLE_COUNTING_PATTERNS + EXCLUDED_PATTERNS):
            continue
        m = _FIELD_RE.match(f)
        if m is None:
            continue
        abv = m.group("sub")
        rows.append(
            {
                "field": f,
                "subsector_abv": abv,
                "gas": m.group("gas"),
                "gas_group": gas_group(m.group("gas")),
                "detail": detail_of(abv, m.group("cat")),
            }
        )
    return pd.DataFrame(rows, columns=["field", "subsector_abv", "gas", "gas_group", "detail"])


def classify_fields(fields: Iterable[str]) -> pd.DataFrame:
    """field, subsector_abv, gas, gas_group, detail -- one row per detail emission field."""
    return _classify(tuple(fields))


def _years(df: pd.DataFrame) -> pd.Series:
    return df["time_period"].astype(int) + YEAR_0


def by_subsector(df_output: pd.DataFrame) -> pd.DataFrame:
    """Long: year, subsector_abv, subsector, sector, value (MtCO2e)."""
    cols = [c for c in df_output.columns if c.startswith(_TOTAL_PREFIX)]
    wide = df_output[cols].copy()
    wide.columns = [c[len(_TOTAL_PREFIX) :] for c in cols]
    wide["year"] = _years(df_output).values
    out = wide.melt(id_vars="year", var_name="subsector_abv", value_name="value")
    out["subsector"] = out["subsector_abv"].map(subsector_label)
    out["sector"] = out["subsector_abv"].map(sector_of)
    return out


def detail(df_output: pd.DataFrame, subsector_abv: Optional[str] = None) -> pd.DataFrame:
    """Long: year, subsector_abv, detail, gas_group, gas, field, value (MtCO2e)."""
    cls = classify_fields(df_output.columns)
    if subsector_abv is not None:
        cls = cls[cls["subsector_abv"] == subsector_abv]
    if cls.empty:
        return pd.DataFrame(columns=["year", "subsector_abv", "detail", "gas_group", "gas", "field", "value"])
    wide = df_output[cls["field"].tolist()].copy()
    wide["year"] = _years(df_output).values
    out = wide.melt(id_vars="year", var_name="field", value_name="value").merge(cls, on="field")
    return out[["year", "subsector_abv", "detail", "gas_group", "gas", "field", "value"]]


def net_total(df_output: pd.DataFrame) -> pd.Series:
    """Net emissions by year (MtCO2e)."""
    s = by_subsector(df_output).groupby("year")["value"].sum()
    return s


def kpis(net_by_pathway: Dict[str, pd.Series], bau_key: str, years: Tuple[int, ...] = (2030, 2050), cum_from: int = 2025) -> List[dict]:
    """Per pathway: net in each of `years`, % vs BAU, cumulative avoided vs BAU from `cum_from` on."""
    bau = net_by_pathway.get(bau_key)
    out = []
    for key, s in net_by_pathway.items():
        row = {"key": key}
        for y in years:
            v = float(s.get(y, float("nan")))
            row[f"net_{y}"] = v
            if bau is not None and key != bau_key and y in bau.index and bau[y]:
                row[f"pct_{y}"] = (v / float(bau[y]) - 1) * 100
            else:
                row[f"pct_{y}"] = None
        if bau is not None and key != bau_key:
            common = [y for y in s.index if y >= cum_from and y in bau.index]
            row["avoided_cum"] = float((bau[common] - s[common]).sum())
        else:
            row["avoided_cum"] = None
        out.append(row)
    return out

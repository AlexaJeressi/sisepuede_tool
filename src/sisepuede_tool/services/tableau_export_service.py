"""Tableau download: the CSVs the Egypt Tableau workbook reads, in the same
columns as ssp_egypt/ssp_modeling/tableau/data/tool_pathways:

  - emissions_egypt.csv                 emissions, SISEPUEDE taxonomy
  - drivers_egypt.csv                   driver variables
  - cb_data.csv                         costs and benefits (long, per variable)
  - tableau_levers_table_complete.csv   transformer ramps by pathway, with
                                        descriptions and stakeholder names

Ported from ssp_egypt notebooks/shared_scripts/tableau_postprocessing.py and
cost_benefits_pipeline.py (postprocess_tool_pathways.py), reading the tool's
runs instead of a run directory: one baseline, every pathway that ran on it.
Model values only, every model year from 2015: the baselines are calibrated
to 2015 alone, so the notebooks' inventory history (NIR 2015-2022), their
level adjustment to it and the GDP history rows are left out, and every
emission field is kept (the notebooks keep only the fields with an inventory
category, to meet the NIR).
There is no primary/design/future dimension here, so primary_id = strategy_id
and design_id = future_id = 0. The checks that raise in the notebook scripts
only log here, so a download never fails on them.

Reference tables are copies from ssp_egypt in resources/tableau/.
"""

import io
import logging
import re
import types
import zipfile
from typing import Dict, Iterable, List, Optional

import numpy as np
import pandas as pd

from sisepuede_tool import config

logger = logging.getLogger(__name__)

RESOURCES_DIR = config.SISEPUEDE_TOOL_PACKAGE_DIR / "resources" / "tableau"
TAXONOMY_PATH = RESOURCES_DIR / "driver_variables_taxonomy_20251013.csv"
DESCRIPTIONS_PATH = RESOURCES_DIR / "ssp_descriptions.csv"
STAKEHOLDER_CODES_PATH = RESOURCES_DIR / "stakeholder_codes.csv"

ISO_CODE3 = "EGY"
BASE_STRATEGY_ID = 0
YEAR_0 = 2015


# ---------------------------------------------------------------------------
# SISEPUEDE taxonomy (tableau_postprocessing.py)
# ---------------------------------------------------------------------------

SSP_SUBSECTORS: Dict[str, tuple] = {
    "agrc": ("AFOLU", "Agriculture"),
    "frst": ("AFOLU", "Forest"),
    "lndu": ("AFOLU", "Land Use"),
    "lsmm": ("AFOLU", "Livestock Manure Management"),
    "lvst": ("AFOLU", "Livestock"),
    "soil": ("AFOLU", "Soil Management"),
    "wali": ("Circular Economy", "Liquid Waste"),
    "waso": ("Circular Economy", "Solid Waste"),
    "trww": ("Circular Economy", "Wastewater Treatment"),
    "ccsq": ("Energy", "Carbon Capture and Sequestration"),
    "enfu": ("Energy", "Energy Fuels"),
    "enst": ("Energy", "Energy Storage"),
    "entc": ("Energy", "Energy Technology"),
    "fgtv": ("Energy", "Fugitive Emissions"),
    "inen": ("Energy", "Industrial Energy"),
    "scoe": ("Energy", "Stationary Combustion and Other Energy"),
    "trns": ("Energy", "Transportation"),
    "trde": ("Energy", "Transportation Demand"),
    "ippu": ("IPPU", "IPPU"),
    "econ": ("Socioeconomic", "Economy"),
    "gnrl": ("Socioeconomic", "General"),
}

# ordered prefixes matched against the category (accounting prefixes stripped)
SUBSECTOR_DETAIL_RULES: Dict[str, tuple] = {
    "agrc": (
        ("anaerobicdom_rice", "Rice Cultivation"),
        ("biomass_burning", "Biomass Burning"),
        ("residue_and_biomass_burning", "Biomass Burning"),
        ("crop_residues", "Crop Residues"),
        ("residue_emit_", "Crop Residues"),
        ("residue_sequestration_", "Crop Residues"),
        ("biomass_", "Crop Biomass"),
        ("woody_biomass_", "Crop Biomass"),
    ),
    "ccsq": (("direct_air_capture", "Direct Air Capture"),),
    "entc": (
        ("generation_pp_", "Electricity Generation"),
        ("mining_and_extraction_", "Fuel Extraction"),
        ("processing_and_refinement_", "Fuel Processing and Refining"),
    ),
    "fgtv": (
        ("dtp_", "Distribution, Transmission and Processing"),
        ("flaring_", "Flaring"),
        ("venting_", "Venting"),
    ),
    "frst": (
        ("forest_fires", "Forest Fires"),
        ("harvested_wood_products", "Harvested Wood Products"),
        ("methane_", "Forest Methane"),
        ("sequestration_", "Forest Sequestration"),
        ("decomposition_", "Forest Decomposition"),
        ("fuelwood_removals", "Fuelwood Removals"),
    ),
    "inen": (
        ("recycled_", "Recycling"),
        ("agriculture_and_livestock", "Agriculture and Livestock"),
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
        ("production_", "Industrial Production"),
        ("product_use_", "Product Use"),
    ),
    "lndu": (
        ("conversion_", "Land Use Conversion"),
        ("biomass_sequestration_", "Biomass Sequestration"),
        ("drained_organic_soils_", "Drained Organic Soils"),
        ("wetlands", "Wetlands"),
    ),
    "lsmm": (
        ("direct_", "Manure N2O (Direct)"),
        ("indirect_", "Manure N2O (Indirect)"),
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
    "lvst": (("entferm_", "Enteric Fermentation"),),
    "scoe": (
        ("residential", "Residential"),
        ("commercial_municipal", "Commercial and Municipal"),
        ("other_se", "Other Stationary"),
    ),
    "soil": (
        ("fertilizer", "Synthetic and Organic Inputs"),
        ("urea_use", "Synthetic and Organic Inputs"),
        ("lime_use", "Synthetic and Organic Inputs"),
        ("soc_mineral_soils", "Mineral Soils"),
        ("mineral_soils", "Mineral Soils"),
        ("organic_soils", "Organic Soils"),
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
        ("treated_", "Treated Wastewater"),
        ("untreated_", "Untreated Wastewater"),
    ),
    "waso": (
        ("landfilled_", "Landfill"),
        ("open_dump_", "Open Dump"),
        ("compost_", "Composting"),
        ("biogas_", "Anaerobic Digestion"),
        ("incineration", "Incineration"),
    ),
}

_ACCOUNTING_PREFIXES = ("nbmass_", "bmass_", "fuel_")

EMISSION_FIELD_RE = re.compile(r"^emission_co2e_(?P<gas>.+?)_(?P<sub>" + "|".join(SSP_SUBSECTORS) + r")_(?P<cat>.+)$")

# fields that restate others (summing them double counts)
DOUBLE_COUNTING_PATTERNS = (
    "_entc_generation_for_",
    "_lndu_conversion_away_",
    "_lndu_conversion_agb_away_",
    "_lndu_conversion_bgb_away_",
)
BIOGENIC_CO2_RE = re.compile(r"^emission_co2e_co2_[a-z]+_bmass_")


def _strip_accounting_prefix(category: str) -> str:
    for prefix in _ACCOUNTING_PREFIXES:
        if category.startswith(prefix):
            return category[len(prefix):]
    return category


def subsector_detail(code: str, category: str, subsector: str) -> str:
    """Mid-level grouping; the subsector name when no rule matches."""
    rules = SUBSECTOR_DETAIL_RULES.get(code)
    if not rules:
        return subsector
    stripped = _strip_accounting_prefix(category)
    for marker, label in rules:
        if stripped.startswith(marker):
            return label
    logger.warning("tableau export: no subsector_detail rule for %s %s", code, category)
    return subsector


def gas_group(gas: str) -> str:
    g = str(gas).upper()
    return g if g in ("CO2", "CH4", "N2O") else "F-gases"


def _taxonomy() -> pd.DataFrame:
    return pd.read_csv(TAXONOMY_PATH).drop_duplicates(subset=["field"]).set_index("field")


def _subsector_totals(df: pd.DataFrame) -> List[str]:
    return [c for c in df.columns if c.startswith("emission_co2e_subsector_total_")]


def _biogenic_in_totals(df: pd.DataFrame, fields: List[str]) -> bool:
    """True if the subsector totals include the biogenic CO2 fields (sisepuede
    1.4), False if they leave them out (2.0): whichever reconciles better."""
    biogenic = [f for f in fields if BIOGENIC_CO2_RE.match(f)]
    totals = _subsector_totals(df)
    if not biogenic or not totals:
        return True
    want = df[totals].sum(axis=1)
    diff_with = float((df[fields].sum(axis=1) - want).abs().max())
    diff_without = float((df[[f for f in fields if f not in biogenic]].sum(axis=1) - want).abs().max())
    return diff_with <= diff_without


def _check_reconciles(df: pd.DataFrame, fields: List[str], tol: float = 1e-4) -> None:
    totals = _subsector_totals(df)
    if not totals:
        return
    worst = float((df[fields].sum(axis=1) - df[totals].sum(axis=1)).abs().max())
    if worst > tol:
        logger.warning("tableau export: emission fields off the subsector totals by up to %.6f MtCO2e", worst)


BASE_NAME = "Strategy TX:BASE"
BASE_CODE = "BASE"


def tableau_code(strategy_id: int, name: str) -> str:
    """Strategy code as in the notebook runs: PFLO:<name> (PFLO:NDC, PFLO:LEP),
    BASE for business as usual. The tool's own codes (STRAT_<id>) mean nothing
    to the workbook."""
    if strategy_id == BASE_STRATEGY_ID:
        return BASE_CODE
    return "PFLO:" + re.sub(r"[^A-Z0-9]+", "_", str(name).upper()).strip("_")


def strategy_table(strategies_map, strategy_ids: Iterable[int]) -> pd.DataFrame:
    """strategy_id, strategy_code, strategy (name) with the workbook's codes and
    BAU's notebook name."""
    rows = []
    for sid in strategy_ids:
        name = strategies_map[sid].strategy.name or str(sid)
        rows.append({"strategy_id": sid, "strategy_code": tableau_code(sid, name), "strategy": BASE_NAME if sid == BASE_STRATEGY_ID else name})
    return pd.DataFrame(rows, columns=["strategy_id", "strategy_code", "strategy"])


def recode_cb(cb_data: pd.DataFrame, attr_strat: pd.DataFrame) -> pd.DataFrame:
    """cb_data with the workbook's strategy codes (cb_table names them by the
    codes the cost-benefit run used)."""
    codes = dict(zip(attr_strat["strategy_id"], attr_strat["strategy_code"]))
    out = cb_data.copy()
    new = out["strategy_id"].map(codes)
    out["strategy_code"] = new.fillna(out["strategy_code"])
    out["strategy"] = out["strategy_code"]
    return out


def _run_columns(attr_strat: pd.DataFrame) -> pd.DataFrame:
    """strategy_id -> primary_id, design_id, future_id, strategy (ATTRIBUTE_PRIMARY
    and ATTRIBUTE_STRATEGY of a sisepuede run)."""
    out = attr_strat[["strategy_id", "strategy"]].copy()
    out["primary_id"] = out["strategy_id"]
    out["design_id"] = 0
    out["future_id"] = 0
    return out


# ---------------------------------------------------------------------------
# Emissions
# ---------------------------------------------------------------------------


def emissions_table(df_wide: pd.DataFrame, attr_strat: pd.DataFrame) -> pd.DataFrame:
    """emissions_egypt.csv from the wide input+output frame of one baseline
    (cost_benefit_service.build_wide_results)."""
    region = str(df_wide["region"].iloc[0])
    fields = [
        c for c in df_wide.columns
        if c.startswith("emission_co2e_")
        and "_subsector_total_" not in c
        and not any(p in c for p in DOUBLE_COUNTING_PATTERNS)
        and EMISSION_FIELD_RE.match(c)
    ]
    if not _biogenic_in_totals(df_wide, fields):
        fields = [c for c in fields if not BIOGENIC_CO2_RE.match(c)]
    _check_reconciles(df_wide, fields)

    long_df = df_wide[["strategy_id", "time_period"] + fields].melt(
        id_vars=["strategy_id", "time_period"], var_name="variable", value_name="value"
    )

    parsed = pd.DataFrame({"variable": fields})
    m = [EMISSION_FIELD_RE.match(f) for f in fields]
    parsed["gas"] = [x.group("gas") for x in m]
    code = [x.group("sub") for x in m]
    parsed["category"] = [x.group("cat") for x in m]
    parsed["sector"] = [SSP_SUBSECTORS[c][0] for c in code]
    parsed["subsector"] = [SSP_SUBSECTORS[c][1] for c in code]
    parsed["subsector_detail"] = [subsector_detail(c, cat, s) for c, cat, s in zip(code, parsed["category"], parsed["subsector"])]
    tax = _taxonomy()
    for col in ("model_variable", "category_value", "gas_name"):
        parsed[col] = parsed["variable"].map(tax[col])
    parsed["Gas"] = parsed["gas"].str.upper()
    parsed["gas_group"] = parsed["Gas"].map(gas_group)

    long_df = long_df.merge(parsed, on="variable", how="left")
    long_df["Year"] = long_df["time_period"] + YEAR_0
    long_df = long_df.drop(columns=["time_period"]).merge(_run_columns(attr_strat), on="strategy_id", how="left")
    long_df["ID"] = long_df["subsector"] + ":" + long_df["Gas"]
    long_df["Code"] = ISO_CODE3
    long_df["Country"] = region
    long_df["source"] = "SISEPUEDE"

    out_cols = [
        "strategy_id", "primary_id", "design_id", "future_id", "strategy",
        "ID", "sector", "subsector", "subsector_detail", "category", "variable", "model_variable",
        "category_value", "gas", "Gas", "gas_group", "gas_name", "Year", "value",
        "Code", "Country", "source",
    ]
    out = long_df[out_cols].copy()

    # columns the workbook reads: the value before the notebooks' level
    # adjustment to the NIR (none here), `Contry` (sic) and the smoothed value
    # (no smoothing here)
    out["value_original"] = out["value"]
    out["Contry"] = out["Country"]
    out["value_hp"] = out["value"]
    return out


# ---------------------------------------------------------------------------
# Drivers
# ---------------------------------------------------------------------------

_ENERGY_KEYWORDS = {
    "ccsq": "Carbon Capture and Sequestration",
    "inen": "Industrial Energy",
    "entc": "Power(electricity/heat)",
    "trns": "Transportation",
    "scoe": "Buildings",
}
DRIVERS_COLUMNS = [
    "variable", "strategy_id", "primary_id", "value", "sector", "subsector",
    "model_variable", "category_value", "category_name", "gas", "gas_name",
    "Year", "design_id", "future_id", "strategy", "Units", "Data_Type",
    "iso_code3", "Country", "output_type", "energy_subsector",
]


def drivers_table(df_wide: pd.DataFrame, attr_strat: pd.DataFrame) -> pd.DataFrame:
    """drivers_egypt.csv: every taxonomy variable, every model year."""
    region = str(df_wide["region"].iloc[0])
    tax = _taxonomy().reset_index().rename(columns={"field": "variable"})
    fields = [c for c in tax["variable"] if c in df_wide.columns]
    long_df = df_wide[["strategy_id", "time_period"] + fields].melt(
        id_vars=["strategy_id", "time_period"], var_name="variable", value_name="value"
    )
    long_df = long_df.merge(tax, on="variable", how="left")
    long_df["Year"] = long_df["time_period"] + YEAR_0
    long_df = long_df.drop(columns=["time_period"])
    long_df = long_df.merge(_run_columns(attr_strat), on="strategy_id", how="left")
    long_df["Units"] = "NA"
    long_df["Data_Type"] = "sisepuede simulation"
    long_df["iso_code3"] = ISO_CODE3
    long_df["Country"] = region
    long_df["output_type"] = "drivers"
    long_df["gas"] = np.nan

    long_df["energy_subsector"] = pd.Series(pd.NA, index=long_df.index, dtype=object)
    energy = long_df["variable"].str.contains("energy", regex=False, na=False)
    es = pd.Series("TBD", index=long_df.index, dtype=object)
    for kw, label in _ENERGY_KEYWORDS.items():
        es = es.where(~long_df["variable"].str.contains(kw, regex=False, na=False), label)
    long_df.loc[energy, "energy_subsector"] = es[energy]

    for c in DRIVERS_COLUMNS:
        if c not in long_df.columns:
            long_df[c] = np.nan
    return long_df[DRIVERS_COLUMNS].reset_index(drop=True)


# ---------------------------------------------------------------------------
# Costs and benefits (cost_benefits_pipeline._reshape_for_tableau)
# ---------------------------------------------------------------------------


def cb_table(
    results_shifted: pd.DataFrame,
    df_wide: pd.DataFrame,
    strategy_id_map: Dict[str, int],
    primary_id_map: Dict[str, int],
) -> pd.DataFrame:
    """cb_data.csv from costs_benefits_ssp's results after cb_shift_costs (the
    same rows the tool's wrapper sums into its wide table)."""
    cb = results_shifted.copy()
    parts = cb["variable"].astype(str).str.split(":", n=4, expand=True)
    parts = parts.reindex(columns=range(5))
    parts.columns = ["name", "sector", "cb_type", "item_1", "item_2"]
    cb = pd.concat([cb, parts], axis=1)
    cb["value"] = cb["value"] / 1e9
    cb = cb[~cb["item_2"].astype(str).str.contains("shifted", na=False)]
    cb = cb[~cb["variable"].astype(str).str.contains("shifted2", na=False)]
    cb["Year"] = cb["time_period"] + YEAR_0
    cb["strategy_id"] = cb["strategy_code"].map(strategy_id_map)
    cb["primary_id"] = cb["strategy_code"].map(primary_id_map)
    cb["strategy"] = cb["strategy_code"]
    cb["ids"] = cb["variable"].astype(str) + ":" + cb["strategy_id"].astype(str)
    if "gdp_mmm_usd" in df_wide.columns:
        gdp = df_wide[["strategy_id", "time_period", "gdp_mmm_usd"]].drop_duplicates().rename(columns={"strategy_id": "primary_id"})
        cb = cb.merge(gdp, on=["primary_id", "time_period"], how="left")
    else:
        cb["gdp_mmm_usd"] = np.nan
    # ENTC technical costs with the wrong sign (the wrapper's TEMP PATCH)
    bad_sign = (cb["sector"] == "entc") & (cb["cb_type"] == "technical_cost") & (cb["value"] > 0)
    return cb[~bad_sign].reset_index(drop=True)


# ---------------------------------------------------------------------------
# Levers (sisepuede LeversImplementationTable + descriptions + stakeholder names)
# ---------------------------------------------------------------------------

_R_MAKE_NAMES_RENAME = {
    "Sector (output)": "Sector..output.",
    "Subsector (output)": "Subsector..output.",
    "Example government policies": "Example.government.policies",
}


class _StrategiesView:
    """Just enough of a sisepuede `Strategies` for LeversImplementationTable,
    over the tool's pathways (the tool never builds a `Strategies`)."""

    is_strategies = True

    def __init__(self, strategies_map, transformations_obj, model_attributes):
        from sisepuede.transformers import strategies as sst

        self._uuid = sst._MODULE_UUID
        self._map = strategies_map
        self.transformations = transformations_obj
        self.model_attributes = model_attributes

    def get_strategy(self, spec, stop_on_error: bool = False, **kwargs):
        # the tool's Strategy objects carry no transformation_specification
        entry = self._map[spec]
        return types.SimpleNamespace(
            code=tableau_code(spec, entry.strategy.name),
            transformation_specification="|".join(entry.transformation_codes),
            get_transformation_list=entry.strategy.get_transformation_list,
        )


def levers_table(strategy_ids: Iterable[int], strategies_map, transformations_obj, model_attributes) -> pd.DataFrame:
    """tableau_levers_table_complete.csv for the pathways (BAU left out). One
    `strategy_<code>` column per pathway; transformers without an entry in the
    descriptions / stakeholder tables are dropped (inner merges, as in the
    notebooks)."""
    import sisepuede.visualization.tables as svt

    sids = [s for s in strategy_ids if s != BASE_STRATEGY_ID and s in strategies_map]
    if not sids:
        return pd.DataFrame()
    view = _StrategiesView(strategies_map, transformations_obj, model_attributes)
    table = svt.LeversImplementationTable(view).build_table_for_strategies(sids)
    table["transformation_code"] = table["transformer_code"].str.replace("TFR:", "", regex=False)

    desp = pd.read_csv(DESCRIPTIONS_PATH)
    scodes = pd.read_csv(STAKEHOLDER_CODES_PATH).rename(columns=_R_MAKE_NAMES_RENAME)
    scodes["transformation_code"] = scodes["transformation_code"].str.replace("TX:", "", regex=False)
    merged = table.merge(desp, on="transformation_code", how="inner")
    return merged.merge(
        scodes[["transformation_code", "transformation_name_stakeholder", "Sector..output.", "Subsector..output.", "Example.government.policies"]],
        on="transformation_code",
        how="inner",
    )


# ---------------------------------------------------------------------------
# Zip
# ---------------------------------------------------------------------------


def tableau_zip(tables: Dict[str, Optional[pd.DataFrame]]) -> bytes:
    """{file name: frame}; a None frame is left out."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, df in tables.items():
            if df is not None:
                zf.writestr(name, df.to_csv(index=False))
    return buf.getvalue()

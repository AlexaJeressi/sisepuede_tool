"""Driver cards for the "Emissions & drivers" page.

The default cards are curated in resources/results_groups.yaml (context cards
plus one area per group of emitting subsectors). Users can add more cards in
advanced mode from any model variable (`custom_card`). This module resolves a
card to model fields and pulls its values out of run results, without any UI.
"""

import functools
import pathlib
import re
from typing import Dict, List, Optional, Tuple

import pandas as pd
import yaml

from sisepuede_tool.services.emissions_service import YEAR_0
from sisepuede_tool.services.labels import clean_label

VIEWS = ("total", "stacked", "share")

# fuel / technology categories -> plain names
_CATEGORY_NAMES = {
    "hydrocarbon_gas_liquids": "LPG / gas liquids",
    "pp_hydropower": "Hydropower",
    "pp_solar": "Solar",
    "pp_wind": "Wind",
    "pp_gas": "Natural gas",
    "pp_gas_ccs": "Natural gas + CCS",
    "pp_coal": "Coal",
    "pp_coal_ccs": "Coal + CCS",
    "pp_oil": "Oil",
    "pp_nuclear": "Nuclear",
    "pp_biomass": "Biomass",
    "pp_biogas": "Biogas",
    "pp_geothermal": "Geothermal",
    "pp_ocean": "Ocean",
    "pp_waste_incineration": "Waste incineration",
    "other_se": "Other stationary",
    "commercial_municipal": "Commercial & municipal",
    "private_and_public": "Urban (private & public)",
    "road_light": "Road, light duty",
    "road_heavy_freight": "Road, heavy freight",
    "road_heavy_regional": "Road, heavy regional",
    "rail_freight": "Rail, freight",
    "rail_passenger": "Rail, passenger",
    "powered_bikes": "Motorbikes",
    "human_powered": "Walking & cycling",
    "public": "Public transport",
    "water_borne": "Water-borne",
    "cattle_dairy": "Dairy cattle",
    "cattle_nondairy": "Other cattle",
    "forests_mangroves": "Mangroves",
    "forests_primary": "Primary forest",
    "forests_secondary": "Secondary forest",
    "ccs": "Carbon capture (CCS)",
}


def category_name(category: Optional[str]) -> str:
    if not category:
        return "Total"
    if category in _CATEGORY_NAMES:
        return _CATEGORY_NAMES[category]
    c = re.sub(r"^(fuel_|pp_)", "", category)
    return _CATEGORY_NAMES.get(c, c.replace("_", " ").capitalize())


def _variable_names(variables: List[str]) -> Dict[str, str]:
    """Short series names for several variables: their clean labels without the
    words they all share at the start (e.g. 'Treatment Fraction ', 'Total Waste ')."""
    labels = [clean_label(v) for v in variables]
    if len(labels) < 2:
        return dict(zip(variables, labels))
    words = [l.split(" ") for l in labels]
    n = 0
    while all(len(w) > n + 1 for w in words) and len({w[n] for w in words}) == 1:
        n += 1
    out = {}
    for v, w in zip(variables, words):
        name = " ".join(w[n:])
        out[v] = name[:1].upper() + name[1:]
    return out


def default_groups_path() -> pathlib.Path:
    import sisepuede_tool

    return pathlib.Path(sisepuede_tool.__file__).parent / "resources" / "results_groups.yaml"


@functools.lru_cache(maxsize=2)
def load_groups(path: Optional[str] = None) -> dict:
    data = yaml.safe_load(pathlib.Path(path or default_groups_path()).read_text())
    for card in data.get("context", []) + [c for a in data.get("areas", []) for c in a.get("cards", [])]:
        card.setdefault("series", "category")
        card.setdefault("view", "total")
        card.setdefault("scale", 1.0)
        card.setdefault("unit", "")
        card.setdefault("categories", None)
        card.setdefault("source", "output")
        card.setdefault("labels", {})
    return data


def area_for_subsector(groups: dict, subsector_abv: Optional[str]) -> Optional[dict]:
    for area in groups.get("areas", []):
        if subsector_abv in area.get("subsectors", []):
            return area
    return None


def split_cards_for_subsector(cards: List[dict], subsector_abv: Optional[str]) -> Tuple[List[dict], List[dict]]:
    """(cards that explain `subsector_abv`, the rest of the area). Untagged
    cards explain every subsector; if nothing matches, every card counts."""
    if not subsector_abv:
        return list(cards), []
    primary = [c for c in cards if not c.get("subsectors") or subsector_abv in c["subsectors"]]
    if not primary:
        return list(cards), []
    return primary, [c for c in cards if c not in primary]


def _match(category: Optional[str], patterns: Optional[List[str]]) -> bool:
    if not patterns:
        return True
    if category is None:
        return False
    for p in patterns:
        if p.endswith("*") and category.startswith(p[:-1]):
            return True
        if category == p:
            return True
    return False


def card_fields(card: dict, field_catalog: pd.DataFrame) -> pd.DataFrame:
    """field, variable, category, series -- the model fields a card plots."""
    cat = field_catalog[field_catalog["variable"].isin(card["variables"])]
    cat = cat[[_match(c, card.get("categories")) for c in cat["category"]]]
    names = _variable_names(card["variables"])
    out = cat[["field", "variable", "category"]].copy()
    if card["series"] == "variable":
        out["series"] = out["variable"].map(names)
    else:
        out["series"] = out["category"].map(category_name)
    labels = card.get("labels") or {}
    out["series"] = out["series"].map(lambda s: labels.get(s, s))
    return out.reset_index(drop=True)


def card_frame(card: dict, field_catalog: pd.DataFrame, run_result) -> pd.DataFrame:
    """Long [year, series, value] (scaled) for one run; empty if the run lacks the fields."""
    df = run_result.df_input if card["source"] == "input" else run_result.df_output
    fields = card_fields(card, field_catalog)
    if df is None or fields.empty:
        return pd.DataFrame(columns=["year", "series", "value"])
    present = fields[fields["field"].isin(df.columns)]
    if present.empty:
        return pd.DataFrame(columns=["year", "series", "value"])
    wide = df[present["field"].tolist()].copy()
    wide["year"] = df["time_period"].astype(int).values + YEAR_0
    long = wide.melt(id_vars="year", var_name="field", value_name="value").merge(present[["field", "series"]], on="field")
    out = long.groupby(["year", "series"], as_index=False, sort=False)["value"].sum()
    out["value"] = out["value"] * float(card["scale"])
    return out


def custom_card(variable: str, field_catalog: pd.DataFrame) -> dict:
    """A card for any model variable picked in advanced mode."""
    rows = field_catalog[field_catalog["variable"] == variable]
    is_input = bool(rows["is_input"].any()) if not rows.empty else False
    units = rows["units"].dropna().iloc[0] if not rows.empty and rows["units"].notna().any() else ""
    return {
        "key": "custom:" + variable,
        "title": clean_label(variable),
        "why": "Added by you (advanced).",
        "source": "input" if is_input else "output",
        "variables": [variable],
        "series": "category",
        "view": "stacked" if len(rows) > 1 else "total",
        "categories": None,
        "scale": 1.0,
        "unit": ", ".join(u.split(":")[-1].strip() for u in str(units).split(",")) if units else "",
        "custom": True,
    }

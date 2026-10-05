"""Costs & benefits for display: long format, plain categories, totals.

`costs_benefits_ssp` returns a wide frame (`df_cb`: strategy_id, time_period,
one column per cb variable, billions USD, relative to the reference strategy)
plus `df_attr_variable` (variable, sector, cb_type, item_1, item_2). Costs are
negative and benefits positive. Totals over 2025-2050, the benefit/cost ratio
and the net-positive year are computed here: not discounted by default, with
an optional discount rate (the package itself does no discounting).
"""

import functools
import pathlib
from typing import Dict, List, Optional

import pandas as pd

from sisepuede_tool.services.emissions_service import SUBSECTORS as SUBSECTORS_ABV
from sisepuede_tool.services.emissions_service import YEAR_0, subsector_label

# cb_type -> display category (order = legend order)
CATEGORIES: Dict[str, str] = {
    "technical_cost": "Technology capex & opex",
    "technical_savings": "O&M & technical savings",
    "fuel_cost": "Fuel costs & savings",
    "consumer_savings": "Consumer savings",
    "human_health": "Health & air quality",
    "air_pollution": "Health & air quality",
    "water_pollution": "Pollution avoided",
    "land_pollution": "Pollution avoided",
    "env_pollution": "Pollution avoided",
    "ecosystem_services": "Ecosystem services",
    "crop_value": "Crop & livestock output",
    "lvst_value": "Crop & livestock output",
    "ippu_value": "Industrial output",
    "congestion": "Congestion & road safety",
    "road_safety": "Congestion & road safety",
    "sector_specific": "Other sector-specific",
    "system_cost": "Other sector-specific",
}
CATEGORY_ORDER: List[str] = list(dict.fromkeys(CATEGORIES.values()))
OTHER = "Other"

DISCOUNT_RATES = (0, 3, 5, 7)  # 0 = not discounted (plain sum 2025-2050)
DEFAULT_RATE = 0.0  # not discounted by default, as in the team's usual C&B reporting; a rate is an advanced option


def rate_label(rate_pct: float) -> str:
    return "not discounted" if rate_pct == 0 else f"discounted at {rate_pct:g}% to {START_YEAR}"
START_YEAR = 2025  # the package shifts earlier costs into 2025


def category_of(cb_type: Optional[str]) -> str:
    return CATEGORIES.get(cb_type or "", OTHER)


@functools.lru_cache(maxsize=2)
def display_names(config_path: str) -> Dict[str, str]:
    """df_cb column name (cb_<sector>_<type>_...) -> display name from the C&B config workbook."""
    out: Dict[str, str] = {}
    try:
        sheets = pd.read_excel(config_path, sheet_name=["tx_table", "cost_factors"])
    except Exception:
        return out
    for df in sheets.values():
        if "output_display_name" not in df.columns:
            continue
        for name, label in zip(df["output_variable_name"], df["output_display_name"]):
            if isinstance(name, str) and isinstance(label, str):
                out.setdefault(name.replace(":", "_"), label)
    return out


_TYPE_LABELS = {
    "fuel_cost": "Fuel spending",
    "technical_cost": "Cost",
    "technical_savings": "Savings",
}


def _pretty(token: Optional[str]) -> str:
    if not isinstance(token, str) or token in ("", "X"):
        return ""
    if token in SUBSECTORS_ABV:
        return subsector_label(token)
    from sisepuede_tool.services.results_groups_service import category_name

    return category_name(token)


def generated_name(cb_type: Optional[str], item_1: Optional[str], item_2: Optional[str]) -> str:
    """Readable name from the variable's parts, e.g. fuel_cost / trns / gasoline ->
    'Fuel spending · Transportation · Gasoline'."""
    head = _TYPE_LABELS.get(cb_type or "", (cb_type or "Item").replace("_", " ").capitalize())
    parts = [x for x in (_pretty(item_1), _pretty(item_2)) if x]
    return " · ".join([head] + parts)


def to_long(df_cb: pd.DataFrame, df_attr_variable: pd.DataFrame, config_path: Optional[pathlib.Path] = None) -> pd.DataFrame:
    """[strategy_id, year, variable, display_name, sector, sector_label, cb_type, category, value_busd]."""
    value_cols = [c for c in df_cb.columns if c not in ("strategy_id", "time_period")]
    long = df_cb.melt(id_vars=["strategy_id", "time_period"], value_vars=value_cols, var_name="variable", value_name="value_busd")
    long["year"] = long["time_period"].astype(int) + YEAR_0
    attr = df_attr_variable.drop_duplicates("variable").set_index("variable")
    long["sector"] = long["variable"].map(attr["sector"]) if "sector" in attr else None
    long["cb_type"] = long["variable"].map(attr["cb_type"]) if "cb_type" in attr else None
    long["category"] = long["cb_type"].map(category_of)
    long["sector_label"] = long["sector"].map(lambda s: subsector_label(s) if isinstance(s, str) else OTHER)
    names = display_names(str(config_path)) if config_path else {}
    # The config's display name is missing for some variables and is a shared
    # placeholder for others (all 47 enfu fuel_cost items are "Fuel Cost bio
    # fuel_biogas"); those get a name built from the variable's parts instead.
    shown = {v: names.get(v) for v in value_cols}
    counts = pd.Series([n for n in shown.values() if n]).value_counts()
    for v, n in shown.items():
        if not n or counts.get(n, 0) > 1:
            row = attr.loc[v] if v in attr.index else None
            shown[v] = generated_name(
                row.get("cb_type") if row is not None else None,
                row.get("item_1") if row is not None else None,
                row.get("item_2") if row is not None else None,
            ) if row is not None else v
    long["display_name"] = long["variable"].map(shown)
    long["value_busd"] = long["value_busd"].fillna(0.0)
    cols = ["strategy_id", "year", "variable", "display_name", "sector", "sector_label", "cb_type", "category", "value_busd"]
    return long[cols]


def by_group(long: pd.DataFrame, strategy_id: int, group: str = "category") -> pd.DataFrame:
    """Wide by year: one column per group (category or sector_label), billions USD."""
    d = long[(long["strategy_id"] == strategy_id) & (long["year"] >= START_YEAR)]
    wide = d.pivot_table(index="year", columns=group, values="value_busd", aggfunc="sum", fill_value=0.0)
    order = CATEGORY_ORDER + [OTHER] if group == "category" else sorted(wide.columns)
    return wide[[c for c in order if c in wide.columns]]


def discount_factors(years, rate_pct: float, base_year: int = START_YEAR) -> pd.Series:
    years = pd.Index(years)
    return pd.Series([(1 + rate_pct / 100.0) ** -(y - base_year) for y in years], index=years)


def npv_summary(long: pd.DataFrame, strategy_id: int, rate_pct: float, group: str = "category") -> dict:
    """Net benefits 2025-2050 (billions USD; discounted to START_YEAR when
    rate_pct > 0, a plain sum when 0) of the net and of each group, the
    benefit/cost ratio, and the first year the annual net turns positive."""
    d = long[(long["strategy_id"] == strategy_id) & (long["year"] >= START_YEAR)]
    if d.empty:
        return {"net": 0.0, "benefits": 0.0, "costs": 0.0, "bcr": None, "net_positive_year": None, "by_group": {}}
    df = discount_factors(sorted(d["year"].unique()), rate_pct)
    d = d.assign(pv=d["value_busd"] * d["year"].map(df))
    per_var = d.groupby("variable")["pv"].sum()
    benefits = float(per_var[per_var > 0].sum())
    costs = float(-per_var[per_var < 0].sum())
    annual = d.groupby("year")["value_busd"].sum()
    positive = annual[annual > 0]
    by = d.groupby(group)["pv"].sum().sort_values(ascending=False)
    return {
        "net": float(per_var.sum()),
        "benefits": benefits,
        "costs": costs,
        "bcr": (benefits / costs) if costs > 0 else None,
        "net_positive_year": int(positive.index[0]) if not positive.empty else None,
        "by_group": {k: float(v) for k, v in by.items() if abs(v) > 1e-9},
    }


def items_npv(long: pd.DataFrame, strategy_id: int, rate_pct: float, category: Optional[str] = None) -> pd.DataFrame:
    """NPV per item (display_name), [display_name, category, sector_label, pv], largest |pv| first."""
    d = long[(long["strategy_id"] == strategy_id) & (long["year"] >= START_YEAR)]
    if category:
        d = d[d["category"] == category]
    if d.empty:
        return pd.DataFrame(columns=["display_name", "category", "sector_label", "pv"])
    df = discount_factors(sorted(d["year"].unique()), rate_pct)
    d = d.assign(pv=d["value_busd"] * d["year"].map(df))
    out = d.groupby(["display_name", "category", "sector_label"], as_index=False)["pv"].sum()
    out = out[out["pv"].abs() > 1e-6]
    return out.reindex(out["pv"].abs().sort_values(ascending=False).index).reset_index(drop=True)


def gdp_by_year(df_input: Optional[pd.DataFrame]) -> Optional[pd.Series]:
    """GDP (billions USD) by year from a run's input, or None."""
    if df_input is None or "gdp_mmm_usd" not in df_input.columns:
        return None
    return pd.Series(df_input["gdp_mmm_usd"].values, index=df_input["time_period"].astype(int).values + YEAR_0)


def npv_table(long: pd.DataFrame, names: Dict[int, str], rates=DISCOUNT_RATES) -> pd.DataFrame:
    """For the download: one row per (pathway, rate, item) with item = Net / Benefits / Costs / B/C / categories."""
    rows = []
    for sid in sorted(long["strategy_id"].unique()):
        for r in rates:
            s = npv_summary(long, sid, r)
            base = {"pathway": names.get(sid, str(sid)), "discount_rate_pct": r}
            rows.append({**base, "item": "Net benefits", "value": s["net"], "unit": "billion USD"})
            rows.append({**base, "item": "Benefits", "value": s["benefits"], "unit": "billion USD"})
            rows.append({**base, "item": "Costs", "value": -s["costs"], "unit": "billion USD"})
            rows.append({**base, "item": "Benefit/cost ratio", "value": s["bcr"], "unit": "ratio"})
            rows.append({**base, "item": "Net-positive year", "value": s["net_positive_year"], "unit": "year"})
            for k, v in s["by_group"].items():
                rows.append({**base, "item": f"Net · {k}", "value": v, "unit": "billion USD"})
    return pd.DataFrame(rows)

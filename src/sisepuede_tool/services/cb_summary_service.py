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
import yaml

import sisepuede_tool

from sisepuede_tool.services.emissions_service import SUBSECTORS as SUBSECTORS_ABV
from sisepuede_tool.services.emissions_service import YEAR_0, subsector_label

OTHER = "Other"


def groups_path() -> pathlib.Path:
    return pathlib.Path(sisepuede_tool.__file__).parent / "resources" / "cb_groups.yaml"


def load_groups(path: Optional[pathlib.Path] = None) -> dict:
    """The C&B crosswalk (resources/cb_groups.yaml): per cb_type its CB sector,
    order, colour, broader category and names in each language."""
    data = yaml.safe_load(pathlib.Path(path or groups_path()).read_text(encoding="utf-8"))
    sectors, types = [], {}
    for block in data["sectors"]:
        sector = block["sector"]["en"]
        sectors.append(sector)
        for t in block.get("types") or ():
            types[t["cb_type"]] = {**t, "sector": sector, "sector_name": block["sector"]}
    if OTHER not in sectors:
        sectors.append(OTHER)
    return {"categories": list(data.get("categories") or ()), "sectors": sectors, "types": types}


_GROUPS = load_groups()
_SECTOR_NAMES: Dict[str, Dict[str, str]] = {t["sector"]: t["sector_name"] for t in _GROUPS["types"].values()}

# cb_type -> display category; CATEGORY_ORDER = legend order
CATEGORIES: Dict[str, str] = {t: v["category"] for t, v in _GROUPS["types"].items() if v.get("category")}
CATEGORY_ORDER: List[str] = _GROUPS["categories"]

# The Egypt Tableau workbook's "CB Sector" of each cb_type (see cb_groups.yaml);
# sectors and types in the file's order, unlisted types in "Other".
CB_SECTOR_ORDER: List[str] = _GROUPS["sectors"]
CB_TYPE_ORDER: List[str] = list(_GROUPS["types"])
CB_SECTORS: Dict[str, str] = {t: v["sector"] for t, v in _GROUPS["types"].items()}
CB_TYPE_COLORS: Dict[str, str] = {t: v["color"] for t, v in _GROUPS["types"].items() if v.get("color")}


def _in_lang(names: Optional[Dict[str, str]], lang: Optional[str], default: str) -> str:
    names = names or {}
    return names.get(lang or "en") or names.get("en") or default


def cb_type_name(cb_type: str, lang: Optional[str] = None) -> str:
    """Shown name of a cb_type ('fuel_cost' -> 'Fuel cost savings (...)')."""
    return _in_lang(_GROUPS["types"].get(cb_type, {}).get("name"), lang, str(cb_type).replace("_", " ").capitalize())


def cb_sector_name(sector: str, lang: Optional[str] = None) -> str:
    """Shown name of a CB sector (its English name, as in cb_sector)."""
    return _in_lang(_SECTOR_NAMES.get(sector), lang, sector)


LONG_COLUMNS = [
    "strategy_id", "year", "variable", "display_name", "sector", "sector_label",
    "cb_type", "cb_sector", "item_1", "item_2", "category", "value_busd",
]
GROUPS = ["category", "sector_label", "cb_type", "item_1", "item_2"]  # what the yearly chart can be split by

DISCOUNT_RATES = (0, 3, 5, 7)  # 0 = not discounted (plain sum 2025-2050)
DEFAULT_RATE = 0.0  # not discounted by default, as in the team's usual C&B reporting; a rate is an advanced option


def rate_label(rate_pct: float) -> str:
    return "not discounted" if rate_pct == 0 else f"discounted at {rate_pct:g}% to {START_YEAR}"
START_YEAR = 2025  # the package shifts earlier costs into 2025


def category_of(cb_type: Optional[str]) -> str:
    return CATEGORIES.get(cb_type or "", OTHER)


def cb_sector_of(cb_type: Optional[str]) -> str:
    """The workbook's "CB Sector" of a cb_type ("Other" when it has none)."""
    return CB_SECTORS.get(cb_type or "", OTHER)


def cb_type_order(cb_types) -> List[str]:
    """`cb_types` in the workbook's order (by CB sector), unknown ones last."""
    have = [t for t in dict.fromkeys(cb_types) if isinstance(t, str)]
    return [t for t in CB_TYPE_ORDER if t in have] + sorted(t for t in have if t not in CB_TYPE_ORDER)


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
    """[strategy_id, year, variable, display_name, sector, sector_label, cb_type,
    cb_sector, item_1, item_2, category, value_busd]. item_1 / item_2 are the last
    two parts of the variable name (cb:<sector>:<cb_type>:<item_1>:<item_2>), e.g.
    trns / gasoline; "" when the variable has none."""
    value_cols = [c for c in df_cb.columns if c not in ("strategy_id", "time_period")]
    long = df_cb.melt(id_vars=["strategy_id", "time_period"], value_vars=value_cols, var_name="variable", value_name="value_busd")
    long["year"] = long["time_period"].astype(int) + YEAR_0
    attr = df_attr_variable.drop_duplicates("variable").set_index("variable")
    long["sector"] = long["variable"].map(attr["sector"]) if "sector" in attr else None
    long["cb_type"] = long["variable"].map(attr["cb_type"]) if "cb_type" in attr else None
    long["category"] = long["cb_type"].map(category_of)
    long["cb_sector"] = long["cb_type"].map(cb_sector_of)
    for item in ("item_1", "item_2"):
        values = long["variable"].map(attr[item]) if item in attr else pd.Series("", index=long.index)
        long[item] = values.where(values.map(lambda v: isinstance(v, str) and v not in ("", "X")), "")
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
    return long[LONG_COLUMNS]


def by_group(long: pd.DataFrame, strategy_id: int, group: str = "category") -> pd.DataFrame:
    """Wide by year: one column per group (category, cb_type or sector_label), billions USD."""
    d = long[(long["strategy_id"] == strategy_id) & (long["year"] >= START_YEAR)]
    wide = d.pivot_table(index="year", columns=group, values="value_busd", aggfunc="sum", fill_value=0.0)
    if group == "category":
        order = CATEGORY_ORDER + [OTHER]
    elif group == "cb_type":
        order = cb_type_order(wide.columns)
    else:
        order = sorted(wide.columns)
    return wide[[c for c in order if c in wide.columns]]


def filter_by(long: pd.DataFrame, **picked) -> pd.DataFrame:
    """Only the rows whose column is in the picked values, e.g.
    filter_by(long, cb_type=["fuel_cost"], item_1=[]); an empty pick keeps all."""
    for column, values in picked.items():
        values = [v for v in (values or ()) if v is not None]
        if values:
            long = long[long[column].isin(values)]
    return long


def item_label(token: str) -> str:
    """Readable item_1 / item_2: a subsector or category name, else the token
    ('trns' -> 'Transportation'); "(none)" for an empty one."""
    return _pretty(token) or ("(none)" if token == "" else token)


def by_cb_type(long: pd.DataFrame, strategy_id: int, rate_pct: float = 0.0) -> pd.DataFrame:
    """[cb_sector, cb_type, value] of a pathway, value = 2025-2050 total in billions
    USD (discounted to START_YEAR when rate_pct > 0). Every cb_type in `long`
    has a row, in the workbook's order, also when it is zero for this pathway."""
    types = cb_type_order(long["cb_type"].dropna().unique())
    d = long[(long["strategy_id"] == strategy_id) & (long["year"] >= START_YEAR)]
    if d.empty:
        values = pd.Series(0.0, index=types)
    else:
        df = discount_factors(sorted(d["year"].unique()), rate_pct)
        values = (d["value_busd"] * d["year"].map(df)).groupby(d["cb_type"]).sum().reindex(types, fill_value=0.0)
    out = pd.DataFrame({"cb_type": types, "value": values.to_numpy()})
    out.insert(0, "cb_sector", out["cb_type"].map(cb_sector_of))
    order = {s: i for i, s in enumerate(CB_SECTOR_ORDER)}
    return out.sort_values("cb_sector", key=lambda s: s.map(order), kind="stable").reset_index(drop=True)


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

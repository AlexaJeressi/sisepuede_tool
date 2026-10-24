"""Marginal abatement cost (MAC) of the transformations of a pathway, from sisepuede_a6.

For now the numbers are static: ref/temporary_mac.csv of the sisepuede_a6
clone (found as in article6_service). For each pathway (`strategy_id_stressed`:
6004 NDC, 6005 LEP), transformation and emission grouping (a subsector, or
"All" = the sum of the subsectors) it has, from two sets of runs (tornado and
whirlpool, strategies in ref/temporary_mac_strategy_map.csv):
- est_transformation_emission_effect_mt_co2e_*: emissions (MtCO2e, < 0 = abated);
- cost_diff_mmm_usd_*: net benefit (billion USD, < 0 = net cost);
- mac_{tornado,whirlpool,mean}_usd_per_tonne: the MAC (USD/tCO2e, > 0 = costs
  money); mean = the average of the two.

The page shows the file's values as they are (it doesn't compute its own
MACs): a transformation's MAC is that of its "All" row, its MAC in a
subsector that of the subsector's row (the chart by transformation), and the
tonnes it abates in a subsector are -emissions of that subsector's row. The file has no tonnes
for the mean: they are the average of the two estimates. A transformation that
raises emissions overall keeps the file's MAC.

A transformation has one MAC over all it abates (its "All" row) and one in
each subsector (that subsector's row; the "All" row is the sum of them). The
charts by subsector and by transformation use the subsector rows: in a
subsector are the transformations that abate there, with what they abate
there, at their MAC there; the average cost of a subsector weighs those MACs
by those tonnes (for tornado and whirlpool, 1000 x the sum of the rows'
cost_diff_mmm_usd over the sum of their emissions).

When the MAC is computed from the tool's runs, load() is the function to
replace; the page only needs its columns.
"""

import functools
import math
import re
from typing import Dict, Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd

from sisepuede_tool.services.article6_service import A6_REF_DIR
from sisepuede_tool.services.emissions_service import SECTOR_ORDER, SUBSECTORS

MAC_PATH = A6_REF_DIR / "temporary_mac.csv"

# strategy_id_stressed -> pathway; the order is the order on the page
PATHWAYS = {6004: "NDC2.0", 6005: "LEP"}
MEASURES = ["mean", "tornado", "whirlpool"]
ESTIMATES = ["tornado", "whirlpool"]

# emission groupings in the file -> sisepuede abbreviation; "All" is left out (see above)
SUBSECTOR_ABV = {
    "Agriculture": "agrc",
    "Energy Technology": "entc",
    "Fugitive Emissions": "fgtv",
    "IPPU": "ippu",
    "Industrial Energy": "inen",
    "Land Use": "lndu",
    "Livestock": "lvst",
    "Livestock Manure Management": "lsmm",
    "Soil Management": "soil",
    "Solid Waste": "waso",
    "Stationary Combustion and Other Energy": "scoe",
    "Transportation": "trns",
    "Wastewater Treatment": "trww",
}

SECTOR_PREFIX = "sector:"  # scope value of a whole sector, e.g. "sector:Energy"; "" = whole economy
ZERO_MT = 1e-4  # abatement below this (MtCO2e, absolute value) doesn't count: the transformation doesn't touch the scope


@functools.lru_cache(maxsize=1)
def load(path=None) -> pd.DataFrame:
    """[pathway, code, subsector, abatement_*, cost_*, mac_*] (* = tornado,
    whirlpool, mean): one row per pathway, transformation and subsector
    (abbreviation). abatement: MtCO2e abated in that subsector (> 0 = emissions
    avoided); cost (billion USD, > 0 = net cost) and mac: the transformation's
    whole ones (its "All" row), the same on each of its rows; sub_cost and
    sub_mac: those of the subsector's own row."""
    df = pd.read_csv(path or MAC_PATH)
    df = df[df["strategy_id_stressed"].isin(PATHWAYS)]
    whole = df[df["emission_grouping"] == "All"].set_index(["strategy_id_stressed", "transformation_code"])
    df = df[df["emission_grouping"].isin(SUBSECTOR_ABV)]
    keys = pd.MultiIndex.from_frame(df[["strategy_id_stressed", "transformation_code"]])
    out = pd.DataFrame({
        "pathway": df["strategy_id_stressed"].map(PATHWAYS),
        "code": df["transformation_code"],
        "subsector": df["emission_grouping"].map(SUBSECTOR_ABV),
    })
    for e in ESTIMATES:
        out[f"abatement_{e}"] = -df[f"est_transformation_emission_effect_mt_co2e_{e}"].astype(float)
        out[f"cost_{e}"] = -whole[f"cost_diff_mmm_usd_{e}"].reindex(keys).to_numpy(float)
        out[f"sub_cost_{e}"] = -df[f"cost_diff_mmm_usd_{e}"].astype(float)
    for x in ("abatement", "cost", "sub_cost"):
        out[f"{x}_mean"] = (out[f"{x}_tornado"] + out[f"{x}_whirlpool"]) / 2
    for m in MEASURES:
        out[f"mac_{m}"] = whole[f"mac_{m}_usd_per_tonne"].reindex(keys).to_numpy(float)
        out[f"sub_mac_{m}"] = df[f"mac_{m}_usd_per_tonne"].astype(float)
    return out.reset_index(drop=True)


def pathways(df: pd.DataFrame) -> List[str]:
    """Pathways in `df`, in PATHWAYS order."""
    have = set(df["pathway"])
    return [p for p in PATHWAYS.values() if p in have]


def scopes(df: pd.DataFrame) -> List[Tuple[str, List[str]]]:
    """[(sector, [subsector abbreviations])] in the file, in SECTOR_ORDER."""
    have = set(df["subsector"])
    out = []
    for sector in SECTOR_ORDER:
        subs = [abv for abv in SUBSECTOR_ABV.values() if abv in have and SUBSECTORS[abv][0] == sector]
        if subs:
            out.append((sector, subs))
    return out


def scope_subsectors(scope: str) -> Optional[List[str]]:
    """Subsectors counted in `scope`: None = all (whole economy, ""), a sector's
    ("sector:Energy") or one ("trns")."""
    if not scope:
        return None
    if scope.startswith(SECTOR_PREFIX):
        sector = scope[len(SECTOR_PREFIX):]
        return [abv for abv in SUBSECTOR_ABV.values() if SUBSECTORS[abv][0] == sector]
    return [scope]


def transformations(df: pd.DataFrame, pathway: str) -> pd.DataFrame:
    """[code, abatement_*, cost_*, mac_*] of each transformation of `pathway`
    (whole economy; * = tornado, whirlpool, mean)."""
    d = df[df["pathway"] == pathway]
    return d.groupby("code", sort=False).agg(
        **{f"abatement_{m}": (f"abatement_{m}", "sum") for m in MEASURES},
        **{f"{x}_{m}": (f"{x}_{m}", "first") for x in ("cost", "mac") for m in MEASURES},
    ).reset_index()


def curve(df: pd.DataFrame, pathway: str, scope: str, measure: str) -> Tuple[pd.DataFrame, Dict[str, List[str]]]:
    """The MAC curve of `pathway` in `scope` for `measure`.

    Rows: the transformations that abate in the scope, cheapest first, with
    [code, mac (the file's), abatement (in the scope), share (of the
    transformation's whole abatement), cost (whole), start (cumulative abatement
    before it), mac_tornado, mac_whirlpool]. Left out: "raises" (more emissions
    in the scope)."""
    t = transformations(df, pathway).set_index("code")
    d = df[df["pathway"] == pathway]
    subs = scope_subsectors(scope)
    if subs is not None:
        d = d[d["subsector"].isin(subs)]
    here = d.groupby("code", sort=False)[f"abatement_{measure}"].sum().reindex(t.index, fill_value=0.0)

    out = pd.DataFrame({
        "code": t.index,
        "mac": t[f"mac_{measure}"].to_numpy(),
        "abatement": here.to_numpy(),
        "total": t[f"abatement_{measure}"].to_numpy(),
        "cost": t[f"cost_{measure}"].to_numpy(),
        "mac_tornado": t["mac_tornado"].to_numpy(),
        "mac_whirlpool": t["mac_whirlpool"].to_numpy(),
    })
    left = {"raises": list(out.loc[out["abatement"] < -ZERO_MT, "code"])}
    out = out[(out["abatement"] > ZERO_MT) & out["mac"].notna()].sort_values("mac", kind="stable").reset_index(drop=True)
    with np.errstate(divide="ignore", invalid="ignore"):
        # above 1 when it raises emissions elsewhere: not a share then
        share = np.where(out["total"] > ZERO_MT, out["abatement"] / out["total"], np.nan)
    out["share"] = np.where(share <= 1 + 1e-9, share, np.nan)
    out["start"] = out["abatement"].cumsum() - out["abatement"]
    return out.drop(columns="total"), left


def summary(rows: pd.DataFrame) -> Dict[str, float]:
    """{abatement, saving (abated at a net saving, MAC < 0), mac (abatement-weighted
    average)} of the rows of curve()."""
    total = float(rows["abatement"].sum())
    return {
        "abatement": total,
        "saving": float(rows.loc[rows["mac"] < 0, "abatement"].sum()),
        "mac": float((rows["mac"] * rows["abatement"]).sum() / total) if total > 0 else float("nan"),
    }


def pair_key(code: str) -> str:
    """The same transformation in both pathways: 'TX:ENTC:TARGET_RENEWABLE_ELEC_STRATEGY_NDC'
    and 'TX:ENTC:TARGET_RENEWABLE_ELEC_LEP' -> 'TX:ENTC:TARGET_RENEWABLE_ELEC'."""
    return re.sub(r"(_STRATEGY)?_(NDC|LEP)$", "", code)


def by_subsector(df: pd.DataFrame, pathways: Iterable[str], measure: str) -> pd.DataFrame:
    """[pathway, subsector, mac, abatement, n] for each pathway and subsector where
    some of its transformations abate: the average of their MACs there (the
    bars of by_transformation, every one of them) weighted by the tonnes they
    abate there, those tonnes and how many."""
    cols = ["pathway", "subsector", "mac", "abatement", "n"]
    rows, _ = by_transformation(df, list(pathways), measure, min_share=0.0)
    if rows.empty:
        return pd.DataFrame(columns=cols)
    rows = rows.assign(weighted=rows["mac"] * rows["abatement"])
    out = rows.groupby(["pathway", "subsector"], sort=False).agg(
        weighted=("weighted", "sum"), abatement=("abatement", "sum"), n=("code", "count")).reset_index()
    out["mac"] = out["weighted"] / out["abatement"]
    return out[cols]


def subsector_order(table: pd.DataFrame, pathways: List[str]) -> List[str]:
    """Subsectors of by_subsector(), cheapest first: by the first pathway that has
    a value (so the bars of the first pathway rise from left to right)."""
    wide = table.pivot(index="subsector", columns="pathway", values="mac")
    key = pd.Series(np.nan, index=wide.index)
    for p in pathways:
        if p in wide:
            key = key.fillna(wide[p])
    return list(key.sort_values(kind="stable").index)


def by_transformation(df: pd.DataFrame, pathways: List[str], measure: str, scope: str = "",
                      min_share: float = 0.01) -> Tuple[pd.DataFrame, int]:
    """The transformations that abate in each subsector of `scope` ("" = all),
    for each pathway: [subsector, key (pair_key), code, pathway, mac, abatement,
    share (of the subsector's abatement in that pathway), cost, mac_tornado,
    mac_whirlpool, mac_all], cheapest first in each subsector. A transformation
    that abates in several subsectors is under each, with what it abates there
    and its MAC there (mac, cost, mac_tornado, mac_whirlpool: the file's row for
    that subsector); mac_all: its whole MAC (the "All" row). Rows under
    `min_share` in every pathway are left out; their number is returned."""
    subs = scope_subsectors(scope) or [abv for _, s in scopes(df) for abv in s]
    cols = ["subsector", "key", "code", "pathway", "mac", "abatement", "share", "cost", "mac_tornado", "mac_whirlpool", "mac_all"]
    d = df[df["pathway"].isin(pathways) & df["subsector"].isin(subs)]
    d = d[(d[f"abatement_{measure}"] > ZERO_MT) & d[f"sub_mac_{measure}"].notna()]
    if d.empty:
        return pd.DataFrame(columns=cols), 0
    t = pd.DataFrame({
        "subsector": d["subsector"], "key": d["code"].map(pair_key), "code": d["code"], "pathway": d["pathway"],
        "mac": d[f"sub_mac_{measure}"], "abatement": d[f"abatement_{measure}"], "cost": d[f"sub_cost_{measure}"],
        "mac_tornado": d["sub_mac_tornado"], "mac_whirlpool": d["sub_mac_whirlpool"], "mac_all": d[f"mac_{measure}"],
    })
    t["share"] = t["abatement"] / t.groupby(["pathway", "subsector"])["abatement"].transform("sum")
    t["_p"] = t["pathway"].map({p: i for i, p in enumerate(pathways)})
    t["_s"] = t["subsector"].map({abv: i for i, abv in enumerate(subs)})
    t = t.sort_values(["_p", "_s", "mac"], kind="stable").drop(columns=["_p", "_s"])[cols].reset_index(drop=True)
    keep = t.groupby(["subsector", "key"])["share"].transform("max") >= min_share
    hidden = t.loc[~keep, ["subsector", "key"]].drop_duplicates().shape[0]
    return t[keep].reset_index(drop=True), hidden


def subsector_of(code: str) -> str:
    """'TX:TRNS:SHIFT_FUEL_RAIL_STRATEGY_NDC' -> 'trns'."""
    parts = code.split(":")
    return parts[1].lower() if len(parts) > 2 else ""


def _abs_nonzero(values: Iterable[float]) -> List[float]:
    return sorted((abs(float(v)) for v in values if not math.isnan(float(v)) and abs(float(v)) > 1e-9), reverse=True)


def axis_limit(values: Iterable[float], ratio: float = 3.0) -> Optional[float]:
    """Half-width of a linear axis when a few values (at most a fifth, at least
    one) would flatten all the others: the values above the last gap of more
    than `ratio` times between two consecutive values (largest first) are cut.
    None when every value fits."""
    a = _abs_nonzero(values)
    gaps = [k for k in range(min(max(1, len(a) // 5), len(a) - 1)) if a[k] > ratio * a[k + 1]]
    return 1.3 * a[gaps[-1] + 1] if gaps else None

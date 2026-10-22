"""Marginal abatement cost (MAC) of the transformations of a pathway, from sisepuede_a6.

For now the numbers are static: ref/temporary_emit_cost_diffs_by_subsec.csv of
the sisepuede_a6 clone (found as in article6_service). For each pathway
(`strategy_id_stressed`: 6004 NDC, 6005 LEP), transformation and emission
subsector it has what the transformation changes, from two sets of runs
(tornado and whirlpool, strategies in ref/temporary_mac_strategy_map.csv):
- emission_diff_mt_co2e_*: emissions in that subsector (MtCO2e, < 0 = abated);
- cost_diff_mmm_usd_*: the transformation's net benefit (billion USD, < 0 = net
  cost), the same in every subsector row.

The page doesn't use the file's own MACs (ref/temporary_mac.csv): there the
whirlpool MAC has the opposite sign of tornado for the same differences, and
the "All" rows divide by k times the abatement (k = 1..43, the row order). Here
the MAC is computed from the differences:
- abatement = -emission difference, whole economy = sum of the subsectors;
- MAC (USD/tCO2e) = net cost / whole-economy abatement, > 0 = costs money;
- mean = both estimates together: (cost T + cost W) / (abatement T + abatement W).
  An estimate that is zero everywhere (cost and every subsector) was not run
  for that transformation: the mean is then the other estimate.

A transformation has one MAC (its cost over all it abates); a scope (a
subsector or a sector) only changes which tonnes are counted: in a subsector
are the transformations that abate there, with what they abate there, at their
MAC. The average cost of a subsector weighs their MACs by those tonnes.

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

DIFFS_PATH = A6_REF_DIR / "temporary_emit_cost_diffs_by_subsec.csv"

# strategy_id_stressed -> pathway; the order is the order on the page
PATHWAYS = {6004: "NDC", 6005: "LEP"}
MEASURES = ["mean", "tornado", "whirlpool"]
ESTIMATES = ["tornado", "whirlpool"]

# subsector names in the file -> sisepuede abbreviation; "All" is left out (see above)
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
    """[pathway, code, subsector, abatement_{tornado,whirlpool}, cost_{tornado,whirlpool}]:
    one row per pathway, transformation and subsector (abbreviation). Abatement
    in MtCO2e (> 0 = emissions avoided), cost in billion USD (> 0 = net cost,
    the transformation's whole cost on each of its rows)."""
    df = pd.read_csv(path or DIFFS_PATH)
    df = df[df["strategy_id_stressed"].isin(PATHWAYS) & df["subsector"].isin(SUBSECTOR_ABV)]
    out = pd.DataFrame({
        "pathway": df["strategy_id_stressed"].map(PATHWAYS),
        "code": df["transformation_code"],
        "subsector": df["subsector"].map(SUBSECTOR_ABV),
    })
    for e in ESTIMATES:
        out[f"abatement_{e}"] = -df[f"emission_diff_mt_co2e_{e}"].astype(float)
        out[f"cost_{e}"] = -df[f"cost_diff_mmm_usd_{e}"].astype(float)
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


def _measure(a_t, a_w, measure: str, h_t=1.0, h_w=1.0):
    """Value of `measure` from the tornado and whirlpool values (arrays or
    numbers); the mean averages the estimates that exist (`h_*`: 1 or 0)."""
    if measure == "mean":
        with np.errstate(divide="ignore", invalid="ignore"):
            return (a_t * h_t + a_w * h_w) / np.maximum(h_t + h_w, 1)
    return {"tornado": a_t, "whirlpool": a_w}[measure]


def _mac(cost, abatement):
    """USD/tCO2e from billion USD and MtCO2e; NaN when nothing is abated."""
    cost, abatement = np.asarray(cost, float), np.asarray(abatement, float)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(abatement > ZERO_MT, cost * 1e3 / abatement, np.nan)


def transformations(df: pd.DataFrame, pathway: str) -> pd.DataFrame:
    """[code, cost_*, abatement_*, mac_*, has_tornado, has_whirlpool] of each
    transformation of `pathway` (whole economy; * = tornado, whirlpool, mean)."""
    d = df[df["pathway"] == pathway]
    t = d.groupby("code", sort=False).agg(
        **{f"abatement_{e}": (f"abatement_{e}", "sum") for e in ESTIMATES},
        **{f"cost_{e}": (f"cost_{e}", "first") for e in ESTIMATES},
        **{f"_abs_{e}": (f"abatement_{e}", lambda s: s.abs().sum()) for e in ESTIMATES},
    ).reset_index()
    for e in ESTIMATES:
        # 1 when the estimate exists (see the module docstring)
        t[f"has_{e}"] = ((t.pop(f"_abs_{e}") > ZERO_MT) | (t[f"cost_{e}"].abs() > 1e-9)).astype(float)
    for x in ("abatement", "cost"):
        t[f"{x}_mean"] = _measure(t[f"{x}_tornado"], t[f"{x}_whirlpool"], "mean", t["has_tornado"], t["has_whirlpool"])
    for m in MEASURES:
        t[f"mac_{m}"] = _mac(t[f"cost_{m}"], t[f"abatement_{m}"])
    return t


def curve(df: pd.DataFrame, pathway: str, scope: str, measure: str) -> Tuple[pd.DataFrame, Dict[str, List[str]]]:
    """The MAC curve of `pathway` in `scope` for `measure`.

    Rows: the transformations that abate in the scope, cheapest first, with
    [code, mac, abatement (in the scope), share (of the transformation's whole
    abatement), cost (whole), start (cumulative abatement before it), mac_tornado,
    mac_whirlpool]. Left out, by reason: "raises" (more emissions in the scope),
    "no_mac" (abates in the scope but not overall, so it has no cost per tonne)."""
    t = transformations(df, pathway).set_index("code")
    d = df[df["pathway"] == pathway]
    subs = scope_subsectors(scope)
    if subs is not None:
        d = d[d["subsector"].isin(subs)]
    a = d.groupby("code", sort=False)[[f"abatement_{e}" for e in ESTIMATES]].sum().reindex(t.index, fill_value=0.0)
    here = pd.Series(_measure(a["abatement_tornado"], a["abatement_whirlpool"], measure, t["has_tornado"], t["has_whirlpool"]), index=t.index)

    out = pd.DataFrame({
        "code": t.index,
        "mac": t[f"mac_{measure}"].to_numpy(),
        "abatement": here.to_numpy(),
        "total": t[f"abatement_{measure}"].to_numpy(),
        "cost": t[f"cost_{measure}"].to_numpy(),
        "mac_tornado": t["mac_tornado"].to_numpy(),
        "mac_whirlpool": t["mac_whirlpool"].to_numpy(),
    })
    left = {
        "raises": list(out.loc[out["abatement"] < -ZERO_MT, "code"]),
        "no_mac": list(out.loc[(out["abatement"] > ZERO_MT) & out["mac"].isna(), "code"]),
    }
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
    some of its transformations abate: the average cost per tonne abated there
    (abatement-weighted, as summary()), what they abate there and how many."""
    out = []
    for p in pathways:
        for _, subs in scopes(df):
            for abv in subs:
                rows, _ = curve(df, p, abv, measure)
                if not rows.empty:
                    out.append({"pathway": p, "subsector": abv, "n": len(rows), **{k: v for k, v in summary(rows).items() if k != "saving"}})
    return pd.DataFrame(out, columns=["pathway", "subsector", "mac", "abatement", "n"])


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
    mac_whirlpool]. A transformation that abates in several
    subsectors is under each, with what it abates there. Rows under
    `min_share` in every pathway are left out; their number is returned."""
    subs = scope_subsectors(scope) or [abv for _, s in scopes(df) for abv in s]
    parts = []
    for p in pathways:
        for abv in subs:
            rows, _ = curve(df, p, abv, measure)
            if rows.empty:
                continue
            rows = rows.assign(pathway=p, subsector=abv, key=rows["code"].map(pair_key))
            rows["share"] = rows["abatement"] / rows["abatement"].sum()
            parts.append(rows.drop(columns="start"))
    if not parts:
        return pd.DataFrame(columns=["subsector", "key", "code", "pathway", "mac", "abatement", "share"]), 0
    t = pd.concat(parts, ignore_index=True)
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

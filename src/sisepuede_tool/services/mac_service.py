"""Marginal abatement cost (MAC) of the NDC transformations, from sisepuede_a6.

For now the numbers are static: ref/temporary_mac.csv of the sisepuede_a6
clone (found as in article6_service), with the cost per tonne abated
(USD/tCO2e) from two sets of runs, tornado and whirlpool (strategies in
ref/temporary_mac_strategy_map.csv), and their mean.

The file has a row per transformation and emission subsector. Two filters:
- the subsector of the transformation (TX:TRNS:... -> trns): which rows;
- the subsector the abatement is measured in (the file's `subsector`; "All"
  is the whole economy): which values. A transformation barely changes the
  emissions of most subsectors, so its cost per tonne there can reach
  10^12 USD/t.

When the MAC is computed from the tool's runs, load() is the function to
replace; the page only needs its columns.
"""

import functools
import math
from typing import Iterable, List, Optional, Sequence

import pandas as pd

from sisepuede_tool.services.article6_service import A6_REF_DIR

MAC_PATH = A6_REF_DIR / "temporary_mac.csv"
SUBSECTOR_ALL = "All"

FIELD_CODE = "transformation_code"
FIELD_SUBSECTOR = "subsector"
# measure key -> column of the file; the order is the order on the page
MEASURE_FIELDS = {
    "mean": "mac_mean_usd_per_tonne",
    "tornado": "mac_tornado_usd_per_tonne",
    "whirlpool": "mac_whirlpool_usd_per_tonne",
}
MEASURES = list(MEASURE_FIELDS)

# subsector names in the file -> sisepuede abbreviation (for the translated name)
SUBSECTOR_ABV = {
    "Agriculture": "agrc",
    "Energy Technology": "entc",
    "Fugitive Emissions": "fgtv",
    "IPPU": "ippu",
    "Industrial Energy": "inen",
    "Land Use": "lndu",
    "Soil Management": "soil",
    "Solid Waste": "waso",
    "Stationary Combustion and Other Energy": "scoe",
    "Transportation": "trns",
    "Wastewater Treatment": "trww",
}

ZERO = 1e-9  # a row with every shown measure below this (in absolute value) has no cost to show
LOG_RATIO = 100.0  # auto scale: logarithmic when the largest value is this many times the median


@functools.lru_cache(maxsize=1)
def load(path=None) -> pd.DataFrame:
    """[code, subsector, mean, tornado, whirlpool] (USD/tCO2e); `subsector` is
    where the abatement is measured ("All" = whole economy)."""
    df = pd.read_csv(path or MAC_PATH)
    df = df.rename(columns={FIELD_CODE: "code", **{v: k for k, v in MEASURE_FIELDS.items()}})
    return df[["code", FIELD_SUBSECTOR, *MEASURES]].reset_index(drop=True)


def transformation_subsectors(df: pd.DataFrame) -> List[str]:
    """Subsectors of the transformations in `df` (abbreviations, e.g. "trns"), sorted."""
    return sorted({subsector_of(c) for c in df["code"]} - {""})


def measured_subsectors(df: pd.DataFrame) -> List[str]:
    """Subsectors the abatement is measured in, as in the file: "All" first, then file order."""
    names = list(dict.fromkeys(df[FIELD_SUBSECTOR]))
    return ([SUBSECTOR_ALL] if SUBSECTOR_ALL in names else []) + [s for s in names if s != SUBSECTOR_ALL]


def _select(df: pd.DataFrame, tx_subsector: str, measured_in: str) -> pd.DataFrame:
    """Transformations of `tx_subsector` ("" = all), values measured in `measured_in`."""
    d = df[df[FIELD_SUBSECTOR] == (measured_in or SUBSECTOR_ALL)]
    return d[d["code"].map(subsector_of) == tx_subsector] if tx_subsector else d


def sort_measure(measures: Sequence[str]) -> str:
    """The measure rows are sorted by: the mean, unless a single other measure
    is shown (the mean is the midpoint of tornado and whirlpool, so it also
    orders the ranges)."""
    return measures[0] if len(measures) == 1 else "mean"


def rows(df: pd.DataFrame, tx_subsector: str, measured_in: str, measures: Sequence[str]) -> pd.DataFrame:
    """Transformations of `tx_subsector` ("" = all) with their values measured in
    `measured_in` ("All" = whole economy) and a non-zero value in at least one
    of `measures`, cheapest first (by sort_measure)."""
    d = _select(df, tx_subsector, measured_in)
    if not measures:
        return d.iloc[0:0]
    d = d[(d[list(measures)].abs() > ZERO).any(axis=1)]
    return d.sort_values(sort_measure(measures)).reset_index(drop=True)


def zero_codes(df: pd.DataFrame, tx_subsector: str, measured_in: str, measures: Sequence[str]) -> List[str]:
    """Transformations left out by rows() (every shown measure is zero)."""
    d = _select(df, tx_subsector, measured_in)
    return list(d.loc[~(d[list(measures)].abs() > ZERO).any(axis=1), "code"]) if measures else []


def subsector_of(code: str) -> str:
    """'TX:TRNS:SHIFT_FUEL_RAIL_STRATEGY_NDC' -> 'trns'."""
    parts = code.split(":")
    return parts[1].lower() if len(parts) > 2 else ""


def _abs_nonzero(values: Iterable[float]) -> List[float]:
    return sorted((abs(float(v)) for v in values if abs(float(v)) > ZERO), reverse=True)


def wants_log(values: Iterable[float]) -> bool:
    """Auto scale: logarithmic when the values span too many orders of magnitude
    for a linear axis (the largest is more than LOG_RATIO times the median). A
    single outlier doesn't count: a linear axis cuts it (axis_limit)."""
    a = _abs_nonzero(values)
    if axis_limit(a) is not None:
        a = a[1:]
    return len(a) > 1 and a[0] > LOG_RATIO * a[len(a) // 2]


def axis_limit(values: Iterable[float], ratio: float = 5.0) -> Optional[float]:
    """Half-width of a linear axis when one value would flatten all the others
    (it is more than `ratio` times the next largest); None when every value fits."""
    a = _abs_nonzero(values)
    if len(a) < 2 or a[0] <= ratio * a[1]:
        return None
    return 1.3 * a[1]


def signed_log(v: float) -> float:
    """Position on the logarithmic axis: sign(v) * log10(1 + |v|), so 0 stays at 0
    and costs and savings are mirrored."""
    return math.copysign(math.log10(1 + abs(v)), v)


def log_ticks(lo: float, hi: float) -> List[float]:
    """Values for the ticks of a logarithmic axis covering [lo, hi]: 0 and powers
    of ten on each side that has values, every 2nd or 3rd power when there are many."""
    def kmax(v):
        return math.ceil(math.log10(max(abs(v), 1.0)))

    k_lo, k_hi = kmax(lo), kmax(hi)
    span = (k_lo if lo < 0 else 0) + (k_hi if hi > 0 else 0)
    step = 1 if span <= 8 else 2 if span <= 16 else 3
    # 1 and 10 crowd 0 on a wide axis: such a side starts at its first step above 10
    k0 = step if span > 4 else 0
    neg = [-(10.0**k) for k in range(k0 if k_lo > k0 else 0, k_lo + 1, step)][::-1] if lo < 0 else []
    pos = [10.0**k for k in range(k0 if k_hi > k0 else 0, k_hi + 1, step)] if hi > 0 else []
    return neg + [0.0] + pos

"""Implementation ramp in policy terms: start year, full-effect year, shape.

sisepuede's `vec_implementation_ramp` dict has `tp_0_ramp` (the last time
period with no change), `n_tp_ramp` (periods until full effect; the first
period at full effect is `tp_0_ramp + n_tp_ramp`, capped at the final
period), `alpha_logistic` (0 = linear, 1 = fully logistic) and
`window_logistic` (the slice of the standard logistic curve used; an
asymmetric window shifts the change earlier or later). `d` is validated by
sisepuede but never used (transformer_kernels.py build_implementation_ramp_vector),
so it is always written as 0.

The basic UI shows only the three policy terms. Shapes not matching a preset
are reported as "custom" and can only be edited in advanced mode.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

import numpy as np
import sisepuede.utilities._toolbox as sf

DEFAULT_WINDOW = (-8.0, 8.0)

SHAPES: Dict[str, Dict] = {
    "linear": {"label": "Linear", "alpha_logistic": 0.0, "window_logistic": DEFAULT_WINDOW},
    "s_curve": {"label": "S-curve", "alpha_logistic": 1.0, "window_logistic": (-5.0, 5.0)},
    "front_loaded": {"label": "Front-loaded", "alpha_logistic": 1.0, "window_logistic": (-3.0, 6.0)},
    "back_loaded": {"label": "Back-loaded", "alpha_logistic": 1.0, "window_logistic": (-6.0, 3.0)},
}
CUSTOM_SHAPE = "custom"


@dataclass
class PolicyRamp:
    start_year: int  # first year with any change
    full_year: int  # first year at full effect
    shape: str  # key of SHAPES, or "custom"


class RampError(ValueError):
    pass


def _tp_of_year(years: Sequence[int], year: int) -> int:
    years = list(years)
    if year not in years:
        raise RampError(f"year {year} is outside the model years {years[0]}-{years[-1]}")
    return years.index(year)


def ramp_from_policy(start_year: int, full_year: int, shape: str, years: Sequence[int]) -> Dict:
    """Policy terms -> sisepuede `vec_implementation_ramp` dict."""
    years = list(years)
    if shape not in SHAPES:
        raise RampError(f"unknown ramp shape {shape!r}; choose one of {list(SHAPES)}")
    if full_year <= start_year:
        raise RampError("full effect must come after the start year")
    tp_start = _tp_of_year(years, int(start_year))
    if tp_start < 1:
        raise RampError(f"the ramp cannot start in the first model year ({years[0]})")
    tp_full = _tp_of_year(years, int(full_year))
    tp_0 = tp_start - 1
    preset = SHAPES[shape]
    return {
        "tp_0_ramp": tp_0,
        "n_tp_ramp": tp_full - tp_0,
        "alpha_logistic": float(preset["alpha_logistic"]),
        "d": 0,
        "window_logistic": [float(w) for w in preset["window_logistic"]],
    }


def fill_ramp_defaults(ramp: Optional[Dict], defaults: Dict) -> Dict:
    """Replace missing/None fields (as in the NDC news YAMLs) with `defaults`
    (usually the catalog's ramp: see `catalog_default_ramp`)."""
    ramp = dict(ramp or {})
    out = {}
    for key in ("tp_0_ramp", "n_tp_ramp", "alpha_logistic", "d", "window_logistic"):
        value = ramp.get(key)
        out[key] = defaults.get(key) if value is None else value
    if out["window_logistic"] is None:
        out["window_logistic"] = DEFAULT_WINDOW
    out["window_logistic"] = tuple(float(w) for w in out["window_logistic"])
    if out["alpha_logistic"] is None:
        out["alpha_logistic"] = 0.0
    out["d"] = 0 if out["d"] is None else out["d"]
    return out


def shape_of(ramp: Dict) -> str:
    alpha = float(ramp.get("alpha_logistic") or 0.0)
    window = tuple(float(w) for w in (ramp.get("window_logistic") or DEFAULT_WINDOW))
    if alpha == 0.0:
        return "linear"  # window is irrelevant when there is no logistic part
    for key, preset in SHAPES.items():
        if preset["alpha_logistic"] == alpha and tuple(preset["window_logistic"]) == window:
            return key
    return CUSTOM_SHAPE


def policy_from_ramp(ramp: Optional[Dict], years: Sequence[int], defaults: Dict) -> PolicyRamp:
    """sisepuede ramp dict (possibly partial) -> policy terms."""
    years = list(years)
    r = fill_ramp_defaults(ramp, defaults)
    tp_0 = int(r["tp_0_ramp"])
    tp_full = min(tp_0 + int(r["n_tp_ramp"]), len(years) - 1)
    return PolicyRamp(start_year=years[tp_0 + 1], full_year=years[tp_full], shape=shape_of(r))


def ramp_curve(ramp: Dict, n_time_periods: int, defaults: Optional[Dict] = None) -> np.ndarray:
    """The 0..1 implementation vector sisepuede builds for `ramp`."""
    r = fill_ramp_defaults(ramp, defaults or {})
    vec = sf.ramp_vector(
        n_time_periods,
        alpha_logistic=float(r["alpha_logistic"]),
        r_0=int(r["tp_0_ramp"]),
        r_1=int(r["tp_0_ramp"]) + int(r["n_tp_ramp"]),
        window_logistic=tuple(r["window_logistic"]),
    )
    return np.asarray(vec, dtype=float)


def catalog_default_ramp(transformers_catalog) -> Dict:
    """The ramp sisepuede uses when a transformation sets none."""
    return {
        "tp_0_ramp": int(transformers_catalog.tp_0_ramp),
        "n_tp_ramp": int(transformers_catalog.n_tp_ramp),
        "alpha_logistic": float(transformers_catalog.alpha_logistic),
        "d": 0,
        "window_logistic": tuple(float(w) for w in transformers_catalog.window_logistic),
    }


def model_years(model_attributes) -> List[int]:
    table = model_attributes.get_dimensional_attribute_table(model_attributes.dim_time_period).table
    return table.sort_values("time_period")["year"].astype(int).tolist()


def describe(policy: PolicyRamp) -> str:
    """'2026→2040 · S-curve'"""
    label = SHAPES[policy.shape]["label"] if policy.shape in SHAPES else "Custom"
    return f"{policy.start_year}→{policy.full_year} · {label}"

"""Per-transformer "what this moves" metadata for the Pathways page.

sisepuede's transformer attribute table has a name and description per
transformer, but no list of affected variables (`variables_affected` is empty)
and nothing about emissions. `TransformerKernels.get_tkernel_variable_fields()`
lists changed fields, but it crashes on the biomass_fix branch (one broken
transformer aborts the whole loop) and gives no direction of change.

This module computes that information per transformer, each inside its own
try/except:

* input variables: run the transformer with default parameters and compare
  against `tk.baseline()` over every input field, grouped by model variable;
* emissions when used alone: project baseline and transformed inputs without
  the electricity model (no Julia) and compare subsector totals in the final
  year.

`scripts/build_transformer_metadata.py` runs this offline and writes
`resources/transformer_catalog.yaml`. Each entry there has a `computed` block
(regenerated on every run) and a `curated` block (edited by hand, kept across
runs). `get_card` merges both for the UI, with curated values winning.
"""

import inspect
import logging
import pathlib
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
import yaml

from sisepuede_tool.services import widget_metadata
from sisepuede_tool.services.labels import clean_label, strip_subsector_prefix

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1
TOP_N_VARIABLES = 5
# variables shown in the UI next to the emissions line (design: 5 rows total)
N_VARIABLES_DISPLAYED = 4

# relative change below which a field counts as unchanged (same default as
# sisepuede's get_tkernel_variable_fields)
FIELD_CHANGE_THRESHOLD = 1e-3
# share of total baseline emissions below which the effect counts as "no change"
EMISSIONS_NO_CHANGE_THRESHOLD = 5e-4

DIRECTIONS = ("increases", "decreases", "shifts", "no_change")
EMISSION_DIRECTIONS = ("decreases", "increases", "no_change", "depends_on_grid", "needs_electricity_model")

# subsectors whose outputs are electricity/fuel supply; fuel switches and
# hydrogen elsewhere move emissions into these when NemoMod runs
_GRID_DEPENDENT_TOKENS = ("SHIFT_FUEL", "CLEAN_HYDROGEN")
_GRID_PAIR = "TFR:ENTC:TARGET_RENEWABLE_ELEC"

_CURATED_TEMPLATE = {
    "reviewed": False,
    "name": None,
    "short_description": None,
    "magnitude_label": None,
    "magnitude_help": None,
    "top_variables": None,
    "emissions_direction": None,
    "pair_with": [],
    "notes": None,
}


def default_catalog_path() -> pathlib.Path:
    import sisepuede_tool

    return pathlib.Path(sisepuede_tool.__file__).parent / "resources" / "transformer_catalog.yaml"


##########################
#    TRANSFORMER INFO    #
##########################


def _attribute_row(tk, code: str) -> Dict[str, Any]:
    attr = tk.attribute_transformer_kernel_code
    table = attr.table
    row = table[table[attr.key] == code]
    if row.empty:
        return {}
    rec = row.iloc[0].to_dict()
    return {k: (None if (isinstance(v, float) and np.isnan(v)) else v) for k, v in rec.items()}


def main_magnitude_param(tkernel) -> Optional[Dict[str, Any]]:
    """The parameter basic users set (see widget_metadata.main_magnitude_name)
    and its default, or None if it has none (dict-only transformers)."""
    name = widget_metadata.main_magnitude_name(tkernel)
    if name is None:
        return None
    default = inspect.signature(tkernel.function).parameters[name].default
    return {"param": name, "default": float(default)}


def _subsector_abv(code: str) -> Optional[str]:
    parts = code.split(":")
    return parts[1].lower() if len(parts) >= 3 else None


##########################
#    VARIABLE EFFECTS    #
##########################


def _relative_change(x: np.ndarray, b: np.ndarray) -> np.ndarray:
    """|x/b - 1| elementwise; a change away from a zero baseline counts as 1."""
    with np.errstate(divide="ignore", invalid="ignore"):
        rel = np.abs(x / b - 1.0)
    zero_base = b == 0
    rel[zero_base] = np.where(np.isclose(x[zero_base], 0.0), 0.0, 1.0)
    return np.nan_to_num(rel, nan=0.0, posinf=1.0)


def compute_variable_effects(
    tk,
    df_transformed: pd.DataFrame,
    df_baseline: Optional[pd.DataFrame] = None,
    top_n: int = TOP_N_VARIABLES,
    threshold: float = FIELD_CHANGE_THRESHOLD,
    fields: Optional[List[str]] = None,
    kind: str = "input",
) -> Dict[str, Any]:
    """Rank the model variables changed by a transformation.

    By default compares input fields of the transformed inputs against
    `tk.baseline()`. Pass two model outputs and `fields` /
    `kind="output"` to rank output variables instead.

    Returns {"n_fields_changed", "n_variables_changed", "top_variables": [...]},
    each top variable with its label, direction (sign of the change at the
    time period where each field moves the most) and a few example fields.
    """
    ma = tk.model_attributes
    df_baseline = tk.baseline() if df_baseline is None else df_baseline
    fields = ma.all_variable_fields_input if fields is None else fields
    fields = [f for f in fields if f in df_baseline.columns and f in df_transformed.columns]

    b = df_baseline[fields].to_numpy(dtype=float)
    x = df_transformed[fields].to_numpy(dtype=float)
    rel = _relative_change(x, b)
    score = rel.max(axis=0)
    changed = score > threshold

    if not changed.any():
        return {"n_fields_changed": 0, "n_variables_changed": 0, "top_variables": []}

    delta = x - b
    idx_max = np.abs(delta).argmax(axis=0)
    signed = delta[idx_max, np.arange(delta.shape[1])]

    df = pd.DataFrame({"field": fields, "score": score, "delta": signed})[changed]
    df["variable"] = df["field"].map(ma.dict_variable_fields_to_model_variables)
    df = df.dropna(subset=["variable"])

    units = _units_by_variable(ma)
    rows = []
    for variable, grp in df.groupby("variable"):
        n_up = int((grp["delta"] > 0).sum())
        n_down = int((grp["delta"] < 0).sum())
        if n_up and n_down:
            direction = "shifts"
        elif n_up:
            direction = "increases"
        elif n_down:
            direction = "decreases"
        else:
            direction = "no_change"
        grp = grp.sort_values("score", ascending=False)
        mv = ma.get_variable(variable)
        rows.append(
            {
                "variable": variable,
                "kind": kind,
                "label": clean_label(variable),
                "subsector": _variable_subsector(ma, variable),
                "units": units.get(variable),
                "direction": direction,
                "max_relative_change": round(float(grp["score"].iloc[0]), 4),
                "n_fields_changed": int(len(grp)),
                "n_fields_total": len(mv.fields) if mv is not None else None,
                "example_fields": grp["field"].head(3).tolist(),
            }
        )

    rows.sort(key=lambda r: r["max_relative_change"], reverse=True)
    return {
        "n_fields_changed": int(len(df)),
        "n_variables_changed": len(rows),
        "top_variables": rows[:top_n],
    }


_UNITS_CACHE: Dict[int, Dict[str, str]] = {}


def _units_by_variable(ma) -> Dict[str, str]:
    """variable -> short unit string from build_modvar_attributes (e.g. 'mass: mt')."""
    key = id(ma)
    if key in _UNITS_CACHE:
        return _UNITS_CACHE[key]
    try:
        df = ma.build_modvar_attributes()
    except Exception:
        logger.exception("build_modvar_attributes failed; no units")
        _UNITS_CACHE[key] = {}
        return {}
    dims = [c for c in df.columns if c != "variable"]
    out = {}
    for rec in df.to_dict("records"):
        parts = [f"{d}: {rec[d]}" for d in dims if isinstance(rec.get(d), str) and rec[d]]
        if parts:
            out[rec["variable"]] = ", ".join(parts)
    _UNITS_CACHE[key] = out
    return out


def _variable_subsector(ma, variable: str) -> Optional[str]:
    for subsector, variables in ma.dict_model_variables_by_subsector.items():
        if variable in variables:
            return subsector
    return None


##########################
#    EMISSION EFFECTS    #
##########################


def emission_total_fields(ma) -> Dict[str, str]:
    """subsector abbreviation -> emission_co2e_subsector_total_<abv> field."""
    return ma.get_all_subsector_emission_total_fields(return_type="dict_abv")


def gas_total_emission_fields(ma) -> List[str]:
    """Every field that makes up total emissions, by gas
    (`ma.dict_gas_to_total_emission_fields`). Unlike the subsector totals, it
    leaves out the `emission_co2e_hfcs_ippu_*` aggregates, which restate the
    individual HFC gases: emission_co2e_subsector_total_ippu counts them twice
    (+15.9 MtCO2e in 2050 on the Egypt baseline)."""
    return sum(list(ma.dict_gas_to_total_emission_fields.values()), [])


def _fields_by_subsector(ma, columns) -> Dict[str, List[str]]:
    """subsector abbreviation -> its gas-total emission fields present in `columns`."""
    present = set(columns)
    out: Dict[str, List[str]] = {}
    for abv in emission_total_fields(ma):
        fields = [f for f in gas_total_emission_fields(ma) if f in present and f.split("_")[3:4] == [abv]]
        if fields:
            out[abv] = fields
    return out


def compute_emission_effects(
    ma,
    df_out_baseline: pd.DataFrame,
    df_out_transformed: pd.DataFrame,
    year_index: int = -1,
) -> Dict[str, Any]:
    """Change in emissions (MtCO2e) at one time period (default: the last)
    between two model outputs, summed over gas_total_emission_fields by subsector."""
    fields = _fields_by_subsector(ma, df_out_baseline.columns)
    # some fields are blank (NaN) in some years: count them as zero
    df_out_baseline = df_out_baseline.fillna({f: 0.0 for fs in fields.values() for f in fs})
    df_out_transformed = df_out_transformed.fillna({f: 0.0 for fs in fields.values() for f in fs})
    base = pd.Series({abv: float(df_out_baseline[f].iloc[year_index].sum()) for abv, f in fields.items()})
    trns = pd.Series({abv: float(df_out_transformed[f].iloc[year_index].sum()) for abv, f in fields.items()})
    delta = trns - base
    total_base = float(base.sum())
    total_delta = float(delta.sum())
    by_subsector = {abv: round(float(delta[abv]), 4) for abv in fields if abs(float(delta[abv])) > 1e-6}

    sector_of = subsector_to_sector(ma)
    by_sector: Dict[str, float] = {}
    for abv in fields:
        sector = sector_of.get(abv)
        if sector is not None:
            by_sector[sector] = by_sector.get(sector, 0.0) + float(delta[abv])
    by_sector = {s: round(v, 4) for s, v in by_sector.items() if abs(v) > 1e-6}

    cols = [f for fs in fields.values() for f in fs]
    cumulative_delta = float((df_out_transformed[cols] - df_out_baseline[cols]).to_numpy().sum())

    return {
        "year_index": year_index,
        "total_baseline_mtco2e": round(total_base, 3),
        "total_delta_mtco2e": round(total_delta, 4),
        "total_delta_pct": round(100 * total_delta / total_base, 3) if total_base else None,
        "cumulative_delta_mtco2e": round(cumulative_delta, 3),
        "by_sector_delta_mtco2e": by_sector,
        "by_subsector_delta_mtco2e": by_subsector,
    }


def output_driver_fields(ma) -> List[str]:
    """Output fields that are not emissions (activity, capacity, land, ...).
    Emissions are reported separately as one line per sector."""
    return [f for f in ma.all_variable_fields_output if not f.startswith("emission_")]


def subsector_to_sector(ma) -> Dict[str, str]:
    """subsector abbreviation (e.g. 'agrc') -> sector name (e.g. 'AFOLU')."""
    table = ma.get_subsector_attribute_table().table
    return dict(zip(table["abbreviation_subsector"], table["sector"]))


def classify_emissions(
    code: str,
    effects: Dict[str, Any],
    requires_fp_model_primary: bool,
    threshold: float = EMISSIONS_NO_CHANGE_THRESHOLD,
) -> Dict[str, str]:
    """Direction label for "emissions if used alone".

    `direction_raw` is what the run without the electricity model shows.
    `direction` corrects it for transformers whose main effect happens in
    the electricity/fuel-production model (NemoMod), which the offline run
    skips. This is a heuristic; curate it in the YAML.
    """
    total_base = effects.get("total_baseline_mtco2e") or 0.0
    total_delta = effects.get("total_delta_mtco2e") or 0.0
    rel = abs(total_delta) / total_base if total_base else 0.0
    if rel < threshold:
        raw = "no_change"
    else:
        raw = "decreases" if total_delta < 0 else "increases"

    direction = raw
    if requires_fp_model_primary:
        if any(tok in code for tok in _GRID_DEPENDENT_TOKENS):
            direction = "depends_on_grid"
        elif raw == "no_change":
            direction = "needs_electricity_model"
    return {"direction_raw": raw, "direction": direction}


##########################
#    CATALOG BUILDING    #
##########################


def build_entry(
    tk,
    code: str,
    models=None,
    df_out_baseline: Optional[pd.DataFrame] = None,
    regions: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """`computed` block for one transformer. Never raises: failures are
    recorded as status 'error' with the message."""
    tkernel = tk.get_tkernel(code)
    attr = _attribute_row(tk, code)
    fp_primary = bool(attr.get("requires_fp_model_for_primary_effect") or 0)
    fp_full = bool(attr.get("requires_fp_model_for_full_effect") or 0)

    subsector = _subsector_abv(code)
    computed: Dict[str, Any] = {
        "name": tkernel.name,
        "sector": subsector_to_sector(tk.model_attributes).get(subsector, attr.get("sector")),
        "subsector": subsector,
        "description": tkernel.description,
        "description_long": attr.get("description_long"),
        "units_description": attr.get("units_description"),
        "requires_electricity_model": {"primary_effect": fp_primary, "full_effect": fp_full},
        "electricity_model_note": attr.get("description_of_fp_model_interaction"),
        "magnitude": main_magnitude_param(tkernel),
    }

    try:
        df_transformed = tkernel()
    except Exception as e:
        logger.warning("transformer %s failed with default parameters: %s", code, e)
        computed.update({"status": "error", "error": f"{type(e).__name__}: {e}"})
        return computed

    try:
        computed.update(compute_variable_effects(tk, df_transformed))
    except Exception as e:
        logger.exception("variable effects failed for %s", code)
        computed.update({"status": "error", "error": f"variable effects: {type(e).__name__}: {e}"})
        return computed

    computed["status"] = "ok" if computed["n_fields_changed"] else "no_effect_on_baseline"

    if models is not None and df_out_baseline is not None:
        try:
            df_out = models.project(df_transformed, include_nemo_fuel_production=False, regions=regions)
            effects = compute_emission_effects(tk.model_attributes, df_out_baseline, df_out)
            effects.update(classify_emissions(code, effects, fp_primary))
            computed["emissions_alone"] = effects
            out_effects = compute_variable_effects(
                tk,
                df_out,
                df_baseline=df_out_baseline,
                fields=output_driver_fields(tk.model_attributes),
                kind="output",
            )
            computed["top_output_variables"] = out_effects["top_variables"]
        except Exception as e:
            logger.exception("emissions run failed for %s", code)
            computed["emissions_alone"] = {"direction": None, "error": f"{type(e).__name__}: {e}"}

    return computed


def build_library_entry(
    tk,
    transformation,
    models,
    df_out_baseline: pd.DataFrame,
    regions: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """"Emissions if used alone" for one library transformation, with its own
    parameters (e.g. the NDC magnitude), classified like its transformer.
    Never raises: failures are recorded under `error`."""
    code_tfr = transformation.transformer_code
    entry: Dict[str, Any] = {"transformer": code_tfr}
    try:
        df_out = models.project(transformation(), include_nemo_fuel_production=False, regions=regions)
        effects = compute_emission_effects(tk.model_attributes, df_out_baseline, df_out)
        fp_primary = bool(_attribute_row(tk, code_tfr).get("requires_fp_model_for_primary_effect") or 0)
        effects.update(classify_emissions(code_tfr, effects, fp_primary))
        entry["emissions_alone"] = effects
    except Exception as e:
        logger.exception("emissions run failed for %s", transformation.code)
        entry["emissions_alone"] = {"direction": None, "error": f"{type(e).__name__}: {e}"}
    return entry


def library_direction(catalog: dict, transformation_code: str) -> Optional[str]:
    """Direction of "emissions if used alone" for a library transformation, or None if not computed."""
    entry = ((catalog or {}).get("library") or {}).get(transformation_code) or {}
    return (entry.get("emissions_alone") or {}).get("direction")


def seed_curated(code: str, computed: Dict[str, Any]) -> Dict[str, Any]:
    curated = dict(_CURATED_TEMPLATE)
    curated["pair_with"] = []
    emis = computed.get("emissions_alone") or {}
    if emis.get("direction") == "depends_on_grid" and code != _GRID_PAIR:
        curated["pair_with"] = [_GRID_PAIR]
    return curated


def merge_catalog(
    new_computed: Dict[str, Dict[str, Any]],
    existing: Optional[dict],
    meta: Dict[str, Any],
    library: Optional[Dict[str, Dict[str, Any]]] = None,
) -> dict:
    """Replace every `computed` block; keep existing `curated` blocks (adding
    any template keys they lack); seed `curated` for new transformers.
    Entries for transformers no longer in sisepuede are kept but flagged."""
    old_entries = (existing or {}).get("transformers", {}) or {}
    entries = {}
    for code, computed in new_computed.items():
        old_curated = (old_entries.get(code) or {}).get("curated")
        if old_curated:
            curated = {**_CURATED_TEMPLATE, **old_curated}
        else:
            curated = seed_curated(code, computed)
        entries[code] = {"curated": curated, "computed": computed}
    for code, old in old_entries.items():
        if code not in entries:
            entries[code] = {**old, "computed": {**(old.get("computed") or {}), "status": "missing_in_sisepuede"}}
    out = {"schema_version": SCHEMA_VERSION, "meta": meta, "transformers": dict(sorted(entries.items()))}
    library = library if library is not None else (existing or {}).get("library")
    if library:
        out["library"] = dict(sorted(library.items()))
    return out


def load_catalog(path=None) -> dict:
    path = pathlib.Path(path or default_catalog_path())
    if not path.exists():
        return {"schema_version": SCHEMA_VERSION, "meta": {}, "transformers": {}}
    with open(path) as f:
        return yaml.safe_load(f) or {"transformers": {}}


def save_catalog(catalog: dict, path=None) -> None:
    path = pathlib.Path(path or default_catalog_path())
    header = (
        "# Transformer metadata for the Pathways page. Generated by\n"
        "# scripts/build_transformer_metadata.py.\n"
        "#\n"
        "# Each transformer has two blocks:\n"
        "#   curated:  edit by hand. Kept when the script is re-run. Non-null\n"
        "#             values override `computed`. Set reviewed: true when done.\n"
        "#   computed: regenerated on every run; do not edit.\n"
        "#\n"
        "# curated.top_variables: list of {variable, label, direction}, where\n"
        "#   direction is one of increases | decreases | shifts | no_change.\n"
        "# curated.emissions_direction: decreases | increases | no_change |\n"
        "#   depends_on_grid | needs_electricity_model\n"
    )
    with open(path, "w") as f:
        f.write(header)
        yaml.safe_dump(catalog, f, sort_keys=False, allow_unicode=True, width=100)


##########################
#    UI-FACING ACCESS    #
##########################


MAX_INPUT_VARIABLES_DISPLAYED = 2

# Whether a transformer needs the electricity dispatch (NemoMod), from the
# attribute table's requires_fp_model_for_{primary,full}_effect flags:
# "needed" = its main effect is only computed with the dispatch; "optional" =
# the dispatch only adds indirect energy effects.
ELECTRICITY_NEEDS = {
    "needed": (
        "Needs electricity dispatch",
        "Its main effect is only calculated when the electricity dispatch (NemoMod) runs.",
    ),
    "optional": (
        "Electricity dispatch optional",
        "Its main effect is calculated without the electricity dispatch; running it adds indirect effects on energy.",
    ),
    "not_needed": ("No electricity dispatch needed", "The electricity dispatch does not change its effect."),
}


def electricity_need(requires: Optional[Dict[str, Any]]) -> str:
    """'needed' | 'optional' | 'not_needed' from a card's requires_electricity_model."""
    requires = requires or {}
    if requires.get("primary_effect"):
        return "needed"
    if requires.get("full_effect"):
        return "optional"
    return "not_needed"


def pick_display_variables(
    inputs: List[Dict[str, Any]],
    outputs: List[Dict[str, Any]],
    n: int = N_VARIABLES_DISPLAYED,
) -> List[Dict[str, Any]]:
    """Up to `n` rows for "what this moves": the levers the transformer sets
    (inputs, at most 2) first, then the outputs that move the most. Either
    side fills the other's slots when it has fewer."""
    n_in = min(len(inputs), MAX_INPUT_VARIABLES_DISPLAYED, n)
    picked = list(inputs[:n_in])
    picked += outputs[: n - len(picked)]
    picked += inputs[n_in : n_in + n - len(picked)]
    return picked


def get_card(code: str, catalog: dict, tk=None) -> Dict[str, Any]:
    """Everything the transformer view needs, curated values first.

    Falls back to the transformer attribute table (via `tk`) for a
    transformer missing from the YAML, and to a live variable diff when the
    YAML has no variables for it (no emissions in that case).
    """
    entry = (catalog.get("transformers") or {}).get(code) or {}
    curated = entry.get("curated") or {}
    computed = dict(entry.get("computed") or {})

    if not computed and tk is not None:
        try:
            computed = {"name": tk.get_tkernel(code).name, "description": tk.get_tkernel(code).description}
            computed.update(compute_variable_effects(tk, tk.get_tkernel(code)()))
            computed["status"] = "live"
            attr = _attribute_row(tk, code)
            computed["requires_electricity_model"] = {
                "primary_effect": bool(attr.get("requires_fp_model_for_primary_effect") or 0),
                "full_effect": bool(attr.get("requires_fp_model_for_full_effect") or 0),
            }
            computed["electricity_model_note"] = attr.get("description_of_fp_model_interaction")
        except Exception as e:
            computed.setdefault("status", "error")
            computed["error"] = f"{type(e).__name__}: {e}"

    magnitude = computed.get("magnitude") or {}
    emis = computed.get("emissions_alone") or {}
    variables = curated.get("top_variables") or pick_display_variables(
        computed.get("top_variables") or [], computed.get("top_output_variables") or []
    )

    return {
        "code": code,
        "name": curated.get("name") or strip_subsector_prefix(computed.get("name") or code),
        "name_full": computed.get("name"),
        "description": curated.get("short_description") or clean_label(computed.get("description")),
        "description_long": clean_label(computed.get("description_long")),
        "sector": computed.get("sector"),
        "subsector": computed.get("subsector"),
        "magnitude_param": magnitude.get("param"),
        "magnitude_default": magnitude.get("default"),
        # short label only when curated; the attribute table's sentence is help text
        "magnitude_label": curated.get("magnitude_label"),
        "magnitude_help": curated.get("magnitude_help") or clean_label(computed.get("units_description")),
        "top_variables": variables,
        "emissions_direction": curated.get("emissions_direction") or emis.get("direction"),
        "emissions": emis,
        "requires_electricity_model": computed.get("requires_electricity_model") or {},
        "electricity_model_note": computed.get("electricity_model_note"),
        "electricity_need": electricity_need(computed.get("requires_electricity_model")),
        "pair_with": curated.get("pair_with") or [],
        "notes": curated.get("notes"),
        "status": computed.get("status"),
        "error": computed.get("error"),
        "reviewed": bool(curated.get("reviewed")),
    }

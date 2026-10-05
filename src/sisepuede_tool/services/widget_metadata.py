"""Turns a Transformer's Python function signature into a list of ParamSpec,
so the Transformation Designer page can auto-generate a parameter form.

There is no declarative schema anywhere in sisepuede for parameter bounds or
category choices -- only `inspect.signature` gives names/types/defaults. This
module resolves specs in three tiers, each layered on top of the last:

1. Introspection: infer widget kind + a reasonable default numeric range from
   the Python default value's type.
2. Category resolution: for List[str]-typed params, look up real category
   choices from the relevant `attribute_cat_*` table (via the subsector
   parsed out of the transformer's code), when the mapping is known.
3. Guided schemas (resources/param_schemas.yaml, see
   param_schema_service): valid keys, units and sum rules for dict and
   category-list parameters, which turn them into tables or selects.
4. Hand-curated overrides (resources/transformer_widget_metadata.yaml):
   refine bounds/choices/help text/label/tier per (transformer_code,
   parameter_name) as they're discovered to need it.

Every spec also gets a tier (see `default_tier`): the main magnitude and the
implementation ramp are "basic", everything else "advanced". `return_*`
helper flags (which make a transformer return a dict instead of a
DataFrame) are never shown.
"""

import functools
import inspect
import pathlib
import re
from typing import Any, Dict, List, Optional, Tuple, Union

import yaml
from sisepuede.core.model_attributes import ModelAttributes
from sisepuede.transformers.transformer_kernels import TransformerKernel, TransformerKernels

from sisepuede_tool.models.param_spec import TIER_ADVANCED, TIER_BASIC, TIERS, ParamSpec, WidgetKind
from sisepuede_tool.services import param_schema_service as pss

_SKIP_PARAMS = {"df_input", "strat", "self"}
_RAMP_PARAM_NAME = "vec_implementation_ramp"
_HIDDEN_PARAM_PREFIX = "return_"

# Subsector code (as it appears in a transformer's "TFR:SUBSEC:ACTION" code)
# -> key into ModelAttributes.dict_attributes["cat"]. Best-effort: not every
# subsector maps cleanly to a single category table (e.g. PFLO is
# cross-sector), and those are left unmapped -- callers fall back to free
# text in that case.
_SUBSECTOR_TO_CATEGORY_KEY = {
    "AGRC": "agriculture",
    "CCSQ": "ccsq",
    "ENFU": "fuel",
    "ENTC": "technology",
    "FGTV": "fuel",
    "FRST": "forest",
    "INEN": "industry",
    "IPPU": "industry",
    "LNDU": "landuse",
    "LSMM": "manure_management",
    "LVST": "livestock",
    "SCOE": "scoe",
    "SOIL": "soil_management",
    "TRDE": "transportation_demand",
    "TRNS": "transportation",
    "TRWW": "wastewater_treatment",
    "WALI": "waste_liquid",
    "WASO": "waste_solid",
}


def _numeric_bounds(default: float) -> Tuple[float, float]:
    if 0 <= default <= 1:
        return (0.0, 1.0)
    if default > 1:
        return (0.0, max(2 * default, 1.0))
    if default < 0:
        return (min(2 * default, -1.0), 0.0)
    return (0.0, 1.0)


def _resolve_categories(
    subsector_code: Optional[str], model_attributes: ModelAttributes
) -> Optional[List[str]]:
    if subsector_code is None:
        return None
    category_key = _SUBSECTOR_TO_CATEGORY_KEY.get(subsector_code)
    if category_key is None:
        return None
    table = model_attributes.dict_attributes.get("cat", {}).get(category_key)
    if table is None:
        return None
    return list(table.key_values)


def _parse_help_text(func) -> Dict[str, str]:
    """Best-effort numpydoc 'Parameters' block parser.

    Docstring formatting isn't guaranteed consistent across ~70 hand-written
    transformer functions, so any parse hiccup just yields no help text for
    that parameter rather than raising.
    """
    doc = inspect.getdoc(func) or ""
    help_by_param: Dict[str, str] = {}
    try:
        lines = doc.splitlines()
        in_params = False
        current: Optional[str] = None
        for line in lines:
            stripped = line.strip()
            if stripped == "Parameters":
                in_params = True
                continue
            if not in_params:
                continue
            if set(stripped) == {"-"}:
                continue
            m = re.match(r"^(\w+)\s*:\s*.*$", line)
            if m:
                current = m.group(1)
                help_by_param[current] = ""
            elif current is not None and stripped:
                help_by_param[current] = (help_by_param[current] + " " + stripped).strip()
    except Exception:
        return {}
    return help_by_param


def _ramp_default(transformers_catalog: TransformerKernels) -> dict:
    return {
        "n_tp_ramp": transformers_catalog.n_tp_ramp,
        "tp_0_ramp": transformers_catalog.tp_0_ramp,
        "alpha_logistic": transformers_catalog.alpha_logistic,
        "d": 0,
        "window_logistic": tuple(transformers_catalog.window_logistic),
    }


def _infer_spec(name: str, default: Any, annotation: Any, help_text: Optional[str]) -> ParamSpec:
    ann = str(annotation)

    if isinstance(default, bool):
        return ParamSpec(name=name, kind=WidgetKind.BOOL, default=default, help_text=help_text)

    if isinstance(default, (int, float)):
        return ParamSpec(
            name=name,
            kind=WidgetKind.NUMERIC,
            default=default,
            bounds=_numeric_bounds(float(default)),
            help_text=help_text,
        )

    if isinstance(default, list):
        return ParamSpec(name=name, kind=WidgetKind.CATEGORICAL_MULTI, default=default, help_text=help_text)

    if isinstance(default, dict):
        return ParamSpec(name=name, kind=WidgetKind.JSON, default=default, help_text=help_text)

    if isinstance(default, str):
        return ParamSpec(name=name, kind=WidgetKind.TEXT, default=default, help_text=help_text)

    # default is None (or unset) -- fall back to the type annotation
    if ("float" in ann or "int" in ann) and "Dict" not in ann and "List" not in ann:
        return ParamSpec(name=name, kind=WidgetKind.NUMERIC, default=0.0, help_text=help_text)
    if "Dict" in ann:
        return ParamSpec(name=name, kind=WidgetKind.JSON, default={}, help_text=help_text)
    if "List" in ann:
        return ParamSpec(name=name, kind=WidgetKind.CATEGORICAL_MULTI, default=[], help_text=help_text)
    if "str" in ann:
        return ParamSpec(name=name, kind=WidgetKind.TEXT, default="", help_text=help_text)

    return ParamSpec(name=name, kind=WidgetKind.JSON, default=None, help_text=help_text)


def main_magnitude_name(transformer: TransformerKernel) -> Optional[str]:
    """First numeric `magnitude*` parameter: the one basic users set."""
    for name, param in inspect.signature(transformer.function).parameters.items():
        if name in _SKIP_PARAMS or not name.startswith("magnitude"):
            continue
        default = param.default
        if isinstance(default, (int, float)) and not isinstance(default, bool):
            return name
    return None


def default_tier(name: str, main_magnitude: Optional[str]) -> str:
    if name == _RAMP_PARAM_NAME or name == main_magnitude:
        return TIER_BASIC
    return TIER_ADVANCED


@functools.lru_cache(maxsize=1)
def _shipped_schemas() -> dict:
    return pss.load_schemas()


def apply_schema(spec: ParamSpec, schema: dict, model_attributes: ModelAttributes) -> None:
    """Turn `spec` into the guided widget its param_schemas.yaml entry describes."""
    widget = schema.get("widget")
    resolved = dict(schema)
    if widget == pss.WIDGET_PAIRS:
        resolved["keys_out"] = pss.resolve_keys(schema.get("keys_out"), model_attributes)
        resolved["keys_in"] = pss.resolve_keys(schema.get("keys_in"), model_attributes)
        resolved["labels"] = {
            **pss.key_labels(schema.get("keys_out"), model_attributes),
            **pss.key_labels(schema.get("keys_in"), model_attributes),
        }
    else:
        resolved["keys"] = pss.resolve_keys(schema.get("keys"), model_attributes)
        resolved["labels"] = pss.key_labels(schema.get("keys"), model_attributes)
    spec.schema = resolved

    if widget in pss.TABLE_WIDGETS:
        spec.kind = WidgetKind.DICT_TABLE
    elif widget == pss.WIDGET_MULTI:
        spec.kind = WidgetKind.CATEGORICAL_MULTI
        spec.choices = resolved["labels"]
    elif widget == pss.WIDGET_SELECT:
        spec.kind = WidgetKind.SELECT
        spec.choices = resolved["labels"]
    elif widget == pss.WIDGET_NOTE:
        spec.kind = WidgetKind.NOTE
    if "default" in schema:
        spec.default = schema["default"]
    if "label" in schema:
        spec.label = schema["label"]
    if "help" in schema:
        spec.help_text = schema["help"]
    if "tier" in schema:
        spec.tier = schema["tier"]


def build_param_specs(
    transformer: TransformerKernel,
    model_attributes: ModelAttributes,
    transformers_catalog: TransformerKernels,
    overrides: Optional[dict] = None,
    schemas: Optional[dict] = None,
) -> List[ParamSpec]:
    """`schemas` defaults to the shipped resources/param_schemas.yaml."""
    sig = inspect.signature(transformer.function)
    help_by_param = _parse_help_text(transformer.function)
    subsector_code = transformer.code.split(":")[1] if transformer.code.count(":") >= 1 else None
    transformer_overrides = (overrides or {}).get(transformer.code, {})
    main_magnitude = main_magnitude_name(transformer)
    transformer_schemas = (_shipped_schemas() if schemas is None else schemas).get(transformer.code, {})

    specs: List[ParamSpec] = []
    for name, param in sig.parameters.items():
        if name in _SKIP_PARAMS or name.startswith(_HIDDEN_PARAM_PREFIX):
            continue

        default = param.default if param.default is not inspect.Parameter.empty else None
        help_text = help_by_param.get(name)

        if name == _RAMP_PARAM_NAME:
            spec = ParamSpec(
                name=name,
                kind=WidgetKind.RAMP_VECTOR,
                default=_ramp_default(transformers_catalog),
                extra={"total_time_periods": len(transformers_catalog.time_periods.all_time_periods)},
                help_text=help_text,
            )
        else:
            spec = _infer_spec(name, default, param.annotation, help_text)
            if spec.kind == WidgetKind.CATEGORICAL_MULTI:
                spec.choices = _resolve_categories(subsector_code, model_attributes)

        spec.tier = default_tier(name, main_magnitude)

        if name in transformer_schemas:
            apply_schema(spec, transformer_schemas[name], model_attributes)

        param_override = transformer_overrides.get(name, {})
        if param_override:
            if "bounds" in param_override:
                spec.bounds = tuple(param_override["bounds"])
            if "choices" in param_override:
                spec.choices = param_override["choices"]
            if "help_text" in param_override:
                spec.help_text = param_override["help_text"]
            if "kind" in param_override:
                spec.kind = WidgetKind(param_override["kind"])
            if "label" in param_override:
                spec.label = param_override["label"]
            if "tier" in param_override:
                if param_override["tier"] not in TIERS:
                    raise ValueError(
                        f"{transformer.code}.{name}: tier must be one of {TIERS}, got {param_override['tier']!r}"
                    )
                spec.tier = param_override["tier"]

        specs.append(spec)

    return specs


def load_overrides(path) -> dict:
    with open(path) as f:
        return yaml.safe_load(f) or {}


def default_overrides_path() -> pathlib.Path:
    import sisepuede_tool

    return pathlib.Path(sisepuede_tool.__file__).parent / "resources" / "transformer_widget_metadata.yaml"

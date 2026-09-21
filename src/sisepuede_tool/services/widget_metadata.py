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
3. Hand-curated overrides (resources/transformer_widget_metadata.yaml):
   refine bounds/choices/help text per (transformer_code, parameter_name) as
   they're discovered to need it. Ships mostly empty and grows over time.
"""

import inspect
import pathlib
import re
from typing import Any, Dict, List, Optional, Tuple, Union

import yaml
from sisepuede.core.model_attributes import ModelAttributes
from sisepuede.transformers.transformer_kernels import TransformerKernel, TransformerKernels

from sisepuede_tool.models.param_spec import ParamSpec, WidgetKind

_SKIP_PARAMS = {"df_input", "strat", "self"}
_RAMP_PARAM_NAME = "vec_implementation_ramp"

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


def build_param_specs(
    transformer: TransformerKernel,
    model_attributes: ModelAttributes,
    transformers_catalog: TransformerKernels,
    overrides: Optional[dict] = None,
) -> List[ParamSpec]:
    sig = inspect.signature(transformer.function)
    help_by_param = _parse_help_text(transformer.function)
    subsector_code = transformer.code.split(":")[1] if transformer.code.count(":") >= 1 else None
    transformer_overrides = (overrides or {}).get(transformer.code, {})

    specs: List[ParamSpec] = []
    for name, param in sig.parameters.items():
        if name in _SKIP_PARAMS:
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
                spec.extra["label"] = param_override["label"]

        specs.append(spec)

    return specs


def load_overrides(path) -> dict:
    with open(path) as f:
        return yaml.safe_load(f) or {}


def default_overrides_path() -> pathlib.Path:
    import sisepuede_tool

    return pathlib.Path(sisepuede_tool.__file__).parent / "resources" / "transformer_widget_metadata.yaml"

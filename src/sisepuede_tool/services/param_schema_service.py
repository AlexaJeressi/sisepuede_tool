"""Guided widgets for dict and category-list transformer parameters.

sisepuede has no schema for these parameters: the valid keys, the meaning of
the values and whether they must add up to 1 are only in the transformer
code. `resources/param_schemas.yaml` records them per (transformer_code,
parameter_name); this module loads it, resolves the category keys against
the live ModelAttributes and checks the sum rules.
"""

import pathlib
from typing import Any, Dict, List, Optional, Tuple

import yaml

WIDGET_SHARES = "shares"
WIDGET_VALUES = "values"
WIDGET_BOUNDS = "bounds"
WIDGET_PAIRS = "pairs"
WIDGET_MULTI = "multi"
WIDGET_SELECT = "select"
WIDGET_NOTE = "note"
TABLE_WIDGETS = (WIDGET_SHARES, WIDGET_VALUES, WIDGET_BOUNDS, WIDGET_PAIRS)

SUM_EQ1 = "eq1"
SUM_LEQ1 = "leq1"
SUM_NONE = "none"

BOUND_DIRECTIONS = ("min", "max")
BOUND_DELIM = "|"

# units whose values are fractions in sisepuede and shown as % in the UI
PERCENT_UNITS = ("share", "percent_change")

_SUM_TOL = 1e-6


def default_schemas_path() -> pathlib.Path:
    import sisepuede_tool

    return pathlib.Path(sisepuede_tool.__file__).parent / "resources" / "param_schemas.yaml"


def load_schemas(path=None) -> Dict[str, Dict[str, dict]]:
    """{transformer_code: {param: schema}}. Top-level keys starting with "_"
    hold YAML anchors and are dropped."""
    with open(path or default_schemas_path()) as f:
        raw = yaml.safe_load(f) or {}
    return {code: params for code, params in raw.items() if not code.startswith("_")}


def _table(model_attributes, table_name: str):
    table = model_attributes.dict_attributes.get("cat", {}).get(table_name)
    if table is None:
        raise KeyError(f"unknown category table {table_name!r}")
    return table


def resolve_keys(keys_spec: Optional[dict], model_attributes) -> List[str]:
    """Category keys for `{table: x}` (all of them) or `{table: x, only: [...]}`
    (that subset, in the order given)."""
    if not keys_spec:
        return []
    table = _table(model_attributes, keys_spec["table"])
    if "only" in keys_spec:
        valid = set(table.key_values)
        return [k for k in keys_spec["only"] if k in valid]
    return list(table.key_values)


def key_labels(keys_spec: Optional[dict], model_attributes) -> Dict[str, str]:
    """{key: display name} from the table's `category_name` column (matched
    by row, since the table order differs from `key_values`)."""
    if not keys_spec:
        return {}
    table = _table(model_attributes, keys_spec["table"])
    names = {}
    if "category_name" in table.table.columns:
        names = dict(zip(table.table[table.key], table.table["category_name"]))
    return {k: str(names.get(k) or humanize_key(k)) for k in resolve_keys(keys_spec, model_attributes)}


def humanize_key(key: str) -> str:
    """'fuel_natural_gas' -> 'Natural gas', 'pp_solar' -> 'Solar'."""
    for prefix in ("fuel_", "pp_", "fp_"):
        if key.startswith(prefix):
            key = key[len(prefix):]
            break
    return key.replace("_", " ").capitalize()


def is_percent(schema: dict) -> bool:
    return schema.get("unit") in PERCENT_UNITS


def check_sum(values: Dict[str, float], rule: Optional[str]) -> Tuple[bool, str]:
    """(ok, message) for fractions `values` under `rule`."""
    total = sum(v for v in values.values() if v is not None)
    pct = f"{total * 100:.4g}%"
    if rule == SUM_EQ1:
        if abs(total - 1.0) > _SUM_TOL:
            return False, f"The shares add up to {pct}; they must total exactly 100%."
    elif rule == SUM_LEQ1:
        if total > 1.0 + _SUM_TOL:
            return False, f"The shares add up to {pct}; the total can't be above 100%."
    return True, f"Total {pct}"


def normalize_for_rule(values: Dict[str, float], rule: Optional[str]) -> Dict[str, float]:
    """Remove float noise left by the % → fraction conversion, so a total that
    passed `check_sum` also passes sisepuede's own test (an exact `== 1` for
    eq1, `<= 1` for leq1)."""
    if not values or rule not in (SUM_EQ1, SUM_LEQ1):
        return values
    total = sum(values.values())
    if total <= 0 or (rule == SUM_LEQ1 and total <= 1.0):
        return values
    out = {k: v / total for k, v in values.items()}
    largest = max(out, key=out.get)
    out[largest] = 1.0 - sum(v for k, v in out.items() if k != largest)
    if sum(out.values()) > 1.0:  # still one ulp over: nudge down
        out[largest] -= 1e-15
    return out


def bound_key(key: str, direction: str) -> str:
    return f"{key}{BOUND_DELIM}{direction}"


def parse_bound_key(raw: Any) -> Optional[Tuple[str, str]]:
    """'cat|max' or ('cat', 'max') -> ('cat', 'max')."""
    if isinstance(raw, (tuple, list)) and len(raw) == 2:
        return str(raw[0]), str(raw[1])
    if isinstance(raw, str) and BOUND_DELIM in raw:
        cat, direction = raw.split(BOUND_DELIM, 1)
        return cat, direction
    return None


def expand_value(schema: dict, value: Any, keys: List[str]) -> Dict[str, Any]:
    """A transformation's current value as {key: value} for a values/shares
    table. sisepuede also accepts one number for every key (e.g. the 0.2
    default of SCOE:INC_EFFICIENCY_HEAT)."""
    if isinstance(value, bool):
        return {}
    if isinstance(value, (int, float)):
        return {k: float(value) for k in keys}
    if isinstance(value, dict):
        return dict(value)
    return {}

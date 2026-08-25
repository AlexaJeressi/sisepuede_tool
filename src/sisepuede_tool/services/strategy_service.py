"""Building bare `Strategy` objects from user-selected Transformations.

Every Strategy is strictly the composition of transformation codes the user
selected in the Strategy Builder -- never sourced from the shipped default
strategy library (attribute_dim_strategy_id.csv / attribute_strategy_code.csv).

Important, verified empirically: sisepuede's own `Strategy._initialize_function`
resolves the actual application order by filtering
`transformations.attribute_transformation.key_values` (sorted alphabetically
by transformation_code) down to the selected codes -- it does NOT preserve
the order codes are passed in. So the codes a caller passes are a *set*, not
a *sequence*; `resolve_application_order()` below computes what will really
run, for the UI to display honestly instead of implying user-controlled
ordering that doesn't exist.
"""

from typing import Iterable, List

import pandas as pd
import sisepuede.transformers as trf

DEFAULT_STRATEGY_ID_START = 1000


def next_available_strategy_id(existing_ids: Iterable[int], start: int = DEFAULT_STRATEGY_ID_START) -> int:
    existing = set(existing_ids)
    candidate = start
    while candidate in existing:
        candidate += 1
    return candidate


def build_baseline_strategy(transformations_obj: trf.Transformations) -> trf.Strategy:
    return trf.Strategy(
        0,
        [transformations_obj.code_baseline],
        transformations_obj,
        dict_attributes={"code": "BASE", "name": "Baseline"},
        prebuild=False,
    )


def build_strategy(
    strategy_id: int,
    transformation_codes: List[str],
    transformations_obj: trf.Transformations,
    name: str,
    description: str = "",
) -> trf.Strategy:
    if not transformation_codes:
        raise ValueError("A strategy needs at least one selected transformation.")

    return trf.Strategy(
        strategy_id,
        list(transformation_codes),
        transformations_obj,
        dict_attributes={"code": f"STRAT_{strategy_id}", "name": name, "description": description},
        prebuild=False,
    )


def resolve_application_order(
    transformation_codes: Iterable[str], transformations_obj: trf.Transformations
) -> List[str]:
    codes = set(transformation_codes)
    return [c for c in transformations_obj.attribute_transformation.key_values if c in codes]


def dry_run(strategy: trf.Strategy, df_baseline: pd.DataFrame) -> pd.DataFrame:
    """Apply the strategy to a baseline DataFrame to surface parameter/shape
    errors early. A failure here may be a bug in one of the underlying
    transformer implementations rather than a mistake in the strategy
    composition itself -- callers should present it as informational, not
    block saving on it (M4's per-strategy error isolation is the real
    safety net for that)."""
    return strategy(df_input=df_baseline)

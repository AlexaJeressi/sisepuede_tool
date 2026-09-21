"""Enumerating available ModelVariables and extracting their values from a
run's input or output data, for the Emissions and Drivers page's chart.
"""

from typing import Dict, List, Optional, Tuple

import pandas as pd
from sisepuede.core.model_attributes import ModelAttributes

from sisepuede_tool.models.run_result import RunResult


def get_variable_catalog(model_attributes: ModelAttributes) -> pd.DataFrame:
    """[sector, subsector, variable] for every ModelVariable the model
    knows about -- independent of any run, so this can be built once per
    ModelAttributes instance and reused across the whole session (see
    ui/state.py io_fields_cache). `variable` is a ModelVariable name (e.g.
    "Above Ground Residue Dry Matter Intercept"), which may expand to
    several category-specific fields at extraction time -- not a raw
    column name."""
    subsector_attr = model_attributes.get_subsector_attribute_table().table[["sector", "subsector"]].drop_duplicates()

    rows = [
        {"subsector": subsector, "variable": variable}
        for subsector, variables in model_attributes.dict_model_variables_by_subsector.items()
        for variable in variables
    ]
    catalog = pd.DataFrame(rows, columns=["subsector", "variable"])
    return catalog.merge(subsector_attr, on="subsector", how="left")[["sector", "subsector", "variable"]]


def extract_variable_frame(
    model_attributes: ModelAttributes,
    df: pd.DataFrame,
    variable: str,
    categories: Optional[List[str]] = None,
) -> Optional[pd.DataFrame]:
    """Long-format [time_period, category, value] for one ModelVariable
    pulled from `df` (a run's df_input or df_output). `category` is the
    variable name itself for a variable with no categories; otherwise one
    row-group per category, optionally narrowed to `categories`. Returns
    None if the variable's fields aren't present in `df`.

    `extract_model_variable(..., throw_error_on_missing_fields=False)` is
    documented to return None (not raise) when a variable's fields aren't
    found, but doesn't honor that when *none* of the fields are present at
    all -- it raises ValueError from deep inside its own missing-fields
    handling instead (a bug in sisepuede, not something fixable from here).
    Caught below so this function's own "returns None" contract holds
    regardless."""
    try:
        extracted = model_attributes.extract_model_variable(
            df, variable, include_time_period=True, throw_error_on_missing_fields=False
        )
    except ValueError:
        return None
    if extracted is None:
        return None

    all_categories = model_attributes.get_variable_categories(variable)

    if all_categories is None:
        value_col = next(c for c in extracted.columns if c != "time_period")
        long = extracted[["time_period", value_col]].rename(columns={value_col: "value"})
        long["category"] = variable
        return long

    mv = model_attributes.get_variable(variable)
    field_to_category = dict(zip(mv.fields, all_categories))
    keep_categories = categories if categories else all_categories
    keep_fields = [f for f, c in field_to_category.items() if c in keep_categories]

    long = extracted[["time_period"] + keep_fields].melt(id_vars="time_period", var_name="field", value_name="value")
    long["category"] = long["field"].map(field_to_category)
    return long.drop(columns="field")


def assemble_plot_frame(
    model_attributes: ModelAttributes,
    run_results: Dict[Tuple[int, str], RunResult],
    variable: Optional[str],
    categories: Optional[List[str]],
    data_source: str,
    combinations: List[Tuple[int, str]],
    strategy_labels: Dict[int, str],
    baseline_labels: Dict[str, str],
) -> pd.DataFrame:
    """Long-format [time_period, category, value, strategy, baseline]
    across the selected successful run results, for one ModelVariable --
    ready for a Plotly line chart overlaying strategy and baseline as
    separate series, faceted by category."""
    frames = []
    if variable:
        for strategy_id, baseline_id in combinations:
            result = run_results.get((strategy_id, baseline_id))
            if result is None or not result.ok:
                continue
            df = result.df_input if data_source == "input" else result.df_output
            if df is None:
                continue

            long = extract_variable_frame(model_attributes, df, variable, categories)
            if long is None or long.empty:
                continue
            long = long.copy()
            long["strategy"] = strategy_labels.get(strategy_id, str(strategy_id))
            long["baseline"] = baseline_labels.get(baseline_id, baseline_id)
            frames.append(long)

    if not frames:
        return pd.DataFrame(columns=["time_period", "category", "value", "strategy", "baseline"])
    return pd.concat(frames, ignore_index=True)

"""Enumerating available output variables and assembling long-format data
for the Output Explorer's charts.
"""

from typing import Dict, List, Tuple

import pandas as pd
from sisepuede.core.model_attributes import ModelAttributes

from sisepuede_tool.models.run_result import RunResult


def get_output_catalog(model_attributes: ModelAttributes) -> pd.DataFrame:
    """[sector, subsector, variable, emission_subsector, color_default] for
    every output field the model knows about -- independent of any run, so
    this can be built once per ModelAttributes instance and reused across
    the whole session (see ui/state.py io_fields_cache)."""
    subsector_attr = model_attributes.get_subsector_attribute_table().table[
        ["sector", "subsector", "emission_subsector", "color_default"]
    ]

    frames = []
    for sector in model_attributes.get_sector_list_from_projection_input(None):
        subsectors = model_attributes.get_sector_subsectors(sector)
        _vars_in, vars_out_df = model_attributes.get_input_output_fields(subsectors, build_df_q=True)
        vars_out_df = vars_out_df.copy()
        vars_out_df["sector"] = sector
        frames.append(vars_out_df)

    catalog = pd.concat(frames, ignore_index=True)
    catalog = catalog.merge(subsector_attr, on=["sector", "subsector"], how="left")
    return catalog[["sector", "subsector", "variable", "emission_subsector", "color_default"]]


def assemble_plot_frame(
    run_results: Dict[Tuple[int, str], RunResult],
    variables: List[str],
    combinations: List[Tuple[int, str]],
    strategy_labels: Dict[int, str],
    baseline_labels: Dict[str, str],
) -> pd.DataFrame:
    """Long-format [time_period, variable, value, strategy, baseline] across
    the selected successful run results and variables -- ready for a Plotly
    line chart overlaying strategy and baseline as separate series."""
    frames = []
    for strategy_id, baseline_id in combinations:
        result = run_results.get((strategy_id, baseline_id))
        if result is None or not result.ok or result.df_output is None:
            continue
        df = result.df_output
        present_vars = [v for v in variables if v in df.columns]
        if not present_vars or "time_period" not in df.columns:
            continue
        melted = df[["time_period"] + present_vars].melt(
            id_vars="time_period", var_name="variable", value_name="value"
        )
        melted["strategy"] = strategy_labels.get(strategy_id, str(strategy_id))
        melted["baseline"] = baseline_labels.get(baseline_id, baseline_id)
        frames.append(melted)

    if not frames:
        return pd.DataFrame(columns=["time_period", "variable", "value", "strategy", "baseline"])
    return pd.concat(frames, ignore_index=True)

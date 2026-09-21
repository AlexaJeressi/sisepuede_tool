"""Turning SISEPUEDE run results into cost/benefit figures via
`costs_benefits_ssp.CBSSPWrapperForDFComparison`.

The wrapper needs one wide DataFrame per baseline -- input drivers and model
output side by side, one row per (strategy_id, time_period) -- plus a
strategy attribute table shaped like `strategy_definitions.csv`
(`persistence_service.strategies_to_dataframe`). It has no baseline/scenario
dimension of its own, so cost/benefit figures are computed once per
baseline_id, never across baselines combined.
"""

import pathlib
from typing import Dict, List, Optional, Tuple

import pandas as pd
from costs_benefits_ssp.cb_ssp_wrapper_for_df_comparison import CBSSPWrapperForDFComparison
from sisepuede.core.model_attributes import ModelAttributes

from sisepuede_tool.models.run_result import RunResult
from sisepuede_tool.models.strategy_entry import StrategyEntry
from sisepuede_tool.services import persistence_service


def build_cb_wrapper(
    model_attributes: ModelAttributes, cb_config_path: pathlib.Path
) -> CBSSPWrapperForDFComparison:
    return CBSSPWrapperForDFComparison(model_attributes, cb_config_path)


def _merge_input_output(
    df_input: pd.DataFrame,
    df_output: pd.DataFrame,
    strategy_id: int,
    model_attributes: ModelAttributes,
) -> pd.DataFrame:
    """Wide-merge one strategy's transformed input and SISEPUEDE output on
    (dim_strategy_id, dim_time_period). `df_output` carries neither
    dim_strategy_id nor region (confirmed empirically -- SISEPUEDE's output
    is otherwise unindexed by either), so both are added here before the
    merge; `df_input` already carries both. For columns present in both
    frames (pass-through driver variables the model also echoes into its
    output), the output's value wins -- it reflects the model's final,
    post-transformation state.
    """
    key_strategy = model_attributes.dim_strategy_id
    key_time = model_attributes.dim_time_period

    df_output = df_output.copy()
    df_output[key_strategy] = strategy_id
    if "region" not in df_output.columns:
        region_by_time = df_input.set_index(key_time)["region"]
        df_output["region"] = df_output[key_time].map(region_by_time)

    overlap = (set(df_input.columns) & set(df_output.columns)) - {key_strategy, key_time}
    df_input_reduced = df_input.drop(columns=list(overlap))

    return df_input_reduced.merge(df_output, on=[key_strategy, key_time], how="inner")


def build_wide_results(
    run_results: Dict[Tuple[int, str], RunResult],
    baseline_id: str,
    strategy_ids: List[int],
    model_attributes: ModelAttributes,
) -> pd.DataFrame:
    """Merge and concatenate every successful (strategy_id, baseline_id)
    RunResult for the given baseline into one wide DataFrame -- one strategy's
    input+output per row-block, stacked row-wise across strategies."""
    frames = []
    for strategy_id in strategy_ids:
        result = run_results.get((strategy_id, baseline_id))
        if result is None or not result.ok or result.df_input is None or result.df_output is None:
            continue
        frames.append(_merge_input_output(result.df_input, result.df_output, strategy_id, model_attributes))

    if not frames:
        raise ValueError(f"No successful run results for baseline '{baseline_id}' to build cost-benefit input from.")

    return pd.concat(frames, ignore_index=True)


def calculate_cost_benefit(
    cb_wrapper: CBSSPWrapperForDFComparison,
    df_wide: pd.DataFrame,
    strategies_map: Dict[int, StrategyEntry],
    code_strat_base: str,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Returns (df_cb, df_attr_variable) -- cost/benefit results by strategy
    and time period, and the variable attribute table used to group/label
    them for graphics."""
    attr_strat = persistence_service.strategies_to_dataframe(strategies_map)
    return cb_wrapper(df_wide, attr_strat, code_strat_base=code_strat_base)


def get_cba_plot_data(
    cb_wrapper: CBSSPWrapperForDFComparison,
    df_cb: pd.DataFrame,
    df_attr_variable: pd.DataFrame,
    key_grouping: Optional[str] = None,
) -> pd.DataFrame:
    """[strategy_id, time_period, <cb_type or other grouping>...] -- each
    grouping column is the sum of every variable in df_cb belonging to that
    group (per df_attr_variable), ready to melt into a stacked bar chart.
    Note the baseline ("BASE") strategy is never present here -- cost/benefit
    figures are deltas relative to it, not absolute values for it."""
    return cb_wrapper.get_cba_plot_data(df_cb, df_attr_variable, key_grouping=key_grouping)

import pathlib

import pandas as pd
import pytest

from sisepuede_tool import config
from sisepuede_tool.models.run_result import RunResult
from sisepuede_tool.models.strategy_entry import StrategyEntry
from sisepuede_tool.services import catalog_service, cost_benefit_service, run_service, strategy_service, transformation_service

FIXTURE_CSV = pathlib.Path(__file__).parent / "fixtures" / "example_input.csv"


@pytest.fixture(scope="module")
def model_attributes():
    return catalog_service.build_model_attributes()


def _make_result(strategy_id, baseline_id="b", ok=True):
    df_in = pd.DataFrame(
        {
            "time_period": [0, 1],
            "strategy_id": [strategy_id, strategy_id],
            "region": ["egypt", "egypt"],
            "shared_col": [1.0, 2.0],
            "input_only_col": [10.0, 20.0],
        }
    )
    df_out = pd.DataFrame({"time_period": [0, 1], "shared_col": [100.0, 200.0], "output_only_col": [1000.0, 2000.0]})
    return RunResult(strategy_id=strategy_id, baseline_id=baseline_id, ok=ok, df_input=df_in, df_output=df_out)


def test_merge_input_output_prefers_output_value_for_overlap(model_attributes):
    result = _make_result(5)
    merged = cost_benefit_service._merge_input_output(result.df_input, result.df_output, 5, model_attributes)

    assert merged["shared_col"].tolist() == [100.0, 200.0]
    assert merged["input_only_col"].tolist() == [10.0, 20.0]
    assert merged["output_only_col"].tolist() == [1000.0, 2000.0]
    assert merged["strategy_id"].tolist() == [5, 5]
    assert merged["region"].tolist() == ["egypt", "egypt"]


def test_build_wide_results_skips_failed_and_missing_combos(model_attributes):
    run_results = {
        (1, "b"): _make_result(1),
        (2, "b"): _make_result(2, ok=False),
        # (3, "b") intentionally absent
    }

    df_wide = cost_benefit_service.build_wide_results(run_results, "b", [1, 2, 3], model_attributes)

    assert df_wide.shape[0] == 2
    assert df_wide["strategy_id"].tolist() == [1, 1]


def test_build_wide_results_concatenates_across_strategies(model_attributes):
    run_results = {(1, "b"): _make_result(1), (2, "b"): _make_result(2)}

    df_wide = cost_benefit_service.build_wide_results(run_results, "b", [1, 2], model_attributes)

    assert sorted(df_wide["strategy_id"].unique().tolist()) == [1, 2]
    assert df_wide.shape[0] == 4


def test_build_wide_results_raises_when_nothing_succeeded(model_attributes):
    with pytest.raises(ValueError):
        cost_benefit_service.build_wide_results({}, "b", [1], model_attributes)


# --- Slower, real end-to-end test: full SISEPUEDE run + real CB config ---
# Module-scoped so the whole file pays Julia connection cost once.


@pytest.fixture(scope="module")
def df_baseline():
    return pd.read_csv(FIXTURE_CSV)


@pytest.fixture(scope="module")
def transformers_catalog(df_baseline):
    return catalog_service.build_transformers_catalog(df_baseline)


@pytest.fixture(scope="module")
def transformations(transformers_catalog):
    coll = transformation_service.create_transformations_collection(transformers_catalog)
    t = transformation_service.build_transformation(
        "TX:AGRC:DEC_EXPORTS", "dec exports", "TFR:AGRC:DEC_EXPORTS", {"magnitude": 0.4}, transformers_catalog
    )
    transformation_service.add_transformation(coll, t)
    return coll


@pytest.fixture(scope="module")
def models(model_attributes):
    return run_service.build_models(model_attributes)


@pytest.fixture(scope="module")
def cb_wrapper(model_attributes):
    return cost_benefit_service.build_cb_wrapper(model_attributes, config.CB_CONFIG_XLSX_PATH)


def test_calculate_cost_benefit_end_to_end(models, transformations, df_baseline, model_attributes, cb_wrapper):
    """Full pipeline: run baseline + one policy strategy through SISEPUEDE,
    merge/concatenate their results, and confirm CBSSPWrapperForDFComparison
    returns two non-empty tables with the expected key columns."""
    baseline_strategy = strategy_service.build_baseline_strategy(transformations)
    policy_strategy = strategy_service.build_strategy(
        1000, ["TX:AGRC:DEC_EXPORTS"], transformations, name="test policy"
    )

    run_results = {}
    for strategy_id, strategy in [(0, baseline_strategy), (1000, policy_strategy)]:
        result = run_service.run_combination(
            models,
            strategy,
            df_baseline,
            region="egypt",
            run_energy_production=False,
            strategy_id=strategy_id,
            baseline_id="baseline_a",
            models_run=None,
        )
        assert result.ok, result.error
        run_results[(strategy_id, "baseline_a")] = result

    strategies_map = {
        0: StrategyEntry(strategy=baseline_strategy, transformation_codes=[transformations.code_baseline]),
        1000: StrategyEntry(strategy=policy_strategy, transformation_codes=["TX:AGRC:DEC_EXPORTS"]),
    }

    df_wide = cost_benefit_service.build_wide_results(run_results, "baseline_a", [0, 1000], model_attributes)
    df_cb, df_attr_variable = cost_benefit_service.calculate_cost_benefit(
        cb_wrapper, df_wide, strategies_map, code_strat_base="BASE"
    )

    assert not df_cb.empty
    assert model_attributes.dim_strategy_id in df_cb.columns
    assert model_attributes.dim_time_period in df_cb.columns
    assert not df_attr_variable.empty
    assert "variable" in df_attr_variable.columns

    plot_data = cost_benefit_service.get_cba_plot_data(cb_wrapper, df_cb, df_attr_variable)
    assert not plot_data.empty
    assert model_attributes.dim_strategy_id in plot_data.columns
    assert model_attributes.dim_time_period in plot_data.columns
    # cost/benefit figures are deltas relative to the baseline -- BASE itself
    # never appears as a row.
    assert 0 not in plot_data[model_attributes.dim_strategy_id].unique()
    assert 1000 in plot_data[model_attributes.dim_strategy_id].unique()

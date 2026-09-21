import pathlib

import pandas as pd
import pytest

from sisepuede_tool.models.run_result import RunResult
from sisepuede_tool.services import catalog_service, output_service

FIXTURE_CSV = pathlib.Path(__file__).parent / "fixtures" / "example_input.csv"

NO_CATEGORY_VARIABLE = ":math:\\text{CH}_4 Crop Biomass Burning Emission Factor"
MULTI_CATEGORY_VARIABLE = "Above Ground Residue Dry Matter Intercept"


@pytest.fixture(scope="module")
def model_attributes():
    return catalog_service.build_model_attributes()


@pytest.fixture(scope="module")
def df_baseline():
    return pd.read_csv(FIXTURE_CSV)


def test_get_variable_catalog_shape_and_columns(model_attributes):
    catalog = output_service.get_variable_catalog(model_attributes)
    assert list(catalog.columns) == ["sector", "subsector", "variable"]
    assert len(catalog) > 0
    assert set(catalog["sector"]) == {"AFOLU", "Circular Economy", "Energy", "IPPU", "Socioeconomic"}


def test_get_variable_catalog_lists_multi_category_variable_once(model_attributes):
    """A ModelVariable that expands to several category fields (confirmed:
    5 crop-category fields for this one) must appear as a single catalog
    row, not once per field."""
    catalog = output_service.get_variable_catalog(model_attributes)
    matches = catalog[catalog["variable"] == MULTI_CATEGORY_VARIABLE]
    assert len(matches) == 1
    assert matches.iloc[0]["subsector"] == "Agriculture"


def test_extract_variable_frame_no_category_variable(model_attributes, df_baseline):
    long = output_service.extract_variable_frame(model_attributes, df_baseline, NO_CATEGORY_VARIABLE)
    assert long is not None
    assert set(long["category"]) == {NO_CATEGORY_VARIABLE}
    assert len(long) == len(df_baseline)


def test_extract_variable_frame_multi_category_variable(model_attributes, df_baseline):
    long = output_service.extract_variable_frame(model_attributes, df_baseline, MULTI_CATEGORY_VARIABLE)
    assert long is not None
    assert set(long["category"]) == {"cereals", "other_annual", "pulses", "rice", "tubers"}
    assert len(long) == len(df_baseline) * 5


def test_extract_variable_frame_narrows_to_selected_categories(model_attributes, df_baseline):
    long = output_service.extract_variable_frame(
        model_attributes, df_baseline, MULTI_CATEGORY_VARIABLE, categories=["cereals", "rice"]
    )
    assert long is not None
    assert set(long["category"]) == {"cereals", "rice"}
    assert len(long) == len(df_baseline) * 2


def test_extract_variable_frame_returns_none_when_fields_missing(model_attributes):
    df_without_fields = pd.DataFrame({"time_period": [0, 1]})
    long = output_service.extract_variable_frame(model_attributes, df_without_fields, NO_CATEGORY_VARIABLE)
    assert long is None


def test_assemble_plot_frame_skips_failed_and_missing_results(model_attributes, df_baseline):
    run_results = {
        (0, "baseline_a"): RunResult(strategy_id=0, baseline_id="baseline_a", ok=True, df_output=df_baseline),
        (1000, "baseline_a"): RunResult(strategy_id=1000, baseline_id="baseline_a", ok=False, error="boom"),
    }
    combinations = [(0, "baseline_a"), (1000, "baseline_a"), (9999, "baseline_a")]

    plot_df = output_service.assemble_plot_frame(
        model_attributes,
        run_results,
        variable=NO_CATEGORY_VARIABLE,
        categories=[],
        data_source="output",
        combinations=combinations,
        strategy_labels={0: "Baseline", 1000: "My strategy"},
        baseline_labels={"baseline_a": "Egypt v1"},
    )

    assert set(plot_df["strategy"]) == {"Baseline"}
    assert set(plot_df["baseline"]) == {"Egypt v1"}
    assert len(plot_df) == len(df_baseline)


def test_assemble_plot_frame_reads_input_when_selected(model_attributes, df_baseline):
    """data_source='input' must read df_input, not df_output."""
    run_results = {
        (0, "baseline_a"): RunResult(
            strategy_id=0, baseline_id="baseline_a", ok=True, df_input=df_baseline, df_output=None
        ),
    }
    plot_df = output_service.assemble_plot_frame(
        model_attributes,
        run_results,
        variable=NO_CATEGORY_VARIABLE,
        categories=[],
        data_source="input",
        combinations=[(0, "baseline_a")],
        strategy_labels={0: "Baseline"},
        baseline_labels={"baseline_a": "Egypt v1"},
    )
    assert len(plot_df) == len(df_baseline)


def test_assemble_plot_frame_empty_when_no_successful_results(model_attributes):
    run_results = {(0, "baseline_a"): RunResult(strategy_id=0, baseline_id="baseline_a", ok=False, error="x")}
    plot_df = output_service.assemble_plot_frame(
        model_attributes,
        run_results,
        variable=NO_CATEGORY_VARIABLE,
        categories=[],
        data_source="output",
        combinations=[(0, "baseline_a")],
        strategy_labels={},
        baseline_labels={},
    )
    assert plot_df.empty

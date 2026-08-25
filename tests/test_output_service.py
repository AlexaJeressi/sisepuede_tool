import pandas as pd
import pytest

from sisepuede_tool.models.run_result import RunResult
from sisepuede_tool.services import catalog_service, output_service


@pytest.fixture(scope="module")
def model_attributes():
    return catalog_service.build_model_attributes()


def test_get_output_catalog_shape_and_columns(model_attributes):
    catalog = output_service.get_output_catalog(model_attributes)
    assert list(catalog.columns) == ["sector", "subsector", "variable", "emission_subsector", "color_default"]
    assert len(catalog) > 0
    assert set(catalog["sector"]) == {"AFOLU", "Circular Economy", "Energy", "IPPU", "Socioeconomic"}


def test_get_output_catalog_colors_are_hex(model_attributes):
    catalog = output_service.get_output_catalog(model_attributes)
    colors = catalog["color_default"].dropna().unique()
    assert len(colors) > 0
    assert all(c.startswith("#") for c in colors)


def test_assemble_plot_frame_skips_failed_and_missing_results():
    df_ok = pd.DataFrame({"time_period": [0, 1, 2], "var_a": [1.0, 2.0, 3.0], "var_b": [4.0, 5.0, 6.0]})
    run_results = {
        (0, "baseline_a"): RunResult(strategy_id=0, baseline_id="baseline_a", ok=True, df_output=df_ok),
        (1000, "baseline_a"): RunResult(strategy_id=1000, baseline_id="baseline_a", ok=False, error="boom"),
    }
    combinations = [(0, "baseline_a"), (1000, "baseline_a"), (9999, "baseline_a")]

    plot_df = output_service.assemble_plot_frame(
        run_results,
        variables=["var_a", "var_b"],
        combinations=combinations,
        strategy_labels={0: "Baseline", 1000: "My strategy"},
        baseline_labels={"baseline_a": "Costa Rica v1"},
    )

    assert set(plot_df["variable"]) == {"var_a", "var_b"}
    assert set(plot_df["strategy"]) == {"Baseline"}
    assert set(plot_df["baseline"]) == {"Costa Rica v1"}
    assert len(plot_df) == 6  # 3 time periods x 2 variables, only the ok result


def test_assemble_plot_frame_empty_when_no_successful_results():
    run_results = {(0, "baseline_a"): RunResult(strategy_id=0, baseline_id="baseline_a", ok=False, error="x")}
    plot_df = output_service.assemble_plot_frame(
        run_results, variables=["var_a"], combinations=[(0, "baseline_a")],
        strategy_labels={}, baseline_labels={},
    )
    assert plot_df.empty

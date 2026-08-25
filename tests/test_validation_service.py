import pandas as pd
import pytest

from sisepuede_tool.services import validation_service


@pytest.fixture()
def output_catalog():
    return pd.DataFrame(
        {
            "sector": ["Circular Economy", "Circular Economy"],
            "subsector": ["Wastewater Treatment", "Wastewater Treatment"],
            "variable": ["emission_co2e_ch4_trww_treated_secondary_anaerobic_treatment", "emission_co2e_ch4_energy"],
            "emission_subsector": [1, 1],
            "color_default": ["#000000", "#111111"],
        }
    )


@pytest.fixture()
def validation_df():
    return pd.DataFrame({"time_period": [0, 1, 2], "obs_ch4_treatment": [1.0, 1.1, 1.2]})


@pytest.fixture()
def crosswalk_df():
    return pd.DataFrame(
        {
            "comparison_id": ["ch4_treatment"],
            "comparison_label": ["Treated CH4"],
            "validation_field": ["obs_ch4_treatment"],
            "sisepuede_output_field": ["emission_co2e_ch4_trww_treated_secondary_anaerobic_treatment"],
        }
    )


@pytest.fixture()
def df_output():
    return pd.DataFrame(
        {
            "time_period": [0, 1, 2],
            "emission_co2e_ch4_trww_treated_secondary_anaerobic_treatment": [0.9, 1.0, 1.3],
        }
    )


def test_validate_crosswalk_ok(crosswalk_df, validation_df, output_catalog):
    result = validation_service.validate_crosswalk(crosswalk_df, validation_df, output_catalog)
    assert result.ok
    assert result.comparison_ids == ["ch4_treatment"]
    assert result.errors == []


def test_validate_crosswalk_missing_columns(validation_df, output_catalog):
    bad_crosswalk = pd.DataFrame({"comparison_id": ["x"]})
    result = validation_service.validate_crosswalk(bad_crosswalk, validation_df, output_catalog)
    assert not result.ok
    assert "missing column" in result.errors[0].lower()


def test_validate_crosswalk_unknown_validation_field(crosswalk_df, validation_df, output_catalog):
    crosswalk_df = crosswalk_df.copy()
    crosswalk_df.loc[0, "validation_field"] = "not_a_real_column"
    result = validation_service.validate_crosswalk(crosswalk_df, validation_df, output_catalog)
    assert not result.ok
    assert "not_a_real_column" in result.errors[0]
    assert result.comparison_ids == []


def test_validate_crosswalk_unknown_output_field(crosswalk_df, validation_df, output_catalog):
    crosswalk_df = crosswalk_df.copy()
    crosswalk_df.loc[0, "sisepuede_output_field"] = "not_a_real_output"
    result = validation_service.validate_crosswalk(crosswalk_df, validation_df, output_catalog)
    assert not result.ok
    assert "not_a_real_output" in result.errors[0]


def test_aggregate_comparison(crosswalk_df, df_output, validation_df):
    frame = validation_service.aggregate_comparison(crosswalk_df, "ch4_treatment", df_output, validation_df)
    observed = frame[frame["series"] == "observed"].sort_values("time_period")["value"].tolist()
    modeled = frame[frame["series"] == "modeled"].sort_values("time_period")["value"].tolist()
    assert observed == [1.0, 1.1, 1.2]
    assert modeled == [0.9, 1.0, 1.3]


def test_aggregate_comparison_sums_multiple_fields_per_side():
    crosswalk_df = pd.DataFrame(
        {
            "comparison_id": ["combo", "combo"],
            "comparison_label": ["Combo", "Combo"],
            "validation_field": ["obs_a", "obs_b"],
            "sisepuede_output_field": ["out_a", "out_b"],
        }
    )
    validation_df = pd.DataFrame({"time_period": [0, 1], "obs_a": [1.0, 2.0], "obs_b": [10.0, 20.0]})
    df_output = pd.DataFrame({"time_period": [0, 1], "out_a": [1.0, 1.0], "out_b": [1.0, 1.0]})

    frame = validation_service.aggregate_comparison(crosswalk_df, "combo", df_output, validation_df)
    observed = frame[frame["series"] == "observed"].sort_values("time_period")["value"].tolist()
    modeled = frame[frame["series"] == "modeled"].sort_values("time_period")["value"].tolist()
    assert observed == [11.0, 22.0]
    assert modeled == [2.0, 2.0]


def test_compute_fit_metrics(crosswalk_df, df_output, validation_df):
    frame = validation_service.aggregate_comparison(crosswalk_df, "ch4_treatment", df_output, validation_df)
    metrics = validation_service.compute_fit_metrics(frame)
    assert set(metrics.keys()) == {"rmse", "mae", "bias"}
    # modeled - observed = [-0.1, -0.1, 0.1]
    assert metrics["bias"] == pytest.approx(-0.1 / 3, abs=1e-9)
    assert metrics["mae"] == pytest.approx(0.1, abs=1e-9)


def test_compute_fit_metrics_empty_when_no_overlap():
    frame = pd.DataFrame({"time_period": [0], "series": ["observed"], "value": [1.0]})
    assert validation_service.compute_fit_metrics(frame) == {}

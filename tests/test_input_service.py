import pathlib

import pandas as pd
import pytest

from sisepuede_tool.services import catalog_service, input_service

FIXTURE_CSV = pathlib.Path(__file__).parent / "fixtures" / "example_input.csv"


@pytest.fixture(scope="module")
def model_attributes():
    return catalog_service.build_model_attributes()


def test_validate_baseline_ok(model_attributes):
    df = input_service.load_csv(FIXTURE_CSV)
    result = input_service.validate_baseline(df, model_attributes)

    assert result.ok
    assert result.error is None
    assert result.region == "costa_rica"
    assert result.n_time_periods == 36
    assert result.interpolated_periods == []
    assert "region" in result.df.columns
    assert "time_period" in result.df.columns


def test_validate_baseline_missing_time_period_column(model_attributes):
    df = input_service.load_csv(FIXTURE_CSV).drop(columns=["time_period"])
    result = input_service.validate_baseline(df, model_attributes)

    assert not result.ok
    assert "time_period" in result.error


def test_validate_baseline_missing_region_column(model_attributes):
    df = input_service.load_csv(FIXTURE_CSV).drop(columns=["region"])
    result = input_service.validate_baseline(df, model_attributes)

    assert not result.ok
    assert "region" in result.error


def test_validate_baseline_multiple_regions_rejected(model_attributes):
    df = input_service.load_csv(FIXTURE_CSV)
    df_other = df.copy()
    df_other["region"] = "mexico"
    df_multi = pd.concat([df, df_other], ignore_index=True)

    result = input_service.validate_baseline(df_multi, model_attributes)

    assert not result.ok
    assert "dimension" in result.error.lower()


def test_validate_baseline_interpolates_missing_periods(model_attributes):
    df = input_service.load_csv(FIXTURE_CSV)
    df_gappy = df[df["time_period"] != 10].reset_index(drop=True)

    result = input_service.validate_baseline(df_gappy, model_attributes)

    assert result.ok
    assert result.interpolated_periods == [10]
    assert result.n_time_periods == 36

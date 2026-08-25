import pathlib

import pandas as pd
import pytest

from sisepuede_tool.services import catalog_service

FIXTURE_CSV = pathlib.Path(__file__).parent / "fixtures" / "example_input.csv"


@pytest.fixture(scope="module")
def model_attributes():
    return catalog_service.build_model_attributes()


@pytest.fixture(scope="module")
def df_baseline():
    return pd.read_csv(FIXTURE_CSV)


def test_build_model_attributes(model_attributes):
    assert model_attributes is not None


def test_build_transformers_catalog(df_baseline):
    transformers = catalog_service.build_transformers_catalog(df_baseline)
    assert len(transformers.all_transformers) > 0
    assert "TFR:AGRC:DEC_CH4_RICE" in transformers.all_transformers


def test_transformers_catalog_independent_of_baseline_values(df_baseline):
    """Two structurally-identical baselines with different values must
    produce the same transformer catalog (same codes/names/descriptions) --
    this is the assumption the app relies on to build the catalog once and
    reuse it across every loaded baseline dataset.
    """
    df_perturbed = df_baseline.copy()
    numeric_cols = df_perturbed.select_dtypes("number").columns.drop(
        "time_period", errors="ignore"
    )
    df_perturbed[numeric_cols] = df_perturbed[numeric_cols] * 1.1

    transformers_a = catalog_service.build_transformers_catalog(df_baseline)
    transformers_b = catalog_service.build_transformers_catalog(df_perturbed)

    assert set(transformers_a.all_transformers) == set(transformers_b.all_transformers)

    code = transformers_a.all_transformers_non_baseline[0]
    ta = transformers_a.get_transformer(code)
    tb = transformers_b.get_transformer(code)
    assert ta.name == tb.name
    assert ta.description == tb.description

import pathlib

import pandas as pd
import pytest

from sisepuede_tool.services import catalog_service, run_service, strategy_service, transformation_service

FIXTURE_CSV = pathlib.Path(__file__).parent / "fixtures" / "example_input.csv"

# Building `models` connects to Julia (~seconds once packages are installed/
# precompiled, much longer cold) -- module-scoped so the whole file pays that
# cost once, not per test.


@pytest.fixture(scope="module")
def df_baseline():
    return pd.read_csv(FIXTURE_CSV)


@pytest.fixture(scope="module")
def model_attributes():
    return catalog_service.build_model_attributes()


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
    # TFR:AGRC:DEC_CH4_RICE still raises AttributeError ('AFOLU' object has no
    # attribute 'modvar_agrc_ef_ch4') against every fixture region tried so far
    # -- it's a code-structural bug in sisepuede's transformer lib, not a
    # data-dependent one, so it's a reliable way to test the never-raises
    # guarantee (unlike the old AFOLU/LivestockDietEstimator failure this file
    # used to rely on, which turned out to be specific to the costa_rica
    # fixture and no longer reproduces on the current egypt one).
    t_broken = transformation_service.build_transformation(
        "TX:AGRC:DEC_CH4_RICE", "broken rice transformer", "TFR:AGRC:DEC_CH4_RICE", {}, transformers_catalog
    )
    transformation_service.add_transformation(coll, t_broken)
    return coll


@pytest.fixture(scope="module")
def models(model_attributes):
    return run_service.build_models(model_attributes)


def test_build_models_connects_julia(models):
    assert models.allow_electricity_run is True


def test_run_combination_succeeds_with_all_sectors(models, transformations, df_baseline):
    """Confirms a clean transformation runs successfully across every sector,
    including AFOLU, against the current (egypt) fixture -- unlike the
    costa_rica fixture this project used to ship, AFOLU doesn't need to be
    excluded here (see the transformations fixture's comment)."""
    strategy = strategy_service.build_strategy(
        1000, ["TX:AGRC:DEC_EXPORTS"], transformations, name="test"
    )
    result = run_service.run_combination(
        models,
        strategy,
        df_baseline,
        region="egypt",
        run_energy_production=False,
        strategy_id=1000,
        baseline_id="baseline_a",
        models_run=None,
    )

    assert result.ok, result.error
    assert result.df_output is not None
    assert result.df_output.shape[0] == df_baseline.shape[0]
    assert result.strategy_id == 1000
    assert result.baseline_id == "baseline_a"
    assert result.elapsed_seconds > 0


def test_run_combination_captures_failure_without_raising(models, transformations, df_baseline):
    """A strategy built from a transformer with a known code bug (see the
    transformations fixture) must have its failure captured into the
    RunResult, not raised, since that's the error-isolation guarantee the
    Run page's batch loop depends on."""
    strategy = strategy_service.build_strategy(
        1001, ["TX:AGRC:DEC_CH4_RICE"], transformations, name="test broken transformer"
    )
    result = run_service.run_combination(
        models,
        strategy,
        df_baseline,
        region="egypt",
        run_energy_production=False,
        strategy_id=1001,
        baseline_id="baseline_a",
        models_run=None,
    )

    assert result.ok is False
    assert result.error is not None
    assert result.df_output is None

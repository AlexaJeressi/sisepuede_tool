import pathlib

import numpy as np
import pandas as pd
import pytest

from sisepuede_tool.services import catalog_service, ramp_service, transformation_service

FIXTURE_CSV = pathlib.Path(__file__).parent / "fixtures" / "egypt_baseline_biomass_fix.csv"
YEARS = list(range(2015, 2051))


@pytest.fixture(scope="module")
def transformers_catalog():
    return catalog_service.build_transformers_catalog(pd.read_csv(FIXTURE_CSV))


@pytest.mark.parametrize("shape", list(ramp_service.SHAPES))
def test_policy_round_trip(shape):
    ramp = ramp_service.ramp_from_policy(2026, 2040, shape, YEARS)
    policy = ramp_service.policy_from_ramp(ramp, YEARS, defaults={})
    assert (policy.start_year, policy.full_year, policy.shape) == (2026, 2040, shape)


@pytest.mark.parametrize("shape", list(ramp_service.SHAPES))
def test_curve_is_zero_before_start_and_one_at_full(shape):
    ramp = ramp_service.ramp_from_policy(2026, 2040, shape, YEARS)
    vec = ramp_service.ramp_curve(ramp, len(YEARS))
    assert vec[YEARS.index(2025)] == 0.0
    assert vec[YEARS.index(2026)] > 0.0
    assert vec[YEARS.index(2040)] == pytest.approx(1.0)
    assert np.all(np.diff(vec) >= -1e-12)


def test_front_loaded_is_ahead_of_back_loaded_at_midpoint():
    mid = YEARS.index(2033)
    front = ramp_service.ramp_curve(ramp_service.ramp_from_policy(2026, 2040, "front_loaded", YEARS), len(YEARS))
    back = ramp_service.ramp_curve(ramp_service.ramp_from_policy(2026, 2040, "back_loaded", YEARS), len(YEARS))
    assert front[mid] > 0.5 > back[mid]


def test_invalid_policies_raise():
    with pytest.raises(ramp_service.RampError):
        ramp_service.ramp_from_policy(2040, 2030, "linear", YEARS)
    with pytest.raises(ramp_service.RampError):
        ramp_service.ramp_from_policy(2015, 2030, "linear", YEARS)
    with pytest.raises(ramp_service.RampError):
        ramp_service.ramp_from_policy(2026, 2060, "linear", YEARS)
    with pytest.raises(ramp_service.RampError):
        ramp_service.ramp_from_policy(2026, 2030, "zigzag", YEARS)


def test_partial_ramp_from_news_yaml_uses_defaults():
    # NDC news files leave alpha_logistic / window_logistic null
    news = {"alpha_logistic": None, "d": 0, "n_tp_ramp": 26, "tp_0_ramp": 9, "window_logistic": None}
    policy = ramp_service.policy_from_ramp(news, YEARS, defaults={"alpha_logistic": 0.0})
    assert (policy.start_year, policy.full_year, policy.shape) == (2025, 2050, "linear")


def test_unknown_window_is_custom():
    ramp = {"tp_0_ramp": 10, "n_tp_ramp": 10, "alpha_logistic": 0.5, "window_logistic": (-8, 8)}
    assert ramp_service.policy_from_ramp(ramp, YEARS, defaults={}).shape == "custom"


def test_model_years(transformers_catalog):
    assert ramp_service.model_years(transformers_catalog.model_attributes) == YEARS


def test_catalog_default_ramp_matches_sisepuede_vector(transformers_catalog):
    tk = transformers_catalog
    ramp = ramp_service.catalog_default_ramp(tk)
    np.testing.assert_allclose(ramp_service.ramp_curve(ramp, len(YEARS)), tk.vec_implementation_ramp)


def test_transformer_output_follows_policy_ramp(transformers_catalog):
    """The ramp built here is the one sisepuede applies: rice CH4 factor is
    unchanged through 2027, starts moving in 2028 and is fully cut by 2035."""
    tk = transformers_catalog
    ramp = ramp_service.ramp_from_policy(2028, 2035, "s_curve", YEARS)
    tx = transformation_service.build_transformation(
        "TX:AGRC:TEST_RAMP",
        "ramp test",
        "TFR:AGRC:DEC_CH4_RICE",
        {"magnitude": 0.5, "vec_implementation_ramp": ramp},
        tk,
    )
    field = "ef_agrc_anaerobicdom_rice_kg_ch4_ha"
    base = tk.baseline()[field].to_numpy()
    out = tx()[field].to_numpy()
    expected = base * (1 - 0.5 * ramp_service.ramp_curve(ramp, len(YEARS)))
    np.testing.assert_allclose(out, expected, rtol=1e-6)
    assert out[YEARS.index(2027)] == pytest.approx(base[YEARS.index(2027)])
    assert out[YEARS.index(2035)] == pytest.approx(0.5 * base[YEARS.index(2035)])

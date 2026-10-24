"""Article 6 credit estimate (services/article6_service.py), which calls
sisepuede_a6 (ssp_asix), on a synthetic output."""

import pandas as pd
import pytest

from sisepuede_tool.services import article6_service as a6
from sisepuede_tool.services import catalog_service
from sisepuede_tool.services.emissions_service import YEAR_0

pytestmark = pytest.mark.skipif(not a6.A6_MODULE_PATH.exists(), reason=f"sisepuede_a6 not found at {a6.A6_DIR}")


@pytest.fixture(scope="module")
def model_attributes():
    return catalog_service.build_model_attributes()


def _ref():
    return {
        "groupings": pd.DataFrame(
            {
                "emission_grouping": ["Energy", "Waste"],
                "sisepuede_fields": ["emission_co2e_subsector_total_entc|emission_co2e_subsector_total_trns", "emission_co2e_subsector_total_waso"],
            }
        ),
        "targets": pd.DataFrame(
            {"year": [2030, 2030, 2035, 2035], "emission_grouping": ["Energy", "Waste", "Energy", "Waste"], "target_mt_co2e_ndc2": [100.0, 10.0, 90.0, 10.0]}
        ),
        "prices": pd.DataFrame({"year": [2030, 2035], "price_mm_usd_carbon_per_mt": [10.0, 20.0]}),
    }


def _output():
    years = [2029, 2030, 2035]
    return pd.DataFrame(
        {
            "time_period": [y - YEAR_0 for y in years],
            "emission_co2e_subsector_total_entc": [70.0, 60.0, 50.0],
            "emission_co2e_subsector_total_trns": [30.0, 30.0, 30.0],
            "emission_co2e_subsector_total_waso": [9.0, 12.0, 8.0],
        }
    )


def test_value_is_sisepuede_a6_get_credit_estimate(model_attributes):
    ref = _ref()
    m = a6.asix()
    expected = m.get_credit_estimate(
        _output(), ref["prices"], ref["groupings"], ref["targets"], m._FIELD_VALUE_NDC2, model_attributes, a6._time_periods(model_attributes)
    ).set_index(["year", "emission_grouping"])[m._FIELD_CREDIT_VALUE]
    est = a6.credit_estimate(_output(), model_attributes, ref).set_index(["year", "emission_grouping"])
    assert sorted(est.index.get_level_values("year").unique()) == [2030, 2035]
    pd.testing.assert_series_equal(est["value_musd"], expected.reindex(est.index), check_names=False)


def test_breakdown_columns(model_attributes):
    est = a6.credit_estimate(_output(), model_attributes, _ref()).set_index(["year", "emission_grouping"])
    assert est.loc[(2030, "Energy"), "emissions"] == pytest.approx(90.0)  # entc + trns
    assert est.loc[(2030, "Energy"), "target"] == pytest.approx(100.0)
    assert est.loc[(2035, "Waste"), "price"] == pytest.approx(20.0)
    # credits_mt x price = value, whatever sign convention ssp_asix uses
    assert (est["credits_mt"] * est["price"]).to_numpy() == pytest.approx(est["value_musd"].to_numpy())
    tot = a6.totals_by_year(est.reset_index()).set_index("year")
    assert tot.loc[2035, "price"] == pytest.approx(20.0)


def test_groups_without_emissions_are_flagged(model_attributes):
    out = _output()
    out["emission_co2e_subsector_total_waso"] = 0.0  # e.g. not modelled in this run
    est = a6.credit_estimate(out, model_attributes, _ref())
    assert a6.not_modelled(est) == ["Waste"]


def test_shipped_reference_is_consistent():
    ref = a6.load_reference()
    groups = set(ref["groupings"]["emission_grouping"])
    assert set(ref["targets"]["emission_grouping"]) <= groups
    assert set(a6.target_years(ref["targets"])) <= set(ref["prices"]["year"])


def test_only_pathways_beyond_the_ndc_earn_credits():
    ndc = ["TX:A_NDC", "TX:B_NDC"]
    assert not a6.earns_credits([], ndc)  # business as usual
    assert not a6.earns_credits(["TX:A_NDC"], ndc)  # NDC transformations only
    assert a6.earns_credits(["TX:A_NDC", "TX:C_LEP"], ndc)
    assert a6.earns_credits(["TX:C_LEP"], ndc)


def test_group_colors_follow_the_subsector():
    colors = a6.group_colors(_ref()["groupings"], {"entc": "#111111", "waso": "#222222"})
    assert colors == {"Energy": "#111111", "Waste": "#222222"}


def test_changed_prices_change_the_value_only_in_their_year(model_attributes):
    ref = _ref()
    assert a6.price_by_year(ref["prices"], [2030, 2035]) == {2030: 10.0, 2035: 20.0}
    edited = {**ref, "prices": a6.with_prices(ref["prices"], {2030: 25.0})}
    base = a6.credit_estimate(_output(), model_attributes, ref).set_index(["year", "emission_grouping"])
    est = a6.credit_estimate(_output(), model_attributes, edited).set_index(["year", "emission_grouping"])
    assert est.loc[2030, "value_musd"].to_numpy() == pytest.approx(base.loc[2030, "value_musd"].to_numpy() * 2.5)
    assert est.loc[2035, "value_musd"].to_numpy() == pytest.approx(base.loc[2035, "value_musd"].to_numpy())  # unchanged
    assert ref["prices"].set_index("year").loc[2030].iloc[0] == 10.0  # the reference table is not modified
    added = a6.with_prices(ref["prices"], {2040: 30.0})
    assert a6.price_by_year(added, [2040]) == {2040: 30.0}


def test_headline_years_are_the_milestones():
    assert a6.headline_years(range(2026, 2036)) == [2030, 2035]
    assert a6.headline_years([2030, 2035]) == [2030, 2035]
    assert a6.headline_years([2026, 2027, 2028]) == [2028]  # no milestone: the last year


def test_emissions_by_year_sums_the_groups_with_a_target(model_attributes):
    ref = _ref()
    ref["targets"].loc[ref["targets"]["emission_grouping"] == "Waste", "target_mt_co2e_ndc2"] = float("nan")
    s = a6.emissions_by_year(_output(), model_attributes, ref)
    assert list(s.index) == [2029, 2030, 2035]  # every year of the run, not only the target years
    assert s.to_dict() == {2029: 100.0, 2030: 90.0, 2035: 80.0}  # Energy only: Waste has no target



def test_ranked_mac_file_is_shown_as_it_is(tmp_path):
    p = tmp_path / "ranked.csv"
    pd.DataFrame({
        "emission_grouping": ["Energy", "Energy", "Waste"],
        "proportional_a6_excess_allocation": [0.75, 0.25, 1.0],
        "transformer_kernel_code": ["TFR:B", "TFR:A", "TFR:C"],
        "mac_aggregate_usd_per_tonne": [10.0, -5.0, 3.0],
        "year": [2030, 2030, 2030],
        "total_value_carbon_credits_mm_usd": [30.0, 10.0, -2.0],
    }).to_csv(p, index=False)
    df = a6.load_ranked.__wrapped__(p)
    # the file's values, cheapest transformer first in each group
    assert df[a6.FIELD_KERNEL].tolist() == ["TFR:A", "TFR:B", "TFR:C"]
    assert df["value_musd"].tolist() == [10.0, 30.0, -2.0] and df["mac"].tolist() == [-5.0, 10.0, 3.0]
    assert a6.load_ranked.__wrapped__(tmp_path / "missing.csv").empty


@pytest.mark.skipif(not a6.RANKED_PATH.exists(), reason=f"{a6.RANKED_PATH} not found")
def test_shipped_ranked_file_groups_are_known():
    df, ref = a6.load_ranked(), a6.load_reference()
    assert set(df[a6.FIELD_GROUP]) <= set(ref["groupings"][a6.FIELD_GROUP]) and not df["mac"].isna().any()


def test_aggregate_file_in_one_group():
    df = a6.load_ranked_aggregate()
    if df.empty:
        pytest.skip("no sisepuede_a6 clone")
    assert list(df.columns) == ["year", a6.FIELD_GROUP, a6.FIELD_KERNEL, "mac", "value_musd"]
    assert set(df[a6.FIELD_GROUP]) == {a6.WHOLE_ECONOMY}
    y = df[df["year"] == 2050]
    assert y["mac"].is_monotonic_increasing  # cheapest first, across every sector
    # the same yearly totals as the file by emission group
    by_group = a6.load_ranked().groupby("year")["value_musd"].sum()
    assert df.groupby("year")["value_musd"].sum().loc[2035] == pytest.approx(by_group.loc[2035], rel=1e-3)

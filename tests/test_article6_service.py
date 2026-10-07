"""Article 6 credit estimate (services/article6_service.py) on a synthetic output."""

import pandas as pd
import pytest

from sisepuede_tool.services import article6_service as a6
from sisepuede_tool.services.emissions_service import YEAR_0


def _ref():
    return {
        "groupings": pd.DataFrame(
            {
                "emission_groups": ["Energy", "Waste"],
                "sisepuede_fields": ["emission_co2e_subsector_total_entc|emission_co2e_subsector_total_trns", "emission_co2e_subsector_total_waso"],
            }
        ),
        "targets": pd.DataFrame(
            {"year": [2030, 2030, 2035, 2035], "emission_groups": ["Energy", "Waste", "Energy", "Waste"], "target_mt_co2e_ndc2": [100.0, 10.0, 90.0, 10.0]}
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


def test_surplus_is_target_minus_emissions():
    d = a6.emissions_vs_targets(_output(), _ref()["groupings"], _ref()["targets"]).set_index(["year", "emission_groups"])
    assert sorted(d.index.get_level_values("year").unique()) == [2030, 2035]
    assert d.loc[(2030, "Energy"), "emissions"] == pytest.approx(90.0)  # entc + trns
    assert d.loc[(2030, "Energy"), "surplus"] == pytest.approx(10.0)  # below target
    assert d.loc[(2030, "Waste"), "surplus"] == pytest.approx(-2.0)  # above target


def test_credits_clip_each_group_and_use_the_year_price():
    est = a6.credit_estimate(_output(), _ref()).set_index(["year", "emission_groups"])
    assert est.loc[(2030, "Waste"), "credits_mt"] == 0.0  # a shortfall earns nothing...
    assert est.loc[(2030, "Energy"), "value_musd"] == pytest.approx(100.0)  # ...and does not offset Energy
    assert est.loc[(2035, "Energy"), "value_musd"] == pytest.approx(10.0 * 20.0)
    assert est.loc[(2035, "Waste"), "value_musd"] == pytest.approx(2.0 * 20.0)
    tot = a6.totals_by_year(est.reset_index()).set_index("year")
    assert tot.loc[2030, "value_musd"] == pytest.approx(100.0)
    assert tot.loc[2035, "credits_mt"] == pytest.approx(12.0)
    assert tot.loc[2035, "price"] == pytest.approx(20.0)


def test_groups_without_emissions_earn_nothing():
    out = _output()
    out["emission_co2e_subsector_total_waso"] = 0.0  # e.g. not modelled in this run
    est = a6.credit_estimate(out, _ref())
    assert a6.not_modelled(est) == ["Waste"]
    assert est.loc[est["emission_groups"] == "Waste", "credits_mt"].sum() == 0.0


def test_shipped_reference_is_consistent():
    ref = a6.load_reference()
    groups = set(ref["groupings"]["emission_groups"])
    assert set(ref["targets"]["emission_groups"]) <= groups
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


def test_changed_prices_change_the_value_only_in_their_year():
    ref = _ref()
    assert a6.price_by_year(ref["prices"], [2030, 2035]) == {2030: 10.0, 2035: 20.0}
    edited = {**ref, "prices": a6.with_prices(ref["prices"], {2030: 25.0})}
    est = a6.credit_estimate(_output(), edited).set_index(["year", "emission_groups"])
    assert est.loc[(2030, "Energy"), "value_musd"] == pytest.approx(10.0 * 25.0)
    assert est.loc[(2035, "Energy"), "value_musd"] == pytest.approx(10.0 * 20.0)  # unchanged
    assert ref["prices"].set_index("year").loc[2030].iloc[0] == 10.0  # the reference table is not modified
    added = a6.with_prices(ref["prices"], {2040: 30.0})
    assert a6.price_by_year(added, [2040]) == {2040: 30.0}

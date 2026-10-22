"""Marginal abatement cost (services/mac_service.py), computed from the static
sisepuede_a6 ref/temporary_emit_cost_diffs_by_subsec.csv."""

import pandas as pd
import pytest

from sisepuede_tool.services import i18n, library_service
from sisepuede_tool.services import mac_service as mac


def _diffs(tmp_path):
    """A diffs file: NDC (6004) with A (transport, also cuts electricity), B
    (saves money) and C (raises emissions); LEP (6005) with A only, whose
    whirlpool estimate was not run. "All" rows are ignored."""
    rows = [
        # strategy, code, subsector, cost T, cost W, emission T, emission W (cost < 0 = net cost, emission < 0 = abated)
        (6004, "TX:TRNS:A", "Transportation", -2.0, -4.0, -80.0, -100.0),
        (6004, "TX:TRNS:A", "Energy Technology", -2.0, -4.0, -20.0, 0.0),
        (6004, "TX:TRNS:A", "All", -2.0, -4.0, -999.0, -999.0),
        (6004, "TX:WASO:B", "Solid Waste", 1.0, 1.0, -50.0, -50.0),
        (6004, "TX:WASO:B", "Energy Technology", 1.0, 1.0, 0.0, 0.0),
        (6004, "TX:ENTC:C", "Energy Technology", -1.0, -1.0, 10.0, 10.0),
        (6004, "TX:ENTC:C", "Transportation", -1.0, -1.0, -5.0, -5.0),
        (6005, "TX:TRNS:A", "Transportation", -3.0, 0.0, -60.0, 0.0),
        (6005, "TX:TRNS:A", "Energy Technology", -3.0, 0.0, 0.0, 0.0),
    ]
    p = tmp_path / "diffs.csv"
    pd.DataFrame(rows, columns=[
        "strategy_id_stressed", "transformation_code", "subsector", "cost_diff_mmm_usd_tornado", "cost_diff_mmm_usd_whirlpool",
        "emission_diff_mt_co2e_tornado", "emission_diff_mt_co2e_whirlpool",
    ]).to_csv(p, index=False)
    return mac.load.__wrapped__(p)


def test_load_signs_and_scopes(tmp_path):
    df = _diffs(tmp_path)
    assert "All" not in set(df["subsector"]) and mac.pathways(df) == ["NDC", "LEP"]
    a = df[(df["pathway"] == "NDC") & (df["code"] == "TX:TRNS:A") & (df["subsector"] == "trns")].iloc[0]
    assert (a["abatement_tornado"], a["cost_tornado"]) == (80.0, 2.0)
    assert mac.scopes(df) == [("Energy", ["entc", "trns"]), ("Circular Economy", ["waso"])]
    assert mac.scope_subsectors("") is None and mac.scope_subsectors("trns") == ["trns"]
    assert {"entc", "trns", "inen"} <= set(mac.scope_subsectors("sector:Energy"))


def test_whole_economy_curve(tmp_path):
    rows, left = mac.curve(_diffs(tmp_path), "NDC", "", "tornado")
    assert list(rows["code"]) == ["TX:WASO:B", "TX:TRNS:A"]  # cheapest first
    b, a = rows.iloc[0], rows.iloc[1]
    assert b["mac"] == pytest.approx(-20.0)  # saves 1 B USD over 50 Mt
    assert a["mac"] == pytest.approx(20.0) and a["abatement"] == 100.0  # 2 B USD over 80 + 20 Mt, not the "All" row
    assert list(rows["start"]) == [0.0, 50.0]
    assert left == {"raises": ["TX:ENTC:C"], "no_mac": []}
    assert mac.summary(rows) == pytest.approx({"abatement": 150.0, "saving": 50.0, "mac": (-20 * 50 + 20 * 100) / 150})


def test_mean_puts_both_estimates_together(tmp_path):
    df = _diffs(tmp_path)
    t = mac.transformations(df, "NDC").set_index("code")
    assert t.loc["TX:TRNS:A", "mac_whirlpool"] == pytest.approx(40.0)
    assert t.loc["TX:TRNS:A", "mac_mean"] == pytest.approx(3.0 * 1e3 / 100.0)  # (2 + 4) / 2 over (100 + 100) / 2
    # LEP: whirlpool not run (all zero), so the mean is the tornado
    t = mac.transformations(df, "LEP").set_index("code")
    assert (t.loc["TX:TRNS:A", "has_whirlpool"], t.loc["TX:TRNS:A", "abatement_mean"]) == (0.0, 60.0)
    assert t.loc["TX:TRNS:A", "mac_mean"] == pytest.approx(50.0)


def test_scope_counts_only_its_tonnes(tmp_path):
    df = _diffs(tmp_path)
    rows, left = mac.curve(df, "NDC", "trns", "tornado")
    # A abates 80 of its 100 Mt here, at its whole-economy cost per tonne; C abates here but raises emissions overall
    assert list(rows["code"]) == ["TX:TRNS:A"]
    assert (rows["abatement"].iloc[0], rows["share"].iloc[0], rows["mac"].iloc[0]) == (80.0, 0.8, pytest.approx(20.0))
    assert left == {"raises": [], "no_mac": ["TX:ENTC:C"]}
    rows, left = mac.curve(df, "NDC", "entc", "tornado")
    assert list(rows["code"]) == ["TX:TRNS:A"] and left["raises"] == ["TX:ENTC:C"]
    assert mac.curve(df, "NDC", "waso", "tornado")[0]["code"].tolist() == ["TX:WASO:B"]
    assert len(mac.curve(df, "NDC", "sector:Energy", "tornado")[0]) == 1
    assert mac.curve(df, "LEP", "waso", "mean")[0].empty


def test_by_subsector(tmp_path):
    df = _diffs(tmp_path)
    t = mac.by_subsector(df, ["NDC", "LEP"], "tornado").set_index(["pathway", "subsector"])
    # NDC transport: A (80 Mt at 20 USD/t); C abates 5 Mt there but raises emissions overall, so it has no cost per tonne
    assert t.loc[("NDC", "trns"), ["mac", "abatement", "n"]].tolist() == [pytest.approx(20.0), 80.0, 1]
    assert t.loc[("NDC", "waso"), "mac"] == pytest.approx(-20.0)
    assert ("LEP", "waso") not in t.index  # no data
    assert mac.subsector_order(t.reset_index(), ["NDC", "LEP"]) == ["waso", "entc", "trns"]


def test_by_transformation(tmp_path):
    df = _diffs(tmp_path)
    rows, hidden = mac.by_transformation(df, ["NDC", "LEP"], "tornado")
    assert hidden == 0
    a = rows[rows["code"] == "TX:TRNS:A"].set_index(["pathway", "subsector"])
    # under each subsector it abates in, with what it abates there
    assert a.loc[("NDC", "trns"), "abatement"] == 80.0 and a.loc[("NDC", "entc"), "abatement"] == 20.0
    assert a.loc[("LEP", "trns"), "share"] == 1.0
    rows, _ = mac.by_transformation(df, ["NDC"], "tornado", "waso")
    assert rows["code"].tolist() == ["TX:WASO:B"]
    # a sector: its subsectors, each with its own rows
    rows, hidden = mac.by_transformation(df, ["NDC"], "tornado", "sector:Energy", min_share=0.5)
    assert hidden == 0 and set(rows["subsector"]) == {"trns", "entc"}


def test_pair_key():
    assert mac.pair_key("TX:ENTC:TARGET_RENEWABLE_ELEC_STRATEGY_NDC") == mac.pair_key("TX:ENTC:TARGET_RENEWABLE_ELEC_LEP")
    assert mac.pair_key("TX:FGTV:DEC_LEAKS_STRATEGY_LEP") == "TX:FGTV:DEC_LEAKS"
    assert mac.pair_key("TX:LVST:INC_PRODUCTIVITY") == "TX:LVST:INC_PRODUCTIVITY"


def test_axis_limit():
    assert mac.axis_limit([1.0, -2.0, 3.0]) is None
    assert mac.axis_limit([1.0, -10.0, 2850.0]) == pytest.approx(13.0)


def test_subsector_of():
    assert mac.subsector_of("TX:TRNS:SHIFT_FUEL_RAIL_STRATEGY_NDC") == "trns"
    assert mac.subsector_of("bad") == ""


@pytest.mark.skipif(not mac.DIFFS_PATH.exists(), reason=f"{mac.DIFFS_PATH} not found")
def test_load_file():
    df = mac.load()
    assert mac.pathways(df) == ["NDC", "LEP"]
    assert not df.duplicated(["pathway", "code", "subsector"]).any()
    assert not df["subsector"].isna().any()  # every subsector of the file is in SUBSECTOR_ABV
    for p in mac.pathways(df):
        rows, _ = mac.curve(df, p, "", "mean")
        assert len(rows) > 5 and rows["mac"].is_monotonic_increasing
    # the page can name every transformation: the library, else mac.names
    named = {i.code for i in library_service.load_all_libraries()}
    assert all(c in named or i18n.t(f"mac.names.{c}", "en", default="") for c in df["code"].unique())


def test_axis_limit_cuts_a_few_outliers():
    # two outliers (as rail and urban wastewater): both cut, then the rest fits a linear axis
    v = [8226.0, 1300.0, 101.0, 62.0, 50.0, 12.0, 11.0, 7.5, 5.9, 3.7, 3.6, -7.4, -32.6, -95.2]
    assert mac.axis_limit(v) == pytest.approx(1.3 * 101.0)
    assert mac.axis_limit([5e9, 4e9, 3e9, 2.0, 1.0]) is None  # more than a fifth: not outliers
    # wastewater in both pathways, far above the rest: both cut (the last gap, not the first)
    assert mac.axis_limit([701.0, 345.0, 88.0, 83.0, 67.0, 64.0, 45.0, 43.0, 36.0, 30.0, 22.0, 17.0, -38.0]) == pytest.approx(1.3 * 88.0)

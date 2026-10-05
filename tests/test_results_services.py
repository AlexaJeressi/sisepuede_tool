"""Results pages' services: emissions grouping, driver cards, C&B summary, downloads.

The module fixture runs business as usual and the shipped NDC pathway on the
Egypt baseline (without the electricity model, to keep it quick), then
computes costs & benefits on them.
"""

import io
import pathlib

import pandas as pd
import pytest

from sisepuede_tool import config
from sisepuede_tool.models.strategy_entry import StrategyEntry
from sisepuede_tool.services import (
    catalog_service,
    cb_summary_service,
    cost_benefit_service,
    download_service,
    emissions_service,
    input_service,
    library_service,
    output_service,
    pathway_service,
    results_groups_service,
    run_service,
    strategy_service,
    transformation_service,
)

EGYPT_CSV = pathlib.Path(__file__).parent / "fixtures" / "example_input.csv"


@pytest.fixture(scope="module")
def model_attributes():
    return catalog_service.build_model_attributes()


@pytest.fixture(scope="module")
def field_catalog(model_attributes):
    return output_service.build_field_catalog(model_attributes)


@pytest.fixture(scope="module")
def egypt_runs(model_attributes):
    v = input_service.validate_baseline(input_service.load_csv(EGYPT_CSV), model_attributes)
    assert v.ok, v.error
    tk = catalog_service.build_transformers_catalog(v.df)
    tx = transformation_service.create_transformations_collection(tk)
    items = library_service.add_library_to_collection(tx, tk)
    pathways = {0: StrategyEntry(strategy=strategy_service.build_baseline_strategy(tx), transformation_codes=[tx.code_baseline])}
    pathways, ndc_id = pathway_service.add_library_pathway(pathways, tx, items, name="NDC")
    models = run_service.build_models(model_attributes)
    results = {}
    for sid in (0, ndc_id):
        r = run_service.run_combination(models, pathways[sid].strategy, v.df, v.region, False, sid, "egypt")
        assert r.ok, r.error
        results[sid] = r
    return {"results": results, "ndc_id": ndc_id, "pathways": pathways}


@pytest.fixture(scope="module")
def cb_long(egypt_runs, model_attributes):
    cbw = cost_benefit_service.build_cb_wrapper(model_attributes, config.CB_CONFIG_XLSX_PATH)
    rr = {(sid, "egypt"): r for sid, r in egypt_runs["results"].items()}
    wide = cost_benefit_service.build_wide_results(rr, "egypt", sorted(egypt_runs["results"]), model_attributes)
    df_cb, df_attr = cost_benefit_service.calculate_cost_benefit(cbw, wide, egypt_runs["pathways"], "BASE")
    return cb_summary_service.to_long(df_cb, df_attr, config.CB_CONFIG_XLSX_PATH)


# emissions


def test_emission_detail_adds_up_to_subsector_totals(egypt_runs):
    for r in egypt_runs["results"].values():
        totals = emissions_service.by_subsector(r.df_output).groupby(["year", "subsector_abv"])["value"].sum()
        detail = emissions_service.detail(r.df_output).groupby(["year", "subsector_abv"])["value"].sum()
        gap = (totals - detail.reindex(totals.index).fillna(0.0)).abs()
        assert gap.max() < 1e-4, gap[gap >= 1e-4].head()


def test_every_emission_field_has_a_detail_group(egypt_runs):
    r = egypt_runs["results"][0]
    cls = emissions_service.classify_fields(r.df_output.columns)
    assert not cls.empty
    assert (cls["detail"] == "Other").sum() == 0, cls[cls["detail"] == "Other"]["field"].tolist()[:5]
    assert set(cls["gas_group"]) <= set(emissions_service.GAS_GROUPS)


def test_kpis_compare_with_bau():
    bau = pd.Series({2030: 100.0, 2050: 200.0, 2025: 90.0})
    ndc = pd.Series({2030: 80.0, 2050: 100.0, 2025: 90.0})
    rows = {k["key"]: k for k in emissions_service.kpis({"BAU": bau, "NDC": ndc}, "BAU")}
    assert rows["NDC"]["pct_2030"] == pytest.approx(-20.0)
    assert rows["NDC"]["pct_2050"] == pytest.approx(-50.0)
    assert rows["NDC"]["avoided_cum"] == pytest.approx(120.0)
    assert rows["BAU"]["pct_2050"] is None


# driver cards


def _all_cards():
    groups = results_groups_service.load_groups()
    return groups["context"] + [c for a in groups["areas"] for c in a["cards"]]


def test_every_card_variable_exists(field_catalog):
    known = set(field_catalog["variable"])
    for card in _all_cards():
        assert card["view"] in results_groups_service.VIEWS, card["key"]
        missing = [v for v in card["variables"] if v not in known]
        assert not missing, (card["key"], missing)
        assert not results_groups_service.card_fields(card, field_catalog).empty, card["key"]


def test_every_card_has_data_in_an_egypt_run(egypt_runs, field_catalog):
    r = egypt_runs["results"][egypt_runs["ndc_id"]]
    for card in _all_cards():
        f = results_groups_service.card_frame(card, field_catalog, r)
        if card.get("needs_electricity_model"):
            # the fixture runs without NemoMod
            assert f.empty, card["key"]
            continue
        assert not f.empty, card["key"]
        assert f["year"].min() == 2015 and f["year"].max() == 2050


def test_every_emitting_subsector_has_an_area():
    groups = results_groups_service.load_groups()
    for abv in ["entc", "trns", "inen", "scoe", "fgtv", "ippu", "agrc", "lvst", "lsmm", "soil", "lndu", "frst", "waso", "trww"]:
        assert results_groups_service.area_for_subsector(groups, abv) is not None, abv


def test_custom_card_from_any_variable(egypt_runs, field_catalog):
    card = results_groups_service.custom_card("Crop Yield", field_catalog)
    assert card["source"] == "output" and card["view"] == "stacked"
    f = results_groups_service.card_frame(card, field_catalog, egypt_runs["results"][0])
    assert f["series"].nunique() > 1


def test_series_names_are_readable():
    assert results_groups_service.category_name("pp_solar") == "Solar"
    assert results_groups_service.category_name("fuel_natural_gas") == "Natural gas"
    assert results_groups_service.category_name(None) == "Total"


# costs & benefits


def test_every_cb_type_in_the_config_has_a_category():
    names = []
    for sheet in ("tx_table", "cost_factors"):
        names += pd.read_excel(config.CB_CONFIG_XLSX_PATH, sheet_name=sheet)["output_variable_name"].dropna().tolist()
    cb_types = {n.split(":")[2] for n in names if n.startswith("cb:") and n.count(":") >= 2}
    assert cb_types
    assert not [t for t in cb_types if t not in cb_summary_service.CATEGORIES]


def test_npv_by_hand():
    long = pd.DataFrame(
        {
            "strategy_id": [1] * 4,
            "year": [2025, 2026, 2025, 2026],
            "variable": ["a", "a", "b", "b"],
            "category": ["Fuel costs & savings"] * 2 + ["Technology capex & opex"] * 2,
            "value_busd": [10.0, 10.0, -15.0, 0.0],
        }
    )
    s = cb_summary_service.npv_summary(long, 1, 10.0)
    assert s["benefits"] == pytest.approx(10 + 10 / 1.1)
    assert s["costs"] == pytest.approx(15.0)
    assert s["net"] == pytest.approx(10 + 10 / 1.1 - 15)
    assert s["bcr"] == pytest.approx((10 + 10 / 1.1) / 15)
    assert s["net_positive_year"] == 2026
    assert s["by_group"]["Technology capex & opex"] == pytest.approx(-15.0)


def test_cb_long_has_categories_and_names(cb_long, egypt_runs):
    assert set(cb_long["strategy_id"]) == {egypt_runs["ndc_id"]}
    assert (cb_long["category"] != cb_summary_service.OTHER).all()
    assert (cb_long["display_name"] != cb_long["variable"]).mean() > 0.5
    wide = cb_summary_service.by_group(cb_long, egypt_runs["ndc_id"])
    assert wide.index.min() == cb_summary_service.START_YEAR


# downloads


def _sheets(blob: bytes):
    return pd.read_excel(io.BytesIO(blob), sheet_name=None)


def test_emissions_workbook(egypt_runs, field_catalog):
    runs = [("Business as usual", egypt_runs["results"][0]), ("NDC", egypt_runs["results"][egypt_runs["ndc_id"]])]
    sheets = _sheets(download_service.emissions_workbook(runs, "egypt", _all_cards(), field_catalog))
    assert list(sheets) == ["emissions_by_subsector", "emissions_detail", "drivers", "dictionary"]
    sub = sheets["emissions_by_subsector"]
    assert set(sub["pathway"]) == {"Business as usual", "NDC"}
    assert {"year", "pathway", "baseline", "sector", "subsector", "unit", "value"} <= set(sub.columns)
    assert not sheets["drivers"].empty and not sheets["dictionary"].empty


def test_cb_workbook(cb_long, egypt_runs):
    gdp = {egypt_runs["ndc_id"]: cb_summary_service.gdp_by_year(egypt_runs["results"][egypt_runs["ndc_id"]].df_input)}
    sheets = _sheets(download_service.cb_workbook(cb_long, {egypt_runs["ndc_id"]: "NDC"}, "egypt", gdp))
    assert list(sheets) == ["cb_by_variable", "cb_by_category", "totals_by_rate", "items_by_rate", "notes"]
    npv = sheets["totals_by_rate"]
    assert set(npv["discount_rate_pct"]) == {0, 3, 5, 7}
    assert sheets["cb_by_category"]["pct_gdp"].notna().any()


def test_item_names_are_unique_and_readable(cb_long):
    names = cb_long.groupby("display_name")["variable"].nunique()
    # a name may cover the same item under two sectors, never a whole family
    assert names.max() <= 2
    assert not cb_long["display_name"].str.contains("bio fuel_biogas").any()
    assert not cb_long["display_name"].str.startswith("cb_").any()


def test_items_npv_adds_up_to_net(cb_long, egypt_runs):
    sid = egypt_runs["ndc_id"]
    items = cb_summary_service.items_npv(cb_long, sid, 5)
    assert items["pv"].sum() == pytest.approx(cb_summary_service.npv_summary(cb_long, sid, 5)["net"], abs=1e-6)


def test_not_discounted_is_the_plain_sum(cb_long, egypt_runs):
    sid = egypt_runs["ndc_id"]
    plain = cb_long[(cb_long["strategy_id"] == sid) & (cb_long["year"] >= cb_summary_service.START_YEAR)]["value_busd"].sum()
    assert cb_summary_service.DEFAULT_RATE == 0
    assert cb_summary_service.npv_summary(cb_long, sid, 0)["net"] == pytest.approx(plain)

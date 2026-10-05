import pathlib

import pandas as pd
import pytest

from sisepuede_tool.models.strategy_entry import StrategyEntry
from sisepuede_tool.services import (
    catalog_service,
    library_service,
    pathway_service,
    ramp_service,
    strategy_service,
    transformation_service,
)

FIXTURE_CSV = pathlib.Path(__file__).parent / "fixtures" / "egypt_baseline_biomass_fix.csv"
YEARS = list(range(2015, 2051))
RICE_FIELD = "ef_agrc_anaerobicdom_rice_kg_ch4_ha"


@pytest.fixture(scope="module")
def baseline_df():
    return pd.read_csv(FIXTURE_CSV)


@pytest.fixture(scope="module")
def catalog(baseline_df):
    return catalog_service.build_transformers_catalog(baseline_df)


@pytest.fixture
def tx(catalog):
    return transformation_service.create_transformations_collection(catalog)


@pytest.fixture
def bau_only(tx):
    return {0: StrategyEntry(strategy=strategy_service.build_baseline_strategy(tx), transformation_codes=[tx.code_baseline])}


def _rice(catalog, code="TX:AGRC:DEC_CH4_RICE", magnitude=0.45):
    return transformation_service.build_transformation(
        code, f"rice {magnitude}", "TFR:AGRC:DEC_CH4_RICE", {"magnitude": magnitude}, catalog
    )


# library


def test_library_parses_all_files():
    items = library_service.load_library()
    assert len(items) == 18
    item = next(i for i in items if i.code == "TX:ENTC:TARGET_RENEWABLE_ELEC_STRATEGY_NDC")
    assert item.transformer_code == "TFR:ENTC:TARGET_RENEWABLE_ELEC"
    assert item.name == "NDC · ENTC: Renewable electricity target"
    assert item.config["parameters"]["magnitude"] == 0.85
    assert item.config["parameters"]["dict_entc_renewable_target_msp"] == {"pp_wind": 0.5, "pp_solar": 0.35}
    # one transformation per transformer
    assert len({i.transformer_code for i in items}) == 18


def test_library_loads_into_collection(tx, catalog):
    items = library_service.add_library_to_collection(tx, catalog)
    assert [i.code for i in items if not i.ok] == []
    assert all(i.code in tx.dict_transformations for i in items)
    assert "TX:ENTC:TARGET_RENEWABLE_ELEC_STRATEGY_NDC" in tx.attribute_transformation.key_values


def test_add_library_pathway_holds_every_ndc_transformation(tx, catalog, bau_only):
    items = library_service.add_library_to_collection(tx, catalog)
    pathways, sid = pathway_service.add_library_pathway(bau_only, tx, items, name="NDC")
    assert pathways[sid].strategy.name == "NDC"
    assert sorted(pathways[sid].transformation_codes) == sorted(i.code for i in items)


# pathways


def test_empty_pathway_runs_as_baseline(tx, bau_only, baseline_df):
    pathways, sid = pathway_service.create_pathway(bau_only, tx, "Unconditional NDC")
    assert sid == 1000
    assert pathways[sid].transformation_codes == []
    out = pathways[sid].strategy(df_input=baseline_df)
    assert out[RICE_FIELD].iloc[-1] == pytest.approx(baseline_df[RICE_FIELD].iloc[-1])


def test_duplicate_names_and_blank_names_rejected(tx, bau_only):
    pathways, _ = pathway_service.create_pathway(bau_only, tx, "A")
    with pytest.raises(ValueError):
        pathway_service.create_pathway(pathways, tx, "A")
    with pytest.raises(ValueError):
        pathway_service.create_pathway(pathways, tx, "  ")


def test_add_remove_and_copy(tx, catalog, bau_only):
    pathways = pathway_service.save_transformation(bau_only, tx, _rice(catalog))
    pathways, a = pathway_service.create_pathway(pathways, tx, "A")
    pathways = pathway_service.add_to_pathway(pathways, tx, a, "TX:AGRC:DEC_CH4_RICE")
    pathways = pathway_service.add_to_pathway(pathways, tx, a, "TX:AGRC:DEC_CH4_RICE")  # no duplicates
    assert pathways[a].transformation_codes == ["TX:AGRC:DEC_CH4_RICE"]

    pathways, b = pathway_service.create_pathway(pathways, tx, "B", copy_from=a)
    assert pathways[b].transformation_codes == ["TX:AGRC:DEC_CH4_RICE"]
    assert pathway_service.pathways_using("TX:AGRC:DEC_CH4_RICE", pathways) == [a, b]

    pathways = pathway_service.remove_from_pathway(pathways, tx, a, "TX:AGRC:DEC_CH4_RICE")
    assert pathways[a].transformation_codes == []
    assert pathways[b].transformation_codes == ["TX:AGRC:DEC_CH4_RICE"]


def test_updating_a_transformation_updates_pathways(tx, catalog, bau_only, baseline_df):
    """Strategies capture transformation functions at build time; saving a
    new version must rebuild them, or runs would use stale parameters."""
    pathways = pathway_service.save_transformation(bau_only, tx, _rice(catalog, magnitude=0.2))
    pathways, a = pathway_service.create_pathway(pathways, tx, "A")
    pathways = pathway_service.add_to_pathway(pathways, tx, a, "TX:AGRC:DEC_CH4_RICE")
    before = pathways[a].strategy(df_input=baseline_df)[RICE_FIELD].iloc[-1]

    pathways = pathway_service.save_transformation(pathways, tx, _rice(catalog, magnitude=0.8))
    after = pathways[a].strategy(df_input=baseline_df)[RICE_FIELD].iloc[-1]
    base = baseline_df[RICE_FIELD].iloc[-1]
    assert before == pytest.approx(base * 0.8, rel=1e-3)
    assert after == pytest.approx(base * 0.2, rel=1e-3)


def test_delete_transformation_refuses_when_used(tx, catalog, bau_only):
    pathways = pathway_service.save_transformation(bau_only, tx, _rice(catalog))
    pathways, a = pathway_service.create_pathway(pathways, tx, "A")
    pathways = pathway_service.add_to_pathway(pathways, tx, a, "TX:AGRC:DEC_CH4_RICE")
    with pytest.raises(ValueError):
        pathway_service.delete_transformation(pathways, tx, "TX:AGRC:DEC_CH4_RICE")
    pathways = pathway_service.remove_from_pathway(pathways, tx, a, "TX:AGRC:DEC_CH4_RICE")
    pathways = pathway_service.delete_transformation(pathways, tx, "TX:AGRC:DEC_CH4_RICE")
    assert "TX:AGRC:DEC_CH4_RICE" not in tx.dict_transformations


def test_bau_is_protected(tx, bau_only):
    with pytest.raises(ValueError):
        pathway_service.delete_pathway(bau_only, 0)
    with pytest.raises(ValueError):
        pathway_service.set_pathway_codes(bau_only, tx, 0, [])


def test_grouping_and_stacked_warning(tx, catalog, bau_only):
    pathways = pathway_service.save_transformation(bau_only, tx, _rice(catalog, "TX:AGRC:DEC_CH4_RICE_B", 0.3))
    pathways = pathway_service.save_transformation(pathways, tx, _rice(catalog, "TX:AGRC:DEC_CH4_RICE_A", 0.2))
    pathways, a = pathway_service.create_pathway(pathways, tx, "A")
    pathways = pathway_service.set_pathway_codes(pathways, tx, a, ["TX:AGRC:DEC_CH4_RICE_B", "TX:AGRC:DEC_CH4_RICE_A"])
    groups = pathway_service.grouped_pathway(pathways[a], tx)
    # application order is code order, not insertion order
    assert groups["TFR:AGRC:DEC_CH4_RICE"] == ["TX:AGRC:DEC_CH4_RICE_A", "TX:AGRC:DEC_CH4_RICE_B"]
    assert pathway_service.stacked_transformers(pathways[a], tx) == ["TFR:AGRC:DEC_CH4_RICE"]


def test_summary(tx, catalog):
    ramp = ramp_service.ramp_from_policy(2026, 2040, "s_curve", YEARS)
    t = transformation_service.build_transformation(
        "TX:AGRC:X", "x", "TFR:AGRC:DEC_CH4_RICE", {"magnitude": 0.3, "vec_implementation_ramp": ramp}, catalog
    )
    default_ramp = ramp_service.catalog_default_ramp(catalog)
    assert pathway_service.summarize(t, "magnitude", YEARS, default_ramp) == "30% · 2026→2040 · S-curve"
    assert pathway_service.format_magnitude(0.99999) == "100%"
    assert pathway_service.format_magnitude(0.125) == "12.5%"
    assert pathway_service.format_magnitude(50) == "50"

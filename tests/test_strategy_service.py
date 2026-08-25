import pathlib

import pandas as pd
import pytest

from sisepuede_tool.services import catalog_service, strategy_service, transformation_service

FIXTURE_CSV = pathlib.Path(__file__).parent / "fixtures" / "example_input.csv"


@pytest.fixture(scope="module")
def transformers_catalog():
    df = pd.read_csv(FIXTURE_CSV)
    return catalog_service.build_transformers_catalog(df)


@pytest.fixture()
def transformations(transformers_catalog):
    coll = transformation_service.create_transformations_collection(transformers_catalog)
    for code, name, transformer_code in [
        ("TX:AGRC:B_EXPORTS", "b exports", "TFR:AGRC:DEC_EXPORTS"),
        ("TX:AGRC:A_LOSSES", "a losses", "TFR:AGRC:DEC_LOSSES_SUPPLY_CHAIN"),
    ]:
        t = transformation_service.build_transformation(
            code, name, transformer_code, {}, transformers_catalog
        )
        transformation_service.add_transformation(coll, t)
    return coll


def test_next_available_strategy_id_starts_at_1000():
    assert strategy_service.next_available_strategy_id([]) == 1000


def test_next_available_strategy_id_skips_taken_ids():
    assert strategy_service.next_available_strategy_id([1000, 1001]) == 1002


def test_build_baseline_strategy(transformations):
    strategy = strategy_service.build_baseline_strategy(transformations)
    assert strategy.id_num == 0
    assert strategy.code == "BASE"


def test_build_strategy_requires_at_least_one_transformation(transformations):
    with pytest.raises(ValueError):
        strategy_service.build_strategy(1000, [], transformations, name="Empty")


def test_build_strategy(transformations):
    strategy = strategy_service.build_strategy(
        1000, ["TX:AGRC:B_EXPORTS", "TX:AGRC:A_LOSSES"], transformations, name="My strategy"
    )
    assert strategy.id_num == 1000
    assert strategy.name == "My strategy"


def test_resolve_application_order_does_not_preserve_selection_order(transformations):
    """sisepuede itself reorders alphabetically by transformation code
    regardless of what order the user picked them in -- this is the
    behavior the Strategy Builder UI must display honestly."""
    order = strategy_service.resolve_application_order(
        ["TX:AGRC:B_EXPORTS", "TX:AGRC:A_LOSSES"], transformations
    )
    assert order == ["TX:AGRC:A_LOSSES", "TX:AGRC:B_EXPORTS"]


def test_strategy_actually_applies_in_the_resolved_order(transformations):
    strategy = strategy_service.build_strategy(
        1000, ["TX:AGRC:B_EXPORTS", "TX:AGRC:A_LOSSES"], transformations, name="My strategy"
    )
    assert len(strategy.function_list) == 2


def test_dry_run_executes_the_strategy(transformations):
    df = pd.read_csv(FIXTURE_CSV)
    strategy = strategy_service.build_strategy(
        1000, ["TX:AGRC:B_EXPORTS"], transformations, name="Just exports"
    )
    df_out = strategy_service.dry_run(strategy, df)
    assert df_out.shape[0] == df.shape[0]

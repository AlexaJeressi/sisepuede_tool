import pathlib

import pandas as pd
import pytest

from sisepuede_tool.services import catalog_service, transformation_service

FIXTURE_CSV = pathlib.Path(__file__).parent / "fixtures" / "example_input.csv"


@pytest.fixture(scope="module")
def transformers_catalog():
    df = pd.read_csv(FIXTURE_CSV)
    return catalog_service.build_transformers_catalog(df)


def test_build_transformation(transformers_catalog):
    transformation = transformation_service.build_transformation(
        transformation_code="TX:AGRC:TEST_RICE",
        transformation_name="Test rice",
        transformer_code="TFR:AGRC:DEC_CH4_RICE",
        parameters={"magnitude": 0.6, "vec_implementation_ramp": None},
        transformers_catalog=transformers_catalog,
        description="a test transformation",
    )

    assert transformation.code == "TX:AGRC:TEST_RICE"
    assert transformation.name == "Test rice"
    assert transformation.transformer_code == "TFR:AGRC:DEC_CH4_RICE"
    assert transformation.dict_parameters["magnitude"] == 0.6


def test_build_transformation_with_ramp_dict(transformers_catalog):
    ramp = {"n_tp_ramp": 20, "tp_0_ramp": 10, "alpha_logistic": 0.5, "d": 0, "window_logistic": (-8, 8)}
    transformation = transformation_service.build_transformation(
        transformation_code="TX:AGRC:TEST_RICE_RAMP",
        transformation_name="Test rice with custom ramp",
        transformer_code="TFR:AGRC:DEC_CH4_RICE",
        parameters={"magnitude": 0.3, "vec_implementation_ramp": ramp},
        transformers_catalog=transformers_catalog,
    )
    assert transformation.dict_parameters["vec_implementation_ramp"] == ramp


def test_suggest_transformation_code_no_collision():
    assert transformation_service.suggest_transformation_code("TFR:AGRC:DEC_CH4_RICE", set()) == (
        "TX:AGRC:DEC_CH4_RICE"
    )


def test_suggest_transformation_code_avoids_collision():
    existing = {"TX:AGRC:DEC_CH4_RICE", "TX:AGRC:DEC_CH4_RICE_2"}
    assert (
        transformation_service.suggest_transformation_code("TFR:AGRC:DEC_CH4_RICE", existing)
        == "TX:AGRC:DEC_CH4_RICE_3"
    )


def test_create_transformations_collection_starts_with_only_baseline(transformers_catalog):
    transformations = transformation_service.create_transformations_collection(transformers_catalog)
    assert list(transformations.dict_transformations.keys()) == [transformations.code_baseline]
    assert list(transformations.all_transformation_codes) == [transformations.code_baseline]


def test_add_and_remove_transformation_updates_attribute_table(transformers_catalog):
    transformations = transformation_service.create_transformations_collection(transformers_catalog)
    transformation = transformation_service.build_transformation(
        transformation_code="TX:AGRC:TEST_RICE",
        transformation_name="Test rice",
        transformer_code="TFR:AGRC:DEC_CH4_RICE",
        parameters={"magnitude": 0.6, "vec_implementation_ramp": None},
        transformers_catalog=transformers_catalog,
    )

    transformation_service.add_transformation(transformations, transformation)
    assert "TX:AGRC:TEST_RICE" in transformations.dict_transformations
    assert "TX:AGRC:TEST_RICE" in transformations.all_transformation_codes
    assert transformations.get_transformation("TX:AGRC:TEST_RICE").code == "TX:AGRC:TEST_RICE"

    transformation_service.remove_transformation(transformations, "TX:AGRC:TEST_RICE")
    assert "TX:AGRC:TEST_RICE" not in transformations.dict_transformations
    assert "TX:AGRC:TEST_RICE" not in transformations.all_transformation_codes


def test_remove_baseline_is_rejected(transformers_catalog):
    transformations = transformation_service.create_transformations_collection(transformers_catalog)
    with pytest.raises(ValueError):
        transformation_service.remove_transformation(transformations, transformations.code_baseline)


def test_transformation_runs_through_a_bare_strategy(transformers_catalog):
    """End-to-end: a Transformation added to the collection must be usable
    by a bare Strategy built directly against it -- this is the mechanism
    M3 (Strategy Builder) relies on."""
    import sisepuede.transformers as trf

    transformations = transformation_service.create_transformations_collection(transformers_catalog)
    transformation = transformation_service.build_transformation(
        transformation_code="TX:AGRC:TEST_EXPORTS",
        transformation_name="Test decrease exports",
        transformer_code="TFR:AGRC:DEC_EXPORTS",
        parameters={"magnitude": 0.4},
        transformers_catalog=transformers_catalog,
    )
    transformation_service.add_transformation(transformations, transformation)

    df = pd.read_csv(FIXTURE_CSV)
    strategy = trf.Strategy(1000, ["TX:AGRC:TEST_EXPORTS"], transformations, prebuild=False)
    df_out = strategy(df_input=df)
    assert df_out.shape[0] == df.shape[0]

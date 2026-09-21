import pathlib

import pytest

from sisepuede_tool.models.param_spec import WidgetKind
from sisepuede_tool.services import catalog_service, widget_metadata

FIXTURE_CSV = pathlib.Path(__file__).parent / "fixtures" / "example_input.csv"


@pytest.fixture(scope="module")
def model_attributes():
    return catalog_service.build_model_attributes()


@pytest.fixture(scope="module")
def transformers_catalog():
    import pandas as pd

    df = pd.read_csv(FIXTURE_CSV)
    return catalog_service.build_transformers_catalog(df)


def _spec_by_name(specs, name):
    return next(s for s in specs if s.name == name)


def test_numeric_param_gets_unit_interval_bounds(model_attributes, transformers_catalog):
    transformer = transformers_catalog.get_tkernel("TFR:AGRC:DEC_CH4_RICE")
    specs = widget_metadata.build_param_specs(transformer, model_attributes, transformers_catalog)

    magnitude = _spec_by_name(specs, "magnitude")
    assert magnitude.kind == WidgetKind.NUMERIC
    assert magnitude.default == 0.45
    assert magnitude.bounds == (0.0, 1.0)


def test_ramp_vector_param_gets_structured_defaults(model_attributes, transformers_catalog):
    transformer = transformers_catalog.get_tkernel("TFR:AGRC:DEC_CH4_RICE")
    specs = widget_metadata.build_param_specs(transformer, model_attributes, transformers_catalog)

    ramp = _spec_by_name(specs, "vec_implementation_ramp")
    assert ramp.kind == WidgetKind.RAMP_VECTOR
    assert set(ramp.default.keys()) == {"n_tp_ramp", "tp_0_ramp", "alpha_logistic", "d", "window_logistic"}
    assert ramp.default["window_logistic"][0] < 0 < ramp.default["window_logistic"][1]
    assert ramp.extra["total_time_periods"] == 36


def test_ramp_default_matches_actual_catalog_ramp_vector(transformers_catalog):
    """The dict a fresh widget submits unchanged must build the same ramp
    vector sisepuede would have used anyway (see check_implementation_ramp),
    so leaving every ramp field at its default is a true no-op."""
    import numpy as np

    ramp_dict = widget_metadata._ramp_default(transformers_catalog)
    rebuilt = transformers_catalog.build_implementation_ramp_vector(**ramp_dict)
    assert np.allclose(rebuilt, transformers_catalog.vec_implementation_ramp)


def test_categorical_param_resolves_real_choices(model_attributes, transformers_catalog):
    transformer = transformers_catalog.get_tkernel("TFR:TRNS:SHIFT_FUEL_LIGHT_DUTY")
    specs = widget_metadata.build_param_specs(transformer, model_attributes, transformers_catalog)

    categories = _spec_by_name(specs, "categories")
    assert categories.kind == WidgetKind.CATEGORICAL_MULTI
    assert categories.default == ["road_light"]
    assert categories.choices is not None
    assert "road_light" in categories.choices


def test_bool_param(model_attributes, transformers_catalog):
    transformer = transformers_catalog.get_tkernel("TFR:AGRC:INC_CONSERVATION_AGRICULTURE")
    specs = widget_metadata.build_param_specs(transformer, model_attributes, transformers_catalog)

    return_dict = _spec_by_name(specs, "return_dict_magnitude")
    assert return_dict.kind == WidgetKind.BOOL
    assert return_dict.default is False


def test_overrides_are_applied_on_top_of_inference(model_attributes, transformers_catalog):
    transformer = transformers_catalog.get_tkernel("TFR:AGRC:DEC_CH4_RICE")
    overrides = {
        "TFR:AGRC:DEC_CH4_RICE": {
            "magnitude": {"bounds": [0.0, 0.9], "help_text": "custom help"},
        }
    }
    specs = widget_metadata.build_param_specs(
        transformer, model_attributes, transformers_catalog, overrides=overrides
    )

    magnitude = _spec_by_name(specs, "magnitude")
    assert magnitude.bounds == (0.0, 0.9)
    assert magnitude.help_text == "custom help"


def test_skips_internal_params(model_attributes, transformers_catalog):
    transformer = transformers_catalog.get_tkernel("TFR:AGRC:DEC_CH4_RICE")
    specs = widget_metadata.build_param_specs(transformer, model_attributes, transformers_catalog)
    names = {s.name for s in specs}
    assert "df_input" not in names
    assert "strat" not in names


def test_build_param_specs_does_not_error_for_any_non_baseline_transformer(
    model_attributes, transformers_catalog
):
    """Every real transformer's signature must be introspectable without
    raising -- this is the coverage guarantee for the whole widget
    generation approach (~70 heterogeneous signatures)."""
    for code in transformers_catalog.all_tkernels_non_baseline:
        transformer = transformers_catalog.get_tkernel(code)
        specs = widget_metadata.build_param_specs(transformer, model_attributes, transformers_catalog)
        assert isinstance(specs, list)


def test_load_overrides_reads_shipped_resource_file():
    from sisepuede_tool import config as _config  # noqa: F401
    import sisepuede_tool

    resource_path = (
        pathlib.Path(sisepuede_tool.__file__).parent / "resources" / "transformer_widget_metadata.yaml"
    )
    overrides = widget_metadata.load_overrides(resource_path)
    assert isinstance(overrides, dict)

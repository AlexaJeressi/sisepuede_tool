import json

import pytest

from sisepuede_tool.models.param_spec import ParamSpec, WidgetKind
from sisepuede_tool.ui.components import param_widget


class FakeInputs:
    """Minimal stand-in for shiny's `input`: input[id]() returns the value."""

    def __init__(self, values: dict):
        self._values = values

    def __getitem__(self, key):
        return lambda: self._values[key]


def test_read_params_ramp_vector_happy_path():
    specs = [
        ParamSpec(
            name="vec_implementation_ramp",
            kind=WidgetKind.RAMP_VECTOR,
            default={},
            extra={"total_time_periods": 36},
        )
    ]
    inputs = FakeInputs(
        {
            "param__vec_implementation_ramp__n_tp_ramp": 20,
            "param__vec_implementation_ramp__tp_0_ramp": 10,
            "param__vec_implementation_ramp__alpha_logistic": 0.5,
            "param__vec_implementation_ramp__window_lower": -8,
            "param__vec_implementation_ramp__window_upper": 8,
            "param__vec_implementation_ramp__d": 0,
        }
    )

    values = param_widget.read_params(inputs, specs)

    assert values["vec_implementation_ramp"] == {
        "n_tp_ramp": 20,
        "tp_0_ramp": 10,
        "alpha_logistic": 0.5,
        "d": 0.0,
        "window_logistic": (-8, 8),
    }


def test_read_params_ramp_vector_rejects_invalid_window_sign():
    specs = [
        ParamSpec(
            name="vec_implementation_ramp", kind=WidgetKind.RAMP_VECTOR, default={},
            extra={"total_time_periods": 36},
        )
    ]
    inputs = FakeInputs(
        {
            "param__vec_implementation_ramp__n_tp_ramp": 20,
            "param__vec_implementation_ramp__tp_0_ramp": 10,
            "param__vec_implementation_ramp__alpha_logistic": 0.5,
            "param__vec_implementation_ramp__window_lower": 3,  # invalid: must be < 0
            "param__vec_implementation_ramp__window_upper": 8,
            "param__vec_implementation_ramp__d": 0,
        }
    )

    with pytest.raises(param_widget.ParamReadError, match="window_logistic"):
        param_widget.read_params(inputs, specs)


def test_read_params_ramp_vector_rejects_d_outside_window():
    specs = [
        ParamSpec(
            name="vec_implementation_ramp", kind=WidgetKind.RAMP_VECTOR, default={},
            extra={"total_time_periods": 36},
        )
    ]
    inputs = FakeInputs(
        {
            "param__vec_implementation_ramp__n_tp_ramp": 20,
            "param__vec_implementation_ramp__tp_0_ramp": 10,
            "param__vec_implementation_ramp__alpha_logistic": 0.5,
            "param__vec_implementation_ramp__window_lower": -8,
            "param__vec_implementation_ramp__window_upper": 8,
            "param__vec_implementation_ramp__d": 10,  # invalid: outside (-8, 8)
        }
    )

    with pytest.raises(param_widget.ParamReadError, match="must lie strictly between"):
        param_widget.read_params(inputs, specs)


def test_read_params_json_kind():
    specs = [ParamSpec(name="dict_lsmm_pathways", kind=WidgetKind.JSON, default={})]
    inputs = FakeInputs({"param__dict_lsmm_pathways": json.dumps({"a": 1.0})})

    values = param_widget.read_params(inputs, specs)
    assert values["dict_lsmm_pathways"] == {"a": 1.0}


def test_read_params_json_kind_rejects_invalid_json():
    specs = [ParamSpec(name="dict_lsmm_pathways", kind=WidgetKind.JSON, default={})]
    inputs = FakeInputs({"param__dict_lsmm_pathways": "{not valid json"})

    with pytest.raises(param_widget.ParamReadError, match="invalid JSON"):
        param_widget.read_params(inputs, specs)


def test_read_params_categorical_multi_free_text_fallback():
    specs = [ParamSpec(name="categories", kind=WidgetKind.CATEGORICAL_MULTI, default=[], choices=None)]
    inputs = FakeInputs({"param__categories": "road_light, road_heavy_freight"})

    values = param_widget.read_params(inputs, specs)
    assert values["categories"] == ["road_light", "road_heavy_freight"]


def test_read_params_numeric_and_bool():
    specs = [
        ParamSpec(name="magnitude", kind=WidgetKind.NUMERIC, default=0.45, bounds=(0.0, 1.0)),
        ParamSpec(name="return_dict_magnitude", kind=WidgetKind.BOOL, default=False),
    ]
    inputs = FakeInputs({"param__magnitude__precise": 0.99999, "param__return_dict_magnitude": True})

    values = param_widget.read_params(inputs, specs)
    assert values == {"magnitude": 0.99999, "return_dict_magnitude": True}


def test_empty_multi_select_reads_as_none_and_tuples_as_lists():
    """An empty selection means sisepuede's default (None), not []; selectize
    returns tuples, which are saved as lists."""
    specs = [
        ParamSpec(name="cats_a", kind=WidgetKind.CATEGORICAL_MULTI, default=[], choices=["x", "y"]),
        ParamSpec(name="cats_b", kind=WidgetKind.CATEGORICAL_MULTI, default=[], choices=["x", "y"]),
        ParamSpec(name="cats_c", kind=WidgetKind.CATEGORICAL_MULTI, default=[], choices=None),
    ]
    inputs = FakeInputs({"param__cats_a": (), "param__cats_b": ("x", "y"), "param__cats_c": "  "})
    assert param_widget.read_params(inputs, specs) == {"cats_a": None, "cats_b": ["x", "y"], "cats_c": None}


YEARS = list(range(2015, 2051))
_RAMP_SPEC = ParamSpec(
    name="vec_implementation_ramp",
    kind=WidgetKind.RAMP_VECTOR,
    default={"n_tp_ramp": 22, "tp_0_ramp": 13, "alpha_logistic": 0.0, "d": 0, "window_logistic": (-8, 8)},
    extra={"total_time_periods": 36},
)


def test_read_editor_params_policy_ramp():
    inputs = FakeInputs(
        {
            "param__vec_implementation_ramp__raw_on": False,
            "param__vec_implementation_ramp__years": (2026, 2040),
            "param__vec_implementation_ramp__shape": "s_curve",
            "param__magnitude__precise": 0.3,
        }
    )
    specs = [ParamSpec(name="magnitude", kind=WidgetKind.NUMERIC, default=0.45, bounds=(0.0, 1.0)), _RAMP_SPEC]
    values = param_widget.read_editor_params(inputs, specs, YEARS)
    assert values["magnitude"] == 0.3
    assert values["vec_implementation_ramp"] == {
        "tp_0_ramp": 10,
        "n_tp_ramp": 15,
        "alpha_logistic": 1.0,
        "d": 0,
        "window_logistic": [-5.0, 5.0],
    }


def test_read_editor_params_raw_ramp_in_advanced():
    inputs = FakeInputs(
        {
            "param__vec_implementation_ramp__raw_on": True,
            "param__vec_implementation_ramp__n_tp_ramp": 20,
            "param__vec_implementation_ramp__tp_0_ramp": 10,
            "param__vec_implementation_ramp__alpha_logistic": 0.5,
            "param__vec_implementation_ramp__window_lower": -8,
            "param__vec_implementation_ramp__window_upper": 4,
            "param__vec_implementation_ramp__d": 0,
        }
    )
    ramp = param_widget.read_editor_params(inputs, [_RAMP_SPEC], YEARS)["vec_implementation_ramp"]
    assert ramp["alpha_logistic"] == 0.5
    assert ramp["window_logistic"] == [-8.0, 4.0]


def test_read_editor_params_rejects_equal_years():
    inputs = FakeInputs(
        {
            "param__vec_implementation_ramp__raw_on": False,
            "param__vec_implementation_ramp__years": (2030, 2030),
            "param__vec_implementation_ramp__shape": "linear",
        }
    )
    with pytest.raises(param_widget.ParamReadError):
        param_widget.read_editor_params(inputs, [_RAMP_SPEC], YEARS)

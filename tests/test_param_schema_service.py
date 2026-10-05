import inspect
import pathlib

import numpy as np
import pandas as pd
import pytest

from sisepuede_tool.models.param_spec import WidgetKind
from sisepuede_tool.services import catalog_service, param_schema_service as pss, transformation_service, widget_metadata
from sisepuede_tool.ui.components import param_widget

EGYPT_CSV = pathlib.Path(__file__).parent / "fixtures" / "egypt_baseline_biomass_fix.csv"
SCHEMAS = pss.load_schemas()


class FakeInputs:
    def __init__(self, values: dict):
        self._values = values

    def __getitem__(self, key):
        return lambda: self._values.get(key)


@pytest.fixture(scope="module")
def model_attributes():
    return catalog_service.build_model_attributes()


@pytest.fixture(scope="module")
def df_baseline():
    return pd.read_csv(EGYPT_CSV)


@pytest.fixture(scope="module")
def transformers_catalog(df_baseline):
    return catalog_service.build_transformers_catalog(df_baseline)


def _schema_items():
    for code, params in SCHEMAS.items():
        for name, schema in params.items():
            yield code, name, schema


def _table_spec(transformers_catalog, model_attributes, code, name):
    specs = widget_metadata.build_param_specs(transformers_catalog.get_tkernel(code), model_attributes, transformers_catalog)
    return next(s for s in specs if s.name == name)


def _inputs_for_default(spec):
    """Fake inputs holding the table's pre-filled (default) cells."""
    schema = spec.schema
    keys = schema["keys"]
    current = pss.expand_value(schema, spec.default, keys)
    return FakeInputs({param_widget._cell_id(spec.name, k): param_widget._to_display(schema, current.get(k)) for k in keys})


# ---------------------------------------------------------------- the YAML itself


def test_every_schema_param_exists_in_the_transformer(transformers_catalog):
    for code, name, _ in _schema_items():
        params = inspect.signature(transformers_catalog.get_tkernel(code).function).parameters
        assert name in params, f"{code}.{name} is not a parameter"


def test_every_schema_key_exists_in_its_table(model_attributes):
    cat = model_attributes.dict_attributes["cat"]
    for code, name, schema in _schema_items():
        for field in ("keys", "keys_out", "keys_in"):
            spec = schema.get(field)
            if not spec:
                continue
            assert spec["table"] in cat, f"{code}.{name}: unknown table {spec['table']}"
            missing = set(spec.get("only", [])) - set(cat[spec["table"]].key_values)
            assert not missing, f"{code}.{name}: {missing} not in {spec['table']}"


def test_every_default_key_is_an_allowed_key(model_attributes):
    for code, name, schema in _schema_items():
        default = schema.get("default")
        if schema.get("widget") in (pss.WIDGET_SHARES, pss.WIDGET_VALUES) and isinstance(default, dict):
            keys = pss.resolve_keys(schema["keys"], model_attributes)
            assert set(default) <= set(keys), f"{code}.{name}: {set(default) - set(keys)}"
        if schema.get("widget") in (pss.WIDGET_SHARES, pss.WIDGET_VALUES) and default:
            ok, message = pss.check_sum(default, schema.get("sum_rule"))
            assert ok, f"{code}.{name} default: {message}"


def test_key_labels_match_by_row(model_attributes):
    # the table order differs from key_values; names must follow the key
    labels = pss.key_labels({"table": "fuel", "only": ["fuel_diesel", "fuel_electricity"]}, model_attributes)
    assert labels == {"fuel_diesel": "Diesel", "fuel_electricity": "Electricity"}


# ---------------------------------------------------------------- sum rules


def test_check_sum_rules():
    assert pss.check_sum({"a": 0.5, "b": 0.5}, pss.SUM_EQ1)[0]
    assert not pss.check_sum({"a": 0.5, "b": 0.4}, pss.SUM_EQ1)[0]
    assert pss.check_sum({"a": 0.5, "b": 0.4}, pss.SUM_LEQ1)[0]
    assert not pss.check_sum({"a": 0.7, "b": 0.4}, pss.SUM_LEQ1)[0]
    assert pss.check_sum({"a": 3.0}, pss.SUM_NONE)[0]


def test_normalize_for_rule_gives_exact_totals():
    out = pss.normalize_for_rule({"a": 0.333, "b": 0.333, "c": 0.334}, pss.SUM_EQ1)
    assert sum(out.values()) == 1.0
    out = pss.normalize_for_rule({"a": 0.1, "b": 0.2, "c": 0.7000000001}, pss.SUM_LEQ1)
    assert sum(out.values()) <= 1.0


# ---------------------------------------------------------------- widget read-back


def test_wali_table_reads_percent_as_fractions(transformers_catalog, model_attributes):
    spec = _table_spec(transformers_catalog, model_attributes, "TFR:WALI:INC_TREATMENT_URBAN", "dict_magnitude")
    assert spec.kind == WidgetKind.DICT_TABLE and spec.tier == "basic"
    inputs = FakeInputs({
        param_widget._cell_id(spec.name, "treated_septic"): 60.0,
        param_widget._cell_id(spec.name, "treated_primary"): 30.0,
    })
    values = param_widget.read_params(inputs, [spec])
    assert values == {"dict_magnitude": pytest.approx({"treated_septic": 0.6, "treated_primary": 0.3})}


def test_wali_table_over_100_percent_is_rejected(transformers_catalog, model_attributes):
    spec = _table_spec(transformers_catalog, model_attributes, "TFR:WALI:INC_TREATMENT_URBAN", "dict_magnitude")
    inputs = FakeInputs({
        param_widget._cell_id(spec.name, "treated_septic"): 70.0,
        param_widget._cell_id(spec.name, "treated_primary"): 40.0,
    })
    with pytest.raises(param_widget.ParamReadError, match="above 100%"):
        param_widget.read_params(inputs, [spec])


def test_trns_fuel_mix_must_total_100(transformers_catalog, model_attributes):
    spec = _table_spec(transformers_catalog, model_attributes, "TFR:TRNS:SHIFT_FUEL_LIGHT_DUTY", "dict_fuel_allocation")
    bad = FakeInputs({param_widget._cell_id(spec.name, "fuel_electricity"): 80.0})
    with pytest.raises(param_widget.ParamReadError, match="exactly 100%"):
        param_widget.read_params(bad, [spec])
    good = FakeInputs({
        param_widget._cell_id(spec.name, "fuel_electricity"): 70.0,
        param_widget._cell_id(spec.name, "fuel_hydrogen"): 30.0,
    })
    values = param_widget.read_params(good, [spec])["dict_fuel_allocation"]
    assert sum(values.values()) == 1.0


def test_blank_table_is_left_out(transformers_catalog, model_attributes):
    spec = _table_spec(transformers_catalog, model_attributes, "TFR:WALI:INC_TREATMENT_RURAL", "dict_magnitude")
    assert param_widget.read_params(FakeInputs({}), [spec]) == {}


def test_bounds_table_writes_delimited_keys(transformers_catalog, model_attributes):
    spec = _table_spec(transformers_catalog, model_attributes, "TFR:LNDU:BOUND_CLASSES", "dict_directional_categories_to_magnitude")
    inputs = FakeInputs({param_widget._cell_id(spec.name, "forests_primary", "min"): 1000.0})
    values = param_widget.read_params(inputs, [spec])
    assert values == {"dict_directional_categories_to_magnitude": {"forests_primary|min": 1000.0}}


def test_pairs_table_builds_nested_dict(transformers_catalog, model_attributes):
    spec = _table_spec(transformers_catalog, model_attributes, "TFR:ENTC:INCREASE_EFFICIENCY_FUEL_PROD", "dict_magnitudes")
    inputs = FakeInputs({
        param_widget._pair_id(spec.name, 0, "out"): "fuel_hydrogen",
        param_widget._pair_id(spec.name, 0, "in"): "fuel_electricity",
        param_widget._pair_id(spec.name, 0, "val"): 0.8,
    })
    values = param_widget.read_params(inputs, [spec])
    assert values == {"dict_magnitudes": {"fuel_hydrogen": {"fuel_electricity": 0.8}}}


def test_note_params_are_not_sent(transformers_catalog, model_attributes):
    specs = widget_metadata.build_param_specs(
        transformers_catalog.get_tkernel("TFR:TRNS:SHIFT_MODE_FREIGHT"), model_attributes, transformers_catalog
    )
    note = next(s for s in specs if s.name == "dict_categories_target")
    assert note.kind == WidgetKind.NOTE
    assert param_widget.read_params(FakeInputs({}), [note]) == {}


def test_lsmm_animals_list_uses_livestock(transformers_catalog, model_attributes):
    spec = _table_spec(transformers_catalog, model_attributes, "TFR:LSMM:INC_MANAGEMENT_POULTRY", "vec_cats_lvst")
    assert "chickens" in spec.choices and "anaerobic_digester" not in spec.choices


def test_schema_params_never_show_the_raw_name(transformers_catalog, model_attributes):
    for code in SCHEMAS:
        specs = widget_metadata.build_param_specs(transformers_catalog.get_tkernel(code), model_attributes, transformers_catalog)
        for spec in specs:
            if spec.name in SCHEMAS[code]:
                assert param_widget._label_text(spec) != spec.name


# ---------------------------------------------------------------- against sisepuede

_TABLE_DEFAULT_CASES = [
    (code, name)
    for code, name, schema in _schema_items()
    if schema.get("widget") in (pss.WIDGET_SHARES, pss.WIDGET_VALUES) and schema.get("default")
]


@pytest.mark.parametrize("code,name", _TABLE_DEFAULT_CASES)
def test_table_defaults_match_sisepuede_defaults(code, name, transformers_catalog, model_attributes, df_baseline):
    """The pre-filled table, read back and passed to sisepuede, gives the same
    result as leaving the parameter unset -- so the YAML defaults are
    sisepuede's real defaults -- and the result differs from the baseline."""
    spec = _table_spec(transformers_catalog, model_attributes, code, name)
    params = param_widget.read_params(_inputs_for_default(spec), [spec])
    assert name in params

    def run(parameters):
        tx = transformation_service.build_transformation("TX:TEST", "test", code, parameters, transformers_catalog)
        return tx().select_dtypes("number").to_numpy()

    with_table = run(params)
    unset = run({})
    np.testing.assert_allclose(with_table, unset, rtol=1e-9, atol=1e-12)
    base = df_baseline[transformers_catalog.get_tkernel(code)().columns].select_dtypes("number").to_numpy()
    if base.shape == with_table.shape:
        assert not np.allclose(with_table, base), f"{code} with its defaults doesn't change the baseline"

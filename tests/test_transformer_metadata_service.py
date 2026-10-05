import pathlib

import pandas as pd
import pytest

from sisepuede_tool.services import catalog_service, labels
from sisepuede_tool.services import transformer_metadata_service as tms

FIXTURE_CSV = pathlib.Path(__file__).parent / "fixtures" / "example_input.csv"


@pytest.fixture(scope="module")
def transformers_catalog():
    return catalog_service.build_transformers_catalog(pd.read_csv(FIXTURE_CSV))


# labels


def test_clean_label_strips_math_markup():
    assert labels.clean_label(r":math:\text{CH}_4 Anaerobic Biogas Emission Factor") == "CH₄ Anaerobic Biogas Emission Factor"
    assert labels.clean_label(r":math:\text{N}_2\text{O} Emissions") == "N₂O Emissions"
    assert labels.clean_label(r"Reduce :math:`\text{CH}_4` emissions") == "Reduce CH₄ emissions"


def test_strip_subsector_prefix():
    assert labels.strip_subsector_prefix("AGRC: Improve rice management") == "Improve rice management"
    assert labels.strip_subsector_prefix("No prefix") == "No prefix"


# pure helpers


def test_relative_change_handles_zero_baseline():
    import numpy as np

    b = np.array([[0.0, 0.0, 2.0]])
    x = np.array([[0.0, 1.0, 3.0]])
    assert tms._relative_change(x, b).tolist() == [[0.0, 1.0, 0.5]]


@pytest.mark.parametrize(
    "code,delta,fp,expected",
    [
        ("TFR:AGRC:DEC_CH4_RICE", -5.0, False, ("decreases", "decreases")),
        ("TFR:AGRC:DEC_CH4_RICE", 0.0001, False, ("no_change", "no_change")),
        ("TFR:TRNS:SHIFT_FUEL_LIGHT_DUTY", -70.0, True, ("decreases", "depends_on_grid")),
        ("TFR:ENTC:TARGET_RENEWABLE_ELEC", 0.0, True, ("no_change", "needs_electricity_model")),
        ("TFR:WASO:INC_RECYCLING", -10.0, True, ("decreases", "decreases")),
    ],
)
def test_classify_emissions(code, delta, fp, expected):
    effects = {"total_baseline_mtco2e": 600.0, "total_delta_mtco2e": delta}
    out = tms.classify_emissions(code, effects, fp)
    assert (out["direction_raw"], out["direction"]) == expected


def test_pick_display_variables_mixes_inputs_and_outputs():
    ins = [{"variable": f"i{k}"} for k in range(3)]
    outs = [{"variable": f"o{k}"} for k in range(3)]
    assert [v["variable"] for v in tms.pick_display_variables(ins, outs)] == ["i0", "i1", "o0", "o1"]
    assert [v["variable"] for v in tms.pick_display_variables(ins[:1], outs)] == ["i0", "o0", "o1", "o2"]
    assert [v["variable"] for v in tms.pick_display_variables(ins, [])] == ["i0", "i1", "i2"]


def test_merge_keeps_curated_and_replaces_computed():
    existing = {
        "transformers": {
            "TFR:A:X": {"curated": {"reviewed": True, "name": "Mine"}, "computed": {"status": "old"}},
            "TFR:GONE:Y": {"curated": {"name": "kept"}, "computed": {"status": "ok"}},
        }
    }
    new = {"TFR:A:X": {"status": "ok"}, "TFR:B:Z": {"status": "ok", "emissions_alone": {"direction": "depends_on_grid"}}}
    merged = tms.merge_catalog(new, existing, meta={})["transformers"]

    assert merged["TFR:A:X"]["curated"]["name"] == "Mine"
    assert merged["TFR:A:X"]["curated"]["reviewed"] is True
    assert "pair_with" in merged["TFR:A:X"]["curated"]  # template keys added
    assert merged["TFR:A:X"]["computed"] == {"status": "ok"}
    assert merged["TFR:B:Z"]["curated"]["pair_with"] == ["TFR:ENTC:TARGET_RENEWABLE_ELEC"]
    assert merged["TFR:GONE:Y"]["computed"]["status"] == "missing_in_sisepuede"


def test_save_and_load_round_trip(tmp_path):
    catalog = tms.merge_catalog({"TFR:A:X": {"status": "ok", "name": "CH₄ thing"}}, None, meta={"m": 1})
    path = tmp_path / "cat.yaml"
    tms.save_catalog(catalog, path)
    assert tms.load_catalog(path) == catalog


def test_get_card_prefers_curated():
    catalog = {
        "transformers": {
            "TFR:AGRC:DEC_CH4_RICE": {
                "curated": {"name": "Better rice", "emissions_direction": "decreases", "top_variables": [{"label": "x"}]},
                "computed": {"name": "AGRC: Improve rice management", "emissions_alone": {"direction": "increases"}},
            }
        }
    }
    card = tms.get_card("TFR:AGRC:DEC_CH4_RICE", catalog)
    assert card["name"] == "Better rice"
    assert card["emissions_direction"] == "decreases"
    assert card["top_variables"] == [{"label": "x"}]


# against sisepuede


def test_shipped_catalog_covers_every_transformer(transformers_catalog):
    catalog = tms.load_catalog()
    codes = set(catalog["transformers"])
    assert set(transformers_catalog.all_tkernels_non_baseline) <= codes


def test_variable_effects_for_rice(transformers_catalog):
    tk = transformers_catalog
    out = tms.compute_variable_effects(tk, tk.get_tkernel("TFR:AGRC:DEC_CH4_RICE")())
    top = out["top_variables"][0]
    assert top["direction"] == "decreases"
    assert "ef_agrc_anaerobicdom_rice_kg_ch4_ha" in top["example_fields"]
    assert top["max_relative_change"] == pytest.approx(0.45, abs=1e-3)


def test_build_entry_records_errors_instead_of_raising(transformers_catalog):
    # broken upstream on biomass_fix (renamed modvar); must not raise
    entry = tms.build_entry(transformers_catalog, "TFR:FRST:INCREASE_SEQUESTRATION")
    assert entry["status"] in {"error", "ok", "no_effect_on_baseline"}
    assert entry["name"]


def test_get_card_live_fallback(transformers_catalog):
    card = tms.get_card("TFR:AGRC:DEC_CH4_RICE", {"transformers": {}}, tk=transformers_catalog)
    assert card["status"] == "live"
    assert card["top_variables"][0]["direction"] == "decreases"

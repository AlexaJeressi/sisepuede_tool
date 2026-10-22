"""C&B by the Egypt Tableau workbook's CB sector / CB type, and the item
filters (services/cb_summary_service.py), on a small made-up result."""

import pandas as pd
import pytest

from sisepuede_tool.services import cb_summary_service as cbs

_VARS = {
    # variable: (sector, cb_type, item_1, item_2)
    "cb:trns:fuel_cost:trns:gasoline": ("trns", "fuel_cost", "trns", "gasoline"),
    "cb:trns:fuel_cost:trns:diesel": ("trns", "fuel_cost", "trns", "diesel"),
    "cb:entc:technical_cost:entc:X": ("entc", "technical_cost", "entc", "X"),
    "cb:fgtv:gas_recovery_savings:X:X": ("fgtv", "gas_recovery_savings", "X", "X"),
    "cb:agrc:crop_value:agrc:X": ("agrc", "crop_value", "agrc", "X"),
}


def _long():
    years = range(10, 13)  # 2025-2027
    rows = []
    for sid, scale in ((1, 1.0), (2, 2.0)):
        for tp in years:
            rows.append({"strategy_id": sid, "time_period": tp, **{v: scale * k for k, v in enumerate(_VARS, start=1)}})
    df_cb = pd.DataFrame(rows)
    df_cb["cb:entc:technical_cost:entc:X"] *= -1  # a cost
    attr = pd.DataFrame([{"variable": v, "sector": s, "cb_type": t, "item_1": i1, "item_2": i2} for v, (s, t, i1, i2) in _VARS.items()])
    return cbs.to_long(df_cb, attr)


def test_long_has_cb_sector_and_items():
    d = _long()
    assert list(d.columns) == cbs.LONG_COLUMNS
    row = d[d["variable"] == "cb:trns:fuel_cost:trns:gasoline"].iloc[0]
    assert (row["cb_sector"], row["item_1"], row["item_2"]) == ("Cost savings", "trns", "gasoline")
    # "X" (no item) becomes empty; a cb_type the workbook doesn't know is "Other"
    row = d[d["variable"] == "cb:fgtv:gas_recovery_savings:X:X"].iloc[0]
    assert (row["cb_sector"], row["item_1"], row["item_2"]) == ("Other", "", "")
    assert cbs.cb_sector_of("technical_cost") == "Capital costs"


def test_by_cb_type_totals_in_workbook_order():
    t = cbs.by_cb_type(_long(), 1)
    assert list(t["cb_type"]) == ["fuel_cost", "crop_value", "technical_cost", "gas_recovery_savings"]
    assert list(t["cb_sector"]) == ["Cost savings", "Food & Agriculture", "Capital costs", "Other"]
    values = dict(zip(t["cb_type"], t["value"]))
    assert values["fuel_cost"] == pytest.approx(3 * (1 + 2))  # gasoline + diesel, 3 years
    assert values["technical_cost"] == pytest.approx(-3 * 3)
    # discounted: smaller in absolute value
    assert abs(dict(zip(*cbs.by_cb_type(_long(), 1, 5.0)[["cb_type", "value"]].T.values))["fuel_cost"]) < 9


def test_filter_by_and_split_by_items():
    d = _long()
    f = cbs.filter_by(d, cb_type=["fuel_cost"], item_2=["diesel"], item_1=[])
    assert set(f["variable"]) == {"cb:trns:fuel_cost:trns:diesel"}
    assert cbs.filter_by(d, cb_type=None).equals(d)
    wide = cbs.by_group(d, 1, "item_2")
    assert set(wide.columns) == {"", "gasoline", "diesel"}
    wide = cbs.by_group(d, 1, "cb_type")
    assert list(wide.columns) == ["fuel_cost", "crop_value", "technical_cost", "gas_recovery_savings"]
    assert cbs.item_label("") == "(none)"


def test_crosswalk_file_is_complete():
    """resources/cb_groups.yaml: each cb_type once, named in every language, a
    valid colour, a known category; each sector named in every language."""
    import re

    import yaml

    data = yaml.safe_load(cbs.groups_path().read_text(encoding="utf-8"))
    types = [t["cb_type"] for s in data["sectors"] for t in s["types"]]
    assert len(types) == len(set(types))
    for block in data["sectors"]:
        assert set(block["sector"]) == {"en", "es", "ar"} and all(block["sector"].values())
        for t in block["types"]:
            assert set(t["name"]) == {"en", "es", "ar"} and all(t["name"].values()), t["cb_type"]
            assert re.fullmatch(r"#[0-9A-Fa-f]{6}", t["color"]), t["cb_type"]
            assert t.get("category") in (None, *data["categories"]), t["cb_type"]
    assert cbs.CB_SECTOR_ORDER[-1] == cbs.OTHER


def test_names_by_language():
    assert cbs.cb_type_name("crop_value", "es") == "Valor de los cultivos"
    assert cbs.cb_type_name("crop_value", "fr") == "Crop value"  # unknown language: English
    assert cbs.cb_type_name("new_type") == "New type"  # not in the file
    assert cbs.cb_sector_name("Cost savings", "es") == "Ahorro de costos"
    assert cbs.cb_sector_name(cbs.OTHER, "es") == "Otros"

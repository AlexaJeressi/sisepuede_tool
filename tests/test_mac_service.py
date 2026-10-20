"""Marginal abatement cost (services/mac_service.py), read from the static
sisepuede_a6 ref/temporary_mac.csv."""

import pandas as pd
import pytest

from sisepuede_tool.services import library_service
from sisepuede_tool.services import mac_service as mac


def _df():
    return pd.DataFrame(
        {
            "code": ["TX:TRNS:A", "TX:TRNS:B", "TX:WASO:C", "TX:ENTC:D", "TX:TRNS:A", "TX:ENTC:D"],
            "subsector": ["All", "All", "All", "All", "Transportation", "Transportation"],
            "mean": [5.0, -1.0, 0.0, 2.0, 50.0, 0.0],
            "tornado": [8.0, 3.0, 0.0, 1.0, 60.0, 0.0],
            "whirlpool": [2.0, -5.0, 4.0, 3.0, 40.0, 0.0],
        }
    )


def test_rows_sort_by_mean_unless_one_other_measure():
    assert list(mac.rows(_df(), "", "All", ["mean"])["code"]) == ["TX:TRNS:B", "TX:ENTC:D", "TX:TRNS:A"]  # C is zero
    assert list(mac.rows(_df(), "", "All", ["tornado", "whirlpool"])["code"]) == ["TX:TRNS:B", "TX:WASO:C", "TX:ENTC:D", "TX:TRNS:A"]
    assert list(mac.rows(_df(), "", "All", ["whirlpool"])["code"]) == ["TX:TRNS:B", "TX:TRNS:A", "TX:ENTC:D", "TX:WASO:C"]
    assert mac.zero_codes(_df(), "", "All", ["mean"]) == ["TX:WASO:C"]
    assert mac.rows(_df(), "", "All", []).empty


def test_filter_by_transformation_subsector():
    assert mac.transformation_subsectors(_df()) == ["entc", "trns", "waso"]
    assert list(mac.rows(_df(), "trns", "All", ["mean"])["code"]) == ["TX:TRNS:B", "TX:TRNS:A"]
    assert mac.rows(_df(), "waso", "All", ["mean"]).empty
    assert mac.zero_codes(_df(), "waso", "All", ["mean"]) == ["TX:WASO:C"]


def test_filter_by_subsector_measured_in():
    assert mac.measured_subsectors(_df()) == ["All", "Transportation"]
    r = mac.rows(_df(), "", "Transportation", ["mean"])
    assert list(r["code"]) == ["TX:TRNS:A"] and r["mean"].iloc[0] == 50.0
    assert mac.zero_codes(_df(), "", "Transportation", ["mean"]) == ["TX:ENTC:D"]
    # both filters together; "" measured in = the whole economy
    assert list(mac.rows(_df(), "entc", "Transportation", ["mean"])["code"]) == []
    assert list(mac.rows(_df(), "trns", "", ["mean"])["code"]) == ["TX:TRNS:B", "TX:TRNS:A"]


def test_scale_helpers():
    assert mac.axis_limit([1.0, -2.0, 3.0]) is None
    assert mac.axis_limit([1.0, -10.0, 2850.0]) == pytest.approx(13.0)
    assert not mac.wants_log([1.0, -10.0, 2850.0])
    assert not mac.wants_log([1.0, 2.0, 3.0, -4e10])  # one outlier: cut on a linear axis
    assert mac.wants_log([1.0, 2.0, 3.0, -4e10, 5e9])
    assert mac.signed_log(-99.0) == pytest.approx(-2.0)
    assert mac.log_ticks(-5.0, 20.0) == [-10.0, -1.0, 0.0, 1.0, 10.0, 100.0]
    # a wide axis leaves out 1 and 10, which crowd 0
    assert mac.log_ticks(-50.0, 2000.0) == [-100.0, -10.0, 0.0, 10.0, 100.0, 1000.0, 10000.0]
    assert mac.log_ticks(-4e10, 400.0) == [-1e10, -1e8, -1e6, -1e4, -100.0, 0.0, 100.0]
    assert mac.log_ticks(0.0, 1e12) == [0.0, 100.0, 1e4, 1e6, 1e8, 1e10, 1e12]


def test_subsector_of():
    assert mac.subsector_of("TX:TRNS:SHIFT_FUEL_RAIL_STRATEGY_NDC") == "trns"
    assert mac.subsector_of("bad") == ""


@pytest.mark.skipif(not mac.MAC_PATH.exists(), reason=f"{mac.MAC_PATH} not found")
def test_load_file():
    df = mac.load()
    assert list(df.columns) == ["code", "subsector", "mean", "tornado", "whirlpool"]
    assert not df.duplicated(["code", "subsector"]).any()
    subs = mac.measured_subsectors(df)
    assert subs[0] == mac.SUBSECTOR_ALL
    assert set(subs) - {mac.SUBSECTOR_ALL} <= set(mac.SUBSECTOR_ABV)
    assert len(mac.transformation_subsectors(df)) > 1
    # every transformation is in the NDC library, so the page can name it
    assert set(df["code"]) <= {i.code for i in library_service.load_library()}

"""Article 6 charts (ui/components/result_charts.py): credit bars and the
pathway gap band."""

import pandas as pd
import pytest

from sisepuede_tool.ui.components import result_charts as rc


def test_gap_segments_split_where_the_lines_cross():
    # the pathway starts above the reference and crosses it half-way between 2031 and 2032
    seg = rc._gap_segments([2030, 2031, 2032], [10.0, 10.0, 10.0], [14.0, 12.0, 8.0])
    assert [s[0] for s in seg] == [False, True]  # above, then below
    above, below = seg
    assert above[1] == [2030.0, 2031.0, 2031.5] and below[1][0] == 2031.5
    assert above[3][-1] == pytest.approx(10.0) and below[3] == [10.0, 8.0]


def test_gap_band_colours_and_legend():
    s = {"NDC": pd.Series([10.0, 10.0, 10.0], index=[2030, 2031, 2032]), "LEP": pd.Series([14.0, 12.0, 8.0], index=[2030, 2031, 2032])}
    fig = rc.gap_lines(s, {}, "Mt", gaps=[("NDC", "LEP")], gap_label="below", above_label="above")
    fills = [t for t in fig.data if t.fill == "tonexty"]
    assert [t.name for t in fills] == ["above", "below"] and all(t.showlegend for t in fills)
    assert "192,57,43" in fills[0].fillcolor and "46,139,87" in fills[1].fillcolor


def test_credit_bars_put_negative_groups_below_zero():
    frame = pd.DataFrame({"year": [2030, 2030], "series": ["Energy", "Transport"], "value": [-500.0, 200.0]})
    fig = rc.credit_bars({"LEP": frame}, {}, ["Energy", "Transport"], "M USD")
    assert fig.layout.barmode == "relative"
    (label,) = fig.layout.annotations[1:]  # [0] is the panel title
    # the total (-300) is written under the negative part of the bar
    assert (label.text, label.y, label.yshift) == ("-300", -500.0, -10)

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


def test_years_after_the_ndc_targets_are_grey():
    s = {"NDC": pd.Series([10.0, 10.0, 10.0], index=[2034, 2035, 2036])}
    fig = rc.gap_lines(s, {}, "Mt", outside=(2035, "after 2035"))
    (rect,) = fig.layout.shapes
    assert (rect.x0, rect.x1) == (2035, 2036) and fig.layout.annotations[-1].text == "after 2035"
    # no shading when the shown years end before it
    assert not rc.gap_lines(s, {}, "Mt", outside=(2036, "after 2036")).layout.shapes


def test_credit_bars_put_negative_groups_below_zero():
    frame = pd.DataFrame({"year": [2030, 2030], "series": ["Energy", "Transport"], "value": [-500.0, 200.0]})
    fig = rc.credit_bars({"LEP": frame}, {}, ["Energy", "Transport"], "M USD")
    assert fig.layout.barmode == "relative"
    (label,) = fig.layout.annotations[1:]  # [0] is the panel title
    # the total (-300) is written under the negative part of the bar
    assert (label.text, label.y, label.yshift) == ("-300", -500.0, -10)


def test_credit_bars_grey_after_the_ndc_targets():
    frame = pd.DataFrame({"year": [2034, 2035, 2036, 2037], "series": ["Energy"] * 4, "value": [1.0, 2.0, 3.0, 4.0]})
    fig = rc.credit_bars({"NDC": frame, "LEP": frame}, {}, ["Energy"], "M USD", outside=(2035, "after 2035"))
    # one band per panel, on the category positions of 2036 and 2037
    assert [(r.x0, r.x1) for r in fig.layout.shapes] == [(1.5, 3.5), (1.5, 3.5)]
    assert not rc.credit_bars({"NDC": frame}, {}, ["Energy"], "M USD", outside=(2037, "x")).layout.shapes


def test_credit_bars_split_a_group_into_its_parts():
    frame = pd.DataFrame({"year": [2030, 2030], "series": ["Energy", "Energy"], "part": ["TFR:A", "TFR:B"], "mac": [-5.0, 10.0], "value": [10.0, 30.0]})
    fig = rc.credit_bars({"LEP": frame}, {"Energy": "#E0A040"}, ["Energy"], "M USD", part_labels={"TFR:A": "Alpha"})
    assert [t.y.tolist() for t in fig.data] == [[10.0], [30.0]]  # in the frame's order
    assert all(t.marker.color == "#E0A040" for t in fig.data)  # the group's colour
    assert "Alpha" in fig.data[0].hovertemplate and "MAC -5.0" in fig.data[0].hovertemplate
    assert fig.layout.annotations[-1].text == "40.0"  # the group total


def test_ranked_hover_lists_the_projects():
    frame = pd.DataFrame({"year": [2030], "series": ["Energy"], "part": ["TFR:A"], "mac": [5.0], "value": [10.0]})
    fig = rc.credit_bars({"LEP": frame}, {}, ["Energy"], "M USD", part_projects={"TFR:A": ["Solar park · Planned"]})
    assert "Solar park · Planned" in fig.data[0].hovertemplate and "1 project" in fig.data[0].hovertemplate

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


def test_ranked_projects_for_the_panel_not_the_hover():
    frame = pd.DataFrame({"year": [2030], "series": ["Energy"], "part": ["TFR:A"], "mac": [5.0], "value": [10.0]})
    fig = rc.credit_bars({"LEP": frame}, {}, ["Energy"], "M USD", part_labels={"TFR:A": "Alpha"},
                         part_projects={"TFR:A": ["Solar park", "Wind farm"]})
    tr = fig.data[0]
    assert "2 projects" in tr.hovertemplate and "Solar park" not in tr.hovertemplate
    assert tr.hoverlabel.bgcolor.startswith("rgba(")  # see-through
    name, detail, count, projects = tr.customdata[0]
    assert name == "Alpha" and detail.startswith("Energy · 2030 · 10.0 M USD · MAC 5.0")
    assert count == "2 projects" and projects == "Solar park\nWind farm"


def test_transport_not_purple_like_energy_technology(monkeypatch):
    class MA:
        def get_subsector_color_map(self):
            return {"emission_co2e_subsector_total_entc": "#6B6ECF", "emission_co2e_subsector_total_trns": "#756BB1"}

    monkeypatch.setattr(rc, "SUBSECTOR_COLORS", dict(rc.SUBSECTOR_COLORS))
    rc.use_model_subsector_colors(MA())
    assert rc.SUBSECTOR_COLORS["entc"] == "#6B6ECF"  # the model's
    assert rc.SUBSECTOR_COLORS["trns"] == rc.SUBSECTOR_COLOR_OVERRIDES["trns"]
    # wastewater no longer a red next to transport's orange
    assert rc.SUBSECTOR_COLORS["trww"] == rc.SUBSECTOR_COLOR_OVERRIDES["trww"] != rc.SUBSECTOR_COLORS["trns"]


def test_ranked_hover_only_in_the_panel():
    frame = pd.DataFrame({"year": [2030], "series": ["Energy"], "part": ["TFR:A"], "mac": [5.0], "value": [10.0]})
    tr = rc.credit_bars({"LEP": frame}, {}, ["Energy"], "M USD", part_projects={"TFR:A": ["Solar park"]},
                        hover_panel=True).data[0]
    assert tr.hoverinfo == "none" and tr.hovertemplate is None  # no label over the bars; the events still fire
    assert tr.customdata[0][3] == "Solar park"


def test_ranked_hover_without_projects():
    frame = pd.DataFrame({"year": [2030], "series": ["Energy"], "part": ["TFR:A"], "mac": [5.0], "value": [10.0]})
    tr = rc.credit_bars({"LEP": frame}, {}, ["Energy"], "M USD", part_labels={"TFR:A": "Alpha"}).data[0]
    # the hover by the bar, with no project count
    assert "Alpha" in tr.hovertemplate and "MAC 5.0" in tr.hovertemplate and "project" not in tr.hovertemplate
    assert tr.hoverinfo is None


def test_total_outside_bars_of_both_signs():
    # one group with a positive and a negative part: the net (-30) under the negative end (-50)
    frame = pd.DataFrame({"year": [2030, 2030], "series": ["All", "All"], "part": ["TFR:A", "TFR:B"], "mac": [1.0, 2.0], "value": [20.0, -50.0]})
    fig = rc.credit_bars({"LEP": frame}, {}, ["All"], "M USD")
    total = fig.layout.annotations[-1]
    assert total.text == "−30.0" or total.text == "-30.0"
    assert total.y == -50.0 and total.yshift < 0


def test_shades_and_part_colours():
    assert rc.shade("#808080", 0.5) == "#C0C0C0" and rc.shade("#808080", -0.5) == "#404040"
    s = rc.shades("#808080", 3)
    # all lighter than the colour, the first closest to it
    assert all(int(c[1:3], 16) > 0x80 for c in s) and int(s[0][1:3], 16) < int(s[-1][1:3], 16)
    assert len(rc.shades("#808080", 1)) == 1
    # they keep the colour's hue: an orange stays orange (red > green > blue)
    for c in rc.shades("#E6550D", 4):
        r, g, b = (int(c[i:i + 2], 16) for i in (1, 3, 5))
        assert r > g > b
    frame = pd.DataFrame({"year": [2030, 2030], "series": ["T", "T"], "part": ["TFR:A", "TFR:B"], "mac": [9.0, 1.0], "value": [5.0, 5.0]})
    fig = rc.credit_bars({"LEP": frame}, {"T": "#E6550D"}, ["T"], "M USD", part_colors={("T", "TFR:A"): "#111111"})
    assert fig.data[0].marker.color == "#111111" and fig.data[1].marker.color == "#E6550D"  # the group's colour without one

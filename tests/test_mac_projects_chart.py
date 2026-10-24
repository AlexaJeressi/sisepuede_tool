"""Projects in the MAC chart by transformation (result_charts.mac_by_transformation)."""

import pandas as pd

from sisepuede_tool.ui.components import result_charts as rc


def _rows():
    return pd.DataFrame({
        "subsector": ["entc", "entc"], "key": ["TX:ENTC:A", "TX:ENTC:B"], "pathway": ["NDC2.0", "NDC2.0"],
        "code": ["TX:ENTC:A_STRATEGY_NDC", "TX:ENTC:B_STRATEGY_NDC"], "mac": [5.0, 10.0], "abatement": [100.0, 50.0],
        "share": [1.0, 1.0], "mac_tornado": [4.0, 9.0], "mac_whirlpool": [6.0, 11.0],
    })


def test_counts_after_the_name_and_projects_in_the_hover():
    lines = [f"P{i} · Planned" for i in range(8)]
    fig = rc.mac_by_transformation(_rows(), ["entc"], ["NDC2.0"], {}, {"entc": "Electricity"}, {"TX:ENTC:A": "A", "TX:ENTC:B": "B"},
                                   "USD/t", projects={"TX:ENTC:A": lines})
    ticks = list(fig.layout.yaxis.ticktext)
    assert "8 projects" in ticks[1] and ticks[2] == "B"  # no projects: the name alone
    hover = fig.data[0].hovertext[0]
    assert "P0 · Planned" in hover and "P5 · Planned" in hover and "P6" not in hover and "+ 2 more" in hover

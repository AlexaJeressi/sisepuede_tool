"""Article 6 charts (ui/components/result_charts.py): credit bars."""

import pandas as pd

from sisepuede_tool.ui.components import result_charts as rc


def test_credit_bars_put_negative_groups_below_zero():
    frame = pd.DataFrame({"year": [2030, 2030], "series": ["Energy", "Transport"], "value": [-500.0, 200.0]})
    fig = rc.credit_bars({"LEP": frame}, {}, ["Energy", "Transport"], "M USD")
    assert fig.layout.barmode == "relative"
    (label,) = fig.layout.annotations[1:]  # [0] is the panel title
    # the total (-300) is written under the negative part of the bar
    assert (label.text, label.y, label.yshift) == ("-300", -500.0, -10)

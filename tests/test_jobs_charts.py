"""Jobs charts (result_charts.jobs_bars, jobs_heatmap) and the page's labels."""

import pandas as pd

from sisepuede_tool.services import i18n
from sisepuede_tool.ui import page_jobs
from sisepuede_tool.ui.components import result_charts as rc


def _frame(rows):
    return pd.DataFrame(rows, columns=["year", "series", "value"])


def test_jobs_bars_grid_and_one_legend():
    a = _frame([(2030, "Construction", 10.0), (2030, "Agriculture", -4.0), (2031, "Construction", 0.0)])
    fig = rc.jobs_bars({"Energy": {"NDC2.0": a, "LEP": a}, "Non-energy": {"NDC2.0": a}}, {"Construction": "#123456"},
                       ["Construction", "Agriculture"], "jobs")
    assert len(fig.data) == 6  # 2 series x 3 cells
    assert [t.showlegend for t in fig.data].count(True) == 2  # one legend entry per series
    assert fig.layout.barmode == "relative"
    titles = {a.text for a in fig.layout.annotations}
    assert {"NDC2.0", "LEP", "Energy", "Non-energy"} <= titles


def test_jobs_bars_total_line_on_category_years():
    a = _frame([(2025, "Construction", 3e6), (2025, "Agriculture", 2e6), (2050, "Construction", 4e6)])
    fig = rc.jobs_bars({"": {"": a}}, {}, ["Construction", "Agriculture"], "jobs", total_line=True)
    line = fig.data[-1]
    assert list(line.x) == ["2025", "2050"] and list(line.text) == ["5.00M", "4.00M"]
    assert fig.layout.xaxis.type == "category"


def test_jobs_heatmap_cells():
    t = pd.DataFrame({"row": ["Construction", "Agriculture"], "col": ["Buildings", "Buildings"], "value": [27.28, 0.6]})
    fig = rc.jobs_heatmap(t, ["Construction", "Agriculture"], ["Buildings"], {}, {}, "jobs per million USD")
    assert fig.data[0].text.tolist() == [["27.3"], ["0.6"]] and fig.data[0].zmax == 10


def test_every_sector_has_a_name_and_colour():
    data = page_jobs.jobs.load()
    sectors = set(data["total"]["Economic.Sector"])
    assert sectors == set(page_jobs.SECTOR_COLORS)
    for lang in ("en", "es", "ar"):
        for s in sectors:
            assert page_jobs.sector_name(s, lang) != s or lang == "en"
    assert set(data["direct_detail"]["Ssp.Sector"]) <= set(page_jobs.SSP_SUBSECTORS)
    assert page_jobs.ssp_name("Power Industry", "en") == i18n.t("subsectors.entc", "en")

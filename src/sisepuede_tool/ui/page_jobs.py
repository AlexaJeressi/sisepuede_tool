"""Jobs page (results): the labour demand of the NDC2.0 and LEP pathways'
investments, and how the LEP changes Egypt's baseline jobs.

The numbers are static for now: services/jobs_service.py reads
resources/jobs/data, the tables the Egypt deck's jobs slides were made from
(rebuilt from new runs with scripts/build_jobs_data.py). Charts, in the deck's
order:
- jobs per million USD invested, by economic sector and SSP sector;
- jobs demanded each year by the investments, by economic sector, NDC2.0 and
  LEP side by side; then split into energy and non-energy investments; then by
  the SSP sector that invests;
- the baseline jobs by economic sector (2025-2050);
- the change the LEP makes to them: reallocated (same total jobs) or added
  (expansionary).
"""

import re

import pandas as pd
from shiny import module, render, ui
from shinywidgets import output_widget, render_plotly

from sisepuede_tool.services import i18n
from sisepuede_tool.services import jobs_service as jobs
from sisepuede_tool.ui.components import result_charts as rc
from sisepuede_tool.ui.components.chart_export import export_button
from sisepuede_tool.ui.components.info_tip import info_tip
from sisepuede_tool.ui.state import AppState

# the data's pathway names, shown as the tool names them
PATHWAY_NAMES = {"NDC": "NDC2.0", "LEP": "LEP"}
FIRST_YEAR = 2025  # the investments start in 2025 (2023-2024 are zero)
BASELINE_YEARS = [2025, 2030, 2035, 2040, 2050]

# SSP sector of the data -> the tool's subsector (its name and colour)
SSP_SUBSECTORS = {
    "Buildings": "scoe", "CCS": "ccsq", "Crops": "agrc", "Forest": "frst", "Fugitive Emissions": "fgtv", "IPPU": "ippu",
    "Industrial Energy": "inen", "Land Use": "lndu", "Liquid Waste": "wali", "Livestock": "lvst",
    "Livestock Manure Management": "lsmm", "Power Industry": "entc", "Solid Waste": "waso", "Transportation": "trns",
    "Wastewater treatment": "trww",
}

# EORA26 economic sectors, in the data's order, each with its colour
SECTOR_COLORS = {
    "Agriculture": "#6E9B3A",
    "Construction": "#2F6F9F",
    "Education, Health and Other Services": "#E3A86B",
    "Electrical and Machinery": "#E07B1F",
    "Electricity, Gas and Water": "#4F7CAC",
    "Financial Intermediation and Business Activities": "#B59A3A",
    "Fishing": "#3E9C9C",
    "Food & Beverages": "#D9B44A",
    "Hotels and Restaurants": "#A8B545",
    "Maintenance and Repair": "#5E8F5A",
    "Metal Products": "#C9463D",
    "Mining and Quarrying": "#8C6D4F",
    "Other Manufacturing": "#E58FA8",
    "Others": "#7C8A8F",
    "Petroleum, Chemical and Non-Metallic Mineral Products": "#93B3C9",
    "Post and Telecommunications": "#F2B134",
    "Private Households": "#C77C9E",
    "Public Administration": "#3D9970",
    "Re-export & Re-import": "#6A5ACD",
    "Recycling": "#9F7AC2",
    "Retail Trade": "#46B3A8",
    "Textiles and Wearing Apparel": "#8BAA2E",
    "Transport": "#1F8A5B",
    "Transport Equipment": "#B07AA1",
    "Wholesale Trade": "#7FA7D6",
    "Wood and Paper": "#B5835A",
}


def _slug(name: str) -> str:
    """'Food & Beverages' -> 'food_beverages' (the i18n key of a sector)."""
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def sector_name(name: str, lang=None) -> str:
    return i18n.t(f"jobs.sectors.{_slug(name)}", lang, default=name)


def ssp_name(name: str, lang=None) -> str:
    abv = SSP_SUBSECTORS.get(name)
    return i18n.t(f"subsectors.{abv}", lang, default=name) if abv else name


def _frame(df: pd.DataFrame, series: str, value: str, year: str = "Year") -> pd.DataFrame:
    return pd.DataFrame({"year": df[year].astype(int), "series": df[series], "value": df[value].astype(float)})


def _box(chart_id: str, title_key: str, tip_key: str, unit_key: str = "unit_jobs") -> ui.Tag:
    return ui.div(
        ui.div(
            ui.span(i18n.t(f"jobs.{title_key}"), class_="section-label"),
            info_tip(i18n.t(f"jobs.{tip_key}")),
            ui.span(i18n.t(f"jobs.{unit_key}"), class_="small muted"),
            export_button(chart_id, i18n.t(f"jobs.{title_key}")),
            class_="box-head",
        ),
        output_widget(chart_id),
        class_="box",
    )


@module.ui
def page_jobs_ui():
    return ui.div(
        ui.div(i18n.t("jobs.intro"), class_="small muted"),
        _box("multiplier_chart", "multiplier", "multiplier_tip", "unit_multiplier"),
        _box("demand_chart", "demand", "demand_tip"),
        _box("energy_chart", "energy", "energy_tip"),
        _box("ssp_chart", "by_ssp", "by_ssp_tip"),
        _box("baseline_chart", "baseline", "baseline_tip"),
        _box("impact_chart", "impact", "impact_tip", "unit_jobs_change"),
        ui.output_ui("missing_note"),
        class_="res-page",
    )


@module.server
def page_jobs_server(input, output, session, state: AppState):
    data = jobs.load()

    def _t(key, **fmt):
        return i18n.t(f"jobs.{key}", state.lang(), **fmt)

    def _pathways(df: pd.DataFrame):
        """The data's pathways in PATHWAY_NAMES order, with the names shown."""
        have = set(df["Pathway"])
        return [(p, PATHWAY_NAMES[p]) for p in PATHWAY_NAMES if p in have]

    def _sectors():
        lang = state.lang()
        order = list(SECTOR_COLORS)
        return order, {s: sector_name(s, lang) for s in order}

    def _missing(key):
        return rc.empty_figure(_t("missing"), height=260) if key not in data else None

    @render.ui
    def missing_note():
        gone = [f for k, f in jobs.FILES.items() if k not in data]
        return ui.div(_t("missing_files", files=", ".join(gone)), class_="small muted") if gone else None

    @render_plotly
    @rc.bidi_for(state.lang)
    def multiplier_chart():
        if (empty := _missing("multiplier")) is not None:
            return empty
        lang = state.lang()
        m = data["multiplier"]
        table = pd.DataFrame({"row": m["Economic Sector"], "col": m["Ssp Sector"], "value": m["Total Jobs"]})
        cols = sorted(table["col"].unique(), key=lambda c: ssp_name(c, "en"))
        rows = [s for s in SECTOR_COLORS if s in set(table["row"])] + sorted(set(table["row"]) - set(SECTOR_COLORS))
        return rc.jobs_heatmap(table, rows, cols, {r: sector_name(r, lang) for r in rows}, {c: ssp_name(c, lang) for c in cols},
                               _t("unit_multiplier"))

    def _direct():
        d = data["direct"]
        return d[d["Year"] >= FIRST_YEAR]

    @render_plotly
    @rc.bidi_for(state.lang)
    def demand_chart():
        if (empty := _missing("direct")) is not None:
            return empty
        d = _direct()
        order, labels = _sectors()
        grid = {"": {name: _frame(d[d["Pathway"] == p], "Economic.Sector", "Total.Jobs") for p, name in _pathways(d)}}
        return rc.jobs_bars(grid, SECTOR_COLORS, order, _t("unit_jobs"), labels=labels, height=460, lang=state.lang())

    def _detail():
        d = data["direct_detail"]
        return d[d["Year"] >= FIRST_YEAR]

    @render_plotly
    @rc.bidi_for(state.lang)
    def energy_chart():
        if (empty := _missing("direct_detail")) is not None:
            return empty
        d = _detail()
        group = d["Ssp.Sector"].map(jobs.investment_group)
        order, labels = _sectors()
        grid = {
            _t(f"group_{g}"): {name: _frame(d[(group == g) & (d["Pathway"] == p)], "Economic.Sector", "Total.Jobs") for p, name in _pathways(d)}
            for g in ("energy", "non_energy")
        }
        return rc.jobs_bars(grid, SECTOR_COLORS, order, _t("unit_jobs"), labels=labels, height=560, lang=state.lang())

    @render_plotly
    @rc.bidi_for(state.lang)
    def ssp_chart():
        if (empty := _missing("direct_detail")) is not None:
            return empty
        d = _detail()
        lang = state.lang()
        order = sorted(set(d["Ssp.Sector"]), key=lambda c: ssp_name(c, "en"))
        colors = {s: rc.SUBSECTOR_COLORS.get(SSP_SUBSECTORS.get(s, ""), rc.OTHER_COLOR) for s in order}
        grid = {"": {name: _frame(d[d["Pathway"] == p], "Ssp.Sector", "Total.Jobs") for p, name in _pathways(d)}}
        return rc.jobs_bars(grid, colors, order, _t("unit_jobs"), labels={s: ssp_name(s, lang) for s in order}, height=460, lang=lang)

    def _total(pathway: str) -> pd.DataFrame:
        t = data["total"]
        return t[t["Pathway"] == pathway]

    @render_plotly
    @rc.bidi_for(state.lang)
    def baseline_chart():
        if (empty := _missing("total")) is not None:
            return empty
        b = _total(jobs.BASELINE)
        b = b[b["Year"].isin(BASELINE_YEARS)]
        order, labels = _sectors()
        # the largest employers at the base of the bars, as in the deck
        order = list(b.groupby("Economic.Sector")["Jobs"].sum().reindex(order).sort_values(ascending=False).index)
        grid = {"": {"": _frame(b, "Economic.Sector", "Jobs")}}
        return rc.jobs_bars(grid, SECTOR_COLORS, order, _t("unit_jobs"), labels=labels, height=520, total_line=True, lang=state.lang())

    @render_plotly
    @rc.bidi_for(state.lang)
    def impact_chart():
        if (empty := _missing("total")) is not None:
            return empty
        base = _total(jobs.BASELINE).set_index(["Economic.Sector", "Year"])["Jobs"]
        order, labels = _sectors()
        cells = {}
        for pathway, key in ((jobs.REALLOCATION, "reallocation"), (jobs.EXPANSIONARY, "expansionary")):
            p = _total(pathway).set_index(["Economic.Sector", "Year"])["Jobs"]
            diff = (p - base.reindex(p.index)).rename("diff").reset_index()
            diff = diff[diff["Year"].isin(BASELINE_YEARS)]
            cells[_t(key)] = _frame(diff, "Economic.Sector", "diff")
        return rc.jobs_bars({"": cells}, SECTOR_COLORS, order, _t("unit_jobs_change"), labels=labels, height=500, categories=True,
                            lang=state.lang())

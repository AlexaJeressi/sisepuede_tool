"""Marginal abatement cost page (results): the cost of each tonne of CO2e a
transformation abates, cheapest first.

The numbers are static for now (services/mac_service.py reads
sisepuede_a6 ref/temporary_mac.csv): the page doesn't depend on the runs and
says so. Filters:
- transformations: all, or those of one subsector (TX:TRNS:... is transportation);
- abatement measured in: the whole economy ("All", default) or one emission
  subsector (the file's `subsector`): the cost of each transformation per
  tonne it abates in that subsector, with a note on what that means;
- values: mean, tornado and whirlpool, any combination. The toggles carry
  each value's colour and shape, so they are also the chart's legend;
- axis: auto, linear or logarithmic. Auto picks logarithmic when the values
  span too many orders of magnitude (mac_service.wants_log); on a linear axis
  a value far beyond the others is cut at the edge.

One value is drawn as a lollipop, two or three as dots joined by a line
(result_charts.mac_chart). Transformations with zero for every value shown are
listed under the chart instead.
"""

from shiny import module, render, ui
from shinywidgets import output_widget, render_plotly

from sisepuede_tool.services import i18n, library_service
from sisepuede_tool.services import mac_service as mac
from sisepuede_tool.ui.components import result_charts as rc
from sisepuede_tool.ui.components.chart_export import export_button
from sisepuede_tool.ui.components.info_tip import info_tip
from sisepuede_tool.ui.state import AppState

_SWATCH_SHAPES = {
    "circle": '<circle cx="6" cy="6" r="5"/>',
    "diamond": '<path d="M6 0.5 11.5 6 6 11.5 0.5 6z"/>',
    "square": '<rect x="1" y="1" width="10" height="10"/>',
}


def _subsector_name(abv: str, lang=None) -> str:
    """Name of a transformation subsector; PFLO (cross-sector policies) is not a sisepuede subsector."""
    if abv == "pflo":
        return i18n.t("mac.pflo", lang)
    return i18n.t(f"subsectors.{abv}", lang, default=abv.upper())


def _measured_name(subsector: str, lang=None) -> str:
    """Name of a subsector the abatement is measured in (the file's names, translated)."""
    if subsector == mac.SUBSECTOR_ALL:
        return i18n.t("mac.whole_economy", lang)
    abv = mac.SUBSECTOR_ABV.get(subsector)
    return i18n.t(f"subsectors.{abv}", lang, default=subsector) if abv else subsector


def _measure_choice(m: str) -> ui.Tag:
    """Toggle label: the measure's marker (colour and shape, as in the chart) and its name."""
    color, shape = rc.MAC_MEASURE_STYLE[m]
    svg = f'<svg width="12" height="12" viewBox="0 0 12 12" fill="{color}" aria-hidden="true">{_SWATCH_SHAPES[shape]}</svg>'
    return ui.span(ui.HTML(svg), i18n.t(f"mac.{m}"), class_="mac-measure")


@module.ui
def page_mac_ui():
    data = mac.load()
    return ui.div(
        ui.div(i18n.t("mac.static_note"), class_="info-box small"),
        ui.div(
            ui.div(
                ui.span(i18n.t("mac.by_transformation"), class_="section-label"),
                info_tip(i18n.t("mac.by_transformation_tip")),
                ui.span(i18n.t("mac.unit"), class_="small muted"),
                export_button("mac_chart", i18n.t("mac.by_transformation")),
                class_="box-head",
            ),
            ui.div(
                ui.input_select(
                    "subsector", i18n.t("mac.filter_transformations"),
                    {"": i18n.t("mac.all_subsectors"),
                     **dict(sorted(((s, _subsector_name(s)) for s in mac.transformation_subsectors(data)), key=lambda kv: kv[1]))},
                    width="300px",
                ),
                ui.input_select(
                    "measured_in", i18n.t("mac.filter_measured_in"),
                    {s: _measured_name(s) for s in mac.measured_subsectors(data)},
                    width="300px",
                ),
                ui.div(
                    ui.input_checkbox_group("measures", None, {m: _measure_choice(m) for m in mac.MEASURES}, selected=["mean"], inline=True),
                    class_="mac-measures",
                ),
                ui.div(
                    ui.input_radio_buttons(
                        "scale", None,
                        {"auto": i18n.t("mac.scale_auto"), "linear": i18n.t("mac.scale_linear"), "log": i18n.t("mac.scale_log")},
                        inline=True,
                    ),
                    class_="seg",
                ),
                class_="res-controls mac-controls",
            ),
            output_widget("mac_chart"),
            ui.output_ui("notes"),
            class_="box",
        ),
        class_="res-page",
    )


@module.server
def page_mac_server(input, output, session, state: AppState):
    data = mac.load()
    english_names = {i.code: i.name for i in library_service.load_library()}

    def _t(key, **fmt):
        return i18n.t(f"mac.{key}", state.lang(), **fmt)

    def _name(code: str) -> str:
        """'AGRC: Improve rice management' (NDC library name, translated, without the 'NDC · ' set prefix)."""
        name = english_names.get(code)
        if name is None:
            return code
        return library_service.strip_set_prefix(i18n.td("library", code, "name", name, state.lang()))

    def _measures() -> list:
        picked = set(input.measures() or ())
        return [m for m in mac.MEASURES if m in picked]

    def _view():
        """(rows, measures, log axis?, linear limit or None)."""
        measures = _measures()
        rows = mac.rows(data, input.subsector(), input.measured_in(), measures)
        values = rows[measures].to_numpy().ravel() if measures else []
        scale = input.scale()
        log = scale == "log" or (scale == "auto" and mac.wants_log(values))
        return rows, measures, log, None if log else mac.axis_limit(values)

    @render_plotly
    @rc.bidi_for(state.lang)
    def mac_chart():
        rows, measures, log, limit = _view()
        if not measures:
            return rc.empty_figure(_t("empty_measures"), height=240)
        if rows.empty:
            return rc.empty_figure(_t("empty_zero"), height=240)
        lang = state.lang()
        return rc.mac_chart(rows, measures, {c: _name(c) for c in rows["code"]}, _t("unit"), log=log, limit=limit, lang=lang)

    @render.ui
    def notes():
        rows, measures, log, limit = _view()
        if not measures:
            return None
        sep = i18n.t("results.list_sep", state.lang())
        out = []
        if input.measured_in() != mac.SUBSECTOR_ALL:
            out.append(_t("measured_note", subsector=_measured_name(input.measured_in(), state.lang())))
        if log and input.scale() == "auto":
            out.append(_t("log_note"))
        if limit:
            cut = rows.loc[(rows[measures].abs() > limit).any(axis=1), "code"]
            out.append(_t("cut", names=sep.join(_name(c) for c in cut)))
        zero = mac.zero_codes(data, input.subsector(), input.measured_in(), measures)
        if zero and not rows.empty:
            # a long list (most transformations, when the abatement is measured in one subsector) becomes a count
            if len(zero) > 5:
                out.append(i18n.tn("mac.zero_count", len(zero), state.lang()))
            else:
                out.append(_t("zero_rows", names=sep.join(_name(c) for c in zero)))
        return ui.div(*[ui.div(n, class_="small muted") for n in out]) if out else None

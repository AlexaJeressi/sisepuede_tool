"""Marginal abatement cost page (results): what each tonne of CO2e abated
costs, by subsector and by transformation, for the NDC and LEP pathways.

The numbers are static for now (services/mac_service.py reads sisepuede_a6
ref/temporary_emit_cost_diffs_by_subsec.csv): the page doesn't depend on the
runs and says so. Filters on top, for both charts:
- pathways: NDC, LEP or both (side by side), toggles that are also the legend;
- estimate: mean, tornado or whirlpool.

Charts:
- by subsector (result_charts.mac_by_subsector): the average cost per tonne
  abated in each subsector, cheapest first, with the tonnes abated there;
- by transformation (result_charts.mac_by_transformation): the transformations
  that abate in each subsector, under a light subsector header in the same
  order. Its own filter narrows it to a sector or a subsector.
A bar far beyond the others is cut with a break and its value written inside
(mac_service.axis_limit).
"""

from shiny import module, render, ui
from shinywidgets import output_widget, render_plotly

from sisepuede_tool.services import i18n, library_service
from sisepuede_tool.services import mac_service as mac
from sisepuede_tool.ui.components import result_charts as rc
from sisepuede_tool.ui.components.chart_export import export_button
from sisepuede_tool.ui.components.info_tip import info_tip
from sisepuede_tool.ui.state import AppState


def _pathway_colors(pathways) -> dict:
    """NDC and LEP in the order and colours they have on the other results pages
    (pathway palette by id; the NDC pathway is created before the LEP one)."""
    return {p: rc.PATHWAY_PALETTE[i % len(rc.PATHWAY_PALETTE)] for i, p in enumerate(pathways)}


def _sector_key(sector: str) -> str:
    return sector.lower().replace(" ", "_")


def _subsector_name(abv: str, lang=None) -> str:
    return i18n.t(f"subsectors.{abv}", lang, default=abv.upper())


def _scope_name(scope: str, lang=None) -> str:
    """'' -> all subsectors; 'sector:Energy' -> 'Energy (all subsectors)'; 'trns' -> 'Transportation'."""
    if not scope:
        return i18n.t("mac.all_subsectors", lang)
    if scope.startswith(mac.SECTOR_PREFIX):
        sector = scope[len(mac.SECTOR_PREFIX):]
        return i18n.t("mac.sector_all", lang, sector=i18n.t(f"sectors.{_sector_key(sector)}", lang, default=sector))
    return _subsector_name(scope, lang)


def _scope_choices(data, lang=None) -> dict:
    """Grouped choices: all subsectors, then per sector the whole sector (when
    it has more than one subsector) and its subsectors."""
    out = {"": _scope_name("", lang)}
    for sector, subs in mac.scopes(data):
        group = {}
        if len(subs) > 1:
            group[mac.SECTOR_PREFIX + sector] = _scope_name(mac.SECTOR_PREFIX + sector, lang)
        group.update({abv: _subsector_name(abv, lang) for abv in subs})
        out[i18n.t(f"sectors.{_sector_key(sector)}", lang, default=sector)] = group
    return out


def _pathway_choice(p: str, color: str) -> ui.Tag:
    """Toggle label: the pathway's colour, as in the charts, and its name."""
    return ui.span(ui.span(class_="swatch", style=f"background:{color}"), p, class_="mac-pathway")


@module.ui
def page_mac_ui():
    data = mac.load()
    pathways = mac.pathways(data)
    colors = _pathway_colors(pathways)
    return ui.div(
        ui.div(i18n.t("mac.static_note"), class_="info-box small"),
        ui.div(
            ui.div(
                ui.input_checkbox_group("pathways", i18n.t("mac.pathways"), {p: _pathway_choice(p, colors[p]) for p in pathways},
                                        selected=pathways, inline=True),
                class_="mac-toggles",
            ),
            ui.div(
                ui.input_radio_buttons("measure", i18n.t("mac.estimate"), {m: i18n.t(f"mac.{m}") for m in mac.MEASURES}, inline=True),
                class_="seg",
            ),
            class_="res-controls mac-controls",
        ),
        ui.div(
            ui.div(
                ui.span(i18n.t("mac.by_subsector"), class_="section-label"),
                info_tip(i18n.t("mac.by_subsector_tip")),
                ui.span(i18n.t("mac.unit"), class_="small muted"),
                export_button("subsector_chart", i18n.t("mac.by_subsector")),
                class_="box-head",
            ),
            output_widget("subsector_chart"),
            ui.output_ui("subsector_notes"),
            class_="box",
        ),
        ui.div(
            ui.div(
                ui.span(i18n.t("mac.by_transformation"), class_="section-label"),
                info_tip(i18n.t("mac.by_transformation_tip")),
                ui.span(i18n.t("mac.unit"), class_="small muted"),
                ui.div(
                    ui.input_select("scope", None, _scope_choices(data), width="280px"),
                    export_button("transformation_chart", i18n.t("mac.by_transformation")),
                    class_="btn-row",
                ),
                class_="box-head",
            ),
            output_widget("transformation_chart"),
            ui.output_ui("transformation_notes"),
            class_="box",
        ),
        class_="res-page",
    )


@module.server
def page_mac_server(input, output, session, state: AppState):
    data = mac.load()
    colors = _pathway_colors(mac.pathways(data))
    english_names = {i.code: i.name for i in library_service.load_all_libraries()}

    def _t(key, **fmt):
        return i18n.t(f"mac.{key}", state.lang(), **fmt)

    def _name(code: str) -> str:
        """'AGRC: Improve rice management' (library name, translated, without the
        'NDC · ' set prefix); mac.names for the transformations not in the library."""
        name = english_names.get(code)
        if name is None:
            return i18n.t(f"mac.names.{code}", state.lang(), default=code)
        return library_service.strip_set_prefix(i18n.td("library", code, "name", name, state.lang()))

    def _pathways() -> list:
        picked = set(input.pathways() or ())
        return [p for p in mac.pathways(data) if p in picked]

    def _sub_names() -> dict:
        return {abv: _subsector_name(abv, state.lang()) for _, subs in mac.scopes(data) for abv in subs}

    def _subsectors():
        """(table, order, limit) of the chart by subsector."""
        pws = _pathways()
        table = mac.by_subsector(data, pws, input.measure())
        return table, mac.subsector_order(table, pws), mac.axis_limit(table["mac"])

    def _transformations():
        """(rows, hidden, limit) of the chart by transformation."""
        rows, hidden = mac.by_transformation(data, _pathways(), input.measure(), input.scope())
        return rows, hidden, mac.axis_limit(rows["mac"])

    @render_plotly
    @rc.bidi_for(state.lang)
    def subsector_chart():
        if not _pathways():
            return rc.empty_figure(_t("empty_pathways"), height=240)
        table, order, limit = _subsectors()
        if table.empty:
            return rc.empty_figure(_t("empty_scope"), height=240)
        return rc.mac_by_subsector(table, order, _pathways(), colors, _sub_names(), _t("unit"), limit=limit, lang=state.lang())

    @render_plotly
    @rc.bidi_for(state.lang)
    def transformation_chart():
        if not _pathways():
            return rc.empty_figure(_t("empty_pathways"), height=240)
        rows, _, limit = _transformations()
        if rows.empty:
            return rc.empty_figure(_t("empty_scope"), height=240)
        _, order, _ = _subsectors()
        order = order + [s for s in dict.fromkeys(rows["subsector"]) if s not in order]
        # one name per row: the NDC version's when both pathways have it
        names = {}
        for code, key in zip(rows["code"], rows["key"]):
            names.setdefault(key, _name(code))
        return rc.mac_by_transformation(rows, order, _pathways(), colors, _sub_names(), names, _t("unit"),
                                        limit=limit, lang=state.lang())

    def _notes(*texts) -> ui.Tag:
        out = [x for x in texts if x]
        return ui.div(*[ui.div(x, class_="small muted") for x in out]) if out else None

    @render.ui
    def subsector_notes():
        if not _pathways():
            return None
        table, _, limit = _subsectors()
        return _notes(_t("cut_note") if limit else None)

    @render.ui
    def transformation_notes():
        if not _pathways():
            return None
        rows, hidden, limit = _transformations()
        return _notes(
            _t("cut_note") if limit else None,
            i18n.tn("mac.hidden", hidden, state.lang()) if hidden else None,
        )

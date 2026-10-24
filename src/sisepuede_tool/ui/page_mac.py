"""Marginal abatement cost page (results): what each tonne of CO2e abated
costs, by subsector and by transformation, for the NDC and LEP pathways.

The numbers are static for now (services/mac_service.py reads sisepuede_a6
ref/temporary_mac.csv): the page doesn't depend on the runs. Filters on top,
for both charts:
- pathways: NDC, LEP or both (side by side), toggles that are also the legend;
- estimate: mean, tornado or whirlpool.

Charts:
- by subsector (result_charts.mac_by_subsector): the average cost per tonne
  abated in each subsector, cheapest first, with the tonnes abated there;
- by transformation (result_charts.mac_by_transformation): the transformations
  that abate in each subsector, under a light subsector header in the same
  order. Its own filter narrows it to a sector or a subsector. Next to each
  transformation, how many projects are linked to it (as on the Pathways
  page), listed in the hover;
- projects behind each transformation: the same transformations, in the same
  order and filter, with their cost per tonne, the tonnes they abate and the
  projects linked to them (investment and start as the project list gives
  them).
A bar far beyond the others is cut with a break and its value written inside
(mac_service.axis_limit).
"""

from shiny import module, render, ui
from shinywidgets import output_widget, render_plotly

from sisepuede_tool import config
from sisepuede_tool.services import i18n, library_service, projects_service
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
        ui.div(
            ui.div(
                ui.span(i18n.t("mac.projects_box"), class_="section-label"),
                info_tip(i18n.t("mac.projects_box_tip")),
                ui.input_switch("only_projects", i18n.t("mac.only_with_projects"), value=False),
                class_="box-head",
            ),
            ui.output_ui("projects_table"),
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
        'NDC2.0 · ' set prefix); mac.names for the transformations not in the library."""
        name = english_names.get(code)
        if name is None:
            return i18n.t(f"mac.names.{code}", state.lang(), default=code)
        return library_service.strip_set_prefix(i18n.td("library", code, "name", name, state.lang()))

    workbook = projects_service.load_project_records_cached(config.PROJECTS_XLSX_PATH)

    def _projects() -> dict:
        """{key: [project record]}: the projects linked to each transformation
        now (Pathways page links), the NDC2.0 and LEP versions together."""
        records = projects_service.all_projects(workbook, state.custom_projects.get())
        return projects_service.projects_by(state.project_links.get(), records, mac.pair_key)

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
        projects = {k: [r["name"] for r in recs] for k, recs in _projects().items()}
        return rc.mac_by_transformation(rows, order, _pathways(), colors, _sub_names(), names, _t("unit"),
                                        limit=limit, lang=state.lang(), projects=projects)

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

    @render.ui
    def projects_table():
        """One row per transformation of the chart above (same filter, same
        order), with its cost per tonne and tonnes in each pathway and its
        projects, opened on a click."""
        pws = _pathways()
        if not pws:
            return ui.div(_t("empty_pathways"), class_="small muted")
        rows, _, _ = _transformations()
        if rows.empty:
            return ui.div(_t("empty_scope"), class_="small muted")
        lang = state.lang()
        sub_names = _sub_names()
        projects = _projects()
        _, order, _ = _subsectors()
        rank = {sub: i for i, sub in enumerate(order)}
        # chart order: subsector, then cheapest first; a transformation appears once, at its first subsector
        rows = rows.assign(_r=rows["subsector"].map(rank).fillna(len(rank))).sort_values(["_r", "mac"], kind="stable")
        keys = list(dict.fromkeys(rows["key"]))
        if input.only_projects():
            keys = [k for k in keys if projects.get(k)]
        if not keys:
            return ui.div(_t("no_projects_here"), class_="small muted")

        def mac_cell(k):
            out = []
            for p in pws:
                d = rows[(rows["key"] == k) & (rows["pathway"] == p)]
                if d.empty:
                    continue
                v = float(d["mac"].iloc[0])
                out.append(ui.div(ui.span(class_="swatch", style=f"background:{colors.get(p)}"),
                                  f"{v:+,.1f}" if abs(v) < 1000 else f"{v:+,.0f}", class_="mono mac-cell"))
            return ui.tags.td(*out)

        def mt_cell(k):
            out = []
            for p in pws:
                d = rows[(rows["key"] == k) & (rows["pathway"] == p)]
                if not d.empty:
                    out.append(ui.div(ui.span(class_="swatch", style=f"background:{colors.get(p)}"), f"{d['abatement'].sum():,.0f}",
                                      class_="mono mac-cell"))
            return ui.tags.td(*out)

        def projects_cell(k):
            recs = projects.get(k) or []
            if not recs:
                return ui.tags.td(ui.span(_t("no_projects"), class_="muted small"))
            items = []
            for r in recs:
                facts = [x for x in (r.get("investment"), r.get("start")) if isinstance(x, str) and x.strip()]
                items.append(ui.tags.li(ui.tags.b(r["name"]), ui.div(" · ".join(facts), class_="small muted") if facts else None))
            return ui.tags.td(ui.tags.details(ui.tags.summary(i18n.tn("mac.n_projects", len(recs), lang)), ui.tags.ul(*items, class_="mac-projects")))

        body = []
        for k in keys:
            first = rows[rows["key"] == k].iloc[0]
            subs = ", ".join(sub_names.get(x, x) for x in dict.fromkeys(rows.loc[rows["key"] == k, "subsector"]))
            body.append(ui.tags.tr(
                ui.tags.td(ui.div(_name(first["code"])), ui.div(subs, class_="small muted")),
                mac_cell(k), mt_cell(k), projects_cell(k),
            ))
        head = ui.tags.tr(*[ui.tags.th(_t(c)) for c in ("col_transformation", "col_mac", "col_abated", "col_projects")])
        return ui.div(ui.tags.table(ui.tags.thead(head), ui.tags.tbody(*body), class_="history mac-projects-table"), class_="table-wrap")

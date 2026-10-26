"""Article 6 page (results): credits the country could sell from mitigation
beyond its NDC targets.

Only pathways that go beyond the NDC are estimated: business as usual and
pathways made of NDC transformations only are left out
(article6_service.earns_credits), e.g. the preloaded LEP pathway is shown and
the NDC pathway is not.

The credits are computed by sisepuede_a6 (ssp_asix.get_credit_estimate, called
from services/article6_service.py) for each NDC target year and emission group
in its ref/ files. Shows:
- one tile per pathway: credits (MtCO2e) and their value (million USD) over
  all the target years and in the milestone years (every fifth year);
- the carbon price used, as a range and average (each year in the ⓘ); in
  advanced mode it can be set for every year at once or year by year (the
  page recomputes at once, no model run needed);
- the emissions of every visible pathway (BAU and NDC too), with the gap
  between the NDC pathway and each pathway that earns credits shaded over the
  target years (green below the NDC, red above): where the credits come from;
  the years after the NDC2.0 targets (2035) shaded grey, here and in the
  credit chart;
- credit value per target year, stacked by emission group (subsector colours),
  totals written above the milestone years; a click on a group in the legend
  under it hides or shows that group (SHOW_GROUPS_CHART);
- the sisepuede_a6 ranked MAC file as it is (static, its own LEP run), in two
  charts: the credits by group (sector), the sectors stacked by their MAC
  (the file's transformer MACs weighted by their share of the sector's
  credits), the lowest at the base; then the same credits by transformation (one per
  sector it abates in), all ranked by their MAC whatever their sector, each
  in a lighter shade of the sector's colour
  (closer to it = higher MAC; the sector's own colour stays the strongest). The first has a plotly legend (a click hides a sector,
  a double click shows it alone); the second an HTML one, its sectors with
  their transformations (lowest MAC first), and a filter by transformation; with its projects switch on, the strip
  above it shows the transformer under the cursor and the names of the
  projects linked to it (Pathways page), instead of the hover;
- the sisepuede_a6 aggregate ranked file, the same way but in one group (the
  whole economy, one colour, a plotly legend of its transformations): each
  year's credits split among the
  transformers by their whole-economy share, the lowest MAC at the base, as
  in the two charts above.

The Excel download has every group, year and pathway, with the emissions, the
target, the difference, the price and the value.
"""

import json
import re

import pandas as pd
from shiny import module, reactive, render, ui
from shiny.module import resolve_id
from shinywidgets import output_widget, render_plotly

from sisepuede_tool.services import article6_service as a6
from sisepuede_tool import config
from sisepuede_tool.services import download_service, i18n, library_service, pathway_service, projects_service
from sisepuede_tool.services import transformer_metadata_service as tms
from sisepuede_tool.ui.components import result_charts as rc
from sisepuede_tool.ui.components.chart_export import export_button
from sisepuede_tool.ui.components.hover_panel import hover_panel
from sisepuede_tool.ui.components import results_bar
from sisepuede_tool.ui.components.info_tip import info_tip
from sisepuede_tool.ui.state import AppState


SHOW_GROUPS_CHART = True  # credits by emission group (False hides it, with its notes under the KPIs instead)


def group_name(group: str, lang=None) -> str:
    """An emission group (sisepuede_a6 ref/emission_groupings_example.csv) in `lang`."""
    return i18n.td("article6", re.sub(r"[^a-z0-9]+", "_", group.lower()).strip("_"), "name", group, lang)


def _ranked_box(kind: str, title_key: str, tip_key: str) -> ui.Tag:
    """A box for one of sisepuede_a6's ranked files (`kind`: ranked, aggregate):
    its projects switch and filter by transformation, the strip with the
    transformer under the cursor and its projects (switched on), the chart and
    its legend."""
    title = i18n.t(f"article_6.{title_key}")
    return ui.div(
        ui.div(
            ui.span(title, class_="section-label"),
            info_tip(i18n.t(f"article_6.{tip_key}", year=a6.NDC_LAST_YEAR)),
            ui.span(i18n.t("results.million_usd"), class_="small muted"),
            ui.div(
                ui.input_switch(f"{kind}_projects", i18n.t("article_6.show_projects"), value=False),
                ui.output_ui(f"{kind}_filter_ui"),
                export_button(f"{kind}_chart", title),
                class_="btn-row",
            ),
            class_="box-head",
        ),
        # the projects of the transformation under the cursor, when switched on
        ui.panel_conditional(f"input.{kind}_projects", hover_panel(f"{kind}_chart", i18n.t("article_6.ranked_hover_hint"))),
        # the whole economy's plotly legend: its clicks come here (legend_events.js)
        ui.div(output_widget(f"{kind}_chart"), **({"data-legend-event": kind, "data-legend-input": resolve_id("ui_event")} if kind == "aggregate" else {})),
        ui.output_ui(f"{kind}_legend"),
        class_="box",
    )


@module.ui
def page_article_6_ui():
    return ui.div(
        results_bar.bar_ui("download_xlsx"),
        ui.output_ui("kpis"),
        None if SHOW_GROUPS_CHART else ui.div(ui.output_ui("modelled_note"), ui.output_ui("excluded_note")),
        ui.div(
            ui.div(
                ui.span(i18n.t("article_6.carbon_price"), class_="section-label"),
                info_tip(i18n.t("article_6.carbon_price_tip")),
                class_="box-head",
            ),
            ui.output_ui("price_used"),
            ui.div(
                ui.div(ui.span(i18n.t("article_6.change_price"), class_="section-label"), ui.span(i18n.t("results.advanced"), class_="adv-tag")),
                ui.div(
                    ui.input_numeric("price_all", i18n.t("article_6.all_years") + " (USD/tCO₂e)", value=None, min=0, step=0.5, width="200px"),
                    ui.input_action_button("price_apply_all", i18n.t("article_6.apply_all"), class_="btn-inline"),
                    class_="btn-row a6-price-all",
                ),
                ui.tags.details(
                    ui.tags.summary(i18n.t("article_6.by_year")),
                    ui.div(
                        *[
                            ui.input_numeric(f"price_{y}", f"{y} (USD/tCO₂e)", value=round(p, 2), min=0, step=0.5, width="150px")
                            for y, p in a6.price_by_year(a6.load_reference()["prices"], a6.target_years(a6.load_reference()["targets"])).items()
                        ],
                        class_="btn-row",
                    ),
                    class_="a6-price-years",
                ),
                ui.input_action_button("price_reset", i18n.t("article_6.reset"), class_="btn-inline btn-ghost"),
                ui.div(i18n.t("article_6.instant"), class_="small muted"),
                class_="adv-only adv-box",
            ),
            class_="box",
        ),
        ui.div(
            ui.div(
                ui.span(i18n.t("article_6.pathways_chart"), class_="section-label"),
                info_tip(i18n.t("article_6.pathways_chart_tip", year=a6.NDC_LAST_YEAR)),
                ui.span("MtCO₂e", class_="small muted"),
                export_button("pathways_chart", i18n.t("article_6.pathways_chart")),
                class_="box-head",
            ),
            output_widget("pathways_chart"),
            class_="box",
        ),
        None if not SHOW_GROUPS_CHART else ui.div(
            ui.div(
                ui.span(i18n.t("article_6.by_group"), class_="section-label"),
                info_tip(i18n.t("article_6.by_group_tip", year=a6.NDC_LAST_YEAR)),
                ui.span(i18n.t("results.million_usd"), class_="small muted"),
                export_button("groups_chart", i18n.t("article_6.by_group")),
                class_="box-head",
            ),
            output_widget("groups_chart"),
            ui.output_ui("groups_legend"),
            ui.output_ui("modelled_note"),
            ui.output_ui("excluded_note"),
            class_="box",
        ),
        ui.div(
            ui.div(
                ui.span(i18n.t("article_6.by_sector_mac"), class_="section-label"),
                info_tip(i18n.t("article_6.by_sector_mac_tip", year=a6.NDC_LAST_YEAR)),
                ui.span(i18n.t("results.million_usd"), class_="small muted"),
                export_button("sectors_chart", i18n.t("article_6.by_sector_mac")),
                class_="box-head",
            ),
            # its plotly legend's clicks come here (legend_events.js)
            ui.div(output_widget("sectors_chart"), **{"data-legend-event": "sector", "data-legend-input": resolve_id("ui_event")}),
            class_="box",
        ),
        _ranked_box("ranked", "by_transformer", "by_transformer_tip"),
        _ranked_box("aggregate", "overall", "overall_tip"),
        class_="res-page",
    )


@module.server
def page_article_6_server(input, output, session, state: AppState):
    ev_id = resolve_id("ui_event")
    results_bar.bar_server(input, state, ev_id)
    # emission groups switched off in each credits chart (its legend toggles
    # them); in the whole-economy chart, its transformations ("group|kernel")
    hidden_groups = reactive.value(frozenset())
    hidden_ranked = reactive.value(frozenset())
    hidden_sectors = reactive.value(frozenset())
    hidden_aggregate = reactive.value(frozenset())
    # transformations switched off in the transformations chart ("group|kernel"),
    # and the sectors opened in its legend (kept across its re-renders)
    hidden_parts = reactive.value(frozenset())
    open_sectors = reactive.value(frozenset())
    ranked_files = {"ranked": a6.load_ranked(), "aggregate": a6.load_ranked_aggregate()}
    sector_mac = a6.ranked_group_macs()

    def _sector_order(highest_first: bool = True) -> list:
        """The ranked file's groups by their MAC, highest first (the legends'
        order, the top of the stack first) or lowest first (the stacking
        order, the base first); those with none last."""
        groups = list(dict.fromkeys(ranked_files["ranked"][a6.FIELD_GROUP]))
        sign = -1 if highest_first else 1
        return sorted(groups, key=lambda g: (g not in sector_mac, sign * sector_mac.get(g, 0.0)))

    def _ranked_parts() -> pd.DataFrame:
        """The ranked file's (group, transformer) rows with a value, in the
        legend's order: groups by MAC, highest first, and the transformers of
        each by MAC, lowest first (as they stack, from the base)."""
        df = ranked_files["ranked"]
        rank = {g: i for i, g in enumerate(_sector_order())}
        live = df.groupby([a6.FIELD_GROUP, a6.FIELD_KERNEL])["value_musd"].transform(lambda v: v.abs().max()) > 1e-9
        out = df[live].assign(_g=df[a6.FIELD_GROUP].map(rank))
        return out.sort_values(["_g", "mac"], kind="stable").drop(columns="_g")

    def _part_colors() -> dict:
        """{(group, transformer): colour}: shades of the group's colour, all
        lighter than it (the group's own colour stays the strongest), the
        closest to it for the highest MAC."""
        colors = a6.group_colors(ref["groupings"], rc.SUBSECTOR_COLORS)
        pairs = _ranked_parts().drop_duplicates([a6.FIELD_GROUP, a6.FIELD_KERNEL])
        out = {}
        for g, d in pairs.groupby(a6.FIELD_GROUP, sort=False):
            # d is lowest MAC first: the shades from the lightest
            for k, c in zip(d[a6.FIELD_KERNEL], rc.shades(colors.get(g, rc.OTHER_COLOR), len(d))[::-1]):
                out[(g, k)] = c
        return out
    hidden_of = {"group": hidden_groups, "ranked": hidden_ranked, "sector": hidden_sectors, "aggregate": hidden_aggregate}
    ref = a6.load_reference()
    years = a6.target_years(ref["targets"])
    headline = a6.headline_years(years)
    ref_price = a6.price_by_year(ref["prices"], years)

    def _t(key, **fmt):
        return i18n.t(f"article_6.{key}", state.lang(), **fmt)

    def _price(p: float) -> str:
        return i18n.t("results.price_t", state.lang(), p=f"{p:.2f}")

    @reactive.calc
    def edited_prices() -> dict:
        """{year: price} the user changed (advanced mode only; empty = reference prices)."""
        if not state.advanced_mode.get():
            return {}
        out = {}
        for y in years:
            v = input[f"price_{y}"]()
            if v is not None and v >= 0 and abs(float(v) - round(ref_price[y], 2)) > 1e-9:
                out[y] = float(v)
        return out

    @reactive.calc
    def ref_used() -> dict:
        """The reference tables with the carbon prices in use."""
        return {**ref, "prices": a6.with_prices(ref["prices"], edited_prices())}

    @reactive.effect
    @reactive.event(input.price_reset)
    def _reset_prices():
        ui.update_numeric("price_all", value=None)
        for y in years:
            ui.update_numeric(f"price_{y}", value=round(ref_price[y], 2))

    @reactive.effect
    @reactive.event(input.price_apply_all)
    def _apply_price_to_all():
        v = input.price_all()
        if v is None or v < 0:
            return
        for y in years:
            ui.update_numeric(f"price_{y}", value=float(v))

    def _year_span() -> str:
        return f"{years[0]}–{years[-1]}" if len(years) > 1 else str(years[0])

    def _price_summary(prices: dict) -> str:
        """Short text for the prices of the target years: each year when there
        are a few, otherwise the range and the average."""
        if len(years) <= 3:
            return " · ".join(f"{y}: {_price(prices[y])}" for y in years)
        vals = [prices[y] for y in years]
        if max(vals) - min(vals) < 0.005:
            return f"{_year_span()}: {_price(vals[0])}"
        # one unit for the range: $10.70–12.26/t
        span = i18n.t("results.price_t", state.lang(), p=f"{min(vals):.2f}–{max(vals):.2f}")
        return _t("price_range", years=_year_span(), range=span, avg=_price(sum(vals) / len(vals)))

    def _price_by_year_text(prices: dict) -> str:
        return " · ".join(f"{y}: {_price(prices[y])}" for y in years)

    def _price_text() -> str:
        return _price_summary(a6.price_by_year(ref_used()["prices"], years))

    def _earns_credits(sid: int) -> bool:
        tx = state.transformations_obj.get()
        entry = state.strategies_map.get().get(sid)
        if tx is None or entry is None:
            return False
        state.transformations_revision.get()
        ndc = [i.code for i in state.library_items.get() if i.source == library_service.SOURCE_NDC]
        return a6.earns_credits(pathway_service.pathway_codes(entry, tx), ndc)

    @reactive.calc
    def pathway_rows():
        """(baseline id, eligible [(sid, name, RunResult)], names of the visible ones left out)."""
        bid, rows = results_bar.runs_for_page(state)
        rows = [(sid, name, rr) for sid, name, rr in rows if rr is not None and rr.ok and rr.df_output is not None]
        keep = [(sid, name, rr) for sid, name, rr in rows if _earns_credits(sid)]
        return bid, keep, [name for sid, name, _ in rows if not _earns_credits(sid)]

    @reactive.calc
    def estimates():
        """(baseline id, [(sid, name, estimate frame)]) for the visible pathways that go beyond the NDC."""
        bid, rows, _ = pathway_rows()
        used = ref_used()
        ma = state.model_attributes.get()
        return bid, [(sid, name, a6.credit_estimate(rr.df_output, ma, used)) for sid, name, rr in rows]

    @reactive.effect
    @reactive.event(input.ui_event)
    def _on_event():
        ev = input.ui_event() or {}
        if ev.get("type") == "chip":
            results_bar.toggle_pathway(state, int(ev["value"]))
        elif ev.get("type") in hidden_of:
            hidden = hidden_of[ev["type"]]
            if ev.get("only"):
                # a double click: that group alone, or all again when it already is (as plotly's legend)
                others = frozenset(_shown_groups(ev["type"]) - {ev["value"]})
                hidden.set(frozenset() if hidden.get() == others else others)
            else:
                # "" = show them all again (the ranked charts' transformations too)
                hidden.set(frozenset() if ev["value"] == "" else hidden.get() ^ {ev["value"]})
                if ev["type"] == "ranked" and ev["value"] == "":
                    hidden_parts.set(frozenset())
        elif ev.get("type") == "part":
            if ev.get("only"):
                # that transformation alone in its chart (its sector back on), or all again
                pairs = _ranked_parts().drop_duplicates([a6.FIELD_GROUP, a6.FIELD_KERNEL])
                others = frozenset(pairs[a6.FIELD_GROUP] + "|" + pairs[a6.FIELD_KERNEL]) - {ev["value"]}
                group = ev["value"].split("|", 1)[0]
                if hidden_parts.get() == others and group not in hidden_ranked.get():
                    hidden_parts.set(frozenset())
                else:
                    hidden_parts.set(others)
                    hidden_ranked.set(hidden_ranked.get() - {group})
            else:
                hidden_parts.set(hidden_parts.get() ^ {ev["value"]})
        elif ev.get("type") == "open":
            opened = open_sectors.get()
            open_sectors.set(opened | {ev["value"]} if ev.get("open") else opened - {ev["value"]})

    @render.ui
    def kpis():
        bid, rows = estimates()
        if not rows:
            return None
        colors = results_bar.colors_for(state, bid)
        lang = state.lang()

        def val(key, value_musd, detail):
            return ui.div(
                ui.div(key, class_="k"),
                ui.div(i18n.t("results.money_m", lang, v=rc.fmt(value_musd)), class_="v " + ("pos" if value_musd > 0 else "")),
                ui.div(detail, class_="small muted mono"),
            )

        def credits(mt):
            return i18n.isolate(rc.fmt(mt) + " MtCO₂e", lang)

        tiles = []
        for sid, name, est in rows:
            tot = a6.totals_by_year(est).set_index("year")
            # the whole target period, then the milestone years; every year is in the chart and the download
            vals = []
            if len(tot) > 1:
                vals.append(val(_t("total_years", years=_year_span()), tot["value_musd"].sum(), credits(tot["credits_mt"].sum())))
            for y in headline:
                if y in tot.index:
                    t = tot.loc[y]
                    vals.append(val(str(y), t["value_musd"], f"{credits(t['credits_mt'])} · {i18n.isolate(_price(t['price']), lang)}"))
            tiles.append(
                ui.div(
                    ui.div(ui.span(class_="swatch", style=f"background:{colors.get(sid)}"), ui.span(name, class_="kpi-name"), class_="kpi-head"),
                    ui.div(*vals, class_="kpi-vals"),
                    class_="kpi-tile",
                )
            )
        return ui.div(*tiles, class_="kpi-row")

    @render_plotly

    @rc.bidi_for(state.lang)
    def groups_chart():
        _, rows = estimates()
        if not rows:
            return rc.empty_figure(_t("empty_none"), height=360)
        frames = {
            name: est.rename(columns={a6.FIELD_GROUP: "series", "value_musd": "value"})[["year", "series", "value"]]
            for _, name, est in rows
        }
        if all((f["value"].abs() <= 1e-9).all() for f in frames.values()):
            return rc.empty_figure(_t("empty_zero"), height=360)
        hidden = hidden_groups.get()
        frames = {name: f[~f["series"].isin(hidden)] for name, f in frames.items()}
        if all((f["value"].abs() <= 1e-9).all() for f in frames.values()):
            return rc.empty_figure(_t("empty_hidden"), height=360)
        lang = state.lang()
        order = list(ref["groupings"][a6.FIELD_GROUP])
        return rc.credit_bars(
            frames, a6.group_colors(ref["groupings"], rc.SUBSECTOR_COLORS), order, i18n.t("results.million_usd", lang),
            lang=lang, labels={g: group_name(g, lang) for g in order}, label_years=headline, legend=False,
            outside=(a6.NDC_LAST_YEAR, _t("after_ndc_targets", year=a6.NDC_LAST_YEAR)), years=state.results_years.get(),
        )

    def _kernel_names(codes) -> dict:
        lang = state.lang()
        meta = state.transformer_metadata.get() or {}
        return {c: i18n.td("transformers", c, "name", tms.get_card(c, meta)["name"], lang) for c in codes}

    def _kernel_projects() -> dict:
        """{transformer: [project name]}: the projects linked now (Pathways
        page) to a transformation on each transformer (their details are on
        the Projects page)."""
        transformer_of = {i.code: i.transformer_code for i in state.library_items.get() or []}
        records = projects_service.all_projects(
            projects_service.load_project_records_cached(config.PROJECTS_XLSX_PATH), state.custom_projects.get()
        )
        by_transformer = projects_service.projects_by(state.project_links.get(), records, transformer_of.get)
        return {c: [r["name"] for r in recs] for c, recs in by_transformer.items()}

    def _filter_ui(kind: str):
        df = ranked_files[kind]
        if df.empty:
            return None
        names = _kernel_names(df[a6.FIELD_KERNEL].unique())
        choices = dict(sorted(names.items(), key=lambda kv: kv[1]))
        with reactive.isolate():
            selected = input[f"{kind}_filter"]() if f"{kind}_filter" in input else []
        return ui.input_selectize(f"{kind}_filter", None, choices, selected=list(selected or []), multiple=True, width="320px",
                                  options={"placeholder": _t("all_transformations"), "plugins": ["remove_button"]})

    @render.ui
    def ranked_filter_ui():
        return _filter_ui("ranked")

    @render.ui
    def aggregate_filter_ui():
        return _filter_ui("aggregate")

    def _ranked_figure(kind: str):
        """One of sisepuede_a6's ranked files as it is (its own LEP run,
        static): credit value by year and group, each group split into its
        transformers, the cheapest at the base, without the groups switched off in its
        legend and only the transformations picked in its filter (all when
        none). With its projects switch on, the strip above it shows the
        transformer under the cursor and its projects instead of the hover.
        The whole-economy one has a plotly legend of its transformations
        instead (those switched off greyed out in it)."""
        df = ranked_files[kind]
        if df.empty:
            return rc.empty_figure(_t("ranked_missing"), height=360)
        picked = list(input[f"{kind}_filter"]() or []) if f"{kind}_filter" in input else []
        projects = bool(input[f"{kind}_projects"]())
        if picked:
            df = df[df[a6.FIELD_KERNEL].isin(picked)]
        if kind == "ranked":
            df = df[~df[a6.FIELD_GROUP].isin(hidden_ranked.get())]
            off = hidden_parts.get()
            df = df[~(df[a6.FIELD_GROUP] + "|" + df[a6.FIELD_KERNEL]).isin(off)]
            if (df["value_musd"].abs() <= 1e-9).all():
                return rc.empty_figure(_t("empty_hidden"), height=360)
        lang = state.lang()
        part_colors = None
        order = _sector_order() + [g for g in ref["groupings"][a6.FIELD_GROUP] if g not in _sector_order()] + [a6.WHOLE_ECONOMY]
        colors = {**a6.group_colors(ref["groupings"], rc.SUBSECTOR_COLORS), a6.WHOLE_ECONOMY: rc.PATHWAY_PALETTE[1]}
        labels = {**{g: group_name(g, lang) for g in order}, a6.WHOLE_ECONOMY: _t("whole_economy")}
        frame = df.rename(columns={a6.FIELD_GROUP: "series", a6.FIELD_KERNEL: "part", "value_musd": "value"})
        if kind == "ranked":
            # every (sector, transformer) on its own, all ranked by their MAC
            # (lowest at the base) whatever their sector, each in its shade of
            # the sector's colour; the hover still names the sector
            shade = _part_colors()
            sector_colors = colors
            pairs = frame.drop_duplicates(["series", "part"]).sort_values("mac", kind="stable")
            keys = list(pairs["series"] + "|" + pairs["part"])
            frame = frame.assign(series=frame["series"] + "|" + frame["part"])
            order = keys
            labels = {k: labels.get(k.split("|", 1)[0], k.split("|", 1)[0]) for k in keys}
            colors = {k: sector_colors.get(k.split("|", 1)[0], rc.OTHER_COLOR) for k in keys}
            part_colors = {(k, k.split("|", 1)[1]): shade.get(tuple(k.split("|", 1)), colors[k]) for k in keys}
        else:
            # every transformer its own series (one legend entry each), the lowest MAC at the base
            pairs = frame.drop_duplicates(["series", "part"]).sort_values("mac", kind="stable")
            keys = list(pairs["series"] + "|" + pairs["part"])
            frame = frame.assign(series=frame["series"] + "|" + frame["part"])
            order = keys
            labels = {k: labels[a6.WHOLE_ECONOMY] for k in keys}
            colors = {k: colors[a6.WHOLE_ECONOMY] for k in keys}
        fig = rc.credit_bars(
            {_t("ranked_panel"): frame}, colors, order, i18n.t("results.million_usd", lang),
            lang=lang, labels=labels, label_years=headline, legend=kind == "aggregate",
            outside=(a6.NDC_LAST_YEAR, _t("after_ndc_targets", year=a6.NDC_LAST_YEAR)),
            part_labels=_kernel_names(df[a6.FIELD_KERNEL].unique()),
            part_projects=_kernel_projects() if projects else None, hover_panel=projects, part_colors=part_colors,
            years=state.results_years.get(), hidden=hidden_aggregate.get() if kind == "aggregate" else None,
            height=540 if kind == "aggregate" else 380,
        )
        # the transformations chart: hidden in the tool (the HTML legend is
        # under it) but drawn by the ⤓ export; the whole economy's: shown
        _part_legend(fig, lang, with_group=kind == "ranked")
        return fig

    @render_plotly
    @rc.bidi_for(state.lang)
    def sectors_chart():
        """The ranked file by group only (no transformers), the groups stacked
        by their MAC, the lowest at the base, with a plotly legend "sector ·
        MAC" in the order of the stack (top entry = top segment). A click on
        an entry hides that sector, a double click shows it alone (as plotly,
        but done here, so the bar totals are those of the sectors shown)."""
        df = ranked_files["ranked"]
        if df.empty:
            return rc.empty_figure(_t("ranked_missing"), height=360)
        lang = state.lang()
        order = _sector_order(highest_first=False)
        frame = df.groupby(["year", a6.FIELD_GROUP], as_index=False)["value_musd"].sum().rename(
            columns={a6.FIELD_GROUP: "series", "value_musd": "value"})
        fig = rc.credit_bars(
            {_t("ranked_panel"): frame}, a6.group_colors(ref["groupings"], rc.SUBSECTOR_COLORS), order, i18n.t("results.million_usd", lang),
            lang=lang, labels={g: group_name(g, lang) for g in order}, label_years=headline,
            outside=(a6.NDC_LAST_YEAR, _t("after_ndc_targets", year=a6.NDC_LAST_YEAR)), years=state.results_years.get(),
            hidden=hidden_sectors.get(),
        )
        for t in fig.data:
            g = t.legendgroup
            if t.type == "bar" and g in sector_mac:
                t.name = f"{group_name(g, lang)}{_mac_text(sector_mac[g])}"
        fig.update_layout(legend=dict(traceorder="reversed"))
        return fig

    def _part_legend(fig, lang, with_group: bool):
        """A plotly legend of the parts (transformations) of a ranked chart:
        one entry per (group, transformation), "name · MAC" (and "(sector)"
        `with_group`), in its colour, in the order of the stack, so each entry
        lines up with its segment (the top entry is the top segment, the
        highest MAC; the bottom one the base, the lowest)."""
        kind = "ranked" if with_group else "aggregate"
        names = _kernel_names(ranked_files[kind][a6.FIELD_KERNEL].unique())
        macs = ranked_files[kind].drop_duplicates([a6.FIELD_GROUP, a6.FIELD_KERNEL]).set_index([a6.FIELD_GROUP, a6.FIELD_KERNEL])["mac"]
        bars = [t for t in fig.data if t.type == "bar" and "|" in (t.legendgroup or "")]
        for i, t in enumerate(bars):  # in stacking order: the base first
            g, k = t.legendgroup.split("|", 1)
            mac = float(macs.get((g, k), float("nan")))
            t.name = names.get(k, k) + ("" if mac != mac else _mac_text(mac)) + (f" ({group_name(g, lang)})" if with_group else "")
            t.showlegend = True
            t.legendrank = len(bars) - i
        fig.update_layout(legend=dict(traceorder="normal", font=dict(size=10.5)))

    @render_plotly
    @rc.bidi_for(state.lang)
    def ranked_chart():
        return _ranked_figure("ranked")

    @render_plotly
    @rc.bidi_for(state.lang)
    def aggregate_chart():
        return _ranked_figure("aggregate")

    @render_plotly
    @rc.bidi_for(state.lang)
    def pathways_chart():
        """Every visible pathway (BAU and NDC too), with the gap between the NDC
        pathway (the first visible one that earns no credits, BAU aside) and each
        pathway that earns credits shaded over the target years, green below the
        NDC and red above."""
        bid, rows = results_bar.runs_for_page(state)
        rows = [(sid, name, rr) for sid, name, rr in rows if rr is not None and rr.ok and rr.df_output is not None]
        if not rows:
            return rc.empty_figure(_t("empty_none"), height=360)
        ma = state.model_attributes.get()
        series = {name: a6.emissions_by_year(rr.df_output, ma, ref) for _, name, rr in rows}
        sid_colors = results_bar.colors_for(state, bid)
        colors = {name: sid_colors.get(sid, rc.OTHER_COLOR) for sid, name, _ in rows}
        ndc = next((name for sid, name, _ in rows if sid != 0 and not _earns_credits(sid)), None)
        gaps = [(ndc, name) for sid, name, _ in rows if ndc and _earns_credits(sid)]
        return rc.gap_lines(
            series, colors, "MtCO₂e", gaps=gaps, gap_years=(years[0], years[-1]), gap_label=_t("beyond_ndc"), above_label=_t("above_ndc"),
            outside=(a6.NDC_LAST_YEAR, _t("after_ndc_targets", year=a6.NDC_LAST_YEAR)), years=state.results_years.get(),
        )

    def _legend(shown, hidden, kind, order=None, suffix=None):
        """Legend under a credits chart, as HTML (it wraps on a narrow window
        instead of covering the bars): a click on a group sends a `kind` event
        that hides it from the chart (the bar totals are then those of the
        groups shown), another brings it back; a double click shows that group
        alone, another all of them again; "show all" when some are off."""
        if not shown:
            return None
        lang = state.lang()
        colors = a6.group_colors(ref["groupings"], rc.SUBSECTOR_COLORS)

        def click(value):
            return _send({"type": kind, "value": value}) + " return false;"

        def item(g):
            return ui.tags.button(
                ui.span(class_="swatch", style=f"background:{colors.get(g, rc.OTHER_COLOR)}"),
                group_name(g, lang) + ((suffix or {}).get(g) or ""),
                type="button",
                class_="a6-legend-item" + (" off" if g in hidden else ""),
                **{"aria-pressed": "false" if g in hidden else "true"},
                onclick=_clicks({"type": kind, "value": g}),
            )

        reset = ui.tags.button(_t("show_all"), type="button", class_="link-btn small", onclick=click("")) if hidden & shown else None
        order = list(order or ref["groupings"][a6.FIELD_GROUP])
        order += sorted(g for g in shown if g not in order)
        return ui.div(
            *[item(g) for g in order if g in shown],
            reset,
            ui.span(_t("legend_hint"), class_="small muted"),
            class_="a6-legend",
        )

    def _send(payload: dict) -> str:
        return f"Shiny.setInputValue({json.dumps(ev_id)}, {json.dumps(payload)}, {{priority: 'event'}});"

    def _clicks(payload: dict) -> str:
        """A legend item's onclick, as plotly's legend: `payload` (hide or
        show) after a short wait, unless a second click comes first, then
        `payload` with "only" (that item alone, or all again)."""
        return (f"if (this._a6t) {{ clearTimeout(this._a6t); this._a6t = null; {_send({**payload, 'only': True})} }} "
                f"else {{ this._a6t = setTimeout(() => {{ this._a6t = null; {_send(payload)} }}, 260); }} return false;")

    def _shown_groups(kind: str) -> set:
        """The groups with credits in a credits chart (those in its legend);
        in the whole-economy chart its transformations ("group|kernel") picked
        in its filter (all when none)."""
        if kind == "group":
            _, rows = estimates()
            return {g for _, _, est in rows for g in est.loc[est["value_musd"].abs() > 1e-9, a6.FIELD_GROUP]}
        df = ranked_files["ranked" if kind == "sector" else kind]
        df = df[df["value_musd"].abs() > 1e-9]
        if kind != "aggregate":
            return set(df[a6.FIELD_GROUP])
        picked = list(input["aggregate_filter"]() or []) if "aggregate_filter" in input else []
        if picked:
            df = df[df[a6.FIELD_KERNEL].isin(picked)]
        return set(df[a6.FIELD_GROUP] + "|" + df[a6.FIELD_KERNEL])

    @render.ui
    def groups_legend():
        return _legend(_shown_groups("group"), hidden_groups.get(), "group")

    def _ranked_legend(kind: str):
        return _legend(_shown_groups(kind), hidden_of[kind].get(), kind)

    def _mac_text(v: float) -> str:
        return f" · {v:,.1f} $/t".replace("-", "−")

    @render.ui
    def ranked_legend():
        """Under the transformations chart, one line per sector (its colour, MAC
        and number of transformations): a click on it switches the sector off
        here; its arrow opens the list of its
        transformations, in their shade and with their MAC, each switched off
        or on with a click (this chart only). A double click on either shows it
        alone, another all again. Closed by default; the sectors opened stay
        open."""
        parts = _ranked_parts()
        # only the transformations picked in its filter (all when none)
        picked = list(input["ranked_filter"]() or []) if "ranked_filter" in input else []
        if picked:
            parts = parts[parts[a6.FIELD_KERNEL].isin(picked)]
        if parts.empty:
            return None
        lang = state.lang()
        hidden = hidden_ranked.get()
        off_parts = hidden_parts.get()
        with reactive.isolate():
            opened = open_sectors.get()
        colors = a6.group_colors(ref["groupings"], rc.SUBSECTOR_COLORS)
        part_colors = _part_colors()
        names = _kernel_names(parts[a6.FIELD_KERNEL].unique())
        pairs = parts.drop_duplicates([a6.FIELD_GROUP, a6.FIELD_KERNEL])

        def button(swatch, text, off, payload, *extra, cls="a6-legend-item"):
            return ui.tags.button(
                ui.span(class_="swatch", style=f"background:{swatch}"), *text, *extra, type="button",
                class_=cls + (" off" if off else ""), **{"aria-pressed": "false" if off else "true"}, onclick=_clicks(payload),
            )

        blocks = []
        for g, d in pairs.groupby(a6.FIELD_GROUP, sort=False):
            g_off = g in hidden
            head = button(colors.get(g, rc.OTHER_COLOR), [ui.tags.b(group_name(g, lang))], g_off, {"type": "ranked", "value": g},
                          _mac_text(sector_mac[g]) if g in sector_mac else "", ui.span(f" ({len(d)})", class_="muted"))
            items = [
                button(part_colors.get((g, k), rc.OTHER_COLOR), [names.get(k, k) + _mac_text(m)], g_off or f"{g}|{k}" in off_parts,
                       {"type": "part", "value": f"{g}|{k}"}, cls="a6-legend-item a6-legend-part")
                for k, m in zip(d[a6.FIELD_KERNEL], d["mac"])
            ]
            toggle = f"Shiny.setInputValue({json.dumps(ev_id)}, {{type: 'open', value: {json.dumps(g)}, open: this.open}}, {{priority: 'event'}});"
            blocks.append(ui.tags.details(
                ui.tags.summary(ui.span(class_="a6-caret"), head),
                ui.div(*items, class_="a6-legend-parts"),
                class_="a6-legend-group", open=g in opened or None, ontoggle=toggle,
            ))
        reset = ui.tags.button(_t("show_all"), type="button", class_="link-btn small", onclick=_send({"type": "ranked", "value": ""}) + " return false;") \
            if hidden or off_parts else None
        return ui.div(ui.div(*blocks, class_="a6-legend-groups"), ui.div(reset, ui.span(_t("legend_hint_parts"), class_="small muted")),
                      class_="a6-legend-grouped")

    @render.ui
    def aggregate_legend():
        return None  # one group: nothing to switch off

    @render.ui
    def price_used():
        used = a6.price_by_year(ref_used()["prices"], years)
        tip = info_tip(_price_by_year_text(used)) if len(years) > 3 else None
        if not edited_prices():
            return ui.div(ui.span(_price_text(), class_="mono"), tip, ui.span(" · " + _t("reference_prices"), class_="small muted"))
        return ui.div(
            ui.span(_price_text(), class_="mono"),
            tip,
            ui.div(_t("changed", prices=_price_summary(ref_price)), class_="small", style="color:var(--rust)"),
        )

    @render.ui
    def modelled_note():
        _, rows = estimates()
        missing = sorted({g for _, _, est in rows for g in a6.not_modelled(est)})
        if not missing:
            return None
        lang = state.lang()
        names = i18n.t("results.list_sep", lang).join(group_name(g, lang) for g in missing)
        return ui.div(_t("left_out", groups=names), class_="info-box small")

    @render.ui
    def excluded_note():
        _, _, left_out = pathway_rows()
        if not left_out:
            return None
        return ui.div(_t("not_shown", names=i18n.t("results.list_sep", state.lang()).join(left_out)), class_="small muted")

    @render.download(filename=lambda: "tableau_data.zip")
    def download_tableau():
        yield results_bar.tableau_zip(state)

    @render.download(filename=lambda: "article_6_credits.xlsx")
    def download_xlsx():
        bid, rows = estimates()
        baselines = state.baselines.get()
        label = baselines[bid].label if bid in baselines else (bid or "")
        edited = edited_prices()
        # the workbook is in English, whatever the UI language
        used = a6.price_by_year(ref_used()["prices"], years)
        prices = " · ".join(f"{y}: ${used[y]:.2f}/t" for y in years)
        note = f"Carbon prices changed by the user: {prices} (USD/tCO2e)." if edited else None
        yield download_service.article6_workbook([(name, est) for _, name, est in rows], label, ref_used(), price_note=note)

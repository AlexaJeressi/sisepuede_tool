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
  all the target years and in the milestone years (2030, 2035);
- the carbon price used, as a range and average (each year in the ⓘ); in
  advanced mode it can be set for every year at once or year by year (the
  page recomputes at once, no model run needed);
- credit value per target year, stacked by emission group (subsector colours),
  totals written above the milestone years.

The Excel download has every group, year and pathway, with the emissions, the
target, the difference, the price and the value.
"""

import re

import pandas as pd
from shiny import module, reactive, render, ui
from shiny.module import resolve_id
from shinywidgets import output_widget, render_plotly

from sisepuede_tool.services import article6_service as a6
from sisepuede_tool.services import download_service, i18n, library_service, pathway_service
from sisepuede_tool.ui.components import result_charts as rc
from sisepuede_tool.ui.components.chart_export import export_button
from sisepuede_tool.ui.components import results_bar
from sisepuede_tool.ui.components.info_tip import info_tip
from sisepuede_tool.ui.state import AppState


def group_name(group: str, lang=None) -> str:
    """An emission group (sisepuede_a6 ref/emission_groupings_example.csv) in `lang`."""
    return i18n.td("article6", re.sub(r"[^a-z0-9]+", "_", group.lower()).strip("_"), "name", group, lang)


@module.ui
def page_article_6_ui():
    return ui.div(
        results_bar.bar_ui("download_xlsx"),
        ui.output_ui("kpis"),
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
                ui.span(i18n.t("article_6.by_group"), class_="section-label"),
                info_tip(i18n.t("article_6.by_group_tip")),
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
        class_="res-page",
    )


@module.server
def page_article_6_server(input, output, session, state: AppState):
    ev_id = resolve_id("ui_event")
    results_bar.bar_server(input, state, ev_id)
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
        if all((f["value"] <= 1e-9).all() for f in frames.values()):
            return rc.empty_figure(_t("empty_zero"), height=360)
        lang = state.lang()
        order = list(ref["groupings"][a6.FIELD_GROUP])
        return rc.credit_bars(
            frames, a6.group_colors(ref["groupings"], rc.SUBSECTOR_COLORS), order, i18n.t("results.million_usd", lang),
            lang=lang, labels={g: group_name(g, lang) for g in order}, label_years=headline, legend=False,
            years=state.results_years.get(),
        )

    @render.ui
    def groups_legend():
        """The chart's legend, as HTML under the chart: it wraps on a narrow
        window instead of covering the bars."""
        _, rows = estimates()
        shown = {g for _, _, est in rows for g in est.loc[est["value_musd"] > 1e-9, a6.FIELD_GROUP]}
        if not shown:
            return None
        lang = state.lang()
        colors = a6.group_colors(ref["groupings"], rc.SUBSECTOR_COLORS)
        return ui.div(
            *[
                ui.span(ui.span(class_="swatch", style=f"background:{colors.get(g, rc.OTHER_COLOR)}"), group_name(g, lang), class_="a6-legend-item")
                for g in ref["groupings"][a6.FIELD_GROUP]
                if g in shown
            ],
            class_="a6-legend",
        )

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

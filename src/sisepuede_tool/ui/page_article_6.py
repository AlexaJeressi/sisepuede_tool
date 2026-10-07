"""Article 6 page (results): credits the country could sell from mitigation
beyond its NDC targets.

Only pathways that go beyond the NDC earn credits: the NDC targets are the
NDC pathway's own emissions, so business as usual and pathways made of NDC
transformations only are left out (article6_service.earns_credits), e.g. the
preloaded LEP pathway is shown and the NDC pathway is not.

For each NDC target year (the years in resources/article6/ndc_targets.csv)
and each of those pathways: emissions by emission group are compared with the
group's target; what is below the target is a tradeable credit, valued at
that year's carbon price (services/article6_service.py, ported from
sisepuede_a6). Shows:
- one tile per pathway: credits (MtCO2e) and their value (million USD) in
  each target year;
- the carbon price used in each target year; in advanced mode it can be
  changed per year (the page recomputes at once, no model run needed);
- credit value per target year, stacked by emission group (subsector colours).

The Excel download has every group, year and pathway, with emissions, the
target, the surplus or shortfall, the price and the value.
"""

import pandas as pd
from shiny import module, reactive, render, ui
from shiny.module import resolve_id
from shinywidgets import output_widget, render_plotly

from sisepuede_tool.services import article6_service as a6
from sisepuede_tool.services import download_service, library_service, pathway_service
from sisepuede_tool.ui.components import result_charts as rc
from sisepuede_tool.ui.components import results_bar
from sisepuede_tool.ui.components.info_tip import info_tip
from sisepuede_tool.ui.state import AppState


@module.ui
def page_article_6_ui():
    return ui.div(
        results_bar.bar_ui("download_xlsx"),
        ui.output_ui("kpis"),
        ui.div(
            ui.div(
                ui.span("Carbon price", class_="section-label"),
                info_tip(
                    "Credits are valued at the carbon price of each NDC target year. Only the target years "
                    "count, so only their prices change the result."
                ),
                class_="box-head",
            ),
            ui.output_ui("price_used"),
            ui.div(
                ui.div(ui.span("Change the carbon price", class_="section-label"), ui.span("ADVANCED", class_="adv-tag")),
                ui.div(
                    *[
                        ui.input_numeric(f"price_{y}", f"{y} (USD/tCO₂e)", value=round(p, 2), min=0, step=0.5, width="170px")
                        for y, p in a6.price_by_year(a6.load_reference()["prices"], a6.target_years(a6.load_reference()["targets"])).items()
                    ],
                    class_="btn-row",
                ),
                ui.input_action_button("price_reset", "Reset to reference prices", class_="btn-inline btn-ghost"),
                ui.div("The tiles, the chart and the download update right away; no new run is needed.", class_="small muted"),
                class_="adv-only adv-box",
            ),
            class_="box",
        ),
        ui.div(
            ui.div(
                ui.span("Credits by emission group", class_="section-label"),
                info_tip(
                    "For each NDC target year, the value of the emissions a pathway keeps below the target of each "
                    "emission group. A group above its target earns nothing and does not reduce the credits of another group."
                ),
                ui.span("million USD", class_="small muted"),
                class_="box-head",
            ),
            output_widget("groups_chart"),
            ui.output_ui("modelled_note"),
            ui.output_ui("excluded_note"),
            ui.div(
                "Credits = NDC target − pathway emissions, when positive, times the carbon price of that year.",
                class_="small muted",
            ),
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
    ref_price = a6.price_by_year(ref["prices"], years)

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
        for y in years:
            ui.update_numeric(f"price_{y}", value=round(ref_price[y], 2))

    def _price_text() -> str:
        used = a6.price_by_year(ref_used()["prices"], years)
        return " · ".join(f"{y}: ${used[y]:.2f}/t" for y in years)

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
        return bid, [(sid, name, a6.credit_estimate(rr.df_output, used)) for sid, name, rr in rows]

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
        tiles = []
        for sid, name, est in rows:
            tot = a6.totals_by_year(est).set_index("year")
            vals = []
            for y in years:
                if y not in tot.index:
                    continue
                t = tot.loc[y]
                vals.append(
                    ui.div(
                        ui.div(str(y), class_="k"),
                        ui.div(f"${rc.fmt(t['value_musd'])} M", class_="v " + ("pos" if t["value_musd"] > 0 else "")),
                        ui.div(f"{rc.fmt(t['credits_mt'])} MtCO₂e · ${t['price']:.1f}/t", class_="small muted mono"),
                    )
                )
            tiles.append(
                ui.div(
                    ui.div(ui.span(class_="swatch", style=f"background:{colors.get(sid)}"), ui.span(name, class_="kpi-name"), class_="kpi-head"),
                    ui.div(*vals, class_="kpi-vals"),
                    class_="kpi-tile",
                )
            )
        return ui.div(*tiles, class_="kpi-row")

    @render_plotly
    def groups_chart():
        _, rows = estimates()
        if not rows:
            return rc.empty_figure("Run a pathway that goes beyond the NDC (e.g. LEP) to see its credits.", height=360)
        frames = {
            name: est.rename(columns={a6.FIELD_GROUP: "series", "value_musd": "value"})[["year", "series", "value"]]
            for _, name, est in rows
        }
        if all((f["value"] <= 1e-9).all() for f in frames.values()):
            return rc.empty_figure("No pathway goes below the NDC target of any emission group in the target years.", height=360)
        order = list(ref["groupings"][a6.FIELD_GROUP])
        return rc.credit_bars(frames, a6.group_colors(ref["groupings"], rc.SUBSECTOR_COLORS), order, "million USD")

    @render.ui
    def price_used():
        edited = edited_prices()
        if not edited:
            return ui.div(ui.span(_price_text(), class_="mono"), ui.span(" · reference prices", class_="small muted"))
        ref_txt = " · ".join(f"{y}: ${ref_price[y]:.2f}/t" for y in years)
        return ui.div(
            ui.span(_price_text(), class_="mono"),
            ui.div(f"Changed in advanced options. Reference prices: {ref_txt}.", class_="small", style="color:var(--rust)"),
        )

    @render.ui
    def modelled_note():
        _, rows = estimates()
        missing = sorted({g for _, _, est in rows for g in a6.not_modelled(est)})
        if not missing:
            return None
        return ui.div(
            f"Left out (no emissions in these runs): {', '.join(missing)}. "
            "Electricity and fugitive emissions need the electricity model: tick “Run electricity dispatch "
            "(NemoMod)” on the Run page.",
            class_="info-box small",
        )

    @render.ui
    def excluded_note():
        _, _, left_out = pathway_rows()
        if not left_out:
            return None
        return ui.div(
            f"Not shown: {', '.join(left_out)}. The NDC targets are the NDC pathway's own emissions, so only "
            "pathways with transformations beyond the NDC earn credits.",
            class_="small muted",
        )

    @render.download(filename=lambda: "article_6_credits.xlsx")
    def download_xlsx():
        bid, rows = estimates()
        baselines = state.baselines.get()
        label = baselines[bid].label if bid in baselines else (bid or "")
        edited = edited_prices()
        note = f"Carbon prices changed by the user: {_price_text()} (USD/tCO2e)." if edited else None
        yield download_service.article6_workbook([(name, est) for _, name, est in rows], label, ref_used(), price_note=note)

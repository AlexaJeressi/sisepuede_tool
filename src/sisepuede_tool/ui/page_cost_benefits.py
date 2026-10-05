"""Costs & benefits page (results), relative to business as usual.

Filled by the Run page after every run (`state.cb_results[baseline_id]` =
(df_cb, df_attr_variable) from costs_benefits_ssp). Shows, for one pathway at
a time:
- stacked costs (below zero) and benefits (above zero) per year by category or
  by sector, with the net and the cumulative net; billions USD or % of GDP;
- totals 2025–2050, not discounted (a discount rate is an advanced option): net,
  benefit/cost ratio, the first year the net turns positive, and the net by
  category.

No data tables: the Excel download has every cost/benefit variable by year,
the category totals, and totals at 0 / 3 / 5 / 7% (services/download_service.py).
"""

import json
from typing import Dict, Optional

import pandas as pd
from shiny import module, reactive, render, ui
from shiny.module import resolve_id
from shinywidgets import output_widget, render_plotly

from sisepuede_tool import config
from sisepuede_tool.services import cb_summary_service as cbs
from sisepuede_tool.services import download_service
from sisepuede_tool.ui.components import result_charts as rc
from sisepuede_tool.ui.components import results_bar
from sisepuede_tool.ui.components.info_tip import info_tip
from sisepuede_tool.ui.state import AppState

_BAU = results_bar.BAU


@module.ui
def page_cost_benefits_ui():
    return ui.div(
        results_bar.bar_ui("download_xlsx"),
        ui.div(
            ui.div(
                ui.div(
                    ui.div(ui.span("Costs & benefits by year", class_="section-label"), ui.output_ui("pw_label", inline=True), class_="box-head"),
                    ui.output_ui("pw_tabs"),
                    ui.div(
                        ui.div(ui.input_radio_buttons("group", None, {"category": "By category", "sector_label": "By sector"}, inline=True), class_="seg"),
                        ui.div(ui.input_radio_buttons("units", None, {"busd": "Billion USD", "gdp": "% of GDP"}, inline=True), class_="seg"),
                        class_="res-controls",
                    ),
                    output_widget("cb_chart"),
                    ui.div(
                        "Above zero: benefits (savings, avoided damages). Below zero: costs. "
                        "All values are relative to business as usual.",
                        class_="small muted",
                    ),
                    class_="box",
                ),
                ui.div(
                    ui.div(
                        ui.output_ui("side_title"),
                        class_="box-head",
                    ),
                    ui.div(
                        ui.div(ui.span("Discount rate", class_="section-label"), ui.span("ADVANCED", class_="adv-tag")),
                        ui.div(
                            ui.input_radio_buttons(
                                "rate", None, {"0": "None", "3": "3%", "5": "5%", "7": "7%"}, selected="0", inline=True
                            ),
                            class_="seg",
                        ),
                        ui.input_numeric("rate_custom", "Other rate (%)", value=None, min=0, max=20, step=0.5),
                        ui.div(
                            "By default totals are not discounted. A rate converts each year's value to 2025 money "
                            "and gives less weight to later years.",
                            class_="small muted",
                        ),
                        class_="adv-only adv-box",
                    ),
                    ui.output_ui("npv_panel"),
                    class_="box cb-side",
                ),
                class_="cb-grid",
            ),
        ),
        ui.div(
            ui.div(
                ui.div(
                    ui.span("Largest items", class_="section-label"),
                    info_tip(
                        "The individual costs and benefits behind the categories, ranked by their total over "
                        "2025–2050. Pick a category to see everything inside it."
                    ),
                ),
                ui.input_select("item_category", None, {"": "All categories"}, width="260px"),
                class_="box-head",
            ),
            output_widget("items_chart"),
            class_="box",
        ),
        class_="res-page",
    )


@module.server
def page_cost_benefits_server(input, output, session, state: AppState):
    ev_id = resolve_id("ui_event")
    results_bar.bar_server(input, state, ev_id)
    selected_pw = reactive.Value(None)  # pathway id shown in the chart

    @reactive.calc
    def long() -> Optional[pd.DataFrame]:
        bid = results_bar.current_baseline(state)
        res = state.cb_results.get().get(bid)
        if res is None:
            return None
        df_cb, df_attr = res
        if df_cb is None or df_cb.empty:
            return None
        return cbs.to_long(df_cb, df_attr, config.CB_CONFIG_XLSX_PATH)

    @reactive.calc
    def pathways():
        """Visible pathways that have C&B results (never BAU: it is the reference)."""
        d = long()
        if d is None:
            return []
        bid = results_bar.current_baseline(state)
        have = set(int(s) for s in d["strategy_id"].unique())
        return [s for s in results_bar.visible_pathways(state, bid) if s in have and s != _BAU]

    def current_pw() -> Optional[int]:
        pws = pathways()
        sel = selected_pw.get()
        return sel if sel in pws else (pws[0] if pws else None)

    def rate() -> float:
        """The reference rate in basic mode; the advanced controls override it."""
        if not state.advanced_mode.get():
            return cbs.DEFAULT_RATE
        custom = input.rate_custom()
        if custom is not None and custom >= 0:
            return float(custom)
        return float(input.rate())

    @reactive.effect
    @reactive.event(input.ui_event)
    def _on_event():
        ev = input.ui_event() or {}
        if ev.get("type") == "chip":
            results_bar.toggle_pathway(state, int(ev["value"]))
        elif ev.get("type") == "pw_tab":
            selected_pw.set(int(ev["value"]))

    @render.ui
    def pw_label():
        sid = current_pw()
        return ui.span(results_bar.pathway_name(state, sid), class_="small muted") if sid is not None else None

    @render.ui
    def pw_tabs():
        pws = pathways()
        if len(pws) < 2:
            return None
        bid = results_bar.current_baseline(state)
        colors = results_bar.colors_for(state, bid)
        cur = current_pw()
        tabs = []
        for sid in pws:
            payload = json.dumps({"type": "pw_tab", "value": sid})
            tabs.append(
                ui.tags.button(
                    ui.span(class_="swatch", style=f"background:{colors.get(sid)}"),
                    results_bar.pathway_name(state, sid),
                    class_="chip" + (" active" if sid == cur else ""),
                    onclick=f"Shiny.setInputValue({json.dumps(ev_id)}, {payload}, {{priority: 'event'}}); return false;",
                    type="button",
                )
            )
        return ui.div(*tabs, class_="btn-row")

    def _gdp(sid: int) -> Optional[pd.Series]:
        bid = results_bar.current_baseline(state)
        rr = state.run_results.get().get((sid, bid))
        return cbs.gdp_by_year(rr.df_input if rr is not None else None)

    @render_plotly
    def cb_chart():
        d = long()
        sid = current_pw()
        if d is None or sid is None:
            msg = (
                "Costs & benefits are computed after a run that includes business as usual and a pathway."
                if d is None
                else "Select a pathway other than business as usual."
            )
            return rc.empty_figure(msg, height=420)
        group = input.group()
        wide = cbs.by_group(d, sid, group)
        unit = "billion USD"
        if input.units() == "gdp":
            gdp = _gdp(sid)
            if gdp is None:
                return rc.empty_figure("GDP is not available in this run's inputs.", height=420)
            wide = wide.div(gdp.reindex(wide.index), axis=0).mul(100)
            unit = "% of GDP"
        colors = rc.CB_CATEGORY_COLORS if group == "category" else {
            c: rc.SUBSECTOR_COLORS.get(_abv_of(d, c), rc.OTHER_COLOR) for c in wide.columns
        }
        return rc.cb_bars(wide, colors, unit)

    @reactive.effect
    def _item_categories():
        d = long()
        cats = [c for c in cbs.CATEGORY_ORDER + [cbs.OTHER] if d is not None and (d["category"] == c).any()]
        current = input.item_category() if "item_category" in input else ""
        ui.update_select("item_category", choices={"": "All categories", **{c: c for c in cats}}, selected=current if current in cats else "")

    @render_plotly
    def items_chart():
        d = long()
        sid = current_pw()
        if d is None or sid is None:
            return rc.empty_figure("No costs & benefits yet.", height=200)
        cat = input.item_category() or None
        items = cbs.items_npv(d, sid, rate(), cat).head(15)
        if items.empty:
            return rc.empty_figure("Nothing in this category for this pathway.", height=200)
        return rc.item_bars(items, rc.CB_CATEGORY_COLORS, f"Total 2025–2050, billion USD ({cbs.rate_label(rate())})")

    @render.ui
    def side_title():
        r = rate()
        if r == 0:
            title = "Net benefits 2025–2050"
            tip = (
                "Every year's benefits minus costs from 2025 to 2050, added up (not discounted). "
                "Positive = the pathway's benefits outweigh its costs compared with business as usual."
            )
        else:
            title = "Net present value 2025–2050"
            tip = (
                f"Every year's benefits minus costs from 2025 to 2050, each converted to 2025 money at {r:g}% "
                "a year, then added up. A higher rate gives less weight to later years."
            )
        return ui.div(ui.span(title, class_="section-label"), info_tip(tip))

    @render.ui
    def npv_panel():
        d = long()
        sid = current_pw()
        if d is None or sid is None:
            return ui.div("No costs & benefits yet.", class_="small muted")
        r = rate()
        s = cbs.npv_summary(d, sid, r, group=input.group())

        def money(v):
            return ("+" if v >= 0 else "−") + f"${rc.fmt(abs(v))} B"

        kpis = ui.div(
            ui.div(
                ui.div(
                    "Net benefits" if r == 0 else "Net NPV",
                    info_tip("Total benefits minus total costs, in billions of USD" + ("." if r == 0 else f", in 2025 money at {r:g}%.")),
                    class_="k",
                ),
                ui.div(money(s["net"]), class_="v " + ("pos" if s["net"] >= 0 else "neg")),
            ),
            ui.div(
                ui.div("Benefit / cost", info_tip("Total benefits divided by total costs. Above 1× the benefits are larger."), class_="k"),
                ui.div(f"{s['bcr']:.1f}×" if s["bcr"] else "–", class_="v"),
            ),
            ui.div(
                ui.div("Net positive from", info_tip("First year in which that year's benefits exceed that year's costs (not discounted)."), class_="k"),
                ui.div(str(s["net_positive_year"] or "never"), class_="v"),
            ),
            class_="kpi-vals cb-kpis",
        )
        by = {k: v for k, v in s["by_group"].items() if abs(v) >= 0.005}
        cum = float(d[(d["strategy_id"] == sid) & (d["year"] >= cbs.START_YEAR)]["value_busd"].sum())
        top = max((abs(v) for v in by.values()), default=1.0) or 1.0
        rows = []
        for name, v in by.items():
            color = rc.COST if v < 0 else (rc.CB_CATEGORY_COLORS.get(name, "#0F6E6E") if input.group() == "category" else "#0F6E6E")
            rows.append(
                ui.div(
                    ui.div(name, class_="npv-name"),
                    ui.div(ui.div(class_="npv-bar", style=f"width:{abs(v) / top * 100:.1f}%;background:{color}"), class_="npv-track"),
                    ui.div(money(v), class_="npv-val mono"),
                    class_="npv-row",
                )
            )
        return ui.TagList(
            kpis,
            ui.div(
                f"Benefits {money(s['benefits'])} · costs {money(-s['costs'])}"
                + ("." if r == 0 else f" (present values). Not discounted, the net is {money(cum)}."),
                class_="small muted",
            ),
            ui.div(*rows, class_="npv-list"),
            ui.div(
                f"Billions USD, {cbs.rate_label(r)}, relative to business as usual.",
                class_="small muted",
            ),
        )

    @render.download(filename=lambda: "costs_and_benefits.xlsx")
    def download_xlsx():
        d = long()
        bid = results_bar.current_baseline(state)
        baselines = state.baselines.get()
        label = baselines[bid].label if bid in baselines else (bid or "")
        if d is None:
            yield download_service.cb_workbook(pd.DataFrame(columns=["strategy_id", "year", "variable", "display_name", "sector", "sector_label", "cb_type", "category", "value_busd"]), {}, label)
            return
        sids = [int(s) for s in d["strategy_id"].unique()]
        names = {sid: results_bar.pathway_name(state, sid) for sid in sids}
        gdp = {sid: _gdp(sid) for sid in sids}
        yield download_service.cb_workbook(d, names, label, gdp)


def _abv_of(long: pd.DataFrame, sector_label: str) -> Optional[str]:
    m = long.loc[long["sector_label"] == sector_label, "sector"]
    return m.iloc[0] if not m.empty else None

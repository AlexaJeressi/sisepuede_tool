"""Costs & benefits page (results), relative to business as usual.

Filled by the Run page after every run (`state.cb_results[baseline_id]` =
(df_cb, df_attr_variable) from costs_benefits_ssp). Shows the pathways picked
in the results bar (one or several, side by side):
- the 2025-2050 total by CB type, grouped by CB sector (the Egypt Tableau
  workbook's grouping of cb_data.csv), next to
- stacked costs (below zero) and benefits (above zero) per year, split by CB
  type (default), category or sector, and in advanced mode by item 1 or item 2
  (the last two parts of the variable name), with the net; billions USD or % of GDP;
- filters by CB type, and in advanced mode by item 1 and item 2, for the whole
  page (the Excel download keeps everything);
- in advanced mode, the charts times −1 (costs above zero), to look at or save
  them that way; the totals panel keeps the signs;
- totals 2025–2050, not discounted (a discount rate is an advanced option): net,
  benefit/cost ratio, the first year the net turns positive, and the net by
  category.

No data tables: the Excel download has every cost/benefit variable by year,
the category totals, and totals at 0 / 3 / 5 / 7% (services/download_service.py).
"""

from typing import Dict, Optional

import pandas as pd
from shiny import module, reactive, render, ui
from shiny.module import resolve_id
from shinywidgets import output_widget, render_plotly

from sisepuede_tool import config
from sisepuede_tool.services import cb_summary_service as cbs
from sisepuede_tool.services import download_service, i18n
from sisepuede_tool.ui.components import result_charts as rc
from sisepuede_tool.ui.components.chart_export import export_button
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
                    ui.div(
                        ui.span(i18n.t("cost_benefits.by_year"), class_="section-label"),
                        export_button("cb_chart", i18n.t("cost_benefits.by_year")),
                        class_="box-head",
                    ),
                    ui.div(
                        ui.div(
                            ui.input_radio_buttons("group", None, _group_choices(advanced=False), selected="cb_type", inline=True),
                            class_="seg",
                        ),
                        ui.div(
                            ui.input_radio_buttons(
                                "units", None, {"busd": i18n.t("cost_benefits.billion_usd"), "gdp": i18n.t("results.pct_gdp")}, inline=True
                            ),
                            class_="seg",
                        ),
                        ui.div(
                            ui.input_checkbox("flip", i18n.t("cost_benefits.flip")),
                            info_tip(i18n.t("cost_benefits.flip_tip")),
                            class_="adv-only cb-flip",
                        ),
                        class_="res-controls",
                    ),
                    ui.div(
                        ui.input_selectize("cb_types", i18n.t("cost_benefits.filter_cb_type"), {}, multiple=True, width="420px",
                                           options={"placeholder": i18n.t("cost_benefits.all_cb_types"), "plugins": ["remove_button"]}),
                        ui.div(
                            ui.div(
                                ui.input_selectize("item_1", i18n.t("cost_benefits.filter_item_1"), {}, multiple=True, width="260px",
                                                   options={"placeholder": i18n.t("cost_benefits.all_items"), "plugins": ["remove_button"]}),
                                ui.input_selectize("item_2", i18n.t("cost_benefits.filter_item_2"), {}, multiple=True, width="260px",
                                                   options={"placeholder": i18n.t("cost_benefits.all_items"), "plugins": ["remove_button"]}),
                                class_="cb-item-filters",
                            ),
                            class_="adv-only",
                        ),
                        class_="res-controls cb-filters",
                    ),
                    ui.output_ui("filter_note"),
                    ui.div(
                        ui.div(
                            ui.div(
                                ui.span(i18n.t("cost_benefits.breakdown_title"), class_="section-label"),
                                info_tip(i18n.t("cost_benefits.breakdown_tip")),
                                export_button("breakdown_chart", i18n.t("cost_benefits.breakdown_title")),
                                class_="box-head",
                            ),
                            output_widget("breakdown_chart"),
                            ui.output_ui("breakdown_note"),
                            class_="cb-breakdown",
                        ),
                        ui.div(output_widget("cb_chart"), class_="cb-yearly"),
                        class_="cb-split",
                    ),
                    ui.output_ui("chart_note"),
                    class_="box",
                ),
                ui.div(
                    ui.div(
                        ui.output_ui("side_title"),
                        class_="box-head",
                    ),
                    ui.div(
                        ui.div(
                            ui.span(i18n.t("cost_benefits.discount_rate"), class_="section-label"),
                            ui.span(i18n.t("results.advanced"), class_="adv-tag"),
                        ),
                        ui.div(
                            ui.input_radio_buttons(
                                "rate", None, {"0": i18n.t("cost_benefits.rate_none"), "3": "3%", "5": "5%", "7": "7%"}, selected="0", inline=True
                            ),
                            class_="seg",
                        ),
                        ui.input_numeric("rate_custom", i18n.t("cost_benefits.other_rate"), value=None, min=0, max=20, step=0.5),
                        ui.div(i18n.t("cost_benefits.rate_note"), class_="small muted"),
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
                    ui.span(i18n.t("cost_benefits.largest_items"), class_="section-label"),
                    info_tip(i18n.t("cost_benefits.largest_items_tip")),
                ),
                ui.div(
                    ui.input_select("item_category", None, {"": i18n.t("cost_benefits.all_categories")}, width="260px"),
                    export_button("items_chart", i18n.t("cost_benefits.largest_items")),
                    class_="btn-row",
                ),
                class_="box-head",
            ),
            output_widget("items_chart"),
            class_="box",
        ),
        class_="res-page",
    )


def _group_choices(advanced: bool, lang=None) -> dict:
    """What the yearly chart can be split by; item 1 / item 2 only in advanced mode."""
    out = {
        "cb_type": i18n.t("cost_benefits.by_cb_type", lang),
        "category": i18n.t("cost_benefits.by_category", lang),
        "sector_label": i18n.t("cost_benefits.by_sector", lang),
    }
    if advanced:
        out.update({"item_1": i18n.t("cost_benefits.by_item_1", lang), "item_2": i18n.t("cost_benefits.by_item_2", lang)})
    return out


MAX_ITEM_SERIES = 10  # split by item: the largest items, the rest as one layer


@module.server
def page_cost_benefits_server(input, output, session, state: AppState):
    ev_id = resolve_id("ui_event")
    results_bar.bar_server(input, state, ev_id)

    def _t(key, **fmt):
        return i18n.t(f"cost_benefits.{key}", state.lang(), **fmt)

    def _rate_label(r: float) -> str:
        """Translated cbs.rate_label."""
        return _t("rate_label_none") if r == 0 else _t("rate_label_pct", rate=f"{r:g}", year=cbs.START_YEAR)

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

    def _advanced() -> bool:
        return bool(state.advanced_mode.get())

    @reactive.calc
    def filtered() -> Optional[pd.DataFrame]:
        """long() with the page's filters: CB type, and item 1 / item 2 in advanced mode."""
        d = long()
        if d is None:
            return None
        adv = _advanced()
        return cbs.filter_by(
            d,
            cb_type=input.cb_types(),
            item_1=input.item_1() if adv else None,
            item_2=input.item_2() if adv else None,
        )

    def _flipped() -> bool:
        """Advanced option: the charts times −1 (costs above zero), e.g. to save one that way."""
        return _advanced() and bool(input.flip())

    @reactive.calc
    def charted() -> Optional[pd.DataFrame]:
        """filtered(), times −1 when the charts are flipped (the totals panel is not)."""
        d = filtered()
        if d is None or not _flipped():
            return d
        return d.assign(value_busd=-d["value_busd"])

    def _unit(unit: str) -> str:
        return _t("flip_unit", unit=unit) if _flipped() else unit

    @render.ui
    def chart_note():
        return ui.div(_t("chart_note_flipped" if _flipped() else "chart_note"), class_="small muted")

    def _labels(group: str, names) -> Dict[str, str]:
        lang = state.lang()
        if group == "cb_type":
            return {n: cbs.cb_type_name(n, lang) for n in names}
        if group in ("item_1", "item_2"):
            return {n: cbs.item_label(n) for n in names}
        return {n: rc.series_label(n, lang) for n in names}

    def _colors(group: str, names, d) -> Dict[str, str]:
        if group == "cb_type":
            return cbs.CB_TYPE_COLORS
        if group == "category":
            return rc.CB_CATEGORY_COLORS
        if group in ("item_1", "item_2"):
            return {**rc.series_colors([n for n in names if n != rc.LUMP]), rc.LUMP: rc.OTHER_COLOR}
        return {c: rc.SUBSECTOR_COLORS.get(_abv_of(d, c), rc.OTHER_COLOR) for c in names}

    @reactive.effect
    def _group_options():
        adv, lang = _advanced(), state.lang()
        with reactive.isolate():
            current = input.group()
        choices = _group_choices(adv, lang)
        ui.update_radio_buttons("group", choices=choices, selected=current if current in choices else "cb_type", inline=True)

    @reactive.effect
    def _cb_type_options():
        d, lang = long(), state.lang()
        with reactive.isolate():
            current = list(input.cb_types() or ())
        if d is None:
            return
        groups: Dict[str, Dict[str, str]] = {}
        for t in cbs.cb_type_order(d["cb_type"].dropna().unique()):
            groups.setdefault(cbs.cb_sector_name(cbs.cb_sector_of(t), lang), {})[t] = cbs.cb_type_name(t, lang)
        have = {t for g in groups.values() for t in g}
        ui.update_selectize("cb_types", choices=groups, selected=[t for t in current if t in have])

    @reactive.effect
    def _item_options():
        """Item choices among the CB types picked (item 2: also among the items 1 picked)."""
        d = long()
        if d is None or not _advanced():
            return
        d = cbs.filter_by(d, cb_type=input.cb_types())
        with reactive.isolate():
            cur_1, cur_2 = list(input.item_1() or ()), list(input.item_2() or ())
        items_1 = sorted(d["item_1"].unique(), key=cbs.item_label)
        ui.update_selectize("item_1", choices={i: cbs.item_label(i) for i in items_1}, selected=[i for i in cur_1 if i in items_1])
        d2 = cbs.filter_by(d, item_1=input.item_1())
        items_2 = sorted(d2["item_2"].unique(), key=cbs.item_label)
        ui.update_selectize("item_2", choices={i: cbs.item_label(i) for i in items_2}, selected=[i for i in cur_2 if i in items_2])

    @render.ui
    def filter_note():
        d, f = long(), filtered()
        if d is None or f is None or len(f) == len(d):
            return None
        return ui.div(_t("filter_note", shown=f["variable"].nunique(), total=d["variable"].nunique()), class_="small muted")

    @reactive.calc
    def pathways():
        """Visible pathways that have C&B results (never BAU: it is the reference)."""
        d = long()
        if d is None:
            return []
        bid = results_bar.current_baseline(state)
        have = set(int(s) for s in d["strategy_id"].unique())
        return [s for s in results_bar.visible_pathways(state, bid) if s in have and s != _BAU]

    def _pw_colors() -> Dict[str, str]:
        """{pathway name: colour} of the pathways shown, in the results bar's order."""
        colors = results_bar.colors_for(state, results_bar.current_baseline(state))
        return {results_bar.pathway_name(state, sid): colors.get(sid, rc.OTHER_COLOR) for sid in pathways()}

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

    def _gdp(sid: int) -> Optional[pd.Series]:
        bid = results_bar.current_baseline(state)
        rr = state.run_results.get().get((sid, bid))
        return cbs.gdp_by_year(rr.df_input if rr is not None else None)

    @render_plotly

    @rc.bidi_for(state.lang)
    def cb_chart():
        d = charted()
        pws = pathways()
        if d is None or not pws:
            msg = _t("empty_no_cb") if d is None else _t("empty_pick")
            return rc.empty_figure(msg, height=420)
        if d.empty:
            return rc.empty_figure(_t("empty_filter"), height=420)
        lang = state.lang()
        group = input.group() if input.group() in cbs.GROUPS else "cb_type"
        frames = {sid: cbs.by_group(d, sid, group) for sid in pws}
        names = list(dict.fromkeys(c for w in frames.values() for c in w.columns))
        if group in ("item_1", "item_2") and len(names) > MAX_ITEM_SERIES:
            # the same largest items in every panel
            size = pd.concat([w.abs().sum() for w in frames.values()]).groupby(level=0).sum()
            keep = list(size.sort_values(ascending=False).index[: MAX_ITEM_SERIES - 1])
            frames = {sid: pd.concat([w[[c for c in keep if c in w]], w.drop(columns=[c for c in keep if c in w]).sum(axis=1).rename(rc.LUMP)], axis=1)
                      for sid, w in frames.items()}
            names = keep + [rc.LUMP]
        unit = i18n.t("results.billion_usd", lang)
        if input.units() == "gdp":
            for sid, w in frames.items():
                gdp = _gdp(sid)
                if gdp is None:
                    return rc.empty_figure(_t("no_gdp"), height=420)
                frames[sid] = w.div(gdp.reindex(w.index), axis=0).mul(100)
            unit = i18n.t("results.pct_gdp", lang)
        labels = _labels(group, names)
        if rc.LUMP in names:
            labels[rc.LUMP] = rc.series_label(rc.LUMP, lang)
        frames = {results_bar.pathway_name(state, sid): w for sid, w in frames.items()}
        # about as tall as the total by CB type beside it
        return rc.cb_panels(frames, _colors(group, names, d), _unit(unit), height=540, lang=lang, years=state.results_years.get(), labels=labels)

    @render_plotly
    @rc.bidi_for(state.lang)
    def breakdown_chart():
        d = charted()
        pws = pathways()
        if d is None or not pws:
            return rc.empty_figure(_t("empty_no_cb") if d is None else _t("empty_pick"), height=420)
        if d.empty:
            return rc.empty_figure(_t("empty_filter"), height=420)
        lang = state.lang()
        table = pd.concat([cbs.by_cb_type(d, sid, rate()).assign(pathway=results_bar.pathway_name(state, sid)) for sid in pws],
                          ignore_index=True)
        return rc.cb_type_breakdown(
            table, cbs.CB_TYPE_COLORS, {t: cbs.cb_type_name(t, lang) for t in table["cb_type"]},
            {s: cbs.cb_sector_name(s, lang) for s in table["cb_sector"]}, _unit(i18n.t("results.billion_usd", lang)), lang=lang,
            pathway_colors=_pw_colors(),
        )

    @render.ui
    def breakdown_note():
        return ui.div(_t("breakdown_note", rate=_rate_label(rate())), class_="small muted")

    @reactive.effect
    def _item_categories():
        d = filtered()
        cats = [c for c in cbs.CATEGORY_ORDER + [cbs.OTHER] if d is not None and (d["category"] == c).any()]
        current = input.item_category() if "item_category" in input else ""
        lang = state.lang()
        choices = {"": _t("all_categories"), **{c: rc.series_label(c, lang) for c in cats}}
        ui.update_select("item_category", choices=choices, selected=current if current in cats else "")

    @render_plotly

    @rc.bidi_for(state.lang)
    def items_chart():
        d = charted()
        pws = pathways()
        if d is None or not pws:
            return rc.empty_figure(_t("none_yet"), height=200)
        cat = input.item_category() or None
        unit = _unit(_t("items_unit", rate=_rate_label(rate())))
        if len(pws) == 1:
            items = cbs.items_npv(d, pws[0], rate(), cat).head(15)
            if items.empty:
                return rc.empty_figure(_t("empty_category"), height=200)
            return rc.item_bars(items, rc.CB_CATEGORY_COLORS, unit, lang=state.lang(), flipped=_flipped())
        # several pathways: the items largest in any of them, side by side
        items = pd.concat([cbs.items_npv(d, sid, rate(), cat).assign(pathway=results_bar.pathway_name(state, sid)) for sid in pws],
                          ignore_index=True)
        if items.empty:
            return rc.empty_figure(_t("empty_category"), height=200)
        top = items.groupby("display_name")["pv"].apply(lambda v: v.abs().max()).sort_values(ascending=False).index[:12]
        items = items[items["display_name"].isin(top)]
        items = items.assign(rank=items["display_name"].map({n: i for i, n in enumerate(top)})).sort_values("rank")
        return rc.item_bars_by_pathway(items, _pw_colors(), unit, lang=state.lang())

    @render.ui
    def side_title():
        r = rate()
        if r == 0:
            title, tip = _t("net_benefits_title"), _t("net_benefits_tip")
        else:
            title, tip = _t("npv_title"), _t("npv_tip", rate=f"{r:g}")
        return ui.div(ui.span(title, class_="section-label"), info_tip(tip))

    @render.ui
    def npv_panel():
        d = filtered()
        pws = pathways()
        if d is None or not pws:
            return ui.div(_t("none_yet"), class_="small muted")
        r = rate()
        lang = state.lang()
        group = input.group() if input.group() in cbs.GROUPS else "cb_type"

        def money(v):
            return i18n.t("results.money_b", lang, sign="+" if v >= 0 else "−", v=rc.fmt(abs(v)))

        if len(pws) > 1:
            return _compare_panel(d, pws, r, group, money)
        sid = pws[0]
        s = cbs.npv_summary(d, sid, r, group=group)

        kpis = ui.div(
            ui.div(
                ui.div(
                    _t("kpi_net") if r == 0 else _t("kpi_npv"),
                    info_tip(_t("kpi_net_tip") if r == 0 else _t("kpi_npv_tip", rate=f"{r:g}")),
                    class_="k",
                ),
                ui.div(money(s["net"]), class_="v " + ("pos" if s["net"] >= 0 else "neg")),
            ),
            ui.div(
                ui.div(_t("kpi_bcr"), info_tip(_t("kpi_bcr_tip")), class_="k"),
                ui.div(f"{s['bcr']:.1f}×" if s["bcr"] else "–", class_="v"),
            ),
            ui.div(
                ui.div(_t("kpi_positive"), info_tip(_t("kpi_positive_tip")), class_="k"),
                ui.div(str(s["net_positive_year"] or _t("never")), class_="v"),
            ),
            class_="kpi-vals cb-kpis",
        )
        by = {k: v for k, v in s["by_group"].items() if abs(v) >= 0.005}
        names = _labels(group, by)
        colors = _colors(group, by, d)
        cum = float(d[(d["strategy_id"] == sid) & (d["year"] >= cbs.START_YEAR)]["value_busd"].sum())
        top = max((abs(v) for v in by.values()), default=1.0) or 1.0
        rows = []
        for name, v in by.items():
            color = rc.COST if v < 0 else (colors.get(name, "#0F6E6E") if group in ("category", "cb_type") else "#0F6E6E")
            rows.append(
                ui.div(
                    ui.div(names.get(name, name), class_="npv-name"),
                    ui.div(ui.div(class_="npv-bar", style=f"width:{abs(v) / top * 100:.1f}%;background:{color}"), class_="npv-track"),
                    ui.div(money(v), class_="npv-val mono"),
                    class_="npv-row",
                )
            )
        return ui.TagList(
            kpis,
            ui.div(
                _t("benefits_costs", benefits=money(s["benefits"]), costs=money(-s["costs"]))
                + ("." if r == 0 else _t("pv_note", net=money(cum))),
                class_="small muted",
            ),
            ui.div(*rows, class_="npv-list"),
            ui.div(_t("footer", rate=_rate_label(r)), class_="small muted"),
        )

    def _compare_panel(d: pd.DataFrame, pws, r: float, group: str, money) -> ui.Tag:
        """Totals of several pathways side by side: net, benefit/cost, net-positive
        year, then the net by group (largest first in any pathway)."""
        colors = results_bar.colors_for(state, results_bar.current_baseline(state))
        sums = {sid: cbs.npv_summary(d, sid, r, group=group) for sid in pws}

        def cell(v, cls=""):
            return ui.tags.td(v, class_=("mono " + cls).strip())

        def signed(v):
            return cell(money(v), "pos" if v >= 0 else "neg")

        head = ui.tags.tr(ui.tags.th(""), *[
            ui.tags.th(ui.span(class_="swatch", style=f"background:{colors.get(sid)}"), results_bar.pathway_name(state, sid)) for sid in pws
        ])
        rows = [
            ui.tags.tr(ui.tags.th(_t("kpi_net") if r == 0 else _t("kpi_npv")), *[signed(sums[sid]["net"]) for sid in pws], class_="cb-cmp-key"),
            ui.tags.tr(ui.tags.th(_t("kpi_bcr")), *[cell(f"{sums[sid]['bcr']:.1f}×" if sums[sid]["bcr"] else "–") for sid in pws]),
            ui.tags.tr(ui.tags.th(_t("kpi_positive")), *[cell(str(sums[sid]["net_positive_year"] or _t("never"))) for sid in pws]),
            ui.tags.tr(ui.tags.th(_t("benefits_short")), *[signed(sums[sid]["benefits"]) for sid in pws]),
            ui.tags.tr(ui.tags.th(_t("costs_short")), *[signed(-sums[sid]["costs"]) for sid in pws], class_="cb-cmp-sep"),
        ]
        keys = {}
        for sid in pws:
            for k, v in sums[sid]["by_group"].items():
                keys[k] = max(keys.get(k, 0.0), abs(v))
        keys = [k for k, v in sorted(keys.items(), key=lambda kv: -kv[1]) if v >= 0.005]
        names = _labels(group, keys)
        for k in keys:
            rows.append(ui.tags.tr(ui.tags.th(names.get(k, k), class_="cb-cmp-name"),
                                   *[signed(sums[sid]["by_group"].get(k, 0.0)) for sid in pws]))
        return ui.TagList(
            ui.div(ui.tags.table(ui.tags.thead(head), ui.tags.tbody(*rows), class_="cb-compare"), class_="cb-compare-wrap"),
            ui.div(_t("footer", rate=_rate_label(r)), class_="small muted"),
        )

    @render.download(filename=lambda: "tableau_data.zip")
    def download_tableau():
        yield results_bar.tableau_zip(state)

    @render.download(filename=lambda: "costs_and_benefits.xlsx")
    def download_xlsx():
        d = long()
        bid = results_bar.current_baseline(state)
        baselines = state.baselines.get()
        label = baselines[bid].label if bid in baselines else (bid or "")
        if d is None:
            yield download_service.cb_workbook(pd.DataFrame(columns=cbs.LONG_COLUMNS), {}, label)
            return
        sids = [int(s) for s in d["strategy_id"].unique()]
        names = {sid: results_bar.pathway_name(state, sid) for sid in sids}
        gdp = {sid: _gdp(sid) for sid in sids}
        yield download_service.cb_workbook(d, names, label, gdp)


def _abv_of(long: pd.DataFrame, sector_label: str) -> Optional[str]:
    m = long.loc[long["sector_label"] == sector_label, "sector"]
    return m.iloc[0] if not m.empty else None

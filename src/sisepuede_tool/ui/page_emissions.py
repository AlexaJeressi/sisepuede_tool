"""Emissions & drivers page (results).

Top to bottom:
- shared results bar (baseline, pathway chips, run stamp, Excel download);
- headline KPIs per pathway (net 2030 / 2050, % vs BAU, avoided emissions);
- "Net GHG emissions": small multiples per pathway stacked by subsector, or
  the change vs BAU by subsector in 2030 and 2050, with sector and gas
  filters. Picking a subsector filters the chart to it; in advanced mode it
  can be broken down by emission source (e.g. Transportation -> Road / Rail);
- "What drives ... emissions": curated driver cards for the matching area
  (resources/results_groups.yaml), plus population and GDP (can be hidden).
  Its header is pinned while scrolling: the same subsector picker as the
  chart (one selection, shown in both places), 2050 emissions per pathway, and (with no subsector picked)
  shortcuts to the subsectors that change most vs BAU. The focused
  subsector's cards come first; the rest of its area is dimmed. In advanced
  mode users can add a card for any model variable.

No data tables: everything on the page (and the full emissions detail) is in
the Excel download (services/download_service.py).
"""

import json
from typing import Dict, List, Optional

import pandas as pd
from shiny import module, reactive, render, ui
from shiny.module import resolve_id
from shinywidgets import output_widget, render_plotly

from sisepuede_tool.services import download_service, emissions_service, i18n, output_service, results_groups_service
from sisepuede_tool.ui.components import result_charts as rc
from sisepuede_tool.ui.components import results_bar
from sisepuede_tool.ui.components.info_tip import info_tip
from sisepuede_tool.ui.state import AppState

N_SLOTS = 16  # driver card chart slots (context + area + custom cards)
_BAU = results_bar.BAU
_EMITTING = ["entc", "trns", "inen", "scoe", "fgtv", "ccsq", "ippu", "agrc", "lvst", "lsmm", "soil", "lndu", "frst", "waso", "trww"]

_field_catalog_cache: Dict[int, pd.DataFrame] = {}


def field_catalog(model_attributes) -> pd.DataFrame:
    key = id(model_attributes)
    if key not in _field_catalog_cache:
        _field_catalog_cache[key] = output_service.build_field_catalog(model_attributes)
    return _field_catalog_cache[key]


def _subsector(abv: str, lang: Optional[str] = None) -> str:
    return i18n.t(f"subsectors.{abv}", lang, default=emissions_service.subsector_label(abv))


def _emitting_subsectors(lang: Optional[str] = None) -> Dict[str, str]:
    """{abv: display name} of the subsectors in the emissions chart, in chart order."""
    return {abv: _subsector(abv, lang) for abv in _EMITTING}


def _sectors(lang: Optional[str] = None) -> Dict[str, str]:
    """Sector filter {value: label}; values are emissions_service sector names."""
    names = {"Energy": "energy", "IPPU": "ippu", "AFOLU": "afolu", "Circular Economy": "circular_economy"}
    return {"all": i18n.t("emissions.all", lang), **{v: i18n.t(f"sectors.{k}", lang, default=v) for v, k in names.items()}}


def _gases(lang: Optional[str] = None) -> Dict[str, str]:
    return {"all": i18n.t("emissions.all_gases", lang), "CO2": "CO₂", "CH4": "CH₄", "N2O": "N₂O", "F-gases": i18n.t("emissions.fgases", lang)}


@module.ui
def page_emissions_ui():
    groups = results_groups_service.load_groups()
    return ui.div(
        results_bar.bar_ui("download_xlsx"),
        ui.output_ui("kpis"),
        ui.div(
            ui.div(
                ui.span(i18n.t("emissions.net_ghg"), class_="section-label"),
                ui.span(i18n.t("emissions.net_ghg_note"), class_="small muted"),
                class_="box-head",
            ),
            ui.div(
                ui.div(
                    ui.input_radio_buttons(
                        "view", None, {"emissions": i18n.t("emissions.view_emissions"), "delta": i18n.t("emissions.view_delta")}, inline=True
                    ),
                    class_="seg",
                ),
                ui.div(ui.input_radio_buttons("sector", None, _sectors(), inline=True), class_="seg"),
                ui.input_select("focus", None, {"": i18n.t("emissions.all_subsectors"), **_emitting_subsectors()}, width="240px"),
                ui.div(ui.input_radio_buttons("gas", None, _gases(), inline=True), class_="seg"),
                ui.panel_conditional(
                    "input.focus !== ''",
                    ui.div(ui.input_switch("breakdown", i18n.t("emissions.breakdown"), value=False), class_="adv-only"),
                ),
                class_="res-controls",
            ),
            output_widget("emis_chart"),
            ui.output_ui("emis_note"),
            class_="box",
        ),
        ui.div(
            # pinned while scrolling through the drivers: the subsector picker
            # (same selection as the chart's) and its 2050 emissions
            ui.div(
                ui.div(
                    ui.div(
                        ui.span(i18n.t("emissions.drives_before"), class_="drv-sticky-title"),
                        ui.input_select("focus_bar", None, {"": i18n.t("emissions.all_subsectors"), **_emitting_subsectors()}, width="240px"),
                        ui.span(i18n.t("emissions.drives_after"), class_="drv-sticky-title"),
                        class_="drv-sticky-pick",
                    ),
                    ui.input_switch("show_context", i18n.t("emissions.context_switch"), value=True),
                    class_="drv-sticky-row",
                ),
                ui.output_ui("drivers_context"),
                class_="drv-sticky",
            ),
            ui.div(i18n.t("emissions.drivers_intro"), class_="small muted"),
            ui.output_ui("drivers_grid"),
            ui.div(
                ui.div(ui.span(i18n.t("emissions.add_variable"), class_="section-label"), ui.span(i18n.t("results.advanced"), class_="adv-tag")),
                ui.div(
                    ui.input_selectize(
                        "add_var", None, choices=[], multiple=True,
                        options={"placeholder": i18n.t("emissions.add_var_placeholder")}, width="560px",
                    ),
                    ui.input_action_button("add_var_btn", i18n.t("emissions.add_cards"), class_="btn-inline"),
                    class_="btn-row",
                ),
                ui.div(i18n.t("emissions.inputs_outputs"), class_="small muted"),
                class_="adv-only adv-box",
            ),
            class_="box",
        ),
        class_="res-page",
    )


@module.server
def page_emissions_server(input, output, session, state: AppState):
    ev_id = resolve_id("ui_event")
    results_bar.bar_server(input, state, ev_id)
    groups = results_groups_service.load_groups()

    def _t(key, **fmt):
        return i18n.t(f"emissions.{key}", state.lang(), **fmt)

    def _card_text(card, field):
        """A driver card's text from resources/results_groups.yaml, in the session language."""
        if card.get("custom"):
            return _t("custom_why") if field == "why" else card.get(field, "")
        return i18n.td("results_groups", card["key"], field, card.get(field, ""), state.lang())

    # ------------------------------------------------------------------ data

    @reactive.calc
    def catalog() -> Optional[pd.DataFrame]:
        ma = state.model_attributes.get()
        return field_catalog(ma) if ma is not None else None

    @reactive.calc
    def runs():
        """(baseline id, [(sid, name, RunResult)]) for the visible pathways, OK runs only."""
        bid, rows = results_bar.runs_for_page(state)
        return bid, [(sid, name, rr) for sid, name, rr in rows if rr is not None and rr.ok and rr.df_output is not None]

    @reactive.calc
    def bau_run():
        bid, _ = runs()
        rr = state.run_results.get().get((_BAU, bid))
        return rr if rr is not None and rr.ok else None

    @reactive.calc
    def subsector_frames() -> Dict[str, pd.DataFrame]:
        """Emissions by subsector per pathway, for the selected gas group."""
        _, rows = runs()
        gas = input.gas()
        return {name: emissions_service.by_subsector_for_gas(rr.df_output, gas) for _, name, rr in rows}

    @reactive.calc
    def _bau_frame() -> Optional[pd.DataFrame]:
        rr = bau_run()
        return emissions_service.by_subsector_for_gas(rr.df_output, input.gas()) if rr is not None else None

    def _breakdown() -> bool:
        """Detail by emission source (advanced) instead of the subsector itself."""
        return bool(input.focus()) and state.advanced_mode.get() and bool(input.breakdown())

    def _shown(abv: str) -> bool:
        """Subsectors the chart keeps: the picked one, else those in the sector filter."""
        focus = input.focus()
        return abv == focus if focus else _sector_ok(abv)

    # ------------------------------------------------------------------ events

    @reactive.effect
    @reactive.event(input.ui_event)
    def _on_event():
        ev = input.ui_event() or {}
        kind, value = ev.get("type"), ev.get("value")
        if kind == "chip":
            results_bar.toggle_pathway(state, int(value))
        elif kind == "remove_card":
            state.results_custom_vars.set([v for v in state.results_custom_vars.get() if v != value])
        elif kind == "focus":
            ui.update_select("focus", selected=value)

    # one subsector selection, shown in two places: the chart filter and the drivers header
    @reactive.effect
    @reactive.event(input.focus)
    def _focus_to_bar():
        if input.focus_bar() != input.focus():
            ui.update_select("focus_bar", selected=input.focus())

    @reactive.effect
    @reactive.event(input.focus_bar)
    def _bar_to_focus():
        if input.focus() != input.focus_bar():
            ui.update_select("focus", selected=input.focus_bar())

    @reactive.effect
    def _add_var_choices():
        cat = catalog()
        if cat is None:
            return
        rows = cat.drop_duplicates("variable")
        rows = rows[~rows["variable"].str.contains("NemoMod :math:|emission_co2e", regex=True)]
        choices: Dict[str, Dict[str, str]] = {}
        for r in rows.sort_values(["sector", "subsector", "variable"]).itertuples():
            sector = r.sector or "Other"
            sector = i18n.t(f"sectors.{sector.lower().replace(' ', '_')}", state.lang(), default=sector)
            group = f"{sector} · {r.subsector}"
            name = r.label.split(" · ")[0]
            choices.setdefault(group, {})[r.variable] = f"{name} ({_t('var_input' if r.is_input else 'var_output')})"
        # rebuilt on a language change too: keep what the user picked
        with reactive.isolate():
            picked = list(input.add_var() or [])
        ui.update_selectize("add_var", choices=choices, selected=picked, options={"placeholder": _t("add_var_placeholder")})

    @reactive.effect
    @reactive.event(input.add_var_btn)
    def _add_var():
        picked = list(input.add_var() or [])
        if not picked:
            return
        current = state.results_custom_vars.get()
        state.results_custom_vars.set(current + [v for v in picked if v not in current])
        ui.update_selectize("add_var", selected=[])

    # ------------------------------------------------------------------ KPIs

    @render.ui
    def kpis():
        bid, rows = runs()
        if not rows:
            return None
        nets = {name: emissions_service.net_total(rr.df_output) for _, name, rr in rows}
        bau_name = results_bar.pathway_name(state, _BAU)
        bau = _bau_frame()
        if bau is not None:
            nets.setdefault(bau_name, bau.groupby("year")["value"].sum())
        stats = {k["key"]: k for k in emissions_service.kpis(nets, bau_name)}
        colors = results_bar.colors_for(state, bid)
        tiles = []
        for sid, name, _ in rows:
            k = stats[name]

            def pct(v):
                return "" if v is None else f" ({v:+.1f}%)"

            body = [
                ui.div(ui.span(class_="swatch", style=f"background:{colors.get(sid)}"), ui.span(name, class_="kpi-name"), class_="kpi-head"),
                ui.div(
                    ui.div(ui.div("2030", class_="k"), ui.div(f"{rc.fmt(k['net_2030'])} Mt", ui.span(pct(k["pct_2030"]), class_="pct"), class_="v")),
                    ui.div(ui.div("2050", class_="k"), ui.div(f"{rc.fmt(k['net_2050'])} Mt", ui.span(pct(k["pct_2050"]), class_="pct"), class_="v")),
                    ui.div(
                        ui.div(_t("kpi_avoided"), class_="k"),
                        ui.div(_t("kpi_reference") if sid == _BAU else f"{rc.fmt(k['avoided_cum'])} Mt", class_="v"),
                    ),
                    class_="kpi-vals",
                ),
            ]
            tiles.append(ui.div(*body, class_="kpi-tile"))
        return ui.div(*tiles, class_="kpi-row")

    # ------------------------------------------------------------------ emissions chart

    def _sector_ok(abv: str) -> bool:
        s = input.sector()
        return s == "all" or emissions_service.sector_of(abv) == s

    @render_plotly

    @rc.bidi_for(state.lang)
    def emis_chart():
        bid, rows = runs()
        lang = state.lang()
        if not rows:
            return rc.empty_figure(_t("empty_run"))
        focus = input.focus()
        gas = input.gas()
        if input.view() == "delta":
            return _delta_figure(rows, focus, gas)
        frames, net = {}, {}
        if not _breakdown():
            labels = {abv: emissions_service.subsector_label(abv) for abv in _EMITTING}
            colors = {labels[a]: rc.SUBSECTOR_COLORS.get(a, rc.OTHER_COLOR) for a in labels}
            order = [labels[a] for a in labels]
            for _, name, rr in rows:
                d = subsector_frames()[name]
                d = d[d["subsector_abv"].map(_shown)]
                f = d.assign(series=d["subsector_abv"].map(emissions_service.subsector_label))[["year", "series", "value"]]
                frames[name] = f
                net[name] = f.groupby("year")["value"].sum()
        else:
            for _, name, rr in rows:
                d = emissions_service.detail(rr.df_output, focus)
                if gas != "all":
                    d = d[d["gas_group"] == gas]
                f = d.groupby(["year", "detail"], as_index=False)["value"].sum().rename(columns={"detail": "series"})
                frames[name] = f
                net[name] = f.groupby("year")["value"].sum()
            frames, order = rc.lumped(frames, n=10)
            colors = rc.series_colors(order)
        titles = {}
        bau_net = net.get(results_bar.pathway_name(state, _BAU))
        if bau_net is None and bau_run() is not None:
            bau_net = None  # BAU hidden: titles show totals only
        for name, s in net.items():
            v = float(s.get(2050, float("nan")))
            pct = ""
            if bau_net is not None and name != results_bar.pathway_name(state, _BAU) and bau_net.get(2050):
                pct = _t("panel_pct", pct=f"{((v / float(bau_net[2050])) - 1) * 100:+.0f}")
            titles[name] = _t("panel_title", name=name, value=rc.fmt(v), pct=pct)
        frames = {titles[k]: v for k, v in frames.items()}
        net = {titles[k]: v for k, v in net.items()}
        return rc.stacked_panels(frames, colors, order, "MtCO₂e", net=net, height=380, lang=lang)

    def _delta_figure(rows, focus, gas):
        bau = bau_run()
        if bau is None:
            return rc.empty_figure(_t("no_bau"))
        def table(df_output):
            if not _breakdown():
                d = emissions_service.by_subsector_for_gas(df_output, gas)
                d = d[d["subsector_abv"].map(_shown)]
                return d.groupby(["year", "subsector"])["value"].sum()
            d = emissions_service.detail(df_output, focus)
            if gas != "all":
                d = d[d["gas_group"] == gas]
            return d.groupby(["year", "detail"])["value"].sum().rename_axis(["year", "subsector"])
        base = table(bau.df_output)
        bid, _ = runs()
        colors = results_bar.colors_for(state, bid)
        parts, pcolors = [], {}
        for sid, name, rr in rows:
            if sid == _BAU:
                continue
            delta = (table(rr.df_output) - base.reindex(table(rr.df_output).index).fillna(0)).reset_index(name="delta")
            parts.append(delta.assign(pathway=name))
            pcolors[name] = colors.get(sid)
        if not parts:
            return rc.empty_figure(_t("pick_pathway"))
        deltas = pd.concat(parts)
        deltas = deltas[deltas["year"].isin([2030, 2050])]
        keep = deltas.groupby("subsector")["delta"].apply(lambda s: s.abs().max())
        deltas = deltas[deltas["subsector"].isin(keep[keep > 0.01].index)]
        if deltas.empty:
            return rc.empty_figure(_t("no_change"))
        return rc.delta_bars(deltas, pcolors, height=max(300, 34 * deltas["subsector"].nunique() + 120), lang=state.lang())

    @render.ui
    def emis_note():
        if not runs()[1]:
            return None
        # charts are not mirrored in right-to-left languages, so "left of zero" holds in all of them
        if input.view() == "delta":
            return ui.div(_t("note_delta"), class_="small muted")
        if _breakdown():
            return ui.div(_t("note_breakdown"), class_="small muted")
        return ui.div(_t("note_default"), class_="small muted")

    # ------------------------------------------------------------------ drivers

    @reactive.calc
    def driver_area() -> Optional[dict]:
        """The focused subsector's area; None with "all subsectors"."""
        return results_groups_service.area_for_subsector(groups, input.focus_bar())

    @reactive.calc
    def cards() -> List[dict]:
        cat = catalog()
        area = driver_area()
        context = [dict(c, _context=True) for c in groups.get("context", [])] if input.show_context() else []
        primary, others = results_groups_service.split_cards_for_subsector(area["cards"] if area else [], input.focus_bar())
        out = context + primary + [dict(c, _dim=True) for c in others]
        if cat is not None:
            for v in state.results_custom_vars.get():
                out.append(results_groups_service.custom_card(v, cat))
        return out[:N_SLOTS]

    def _card_frames(card) -> Dict[int, pd.DataFrame]:
        cat = catalog()
        _, rows = runs()
        return {sid: results_groups_service.card_frame(card, cat, rr) for sid, _, rr in rows}

    def _summary(card, frames: Dict[int, pd.DataFrame]) -> Optional[str]:
        if card["view"] == "share":
            return None
        tot = {sid: f[f["year"] == 2050]["value"].sum() for sid, f in frames.items() if not f.empty}
        if not tot:
            return None
        bits = []
        bau = tot.get(_BAU)
        for sid, v in tot.items():
            name = results_bar.pathway_name(state, sid)
            delta = f" ({(v / bau - 1) * 100:+.0f}%)" if bau and sid != _BAU else ""
            bits.append(f"{name}: {rc.fmt(v)}{delta}")
        return "2050 · " + " · ".join(bits)

    @render.ui
    def drivers_context():
        """2050 emissions of what the drivers explain, per pathway; with no
        subsector picked, shortcuts to the subsectors that change most."""
        bid, rows = runs()
        if not rows:
            return None
        focus = input.focus_bar()
        colors = results_bar.colors_for(state, bid)
        bau_name = results_bar.pathway_name(state, _BAU)
        # same totals as the chart above: subsector frames for the selected gas
        def total_frame(d):
            d = d[d["subsector_abv"].map(_shown) & (d["year"] == 2050)]
            return float(d["value"].sum())

        gas = input.gas()
        lang = state.lang()
        if focus:
            scope = _subsector(focus, lang)
        else:
            scope = _t("net_emissions") if input.sector() == "all" else _sectors(lang)[input.sector()]
        scope += "" if gas == "all" else f" · {_gases(lang)[gas]}"
        vals = {sid: total_frame(subsector_frames()[name]) for sid, name, _ in rows}
        bau_f = _bau_frame()
        bau_v = total_frame(bau_f) if bau_f is not None else None
        chips = []
        for sid, name, _ in rows:
            v = vals[sid]
            pct = f" ({(v / bau_v - 1) * 100:+.0f}%)" if bau_v and sid != _BAU else ""
            chips.append(
                ui.span(ui.span(class_="swatch", style=f"background:{colors.get(sid)}"), f"{name} {i18n.isolate(f'{rc.fmt(v)} Mt{pct}', lang)}", class_="drv-val")
            )
        line = ui.div(ui.span(_t("scope_in_2050", scope=scope), class_="muted"), *chips, class_="drv-vals small")
        if focus:
            return line
        bau_f = _bau_frame()
        shortcuts = None
        if bau_f is not None:
            frames = {name: subsector_frames()[name] for sid, name, _ in rows if sid != _BAU}
            allowed = [a for a in _EMITTING if _sector_ok(a)]
            top = emissions_service.largest_changes(frames, bau_f, subsectors=allowed)
            if top:
                btns = []
                for abv, delta in top:
                    payload = json.dumps({"type": "focus", "value": abv})
                    btns.append(
                        ui.tags.button(
                            f"{_subsector(abv, lang)} {i18n.isolate(f'{delta:+.1f} Mt', lang)}",
                            class_="chip-btn",
                            onclick=f"Shiny.setInputValue({json.dumps(ev_id)}, {payload}, {{priority: 'event'}}); return false;",
                        )
                    )
                shortcuts = ui.div(ui.span(_t("biggest_changes"), class_="muted"), *btns, class_="drv-vals small")
        return ui.TagList(line, shortcuts)

    @render.ui
    def drivers_grid():
        bid, rows = runs()
        if not rows:
            return ui.div(_t("no_drivers"), class_="info-box")
        lang = state.lang()
        hint = None
        if driver_area() is None:
            hint = ui.div(_t("pick_hint"), class_="info-box")
        tiles = []
        divided = False
        for i, card in enumerate(cards()):
            if card.get("_dim") and not divided:
                divided = True
                # named with the same subsector labels as the pickers, not the area title
                related = [_subsector(a, lang) for a in driver_area()["subsectors"] if a != input.focus_bar() and a in _EMITTING]
                tiles.append(
                    ui.div(_t("related", names=i18n.t("results.list_sep", lang).join(related)), class_="drv-divider section-label")
                )
            frames = _card_frames(card)
            empty = all(f.empty for f in frames.values())
            remove = None
            if card.get("custom"):
                payload = json.dumps({"type": "remove_card", "value": card["variables"][0]})
                remove = ui.tags.button(
                    "×", class_="x-btn", title=_t("remove_card"),
                    onclick=f"Shiny.setInputValue({json.dumps(ev_id)}, {payload}, {{priority: 'event'}}); return false;",
                )
            wide = card["view"] != "total" and len(rows) > 1
            tiles.append(
                ui.div(
                    ui.div(
                        ui.div(
                            ui.span(_card_text(card, "title"), class_="drv-title"),
                            info_tip(_card_text(card, "why"), class_="drv-why"),
                            ui.span(_t("var_input"), class_="kind-tag") if card["source"] == "input" else None,
                        ),
                        ui.div(ui.span(_card_text(card, "unit"), class_="small muted"), remove, class_="btn-row"),
                        class_="drv-head",
                    ),
                    ui.div(
                        _t("needs_elec") if card.get("needs_electricity_model") else _t("no_data"),
                        class_="info-box small",
                    )
                    if empty
                    else output_widget(f"slot_{i}"),
                    ui.div(_summary(card, frames) or "", class_="small muted mono drv-sum"),
                    class_="drv-card" + (" wide" if wide else "") + (" ctx" if card.get("_context") else "")
                    + (" dim" if card.get("_dim") else ""),
                )
            )
        return ui.TagList(hint, ui.div(*tiles, class_="drv-grid") if tiles else None)

    def _slot_figure(i: int):
        cs = cards()
        if i >= len(cs):
            return rc.empty_figure("")
        card = cs[i]
        bid, rows = runs()
        frames = _card_frames(card)
        names = {sid: results_bar.pathway_name(state, sid) for sid, _, _ in rows}
        colors = results_bar.colors_for(state, bid)
        unit = _card_text(card, "unit")
        if card["view"] == "total" or len(rows) == 0:
            series = {names[sid]: f.groupby("year")["value"].sum() for sid, f in frames.items() if not f.empty}
            return rc.lines_by_pathway(series, {names[s]: colors.get(s) for s in names}, unit, height=200 if card.get("_context") else 230,
                                       dashed=[names.get(_BAU, "")])
        named = {names[sid]: f for sid, f in frames.items() if not f.empty}
        named, order = rc.lumped(named, n=8)
        return rc.stacked_panels(
            named, rc.series_colors(order), order, unit, share=card["view"] == "share", height=270, legend_right=True,
            lang=state.lang(),
        )

    def _make_slot(i: int):
        def fig():
            return _slot_figure(i)

        fig.__name__ = f"slot_{i}"
        output(id=f"slot_{i}")(render_plotly(rc.bidi_for(state.lang)(fig)))

    for _i in range(N_SLOTS):
        _make_slot(_i)

    # ------------------------------------------------------------------ download

    @render.download(filename=lambda: "emissions_and_drivers.xlsx")
    def download_xlsx():
        bid, rows = runs()
        baselines = state.baselines.get()
        label = baselines[bid].label if bid in baselines else (bid or "")
        all_cards = groups.get("context", []) + [c for a in groups["areas"] for c in a["cards"]]
        cat = catalog()
        all_cards += [results_groups_service.custom_card(v, cat) for v in state.results_custom_vars.get()]
        yield download_service.emissions_workbook([(name, rr) for _, name, rr in rows], label, all_cards, cat)

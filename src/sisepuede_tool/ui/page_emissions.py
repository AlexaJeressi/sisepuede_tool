"""Emissions & drivers page (results).

Top to bottom:
- shared results bar (baseline, pathway chips, run stamp, Excel download);
- headline KPIs per pathway (net 2030 / 2050, % vs BAU, avoided emissions);
- "Net GHG emissions": small multiples per pathway stacked by subsector, or
  the change vs BAU by subsector in 2030 and 2050. Focusing a subsector shows
  its detail (e.g. Transportation -> Road / Rail / Aviation) and a gas filter;
- "What drives it": curated driver cards for the matching area
  (resources/results_groups.yaml), plus population and GDP. In advanced mode
  users can add a card for any model variable.

No data tables: everything on the page (and the full emissions detail) is in
the Excel download (services/download_service.py).
"""

import json
from typing import Dict, List, Optional

import pandas as pd
from shiny import module, reactive, render, ui
from shiny.module import resolve_id
from shinywidgets import output_widget, render_plotly

from sisepuede_tool.services import download_service, emissions_service, output_service, results_groups_service
from sisepuede_tool.ui.components import result_charts as rc
from sisepuede_tool.ui.components import results_bar
from sisepuede_tool.ui.components.info_tip import info_tip
from sisepuede_tool.ui.state import AppState

N_SLOTS = 16  # driver card chart slots (context + area + custom cards)
_SECTORS = {"all": "All", "Energy": "Energy", "IPPU": "IPPU", "AFOLU": "AFOLU", "Circular Economy": "Circular economy"}
_GASES = {"all": "All gases", "CO2": "CO₂", "CH4": "CH₄", "N2O": "N₂O", "F-gases": "F-gases"}
_BAU = results_bar.BAU

_field_catalog_cache: Dict[int, pd.DataFrame] = {}


def field_catalog(model_attributes) -> pd.DataFrame:
    key = id(model_attributes)
    if key not in _field_catalog_cache:
        _field_catalog_cache[key] = output_service.build_field_catalog(model_attributes)
    return _field_catalog_cache[key]


def _emitting_subsectors() -> Dict[str, str]:
    order = ["entc", "trns", "inen", "scoe", "fgtv", "ccsq", "ippu", "agrc", "lvst", "lsmm", "soil", "lndu", "frst", "waso", "trww"]
    return {abv: emissions_service.subsector_label(abv) for abv in order}


@module.ui
def page_emissions_ui():
    groups = results_groups_service.load_groups()
    return ui.div(
        results_bar.bar_ui("download_xlsx"),
        ui.output_ui("kpis"),
        ui.div(
            ui.div(
                ui.span("Net GHG emissions", class_="section-label"),
                ui.span("MtCO₂e · dotted line = 2030", class_="small muted"),
                class_="box-head",
            ),
            ui.div(
                ui.div(
                    ui.input_radio_buttons("view", None, {"emissions": "By subsector", "delta": "Change vs BAU"}, inline=True),
                    class_="seg",
                ),
                ui.div(ui.input_radio_buttons("sector", None, _SECTORS, inline=True), class_="seg"),
                ui.input_select("focus", None, {"": "All subsectors", **_emitting_subsectors()}, width="240px"),
                ui.panel_conditional(
                    "input.focus !== ''",
                    ui.div(ui.input_radio_buttons("gas", None, _GASES, inline=True), class_="seg"),
                ),
                class_="res-controls",
            ),
            output_widget("emis_chart"),
            ui.output_ui("emis_note"),
            class_="box",
        ),
        ui.div(
            ui.div(
                ui.span("What drives it", class_="section-label"),
                ui.input_select(
                    "area", None, {a["key"]: a["title"] for a in groups["areas"]}, width="240px"
                ),
                class_="box-head",
            ),
            ui.div(
                "Key model variables for this area, one line or panel per pathway. "
                "Pick a subsector above to switch area. Click ⓘ to see why each one matters.",
                class_="small muted",
            ),
            ui.output_ui("drivers_grid"),
            ui.div(
                ui.div(ui.span("Add a variable", class_="section-label"), ui.span("ADVANCED", class_="adv-tag")),
                ui.div(
                    ui.input_selectize(
                        "add_var", None, choices=[], multiple=True,
                        options={"placeholder": "Search model variables (pick one or more)…"}, width="560px",
                    ),
                    ui.input_action_button("add_var_btn", "Add cards", class_="btn-inline"),
                    class_="btn-row",
                ),
                ui.div("Inputs are the drivers fed to the model; outputs are model results.", class_="small muted"),
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
        _, rows = runs()
        return {name: emissions_service.by_subsector(rr.df_output) for _, name, rr in rows}

    def _bau_frame() -> Optional[pd.DataFrame]:
        rr = bau_run()
        return emissions_service.by_subsector(rr.df_output) if rr is not None else None

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

    @reactive.effect
    @reactive.event(input.focus)
    def _focus_to_area():
        area = results_groups_service.area_for_subsector(groups, input.focus())
        if area is not None:
            ui.update_select("area", selected=area["key"])

    @reactive.effect
    def _add_var_choices():
        cat = catalog()
        if cat is None:
            return
        rows = cat.drop_duplicates("variable")
        rows = rows[~rows["variable"].str.contains("NemoMod :math:|emission_co2e", regex=True)]
        choices: Dict[str, Dict[str, str]] = {}
        for r in rows.sort_values(["sector", "subsector", "variable"]).itertuples():
            group = f"{r.sector or 'Other'} · {r.subsector}"
            name = r.label.split(" · ")[0]
            choices.setdefault(group, {})[r.variable] = f"{name} ({'input' if r.is_input else 'output'})"
        ui.update_selectize("add_var", choices=choices, selected=None)

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
                        ui.div("Avoided 2025–2050", class_="k"),
                        ui.div("reference" if sid == _BAU else f"{rc.fmt(k['avoided_cum'])} Mt", class_="v"),
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
    def emis_chart():
        bid, rows = runs()
        if not rows:
            return rc.empty_figure("Run business as usual and at least one pathway to see results.")
        focus = input.focus()
        gas = input.gas() if focus else "all"
        if input.view() == "delta":
            return _delta_figure(rows, focus, gas)
        frames, net = {}, {}
        if not focus:
            labels = {abv: emissions_service.subsector_label(abv) for abv in _emitting_subsectors()}
            colors = {labels[a]: rc.SUBSECTOR_COLORS.get(a, rc.OTHER_COLOR) for a in labels}
            order = [labels[a] for a in labels]
            for _, name, rr in rows:
                d = subsector_frames()[name]
                d = d[d["subsector_abv"].map(_sector_ok)]
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
                pct = f" · {((v / float(bau_net[2050])) - 1) * 100:+.0f}% vs BAU"
            titles[name] = f"{name} · {rc.fmt(v)} Mt in 2050{pct}"
        frames = {titles[k]: v for k, v in frames.items()}
        net = {titles[k]: v for k, v in net.items()}
        return rc.stacked_panels(frames, colors, order, "MtCO₂e", net=net, height=380)

    def _delta_figure(rows, focus, gas):
        bau = bau_run()
        if bau is None:
            return rc.empty_figure("Business as usual has not run for this baseline: run it to compare.")
        def table(df_output):
            if not focus:
                d = emissions_service.by_subsector(df_output)
                d = d[d["subsector_abv"].map(_sector_ok)]
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
            return rc.empty_figure("Select at least one pathway besides business as usual.")
        deltas = pd.concat(parts)
        deltas = deltas[deltas["year"].isin([2030, 2050])]
        keep = deltas.groupby("subsector")["delta"].apply(lambda s: s.abs().max())
        deltas = deltas[deltas["subsector"].isin(keep[keep > 0.01].index)]
        if deltas.empty:
            return rc.empty_figure("No change vs business as usual here.")
        return rc.delta_bars(deltas, pcolors, height=max(300, 34 * deltas["subsector"].nunique() + 120))

    @render.ui
    def emis_note():
        if not runs()[1]:
            return None
        if input.view() == "delta":
            return ui.div("Bars left of zero are reductions compared with business as usual.", class_="small muted")
        if input.focus():
            return ui.div(
                "Detail groups follow the IPCC-style breakdown used for Egypt's inventory. "
                "Negative areas are removals.",
                class_="small muted",
            )
        return ui.div(
            "Areas below zero are removals (forests, land use). The dark line is net emissions. "
            "Click a legend item to hide it; pick a subsector to see its detail.",
            class_="small muted",
        )

    # ------------------------------------------------------------------ drivers

    @reactive.calc
    def cards() -> List[dict]:
        cat = catalog()
        area = next((a for a in groups["areas"] if a["key"] == input.area()), groups["areas"][0])
        out = [dict(c, _context=True) for c in groups.get("context", [])] + list(area["cards"])
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
    def drivers_grid():
        bid, rows = runs()
        if not rows:
            return ui.div("Run a pathway to see its drivers.", class_="info-box")
        tiles = []
        for i, card in enumerate(cards()):
            frames = _card_frames(card)
            empty = all(f.empty for f in frames.values())
            remove = None
            if card.get("custom"):
                payload = json.dumps({"type": "remove_card", "value": card["variables"][0]})
                remove = ui.tags.button(
                    "×", class_="x-btn", title="Remove card",
                    onclick=f"Shiny.setInputValue({json.dumps(ev_id)}, {payload}, {{priority: 'event'}}); return false;",
                )
            wide = card["view"] != "total" and len(rows) > 1
            tiles.append(
                ui.div(
                    ui.div(
                        ui.div(
                            ui.span(card["title"], class_="drv-title"),
                            info_tip(card.get("why", ""), class_="drv-why"),
                            ui.span("input" if card["source"] == "input" else "", class_="kind-tag") if card["source"] == "input" else None,
                        ),
                        ui.div(ui.span(card["unit"], class_="small muted"), remove, class_="btn-row"),
                        class_="drv-head",
                    ),
                    ui.div(
                        "Needs the electricity model: tick “Run electricity dispatch (NemoMod)” on the Run page."
                        if card.get("needs_electricity_model")
                        else "No data for this variable in these runs.",
                        class_="info-box small",
                    )
                    if empty
                    else output_widget(f"slot_{i}"),
                    ui.div(_summary(card, frames) or "", class_="small muted mono drv-sum"),
                    class_="drv-card" + (" wide" if wide else "") + (" ctx" if card.get("_context") else ""),
                )
            )
        return ui.div(*tiles, class_="drv-grid")

    def _slot_figure(i: int):
        cs = cards()
        if i >= len(cs):
            return rc.empty_figure("")
        card = cs[i]
        bid, rows = runs()
        frames = _card_frames(card)
        names = {sid: results_bar.pathway_name(state, sid) for sid, _, _ in rows}
        colors = results_bar.colors_for(state, bid)
        if card["view"] == "total" or len(rows) == 0:
            series = {names[sid]: f.groupby("year")["value"].sum() for sid, f in frames.items() if not f.empty}
            return rc.lines_by_pathway(series, {names[s]: colors.get(s) for s in names}, card["unit"], height=200 if card.get("_context") else 230,
                                       dashed=[names.get(_BAU, "")])
        named = {names[sid]: f for sid, f in frames.items() if not f.empty}
        named, order = rc.lumped(named, n=8)
        return rc.stacked_panels(
            named, rc.series_colors(order), order, card["unit"], share=card["view"] == "share", height=270, legend_right=True
        )

    def _make_slot(i: int):
        def fig():
            return _slot_figure(i)

        fig.__name__ = f"slot_{i}"
        output(id=f"slot_{i}")(render_plotly(fig))

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

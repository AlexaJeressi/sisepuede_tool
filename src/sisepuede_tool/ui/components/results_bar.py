"""Shared bar on top of the results pages: baseline picker, pathway chips, run
stamp, and the page's download buttons: its Excel and the Tableau zip
(services/tableau_export_service.py, the same for every results page).

The selection lives in `state.results_baseline_id` / `state.results_pathways`
so it carries from one results page to the other. Each page module calls
`bar_ui()` in its UI and `bar_server()` in its server; the chips send their
clicks through the page's `ui_event` input.
"""

import json
import logging
from typing import Dict, List, Optional, Tuple

from shiny import reactive, render, ui

from sisepuede_tool.services import cost_benefit_service, i18n, pathway_service
from sisepuede_tool.services import tableau_export_service as tes
from sisepuede_tool.ui.components import result_charts

logger = logging.getLogger(__name__)

BAU = pathway_service.BAU_STRATEGY_ID
TABLEAU_DOWNLOAD_ID = "download_tableau"


def bar_ui(download_id: str, download_label: Optional[str] = None):
    return ui.div(
        ui.output_ui("results_bar", class_="res-bar-left"),
        ui.download_button(download_id, download_label or i18n.t("results.download"), class_="btn-inline btn-ghost"),
        ui.download_button(TABLEAU_DOWNLOAD_ID, i18n.t("results.download_tableau"), class_="btn-inline btn-ghost"),
        class_="res-bar",
    )


def runs_by_baseline(state) -> Dict[str, List[int]]:
    """{baseline_id: [strategy ids that ran OK]}, BAU first."""
    out: Dict[str, List[int]] = {}
    pathways = state.strategies_map.get()
    for (sid, bid), r in state.run_results.get().items():
        if r.ok and sid in pathways:
            out.setdefault(bid, []).append(sid)
    return {bid: sorted(set(sids), key=lambda s: (s != BAU, s)) for bid, sids in out.items()}


def current_baseline(state) -> Optional[str]:
    runs = runs_by_baseline(state)
    if not runs:
        return None
    chosen = state.results_baseline_id.get()
    if chosen in runs:
        return chosen
    default = state.default_baseline_id.get()
    return default if default in runs else next(iter(runs))


def visible_pathways(state, baseline_id: Optional[str]) -> List[int]:
    """Pathway ids shown for `baseline_id`: the user's chip selection, else all that ran."""
    if baseline_id is None:
        return []
    ran = runs_by_baseline(state).get(baseline_id, [])
    chosen = state.results_pathways.get()
    if chosen is None:
        return ran
    shown = [s for s in ran if s in chosen]
    return shown or ran


def pathway_name(state, sid: int) -> str:
    if sid == BAU:
        return i18n.t("results.bau", state.lang())
    entry = state.strategies_map.get().get(sid)
    return entry.strategy.name if entry else str(sid)


def colors_for(state, baseline_id: Optional[str]) -> Dict[int, str]:
    return result_charts.pathway_colors(runs_by_baseline(state).get(baseline_id, []) or [BAU])


def run_stamp(state, baseline_id: Optional[str]) -> str:
    hist = [h for h in state.run_history.get() if h.get("baseline_id") == baseline_id]
    if not hist:
        return ""
    last = hist[0]
    batch = [h for h in hist if h.get("batch") == last.get("batch")]
    n_ok = sum(1 for h in batch if h["ok"])
    at = last["at"].strftime("%H:%M") if hasattr(last.get("at"), "strftime") else ""
    lang = state.lang()
    elec = i18n.t("results.with_elec" if last.get("nemomod") else "results.no_elec", lang)
    return f"{i18n.tn('results.run_stamp', n_ok, lang, time=at)} · {elec}"


def bar_server(input, state, ev_id: str):
    """Renders the bar and keeps `state.results_*` in sync. Returns nothing;
    pages read the selection with current_baseline / visible_pathways."""

    @render.ui
    def results_bar():
        runs = runs_by_baseline(state)
        lang = state.lang()
        if not runs:
            return ui.div(
                ui.span(i18n.t("results.no_results", lang), class_="muted"),
                ui.tags.button(
                    i18n.t("results.go_to_run", lang), class_="link-btn", onclick="mrvGoTo('run')", style="margin-inline-start:8px"
                ),
            )
        bid = current_baseline(state)
        baselines = state.baselines.get()
        choices = {b: (baselines[b].label if b in baselines else b) for b in runs}
        shown = visible_pathways(state, bid)
        colors = colors_for(state, bid)
        chips = []
        for sid in runs[bid]:
            on = sid in shown
            payload = json.dumps({"type": "chip", "value": sid})
            chips.append(
                ui.tags.button(
                    ui.span(class_="swatch", style=f"background:{colors.get(sid)};" + ("" if on else "opacity:.35")),
                    pathway_name(state, sid),
                    class_="chip" + (" active" if on else ""),
                    onclick=f"Shiny.setInputValue({json.dumps(ev_id)}, {payload}, {{priority: 'event'}}); return false;",
                    type="button",
                )
            )
        first, last = year_range(state)
        return ui.div(
            ui.span(i18n.t("results.baseline", lang), class_="section-label"),
            ui.input_select("rb_baseline", None, choices=choices, selected=bid, width="220px"),
            ui.span(i18n.t("results.pathways", lang), class_="section-label", style="margin-inline-start:10px"),
            *chips,
            ui.span(run_stamp(state, bid), class_="small muted", style="margin-inline-start:10px"),
            ui.div(
                ui.span(i18n.t("results.years", lang), class_="section-label"),
                ui.input_slider(
                    "rb_years", None, result_charts.YEAR_MIN, result_charts.YEAR_MAX, (first, last),
                    step=1, sep="", ticks=False, width="230px",
                ),
                class_="res-years",
            ),
            class_="res-bar-row",
        )

    @reactive.effect
    @reactive.event(input.rb_years)
    def _on_years():
        value = input.rb_years()
        if not value:
            return
        rng = (int(value[0]), int(value[1]))
        full = rng == (result_charts.YEAR_MIN, result_charts.YEAR_MAX)
        new = None if full else rng
        if new != state.results_years.get():
            state.results_years.set(new)

    @reactive.effect
    @reactive.event(input.rb_baseline)
    def _on_baseline():
        value = input.rb_baseline()
        if value and value != state.results_baseline_id.get():
            state.results_baseline_id.set(value)


def year_range(state) -> Tuple[int, int]:
    """(first, last) year shown on the results charts."""
    return state.results_years.get() or (result_charts.YEAR_MIN, result_charts.YEAR_MAX)


def toggle_pathway(state, sid: int):
    bid = current_baseline(state)
    ran = runs_by_baseline(state).get(bid, [])
    shown = set(visible_pathways(state, bid))
    if sid in shown:
        if len(shown) > 1:
            shown.discard(sid)
    else:
        shown.add(sid)
    state.results_pathways.set(frozenset(shown) if shown != set(ran) else None)


def runs_for_page(state) -> Tuple[Optional[str], List[Tuple[int, str, object]]]:
    """(baseline id, [(sid, pathway name, RunResult)]) for the visible pathways."""
    bid = current_baseline(state)
    results = state.run_results.get()
    out = [(sid, pathway_name(state, sid), results.get((sid, bid))) for sid in visible_pathways(state, bid)]
    return bid, out


def tableau_zip(state) -> bytes:
    """The Tableau CSVs for the chosen baseline and every pathway that ran on
    it (Tableau filters pathways itself). A table that cannot be built is left
    out of the zip and logged; cb_data is there only if costs & benefits ran."""
    bid = current_baseline(state)
    if bid is None:
        return tes.tableau_zip({})
    pathways = state.strategies_map.get()
    sids = runs_by_baseline(state).get(bid, [])
    model_attributes = state.model_attributes.get()
    df_wide = cost_benefit_service.build_wide_results(state.run_results.get(), bid, sids, model_attributes)
    attr_strat = tes.strategy_table(pathways, sids)
    builders = {
        "emissions_egypt.csv": lambda: tes.emissions_table(df_wide, attr_strat),
        "drivers_egypt.csv": lambda: tes.drivers_table(df_wide, attr_strat),
        "cb_data.csv": lambda: tes.recode_cb(state.cb_tableau.get()[bid], attr_strat) if bid in state.cb_tableau.get() else None,
        "tableau_levers_table_complete.csv": lambda: tes.levers_table(
            sids, pathways, state.transformations_obj.get(), model_attributes
        ),
    }
    tables = {}
    for name, build in builders.items():
        try:
            tables[name] = build()
        except Exception:
            logger.exception("tableau download: %s failed", name)
    return tes.tableau_zip(tables)

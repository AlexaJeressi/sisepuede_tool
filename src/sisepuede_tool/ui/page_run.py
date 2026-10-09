"""Run page: pick baseline x pathway cells, then run.

Business as usual (strategy 0) runs automatically for every baseline that
has any pathway selected: it's the reference for Costs & Benefits. It can
also be run on its own (its column is a normal checkbox).

`state.models` is already built (Julia connected) by the time this page is
used -- see ui/app_shell.py. The only per-run toggle in basic mode is the
NemoMod electricity run; sector selection and the C&B reference strategy are
advanced options (the sector selection also lets users work around upstream
model bugs by excluding a sector).

Runs are synchronous with a progress bar. Every result is appended to
`state.run_history`, and failures are also written to the server log.
"""

import datetime
import json
import logging
import statistics

from shiny import module, reactive, render, ui
from shiny.module import resolve_id

from sisepuede_tool.services import cost_benefit_service, pathway_service, run_service
from sisepuede_tool.services import transformer_metadata_service as tms
from sisepuede_tool.ui.components.info_tip import info_tip
from sisepuede_tool.ui.state import AppState

logger = logging.getLogger(__name__)

_SECTOR_CHOICES = ["AFOLU", "Circular Economy", "Energy", "IPPU", "Socioeconomic"]
_BAU = pathway_service.BAU_STRATEGY_ID
# rough per-scenario durations used until this session has its own timings
_ETA_DEFAULT_S = {True: 150.0, False: 15.0}


@module.ui
def page_run_ui():
    return ui.div(
        ui.div(
            ui.div(
                ui.div(ui.span("What to run · click cells", class_="section-label"), class_="box-head"),
                ui.output_ui("matrix"),
                ui.div(
                    "Business as usual runs automatically for every baseline you pick. "
                    "It is the reference for costs and benefits.",
                    class_="small muted",
                ),
                ui.div(
                    ui.input_switch("run_energy_production", "Run electricity dispatch (NemoMod)", value=False),
                    ui.div(
                        "More accurate energy results, needed for renewable, hydrogen and grid transformations. "
                        "Adds about 2 min per scenario.",
                        class_="small muted",
                    ),
                    ui.output_ui("dispatch_advice"),
                ),
                ui.div(
                    ui.div(ui.span("Sectors to run", class_="section-label"), ui.span("ADVANCED", class_="adv-tag")),
                    ui.input_checkbox_group(
                        "sectors_run", None, choices=_SECTOR_CHOICES, selected=_SECTOR_CHOICES, inline=True
                    ),
                    ui.tags.small(
                        "Uncheck a sector to skip it, e.g. to work around a model error in that sector.",
                        class_="muted d-block",
                    ),
                    ui.input_select("cb_base_strategy", "Costs & benefits reference", choices={}),
                    class_="adv-only adv-box",
                ),
                ui.input_action_button("run_btn", "▶ Run", class_="btn-primary"),
                ui.output_ui("run_estimate"),
                class_="box",
            ),
            ui.div(
                ui.div(ui.span("Run history", class_="section-label"), ui.output_ui("history_meta", inline=True), class_="box-head"),
                ui.output_ui("history"),
                class_="box",
            ),
            class_="run-grid",
        ),
    )


@module.server
def page_run_server(input, output, session, state: AppState):
    history_event_id = resolve_id("history_event")
    batch_counter = reactive.Value(0)

    @reactive.calc
    def axes():
        """(baseline ids, strategy ids) shown in the matrix; BAU first."""
        baselines = state.baselines.get()
        pathways = state.strategies_map.get()
        sids = ([_BAU] if _BAU in pathways else []) + pathway_service.pathway_ids(pathways)
        return list(baselines.keys()), sids

    def _cell_id(i: int, j: int) -> str:
        return f"cell_{i}_{j}"

    @render.ui
    def matrix():
        bids, sids = axes()
        baselines = state.baselines.get()
        pathways = state.strategies_map.get()
        if not bids:
            return ui.div(
                "Load a baseline first.",
                ui.tags.button("Go to Baseline data →", class_="link-btn d-block mt-1", onclick="mrvGoTo('data_input')"),
                class_="info-box",
            )
        if len(sids) <= 1:
            note = ui.div(
                "No pathways yet: only business as usual can run. ",
                ui.tags.button("Build a pathway →", class_="link-btn", onclick="mrvGoTo('pathways')"),
                class_="info-box",
            )
        else:
            note = None
        head = [ui.tags.th("Baseline")] + [
            ui.tags.th("Business as usual" if sid == _BAU else pathways[sid].strategy.name) for sid in sids
        ]
        rows = []
        for i, bid in enumerate(bids):
            cells = [ui.tags.td(ui.span(baselines[bid].label, class_="mono"))]
            for j, sid in enumerate(sids):
                cells.append(
                    ui.tags.td(ui.input_checkbox(_cell_id(i, j), None, value=True), class_="bau" if sid == _BAU else None)
                )
            rows.append(ui.tags.tr(*cells))
        return ui.TagList(note, ui.tags.table(ui.tags.thead(ui.tags.tr(*head)), ui.tags.tbody(*rows), class_="matrix"))

    def selected_combinations():
        """[(strategy_id, baseline_id)], BAU added for every baseline used."""
        bids, sids = axes()
        combos = []
        for i, bid in enumerate(bids):
            picked = []
            for j, sid in enumerate(sids):
                cid = _cell_id(i, j)
                if cid in input and input[cid]():
                    picked.append(sid)
            if picked and _BAU in state.strategies_map.get() and _BAU not in picked:
                picked.insert(0, _BAU)
            combos += [(sid, bid) for sid in picked]
        return combos

    def _eta_seconds(n: int, nemomod: bool) -> float:
        past = [h["seconds"] for h in state.run_history.get() if h["ok"] and h.get("nemomod") == nemomod]
        per = statistics.median(past) if past else _ETA_DEFAULT_S[nemomod]
        return n * per

    @render.ui
    def run_estimate():
        combos = selected_combinations()
        if not combos:
            return ui.div("Select at least one cell.", class_="small muted")
        eta = _eta_seconds(len(combos), bool(input.run_energy_production()))
        eta_txt = f"about {eta / 60:.0f} min" if eta >= 90 else f"about {max(eta, 1):.0f} s"
        n_bau = sum(1 for sid, _ in combos if sid == _BAU)
        return ui.div(
            f"{len(combos)} scenario{'s' if len(combos) != 1 else ''} ({n_bau} business as usual) · {eta_txt}",
            class_="small muted",
        )

    @render.ui
    def dispatch_advice():
        """Which selected transformations need the electricity dispatch (attribute table flags)."""
        tx = state.transformations_obj.get()
        state.transformations_revision.get()
        if tx is None:
            return None
        pathways = state.strategies_map.get()
        sids = {sid for sid, _ in selected_combinations() if sid != _BAU and sid in pathways}
        if not sids:
            return None
        meta, tk = state.transformer_metadata.get(), state.transformers_catalog.get()
        cards = {}

        def card(code):
            if code not in cards:
                cards[code] = tms.get_card(code, meta, tk=tk)
            return cards[code]

        needs = pathway_service.electricity_needs([pathways[s] for s in sorted(sids)], tx, lambda c: card(c)["electricity_need"])
        n, m = len(needs["needed"]), len(needs["optional"])
        on = bool(input.run_energy_production())
        # a short explanation in the ⓘ bubble; each transformer's own note is on the Pathways page
        tip = []
        if n:
            tip.append(
                "Their main effect happens in power generation and fuel production, which are only calculated "
                "when the electricity dispatch runs."
            )
        if m:
            tip.append(f"{m} other selected transformer{'s' if m != 1 else ''} also get indirect energy effects from it (optional).")
        tip.append("Each transformer on the Pathways page says whether it needs it.")
        more = info_tip(" ".join(tip), class_="tip-right")
        if not n:
            return ui.div("None of the selected transformations needs the electricity dispatch. ", more, class_="small muted mt-1")
        plural = "s" if n != 1 else ""
        if on:
            return ui.div(f"✓ Covers the {n} selected transformer{plural} that need it. ", more, class_="ok-box small mt-1")
        return ui.div(
            ui.tags.b(f"{n} selected transformer{plural} need{'s' if n == 1 else ''} the electricity dispatch. "),
            "Without it their effect will be missing or partial. ",
            more,
            class_="warn-box small mt-1",
        )

    @reactive.effect
    def _sync_cb_base_strategy_choices():
        pathways = state.strategies_map.get()
        choices = {str(sid): ("Business as usual" if sid == _BAU else entry.strategy.name) for sid, entry in pathways.items()}
        current = input.cb_base_strategy() if "cb_base_strategy" in input else None
        selected = current if current in choices else (str(_BAU) if str(_BAU) in choices else next(iter(choices), None))
        ui.update_select("cb_base_strategy", choices=choices, selected=selected)

    def _cb_base_id():
        raw = input.cb_base_strategy() if "cb_base_strategy" in input else None
        return int(raw) if raw else _BAU

    def _run_cost_benefit(baseline_ids, cb_base_strategy_id, run_results):
        cb_wrapper = state.cb_wrapper.get()
        strategies_map = state.strategies_map.get()
        if cb_wrapper is None or cb_base_strategy_id not in strategies_map:
            return
        code_strat_base = strategies_map[cb_base_strategy_id].strategy.code
        model_attributes = state.model_attributes.get()

        cb_results = dict(state.cb_results.get())
        for baseline_id in baseline_ids:
            base_result = run_results.get((cb_base_strategy_id, baseline_id))
            if base_result is None or not base_result.ok:
                msg = f"Costs & benefits skipped for baseline '{baseline_id}': the reference ('{code_strat_base}') did not run successfully."
                logger.warning(msg)
                ui.notification_show(msg, type="warning")
                continue
            strategy_ids = sorted(
                sid for (sid, bid), r in run_results.items() if bid == baseline_id and r.ok and sid in strategies_map
            )
            try:
                df_wide = cost_benefit_service.build_wide_results(run_results, baseline_id, strategy_ids, model_attributes)
                df_cb, df_attr_variable = cost_benefit_service.calculate_cost_benefit(
                    cb_wrapper, df_wide, strategies_map, code_strat_base
                )
            except Exception as e:
                logger.exception("costs & benefits failed for baseline %s", baseline_id)
                ui.notification_show(f"Costs & benefits failed for baseline '{baseline_id}': {e}", type="warning")
                continue
            cb_results[baseline_id] = (df_cb, df_attr_variable)
        state.cb_results.set(cb_results)

    def _execute(combinations):
        models = state.models.get()
        baselines = state.baselines.get()
        strategies_map = state.strategies_map.get()
        if models is None:
            ui.notification_show("Model backend not ready yet.", type="error")
            return
        sectors = list(input.sectors_run())
        nemomod = bool(input.run_energy_production())
        cb_base = _cb_base_id()
        if cb_base in strategies_map:
            for bid in {bid for _, bid in combinations}:
                if (cb_base, bid) not in combinations:
                    combinations = [(cb_base, bid)] + combinations

        batch = batch_counter.get() + 1
        batch_counter.set(batch)
        run_results = dict(state.run_results.get())
        new_history = []
        with ui.Progress(min=0, max=len(combinations)) as p:
            for i, (strategy_id, baseline_id) in enumerate(combinations):
                baseline = baselines[baseline_id]
                entry = strategies_map[strategy_id]
                name = "Business as usual" if strategy_id == _BAU else entry.strategy.name
                p.set(i, message=f"Running {name} × {baseline.label}", detail=f"{i + 1} of {len(combinations)}")
                result = run_service.run_combination(
                    models,
                    entry.strategy,
                    baseline.df,
                    baseline.region,
                    nemomod,
                    strategy_id,
                    baseline_id,
                    models_run=sectors,
                )
                if not result.ok:
                    logger.warning("run failed: strategy %s x baseline %s: %s", strategy_id, baseline.label, result.error)
                run_results[(strategy_id, baseline_id)] = result
                new_history.append(
                    {
                        "batch": batch,
                        "strategy_id": strategy_id,
                        "strategy_name": name,
                        "baseline_id": baseline_id,
                        "baseline_label": baseline.label,
                        "ok": result.ok,
                        "seconds": result.elapsed_seconds,
                        "at": datetime.datetime.now(),
                        "error": result.error,
                        "nemomod": nemomod,
                    }
                )
            p.set(len(combinations), message="Done.")

        state.run_results.set(run_results)
        state.run_history.set(list(reversed(new_history)) + state.run_history.get())
        n_ok = sum(1 for h in new_history if h["ok"])
        msg = f"Ran {len(new_history)} scenario(s): {n_ok} succeeded, {len(new_history) - n_ok} failed."
        logger.info(msg)
        ui.notification_show(msg, type="message" if n_ok == len(new_history) else "warning")
        _run_cost_benefit(sorted({bid for _, bid in combinations}), cb_base, run_results)

    @reactive.effect
    @reactive.event(input.run_btn)
    def _on_run():
        combos = selected_combinations()
        if not combos:
            ui.notification_show("Select at least one baseline × pathway cell.", type="error")
            return
        _execute(combos)

    @reactive.effect
    @reactive.event(input.history_event)
    def _on_history_event():
        ev = input.history_event() or {}
        if ev.get("type") == "retry":
            sid, bid = int(ev["strategy_id"]), ev["baseline_id"]
            if sid in state.strategies_map.get() and bid in state.baselines.get():
                _execute([(sid, bid)])
            else:
                ui.notification_show("That pathway or baseline no longer exists.", type="error")

    @render.ui
    def history_meta():
        history = state.run_history.get()
        if not history:
            return None
        return ui.span(f"{len(history)} run{'s' if len(history) != 1 else ''} this session", class_="small muted")

    @render.ui
    def history():
        history = state.run_history.get()
        if not history:
            return ui.div("No runs yet in this session.", class_="small muted")
        rows = []
        for h in history:
            status = ui.span("✓ done", class_="pill pill-ok") if h["ok"] else ui.span("✕ failed", class_="pill pill-err")
            if h["ok"]:
                action = ui.tags.button("View results", class_="link-btn", onclick="mrvGoTo('output_explorer')")
            else:
                payload = json.dumps({"type": "retry", "strategy_id": h["strategy_id"], "baseline_id": h["baseline_id"]})
                action = ui.tags.button(
                    "Retry",
                    class_="link-btn",
                    onclick=f"Shiny.setInputValue({json.dumps(history_event_id)}, {payload}, {{priority: 'event'}});",
                )
            scenario = ui.div(
                ui.div(h["strategy_name"], style="font-weight:500"),
                ui.div(h["baseline_label"] + (" · NemoMod" if h.get("nemomod") else ""), class_="code"),
                ui.div((h["error"] or "")[:400], class_="err") if not h["ok"] else None,
            )
            rows.append(
                ui.tags.tr(
                    ui.tags.td(scenario),
                    ui.tags.td(status),
                    ui.tags.td(f"{h['seconds']:.0f} s", class_="mono"),
                    ui.tags.td(f"{h['at']:%H:%M}", class_="mono"),
                    ui.tags.td(action),
                )
            )
        head = ui.tags.tr(*[ui.tags.th(t) for t in ("Scenario", "Status", "Time", "At", "")])
        return ui.tags.table(ui.tags.thead(head), ui.tags.tbody(*rows), class_="history")

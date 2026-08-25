"""Run page (M4): select strategy x baseline combinations and run them.

`state.models` is already built (Julia connected) by the time this page is
used -- see ui/app_shell.py. The only per-run toggle here is whether the
Energy Production (NemoMod electricity) sub-step executes, plus an advanced
sector-selection control that also happens to let users work around the
known upstream AFOLU/LivestockDietEstimator bug by excluding that sector.
"""

import pandas as pd
from shiny import module, reactive, render, ui

from sisepuede_tool.services import run_service
from sisepuede_tool.ui.state import AppState

_SECTOR_CHOICES = ["AFOLU", "Circular Economy", "Energy", "IPPU", "Socioeconomic"]


@module.ui
def page_run_ui():
    return ui.layout_columns(
        ui.card(
            ui.card_header("Select what to run"),
            ui.input_checkbox_group("baseline_ids", "Baselines", choices={}),
            ui.input_checkbox_group("strategy_ids", "Strategies", choices={}),
            ui.input_switch(
                "run_energy_production", "Run Energy Production (NemoMod electricity)", value=False
            ),
            ui.accordion(
                ui.accordion_panel(
                    "Advanced: sectors to run",
                    ui.input_checkbox_group(
                        "sectors_run", None, choices=_SECTOR_CHOICES, selected=_SECTOR_CHOICES
                    ),
                    ui.tags.small(
                        "AFOLU currently fails on some inputs due to a known upstream bug "
                        "(LivestockDietEstimator) -- deselect it here to run the other sectors.",
                        class_="text-muted",
                    ),
                ),
                open=False,
            ),
            ui.input_action_button("run_btn", "Run Selected", class_="btn-primary"),
            ui.output_ui("run_summary_ui"),
        ),
        ui.card(
            ui.card_header("Run Results"),
            ui.output_data_frame("run_results_table"),
        ),
        col_widths=[6, 6],
    )


@module.server
def page_run_server(input, output, session, state: AppState):
    last_run_summary = reactive.Value(None)

    @reactive.effect
    def _sync_baseline_choices():
        baselines = state.baselines.get()
        choices = {b.id: b.label for b in baselines.values()}
        ui.update_checkbox_group("baseline_ids", choices=choices, selected=list(choices.keys()))

    @reactive.effect
    def _sync_strategy_choices():
        strategies_map = state.strategies_map.get()
        choices = {str(sid): f"{sid} — {entry.strategy.name}" for sid, entry in strategies_map.items()}
        ui.update_checkbox_group("strategy_ids", choices=choices, selected=list(choices.keys()))

    @reactive.effect
    @reactive.event(input.run_btn)
    def _on_run():
        models = state.models.get()
        baselines = state.baselines.get()
        strategies_map = state.strategies_map.get()
        baseline_ids = list(input.baseline_ids())
        strategy_ids = [int(s) for s in input.strategy_ids()]
        sectors = list(input.sectors_run())
        run_energy_production = input.run_energy_production()

        if models is None:
            ui.notification_show("Model backend not ready yet.", type="error")
            return
        if not baseline_ids or not strategy_ids:
            ui.notification_show("Select at least one baseline and one strategy.", type="error")
            return

        combinations = [(sid, bid) for sid in strategy_ids for bid in baseline_ids]
        run_results = dict(state.run_results.get())

        with ui.Progress(min=0, max=len(combinations)) as p:
            for i, (strategy_id, baseline_id) in enumerate(combinations):
                baseline = baselines[baseline_id]
                p.set(
                    i,
                    message=f"Running strategy {strategy_id} x {baseline.label}",
                    detail=f"{i + 1} of {len(combinations)}",
                )
                entry = strategies_map[strategy_id]
                result = run_service.run_combination(
                    models,
                    entry.strategy,
                    baseline.df,
                    baseline.region,
                    run_energy_production,
                    strategy_id,
                    baseline_id,
                    models_run=sectors,
                )
                run_results[(strategy_id, baseline_id)] = result
            p.set(len(combinations), message="Done.")

        state.run_results.set(run_results)
        n_ok = sum(1 for (sid, bid) in combinations if run_results[(sid, bid)].ok)
        last_run_summary.set(f"Ran {len(combinations)} combination(s): {n_ok} succeeded, {len(combinations) - n_ok} failed.")
        ui.notification_show(last_run_summary.get(), type="message" if n_ok == len(combinations) else "warning")

    @render.ui
    def run_summary_ui():
        summary = last_run_summary.get()
        return ui.div(summary, class_="text-muted") if summary else None

    @render.data_frame
    def run_results_table():
        run_results = state.run_results.get()
        baselines = state.baselines.get()
        if not run_results:
            return render.DataGrid(
                pd.DataFrame(columns=["strategy_id", "baseline", "ok", "elapsed_seconds", "n_output_cols", "error"])
            )
        rows = []
        for (strategy_id, baseline_id), result in sorted(run_results.items()):
            baseline_label = baselines[baseline_id].label if baseline_id in baselines else baseline_id
            rows.append(
                {
                    "strategy_id": strategy_id,
                    "baseline": baseline_label,
                    "ok": result.ok,
                    "elapsed_seconds": round(result.elapsed_seconds, 2),
                    "n_output_cols": result.df_output.shape[1] if result.df_output is not None else None,
                    "error": (result.error or "")[:200],
                }
            )
        return render.DataGrid(pd.DataFrame(rows))

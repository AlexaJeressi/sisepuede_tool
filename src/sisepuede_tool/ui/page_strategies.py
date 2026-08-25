"""Strategy Builder page (M3): combine saved Transformations into a named
Strategy.

Note the picker is an *unordered* multi-select, not a sequence: sisepuede's
own Strategy class applies transformations in the order of
`transformations.attribute_transformation.key_values` (alphabetical by
transformation code), regardless of what order they were selected in --
verified empirically (see services/strategy_service.py). The page shows the
actual resolved application order live so this doesn't surprise anyone.
"""

import pandas as pd
from shiny import module, reactive, render, ui

from sisepuede_tool.models.strategy_entry import StrategyEntry
from sisepuede_tool.services import strategy_service
from sisepuede_tool.ui.state import AppState


@module.ui
def page_strategies_ui():
    return ui.layout_columns(
        ui.card(
            ui.card_header("Build Strategy"),
            ui.input_text("strategy_name", "Name"),
            ui.input_numeric("strategy_id", "Strategy ID", value=1000, min=0),
            ui.input_text_area("strategy_description", "Description", rows=2),
            ui.input_selectize("transformation_codes", "Transformations", choices={}, multiple=True),
            ui.output_ui("application_order_preview"),
            ui.input_action_button("validate_strategy", "Validate (dry run)", class_="btn-outline-secondary"),
            ui.input_action_button("save_strategy", "Save Strategy", class_="btn-primary"),
            ui.output_ui("save_status_ui"),
        ),
        ui.card(
            ui.card_header("Saved Strategies"),
            ui.output_data_frame("strategies_table"),
            ui.input_select("remove_strategy_select", "Remove strategy", choices={}),
            ui.input_action_button("remove_strategy_btn", "Remove selected", class_="btn-outline-danger"),
        ),
        col_widths=[7, 5],
    )


@module.server
def page_strategies_server(input, output, session, state: AppState):
    last_save_result = reactive.Value(None)
    last_validate_result = reactive.Value(None)

    @reactive.effect
    def _sync_transformation_choices():
        state.transformations_revision.get()
        transformations_obj = state.transformations_obj.get()
        if transformations_obj is None:
            return
        choices = {
            code: t.name or code
            for code, t in transformations_obj.dict_transformations.items()
            if code != transformations_obj.code_baseline
        }
        ui.update_selectize("transformation_codes", choices=choices)

    @reactive.effect
    def _suggest_strategy_id():
        strategies_map = state.strategies_map.get()
        suggested = strategy_service.next_available_strategy_id(strategies_map.keys())
        ui.update_numeric("strategy_id", value=suggested)

    @render.ui
    def application_order_preview():
        transformations_obj = state.transformations_obj.get()
        codes = input.transformation_codes()
        if transformations_obj is None or not codes:
            return ui.p("Select at least one transformation.", class_="text-muted")
        order = strategy_service.resolve_application_order(codes, transformations_obj)
        return ui.div(
            ui.tags.small(
                "Actual application order (sisepuede applies transformations in a fixed "
                "code order, not selection order):",
                class_="text-muted d-block",
            ),
            ui.tags.ol(*[ui.tags.li(code) for code in order]),
        )

    @reactive.effect
    @reactive.event(input.validate_strategy)
    def _on_validate():
        transformations_obj = state.transformations_obj.get()
        codes = input.transformation_codes()
        baselines = state.baselines.get()
        if transformations_obj is None or not codes or not baselines:
            last_validate_result.set((False, "Select transformations and load a baseline first."))
            return

        reference_baseline = next(iter(baselines.values()))
        try:
            strategy = strategy_service.build_strategy(
                int(input.strategy_id()), list(codes), transformations_obj, name="(validation preview)"
            )
            strategy_service.dry_run(strategy, reference_baseline.df)
        except Exception as e:
            last_validate_result.set((False, f"Dry run failed: {e}"))
            return
        last_validate_result.set((True, "Dry run succeeded."))

    @reactive.effect
    @reactive.event(input.save_strategy)
    def _on_save():
        transformations_obj = state.transformations_obj.get()
        codes = list(input.transformation_codes())
        name = (input.strategy_name() or "").strip()

        if transformations_obj is None:
            last_save_result.set((False, "Load a baseline first."))
            return
        if not name:
            last_save_result.set((False, "Strategy name is required."))
            return
        if not codes:
            last_save_result.set((False, "Select at least one transformation."))
            return

        strategy_id = int(input.strategy_id())
        strategies_map = state.strategies_map.get()
        if strategy_id in strategies_map:
            last_save_result.set(
                (False, f"Strategy ID {strategy_id} is already used. Choose a different ID.")
            )
            return

        try:
            strategy = strategy_service.build_strategy(
                strategy_id,
                codes,
                transformations_obj,
                name=name,
                description=input.strategy_description() or "",
            )
        except Exception as e:
            last_save_result.set((False, f"Failed to build strategy: {e}"))
            return

        strategies_map = dict(strategies_map)
        strategies_map[strategy_id] = StrategyEntry(strategy=strategy, transformation_codes=codes)
        state.strategies_map.set(strategies_map)

        last_save_result.set((True, f"Saved strategy {strategy_id} ('{name}')."))
        ui.notification_show(f"Saved strategy {strategy_id} ('{name}').", type="message")
        ui.update_text("strategy_name", value="")
        ui.update_selectize("transformation_codes", selected=[])

    @render.ui
    def save_status_ui():
        parts = []
        validate_result = last_validate_result.get()
        if validate_result is not None:
            ok, message = validate_result
            parts.append(ui.div(message, class_="text-success" if ok else "text-danger"))
        save_result = last_save_result.get()
        if save_result is not None:
            ok, message = save_result
            parts.append(ui.div(message, class_="text-success" if ok else "text-danger"))
        return ui.div(*parts) if parts else None

    @reactive.effect
    @reactive.event(input.remove_strategy_btn)
    def _on_remove():
        target = input.remove_strategy_select()
        if not target:
            return
        strategy_id = int(target)
        if strategy_id == 0:
            ui.notification_show("Cannot remove the baseline strategy.", type="error")
            return
        strategies_map = dict(state.strategies_map.get())
        removed = strategies_map.pop(strategy_id, None)
        state.strategies_map.set(strategies_map)
        if removed is not None:
            ui.notification_show(f"Removed strategy {strategy_id}.", type="message")

    @reactive.effect
    def _sync_remove_choices():
        strategies_map = state.strategies_map.get()
        choices = {
            str(sid): f"{sid} — {entry.strategy.name}" for sid, entry in strategies_map.items() if sid != 0
        }
        ui.update_select("remove_strategy_select", choices=choices)

    @render.data_frame
    def strategies_table():
        strategies_map = state.strategies_map.get()
        transformations_obj = state.transformations_obj.get()
        if not strategies_map or transformations_obj is None:
            return render.DataGrid(pd.DataFrame(columns=["id", "name", "application_order"]))

        rows = []
        for sid, entry in sorted(strategies_map.items()):
            order = strategy_service.resolve_application_order(
                entry.transformation_codes, transformations_obj
            )
            rows.append(
                {
                    "id": sid,
                    "code": entry.strategy.code,
                    "name": entry.strategy.name,
                    "application_order": " -> ".join(order),
                }
            )
        return render.DataGrid(pd.DataFrame(rows))

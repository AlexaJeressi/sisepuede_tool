"""Baseline Data Manager page (M1): upload one or more baseline CSVs for a
single region, validate each, and manage the resulting collection.

All loaded baselines are validated to share one region (the first baseline
loaded fixes it for the session). The transformer catalog is built once,
from the first baseline added -- see services/catalog_service.py.
"""

import dataclasses
import datetime
import uuid

import pandas as pd
from shiny import module, reactive, render, ui

from sisepuede_tool.models.baseline import BaselineDataset
from sisepuede_tool.models.strategy_entry import StrategyEntry
from sisepuede_tool.services import catalog_service, input_service, strategy_service, transformation_service
from sisepuede_tool.ui.state import AppState


@module.ui
def page_data_input_ui():
    return ui.layout_columns(
        ui.card(
            ui.card_header("Add a baseline"),
            ui.input_file("csv_file", "Baseline CSV", accept=[".csv"], multiple=False),
            ui.input_text("baseline_label", "Label", placeholder="e.g. NDC 2024 update"),
            ui.input_action_button("add_baseline", "Validate & Add", class_="btn-primary"),
            ui.output_ui("validation_panel"),
            ui.h6("Preview (first 10 rows)"),
            ui.output_data_frame("preview_table"),
        ),
        ui.card(
            ui.card_header("Loaded baselines"),
            ui.output_data_frame("baselines_table"),
            ui.input_select("remove_baseline_select", "Remove baseline", choices={}),
            ui.input_action_button("remove_baseline_btn", "Remove selected", class_="btn-outline-danger"),
        ),
        col_widths=[6, 6],
    )


@module.server
def page_data_input_server(input, output, session, state: AppState):
    last_validation = reactive.Value(None)

    @reactive.effect
    @reactive.event(input.add_baseline)
    def _on_add_baseline():
        file_infos = input.csv_file()
        if not file_infos:
            ui.notification_show("Choose a CSV file first.", type="error")
            return

        label = (input.baseline_label() or "").strip()
        if not label:
            ui.notification_show("Enter a label for this baseline.", type="error")
            return

        df = input_service.load_csv(file_infos[0]["datapath"])
        model_attributes = state.model_attributes.get()
        result = input_service.validate_baseline(df, model_attributes)
        last_validation.set(result)

        if not result.ok:
            ui.notification_show(f"Validation failed: {result.error}", type="error", duration=None)
            return

        baselines = state.baselines.get()
        existing_regions = {b.region for b in baselines.values()}
        if existing_regions and result.region not in existing_regions:
            (session_region,) = existing_regions
            msg = (
                f"Region mismatch: this baseline is '{result.region}', but this "
                f"session is locked to '{session_region}' (set by the first baseline loaded)."
            )
            last_validation.set(dataclasses.replace(result, ok=False, error=msg))
            ui.notification_show(msg, type="error", duration=None)
            return

        new_id = uuid.uuid4().hex[:8]
        baseline = BaselineDataset(
            id=new_id,
            label=label,
            df=result.df,
            region=result.region,
            loaded_at=datetime.datetime.now(),
            n_time_periods=result.n_time_periods,
            interpolated_periods=result.interpolated_periods,
        )
        baselines = dict(baselines)
        baselines[new_id] = baseline
        state.baselines.set(baselines)

        if state.transformers_catalog.get() is None:
            transformers_catalog = catalog_service.build_transformers_catalog(baseline.df)
            state.transformers_catalog.set(transformers_catalog)
            transformations_obj = transformation_service.create_transformations_collection(
                transformers_catalog
            )
            state.transformations_obj.set(transformations_obj)
            baseline_strategy = strategy_service.build_baseline_strategy(transformations_obj)
            state.strategies_map.set(
                {0: StrategyEntry(strategy=baseline_strategy, transformation_codes=[transformations_obj.code_baseline])}
            )

        ui.notification_show(f"Added baseline '{label}' ({result.region}).", type="message")
        ui.update_text("baseline_label", value="")

    @reactive.effect
    @reactive.event(input.remove_baseline_btn)
    def _on_remove_baseline():
        target_id = input.remove_baseline_select()
        if not target_id:
            return
        baselines = dict(state.baselines.get())
        removed = baselines.pop(target_id, None)
        state.baselines.set(baselines)
        if removed is not None:
            ui.notification_show(f"Removed baseline '{removed.label}'.", type="message")

    @reactive.effect
    def _sync_remove_choices():
        baselines = state.baselines.get()
        choices = {b.id: b.label for b in baselines.values()}
        ui.update_select("remove_baseline_select", choices=choices)

    @render.ui
    def validation_panel():
        result = last_validation.get()
        if result is None:
            return ui.p("No baseline validated yet.", class_="text-muted")
        if not result.ok:
            return ui.div(ui.strong("Error: "), result.error, class_="text-danger")

        msg = f"Valid — region '{result.region}', {result.n_time_periods} time periods."
        if result.interpolated_periods:
            msg += f" Interpolated missing periods: {result.interpolated_periods}."
        return ui.div(msg, class_="text-success")

    @render.data_frame
    def preview_table():
        result = last_validation.get()
        if result is None or not result.ok:
            return render.DataGrid(pd.DataFrame())
        return render.DataGrid(result.df.head(10), height="300px")

    @render.data_frame
    def baselines_table():
        baselines = state.baselines.get()
        if not baselines:
            return render.DataGrid(
                pd.DataFrame(columns=["label", "region", "n_time_periods", "n_interpolated", "loaded_at"])
            )
        rows = [
            {
                "label": b.label,
                "region": b.region,
                "n_time_periods": b.n_time_periods,
                "n_interpolated": len(b.interpolated_periods),
                "loaded_at": b.loaded_at.strftime("%H:%M:%S"),
            }
            for b in baselines.values()
        ]
        return render.DataGrid(pd.DataFrame(rows))

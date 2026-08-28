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


_ICON_UPLOAD = ui.HTML(
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" '
    'stroke-linecap="round" stroke-linejoin="round"><path d="M12 15V4M8 8l4-4 4 4"/>'
    '<path d="M4 15v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3"/></svg>'
)
_ICON_LIST = ui.HTML(
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" '
    'stroke-linecap="round" stroke-linejoin="round"><path d="M4 5h16M4 12h16M4 19h16"/></svg>'
)
_ICON_CHECK = ui.HTML(
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
    'stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5"/></svg>'
)
_ICON_TRASH = ui.HTML(
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" '
    'stroke-linecap="round" stroke-linejoin="round"><path d="M4 7h16M9 7V4h6v3M6 7l1 13a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-13"/></svg>'
)


def _field(label: str, *children, hint: str = None) -> ui.Tag:
    parts = [ui.span(label, class_="field-label"), *children]
    if hint:
        parts.append(ui.span(hint, class_="field-hint"))
    return ui.div(*parts, class_="field")


def _card_header(icon, title: str, description: str) -> ui.Tag:
    return ui.div(
        ui.div(icon, class_="icon-badge"),
        ui.div(ui.h2(title), ui.p(description)),
        class_="card-header",
    )


@module.ui
def page_data_input_ui():
    return ui.div(
        ui.div(
            _card_header(_ICON_UPLOAD, "Add a baseline", "Upload a CSV and validate it against the expected SISEPUEDE schema."),
            ui.div(
                _field("Baseline CSV", ui.input_file("csv_file", None, accept=[".csv"], multiple=False)),
                _field(
                    "Label",
                    ui.input_text("baseline_label", None, placeholder="e.g. NDC 2024 update"),
                    hint="Shown in the loaded baselines table and in downstream project pickers.",
                ),
                ui.input_action_button("add_baseline", ui.TagList(_ICON_CHECK, "Validate & Add"), class_="btn-primary"),
                ui.output_ui("validation_panel"),
                _field("Preview (first 10 rows)", ui.div(ui.output_data_frame("preview_table"), class_="table-wrap")),
                class_="card-body",
            ),
            class_="card",
        ),
        ui.div(
            _card_header(_ICON_LIST, "Loaded baselines", "Baselines available to projects in this session."),
            ui.div(
                ui.div(ui.output_data_frame("baselines_table"), class_="table-wrap"),
                ui.div(class_="divider"),
                _field("Remove baseline", ui.input_select("remove_baseline_select", None, choices={})),
                ui.input_action_button(
                    "remove_baseline_btn", ui.TagList(_ICON_TRASH, "Remove selected"), class_="btn-outline-danger"
                ),
                class_="card-body",
            ),
            class_="card",
        ),
        class_="content",
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
        icon_info = ui.HTML(
            '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" '
            'stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/>'
            '<path d="M12 8v5M12 16h.01"/></svg>'
        )

        result = last_validation.get()
        if result is None:
            return ui.div(icon_info, "No baseline validated yet. Choose a file and select Validate & add.", class_="empty-note")
        if not result.ok:
            return ui.div(icon_info, ui.strong("Error: "), result.error, class_="empty-note text-danger")

        msg = f"Valid — region '{result.region}', {result.n_time_periods} time periods."
        if result.interpolated_periods:
            msg += f" Interpolated missing periods: {result.interpolated_periods}."
        return ui.div(icon_info, msg, class_="empty-note text-success")

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

"""Transformer -> Transformation Designer page (M2): pick a Transformer,
adjust its parameters via an auto-generated form, save as a named
Transformation.
"""

import pandas as pd
from shiny import module, reactive, render, ui

from sisepuede_tool.services import transformation_service, widget_metadata
from sisepuede_tool.ui.components import param_widget
from sisepuede_tool.ui.state import AppState


@module.ui
def page_transformations_ui():
    return ui.layout_columns(
        ui.card(
            ui.card_header("Choose a Transformer"),
            ui.input_select("sector", "Sector", choices={}),
            ui.input_select("transformer_code", "Transformer", choices={}),
            ui.output_ui("transformer_description"),
        ),
        ui.card(
            ui.card_header("Configure Transformation"),
            ui.input_text("transformation_code", "Transformation code"),
            ui.input_text("transformation_name", "Name"),
            ui.input_text_area("transformation_description", "Description", rows=2),
            ui.output_ui("param_form"),
            ui.input_action_button("save_transformation", "Save Transformation", class_="btn-primary"),
            ui.output_ui("save_status_ui"),
        ),
        ui.card(
            ui.card_header("Saved Transformations"),
            ui.output_data_frame("transformations_table"),
            ui.input_select("remove_transformation_select", "Remove transformation", choices={}),
            ui.input_action_button(
                "remove_transformation_btn", "Remove selected", class_="btn-outline-danger"
            ),
        ),
        col_widths=[4, 4, 4],
    )


@module.server
def page_transformations_server(input, output, session, state: AppState):
    overrides = widget_metadata.load_overrides(widget_metadata.default_overrides_path())
    last_save_result = reactive.Value(None)  # (ok: bool, message: str) | None

    def _current_transformer_and_specs():
        catalog = state.transformers_catalog.get()
        model_attributes = state.model_attributes.get()
        code = input.transformer_code()
        if catalog is None or not code:
            return None, []
        transformer = catalog.get_transformer(code)
        specs = widget_metadata.build_param_specs(
            transformer, model_attributes, catalog, overrides=overrides
        )
        return transformer, specs

    @reactive.effect
    def _sync_sector_choices():
        catalog = state.transformers_catalog.get()
        if catalog is None:
            return
        sectors = sorted(catalog.get_transformer_codes_by_sector().keys())
        ui.update_select("sector", choices=sectors)

    @reactive.effect
    def _sync_transformer_choices():
        catalog = state.transformers_catalog.get()
        sector = input.sector()
        if catalog is None or not sector:
            return
        codes = catalog.get_transformer_codes_by_sector().get(sector, [])
        choices = {code: catalog.get_transformer(code).name for code in codes}
        ui.update_select("transformer_code", choices=choices)

    @reactive.effect
    @reactive.event(input.transformer_code)
    def _autofill_transformation_fields():
        catalog = state.transformers_catalog.get()
        code = input.transformer_code()
        if catalog is None or not code:
            return
        transformer = catalog.get_transformer(code)
        transformations_obj = state.transformations_obj.get()
        existing = set(transformations_obj.dict_transformations.keys()) if transformations_obj else set()

        ui.update_text("transformation_code", value=transformation_service.suggest_transformation_code(code, existing))
        ui.update_text("transformation_name", value=transformer.name)
        ui.update_text_area("transformation_description", value=transformer.description or "")

    @render.ui
    def transformer_description():
        transformer, _specs = _current_transformer_and_specs()
        if transformer is None:
            return ui.p("Add a baseline on the Baseline Data page first.", class_="text-muted")
        parts = [ui.p(transformer.description or "No description available.")]
        if transformer.description_units:
            parts.append(ui.tags.small(transformer.description_units, class_="text-muted"))
        return ui.div(*parts)

    @render.ui
    def param_form():
        _transformer, specs = _current_transformer_and_specs()
        if not specs:
            return ui.p("No parameters.", class_="text-muted")
        return param_widget.render_params(specs)

    @reactive.effect
    @reactive.event(input.save_transformation)
    def _on_save():
        transformer, specs = _current_transformer_and_specs()
        if transformer is None:
            last_save_result.set((False, "Choose a transformer first."))
            return

        code = (input.transformation_code() or "").strip()
        name = (input.transformation_name() or "").strip()
        if not code or not name:
            last_save_result.set((False, "Transformation code and name are required."))
            return
        if not code.startswith("TX:"):
            last_save_result.set((False, "Transformation code must start with 'TX:'."))
            return

        try:
            parameters = param_widget.read_params(input, specs)
        except param_widget.ParamReadError as e:
            last_save_result.set((False, str(e)))
            return

        transformations_obj = state.transformations_obj.get()
        try:
            transformation = transformation_service.build_transformation(
                transformation_code=code,
                transformation_name=name,
                transformer_code=transformer.code,
                parameters=parameters,
                transformers_catalog=state.transformers_catalog.get(),
                description=input.transformation_description() or "",
            )
            transformation_service.add_transformation(transformations_obj, transformation)
        except Exception as e:
            last_save_result.set((False, f"Failed to save: {e}"))
            return

        state.transformations_revision.set(state.transformations_revision.get() + 1)
        last_save_result.set((True, f"Saved '{code}'."))
        ui.notification_show(f"Saved transformation '{code}'.", type="message")

    @render.ui
    def save_status_ui():
        result = last_save_result.get()
        if result is None:
            return None
        ok, message = result
        return ui.div(message, class_="text-success" if ok else "text-danger")

    @reactive.effect
    @reactive.event(input.remove_transformation_btn)
    def _on_remove():
        transformations_obj = state.transformations_obj.get()
        target_code = input.remove_transformation_select()
        if transformations_obj is None or not target_code:
            return
        try:
            transformation_service.remove_transformation(transformations_obj, target_code)
        except ValueError as e:
            ui.notification_show(str(e), type="error")
            return
        state.transformations_revision.set(state.transformations_revision.get() + 1)
        ui.notification_show(f"Removed transformation '{target_code}'.", type="message")

    @reactive.effect
    def _sync_remove_choices():
        state.transformations_revision.get()
        transformations_obj = state.transformations_obj.get()
        if transformations_obj is None:
            return
        choices = {
            code: t.name
            for code, t in transformations_obj.dict_transformations.items()
            if code != transformations_obj.code_baseline
        }
        ui.update_select("remove_transformation_select", choices=choices)

    @render.data_frame
    def transformations_table():
        state.transformations_revision.get()
        transformations_obj = state.transformations_obj.get()
        if transformations_obj is None:
            return render.DataGrid(pd.DataFrame(columns=["code", "name", "transformer_code"]))
        rows = [
            {"code": t.code, "name": t.name, "transformer_code": t.transformer_code}
            for t in transformations_obj.dict_transformations.values()
        ]
        return render.DataGrid(pd.DataFrame(rows))

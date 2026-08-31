"""Persistence page (M7): export the session's Transformations/Strategies
to a sisepuede-native project .zip (config_general.yaml, transformation_*.yaml,
strategy_definitions.csv) for reuse in the CLI/notebooks, or import one back
in. Session state is otherwise in-memory only -- see persistence_service.
"""

from shiny import module, reactive, render, ui

from sisepuede_tool.services import persistence_service
from sisepuede_tool.ui.state import AppState


@module.ui
def page_save_load_ui():
    return ui.layout_columns(
        ui.card(
            ui.card_header("Export session"),
            ui.p(
                "Download the current session's Transformations and Strategies as a "
                "sisepuede project .zip (config_general.yaml, transformation_*.yaml, "
                "strategy_definitions.csv) -- loadable unmodified by the sisepuede CLI "
                "or notebooks."
            ),
            ui.download_button("download_export", "Download .zip"),
        ),
        ui.card(
            ui.card_header("Import session"),
            ui.p(
                "Upload a previously exported (or CLI-authored) project .zip. This "
                "replaces the current session's Transformations and Strategies -- "
                "export first if you want to keep them."
            ),
            ui.input_file("import_file", "Project .zip", accept=[".zip"]),
            ui.input_action_button("import_btn", "Import", class_="btn-primary"),
            ui.output_ui("import_status_ui"),
        ),
        col_widths=[6, 6],
    )


@module.server
def page_save_load_server(input, output, session, state: AppState):
    last_import_result = reactive.Value(None)  # (ok, message) | None

    @render.download_button(filename="sisepuede_session_export.zip")
    def download_export():
        transformations_obj = state.transformations_obj.get()
        strategies_map = state.strategies_map.get()
        if transformations_obj is None:
            yield b""
            return
        yield persistence_service.export_session_zip(transformations_obj, strategies_map)

    @reactive.effect
    @reactive.event(input.import_btn)
    def _on_import():
        file_infos = input.import_file()
        if not file_infos:
            last_import_result.set((False, "Choose a project .zip file first."))
            return

        transformers_catalog = state.transformers_catalog.get()
        if transformers_catalog is None:
            last_import_result.set((False, "Add a baseline on the Baseline Data page first."))
            return

        try:
            transformations_obj, strategies_map = persistence_service.import_session_zip(
                file_infos[0]["datapath"], transformers_catalog
            )
        except Exception as e:
            last_import_result.set((False, f"Import failed: {e}"))
            return

        state.transformations_obj.set(transformations_obj)
        state.transformations_revision.set(state.transformations_revision.get() + 1)
        state.strategies_map.set(strategies_map)

        n_transformations = len(transformations_obj.dict_transformations) - 1
        n_strategies = len(strategies_map) - (1 if 0 in strategies_map else 0)
        last_import_result.set(
            (True, f"Imported {n_transformations} transformation(s) and {n_strategies} strategy(ies).")
        )
        ui.notification_show("Session imported.", type="message")

    @render.ui
    def import_status_ui():
        result = last_import_result.get()
        if result is None:
            return None
        ok, message = result
        return ui.div(message, class_="text-success" if ok else "text-danger")

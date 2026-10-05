"""Persistence page (M7): export the session's Transformations/Strategies
to a sisepuede-native project .zip (config_general.yaml, transformation_*.yaml,
strategy_definitions.csv) for reuse in the CLI/notebooks, or import one back
in. Session state is otherwise in-memory only -- see persistence_service.
"""

import pandas as pd
from shiny import module, reactive, render, ui

from sisepuede_tool.services import library_service, pathway_service, persistence_service, projects_service
from sisepuede_tool.ui.state import AppState


PROJECT_LINKS_FILENAME = "project_links.csv"
CUSTOM_PROJECTS_FILENAME = "custom_projects.csv"
RESULTS_CUSTOM_VARS_FILENAME = "results_custom_vars.csv"


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
        extra = {
            PROJECT_LINKS_FILENAME: projects_service.links_to_dataframe(
                state.project_links.get(), state.selected_projects.get()
            )
        }
        if state.custom_projects.get():
            extra[CUSTOM_PROJECTS_FILENAME] = pd.DataFrame(state.custom_projects.get(), columns=projects_service.PROJECT_COLUMNS)
        if state.results_custom_vars.get():
            extra[RESULTS_CUSTOM_VARS_FILENAME] = pd.DataFrame({"variable": state.results_custom_vars.get()})
        yield persistence_service.export_session_zip(transformations_obj, strategies_map, extra)

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

        # library transformations not in the file come back from the shipped library
        state.library_items.set(library_service.add_library_to_collection(transformations_obj, transformers_catalog))
        strategies_map = pathway_service.rebuild_pathways(strategies_map, transformations_obj)
        state.transformations_obj.set(transformations_obj)
        state.transformations_revision.set(state.transformations_revision.get() + 1)
        state.strategies_map.set(strategies_map)
        state.active_pathway_id.set(None)

        tables = persistence_service.read_extra_tables(
            file_infos[0]["datapath"], [PROJECT_LINKS_FILENAME, CUSTOM_PROJECTS_FILENAME, RESULTS_CUSTOM_VARS_FILENAME]
        )
        if RESULTS_CUSTOM_VARS_FILENAME in tables:
            state.results_custom_vars.set([v for v in tables[RESULTS_CUSTOM_VARS_FILENAME]["variable"].dropna().tolist() if v])
        if CUSTOM_PROJECTS_FILENAME in tables:
            custom = tables[CUSTOM_PROJECTS_FILENAME].replace({"": None})
            state.custom_projects.set(custom.to_dict("records"))
        if PROJECT_LINKS_FILENAME in tables:
            links, scope = projects_service.links_from_dataframe(tables[PROJECT_LINKS_FILENAME])
            known = set(transformations_obj.dict_transformations)
            state.project_links.set({k: (v if v in known else None) for k, v in links.items()})
            state.selected_projects.set(scope)

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

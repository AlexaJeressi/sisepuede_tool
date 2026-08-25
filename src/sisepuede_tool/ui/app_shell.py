from shiny import ui

from sisepuede_tool.services import catalog_service, run_service
from sisepuede_tool.ui.page_data_input import page_data_input_server, page_data_input_ui
from sisepuede_tool.ui.page_output_explorer import (
    page_output_explorer_server,
    page_output_explorer_ui,
)
from sisepuede_tool.ui.page_persistence import page_persistence_server, page_persistence_ui
from sisepuede_tool.ui.page_projects import page_projects_server, page_projects_ui
from sisepuede_tool.ui.page_run import page_run_server, page_run_ui
from sisepuede_tool.ui.page_strategies import page_strategies_server, page_strategies_ui
from sisepuede_tool.ui.page_transformations import (
    page_transformations_server,
    page_transformations_ui,
)
from sisepuede_tool.ui.page_validation import page_validation_server, page_validation_ui
from sisepuede_tool.ui.state import new_app_state

app_ui = ui.page_navbar(
    ui.nav_panel("Baseline Data", page_data_input_ui("data_input")),
    ui.nav_panel("Projects", page_projects_ui("projects")),
    ui.nav_panel("Transformations", page_transformations_ui("transformations")),
    ui.nav_panel("Pathways", page_strategies_ui("strategies")),
    ui.nav_panel("Run", page_run_ui("run")),
    ui.nav_panel("Output Explorer", page_output_explorer_ui("output_explorer")),
    ui.nav_panel("Monitoring", page_validation_ui("validation")),
    ui.nav_panel("Save/Load", page_persistence_ui("persistence")),
    title="Egypt: MRV with SISEPUEDE",
    id="main_nav",
)


def server(input, output, session):
    state = new_app_state()
    model_attributes = catalog_service.build_model_attributes()
    state.model_attributes.set(model_attributes)
    # Built eagerly at session start (not deferred to first Run click) so the
    # Julia/NemoMod bridge is already connected by the time a user reaches
    # the Run page -- per the confirmed requirement that Julia loads at tool
    # init, with only per-run electricity execution being toggle-able.
    state.models.set(run_service.build_models(model_attributes))

    page_data_input_server("data_input", state)
    page_projects_server("projects", state)
    page_transformations_server("transformations", state)
    page_strategies_server("strategies", state)
    page_run_server("run", state)
    page_output_explorer_server("output_explorer", state)
    page_validation_server("validation", state)
    page_persistence_server("persistence", state)

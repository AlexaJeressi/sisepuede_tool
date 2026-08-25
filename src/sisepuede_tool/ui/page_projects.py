"""Projects page: browse the candidate project list from the shipped Egypt
NDC/LTS workbook, toggle each project on/off, and view its attributes.

The project list is loaded live from config.PROJECTS_XLSX_PATH (via
projects_service.load_projects_cached) at page-build time, not hardcoded --
editing the workbook and restarting the app is enough to pick up changes.
"""

from shiny import module, reactive, render, ui

from sisepuede_tool import config
from sisepuede_tool.services import projects_service

_DETAIL_FIELDS = [
    ("Project Description", "Project Description"),
    ("Total Investment (Estimated)", "Total Investment (Estimated)"),
    ("Status", "Status"),
    ("NDC Notes", "NDC Notes"),
]


@module.ui
def page_projects_ui():
    df = projects_service.load_projects_cached(config.PROJECTS_XLSX_PATH)
    project_names = list(df["Project Name"])

    return ui.layout_columns(
        ui.card(
            ui.card_header(f"Projects ({len(project_names)})"),
            ui.input_action_button("select_all", "Select all", class_="btn-sm btn-outline-secondary"),
            ui.input_action_button("select_none", "Select none", class_="btn-sm btn-outline-secondary"),
            ui.output_ui("selection_summary"),
            ui.div(
                ui.input_checkbox_group("selected_projects", None, choices=project_names, selected=[]),
                style="max-height: 500px; overflow-y: auto;",
            ),
        ),
        ui.card(
            ui.card_header("Project Details"),
            ui.input_select("view_project", "View details for", choices=project_names),
            ui.output_ui("project_details"),
        ),
        col_widths=[6, 6],
    )


@module.server
def page_projects_server(input, output, session, state):
    df = projects_service.load_projects_cached(config.PROJECTS_XLSX_PATH)
    project_names = list(df["Project Name"])

    @reactive.effect
    @reactive.event(input.select_all)
    def _on_select_all():
        ui.update_checkbox_group("selected_projects", selected=project_names)

    @reactive.effect
    @reactive.event(input.select_none)
    def _on_select_none():
        ui.update_checkbox_group("selected_projects", selected=[])

    @reactive.effect
    def _sync_selected_projects():
        checked = set(input.selected_projects())
        state.selected_projects.set({name: (name in checked) for name in project_names})

    @render.ui
    def selection_summary():
        n_selected = len(input.selected_projects())
        return ui.p(f"{n_selected} of {len(project_names)} selected", class_="text-muted")

    @render.ui
    def project_details():
        name = input.view_project()
        if not name:
            return ui.p("Choose a project to view its details.", class_="text-muted")

        rows = df.loc[df["Project Name"] == name]
        if rows.empty:
            return ui.p("Project not found.", class_="text-danger")
        row = rows.iloc[0]

        blocks = []
        for label, column in _DETAIL_FIELDS:
            blocks.append(ui.h6(label))
            blocks.append(ui.p(str(row[column])))
        return ui.div(*blocks)

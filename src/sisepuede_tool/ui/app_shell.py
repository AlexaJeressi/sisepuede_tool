"""Custom sidebar shell (Egypt MRV Console), replacing the stock
page_navbar look per mockups/baseline_data_dashboard.html.

Real page switching goes through `ui.navset_hidden` (zero visual chrome,
purely programmatic) wrapping each page's existing module unchanged; the
sidebar is hand-built markup (bslib's built-in navsets don't support the
mockup's grouped nav labels) whose links set a `sidebar_nav` Shiny input,
which a server-side effect uses to drive `ui.update_navs`. Active-state
highlighting is handled client-side (see the onclick handler in _nav_link)
so only the topbar (page-specific title/description/status) needs a
server round trip.
"""

import pathlib

from shiny import reactive, render, ui

from sisepuede_tool import config
from sisepuede_tool.services import catalog_service, cost_benefit_service, run_service
from sisepuede_tool.ui.page_article_6 import page_article_6_server, page_article_6_ui
from sisepuede_tool.ui.page_cost_benefits import page_cost_benefits_server, page_cost_benefits_ui
from sisepuede_tool.ui.page_data_input import page_data_input_server, page_data_input_ui
from sisepuede_tool.ui.page_macroeconomic_impacts import (
    page_macroeconomic_impacts_server,
    page_macroeconomic_impacts_ui,
)
from sisepuede_tool.ui.page_output_explorer import (
    page_output_explorer_server,
    page_output_explorer_ui,
)
from sisepuede_tool.ui.page_save_load import page_save_load_server, page_save_load_ui
from sisepuede_tool.ui.page_projects import page_projects_server, page_projects_ui
from sisepuede_tool.ui.page_run import page_run_server, page_run_ui
from sisepuede_tool.ui.page_strategies import page_strategies_server, page_strategies_ui
from sisepuede_tool.ui.page_transformations import (
    page_transformations_server,
    page_transformations_ui,
)
from sisepuede_tool.ui.page_monitoring import page_monitoring_server, page_monitoring_ui
from sisepuede_tool.ui.shell_nav import DEFAULT_NAV_ID, NAV_GROUPS, NAV_ITEMS, NAV_ITEMS_BY_ID
from sisepuede_tool.ui.state import new_app_state

_THEME_CSS_PATH = pathlib.Path(__file__).resolve().parent.parent / "resources" / "theme.css"

_PAGE_UI_FNS = {
    "data_input": page_data_input_ui,
    "projects": page_projects_ui,
    "transformations": page_transformations_ui,
    "strategies": page_strategies_ui,
    "run": page_run_ui,
    "output_explorer": page_output_explorer_ui,
    "validation": page_monitoring_ui,
    "cost_benefits": page_cost_benefits_ui,
    "macroeconomic_impacts": page_macroeconomic_impacts_ui,
    "article_6": page_article_6_ui,
    "persistence": page_save_load_ui,
}

_EGYPT_FLAG_SVG = (
    '<svg viewBox="0 0 30 20" xmlns="http://www.w3.org/2000/svg">'
    '<rect width="30" height="20" fill="#EEEEEE"/>'
    '<rect width="30" height="6.667" fill="#CE1126"/>'
    '<rect y="13.333" width="30" height="6.667" fill="#000000"/>'
    '<g transform="translate(15,10)" fill="#C09A2E">'
    '<circle r="2.1"/>'
    '<path d="M0 -3.4 L0.7 -1.2 L-0.7 -1.2 Z"/>'
    '<path d="M-4.6 -1.6 L-2 -0.3 L-2.6 0.9 Z"/>'
    '<path d="M4.6 -1.6 L2 -0.3 L2.6 0.9 Z"/>'
    '<path d="M-3.4 2.6 L-1.1 1.3 L-0.4 2.6 Z"/>'
    '<path d="M3.4 2.6 L1.1 1.3 L0.4 2.6 Z"/>'
    "</g></svg>"
)


def _nav_link(item, active: bool) -> ui.Tag:
    onclick = (
        "document.querySelectorAll('.nav-item').forEach(el => el.classList.remove('active'));"
        "this.classList.add('active');"
        f"Shiny.setInputValue('sidebar_nav', '{item.id}', {{priority: 'event'}});"
        "return false;"
    )
    return ui.tags.a(
        ui.HTML(item.icon_svg),
        item.label,
        class_="nav-item active" if active else "nav-item",
        href="javascript:void(0)",
        onclick=onclick,
    )


def _build_sidebar() -> ui.Tag:
    groups = []
    for group in NAV_GROUPS:
        items = [item for item in NAV_ITEMS if item.group == group]
        groups.append(
            ui.div(
                ui.div(group, class_="nav-group-label"),
                *[_nav_link(item, item.id == DEFAULT_NAV_ID) for item in items],
                class_="nav-group",
            )
        )

    return ui.tags.aside(
        ui.div(
            ui.div(
                ui.span(ui.HTML(_EGYPT_FLAG_SVG), class_="flag-icon"),
                ui.div("MRV Console", class_="brand-eyebrow"),
                class_="brand-top",
            ),
            ui.div("Egypt", class_="brand-title"),
            ui.div(ui.span(class_="dot"), " Built on SISEPUEDE", class_="brand-sub"),
            class_="brand",
        ),
        ui.tags.nav(*groups),
        ui.div(
            ui.span("SISEPUEDE Tool"),
            ui.span("Region: Egypt (EGY)"),
            class_="sidebar-foot",
        ),
        class_="sidebar",
    )


def _head() -> ui.Tag:
    return ui.head_content(
        ui.tags.link(rel="preconnect", href="https://fonts.googleapis.com"),
        ui.tags.link(rel="preconnect", href="https://fonts.gstatic.com", crossorigin=""),
        ui.tags.link(
            href=(
                "https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700"
                "&family=IBM+Plex+Mono:wght@400;500;600&display=swap"
            ),
            rel="stylesheet",
        ),
        ui.include_css(_THEME_CSS_PATH),
    )


app_ui = ui.page_fluid(
    _head(),
    ui.div(
        _build_sidebar(),
        ui.div(
            ui.output_ui("topbar"),
            ui.div(
                ui.navset_hidden(
                    *[
                        ui.nav_panel(item.label, _PAGE_UI_FNS[item.id](item.id), value=item.id)
                        for item in NAV_ITEMS
                    ],
                    id="main_nav",
                    selected=DEFAULT_NAV_ID,
                ),
                class_="page-wrap",
            ),
            class_="main",
        ),
        class_="app-shell",
    ),
    title="Egypt: MRV with SISEPUEDE",
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
    # Cheap to construct (just validates the config workbook exists) -- the
    # DB-backed cost object it wraps is built lazily on first calculation.
    state.cb_wrapper.set(cost_benefit_service.build_cb_wrapper(model_attributes, config.CB_CONFIG_XLSX_PATH))

    page_data_input_server("data_input", state)
    page_projects_server("projects", state)
    page_transformations_server("transformations", state)
    page_strategies_server("strategies", state)
    page_run_server("run", state)
    page_output_explorer_server("output_explorer", state)
    page_monitoring_server("validation", state)
    page_cost_benefits_server("cost_benefits", state)
    page_macroeconomic_impacts_server("macroeconomic_impacts", state)
    page_article_6_server("article_6", state)
    page_save_load_server("persistence", state)

    def _current_nav_id() -> str:
        # `"x" in input` checks `is_set()` reactively without raising --
        # calling `input.sidebar_nav()` directly before the client has ever
        # set it raises Shiny's internal SilentException (caught deep inside
        # the output-rendering machinery, never logged, just renders empty),
        # so this check is required, not just a style preference.
        if "sidebar_nav" in input:
            return input.sidebar_nav() or DEFAULT_NAV_ID
        return DEFAULT_NAV_ID

    @reactive.effect
    def _sync_content():
        ui.update_navs("main_nav", selected=_current_nav_id())

    @output
    @render.ui
    def topbar():
        item = NAV_ITEMS_BY_ID[_current_nav_id()]

        status = None
        if item.id == "data_input":
            n_baselines = len(state.baselines.get())
            status = ui.div(
                ui.span(class_="dot"),
                f"{n_baselines} baseline{'s' if n_baselines != 1 else ''} loaded",
                class_="status-pill",
            )

        return ui.div(
            ui.div(
                ui.div(f"{item.group} / {item.label}", class_="topbar-crumb"),
                ui.div(item.label, class_="topbar-title"),
                ui.div(item.description, class_="topbar-desc"),
            ),
            status,
            class_="topbar",
        )

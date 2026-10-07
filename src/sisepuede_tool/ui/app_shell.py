"""Custom sidebar shell (MRV Console), following the Claude Design "Papyrus"
prototype in info/Emissions Modeling Console-4.

Real page switching goes through `ui.navset_hidden` (zero visual chrome,
purely programmatic) wrapping each page's module; the sidebar is hand-built
markup whose links call `window.mrvGoTo(id)`, which highlights the link and
sets the `sidebar_nav` Shiny input; a server-side effect then drives
`ui.update_navs`. Pages can navigate the same way (e.g. "Continue to Run").

The "Advanced options" switch in the sidebar footer toggles the
`advanced-on` class on <body> client-side (everything marked `.adv-only` is
then shown, see theme.css) and mirrors its value into `state.advanced_mode`
for server-side logic.
"""

import logging
import os
import pathlib

from shiny import reactive, render, ui

from sisepuede_tool import config
from sisepuede_tool.services import (
    catalog_service,
    cost_benefit_service,
    library_service,
    pathway_service,
    projects_service,
    run_service,
    transformer_metadata_service,
)
from sisepuede_tool.ui.components import result_charts
from sisepuede_tool.ui.page_article_6 import page_article_6_server, page_article_6_ui
from sisepuede_tool.ui.page_cost_benefits import page_cost_benefits_server, page_cost_benefits_ui
from sisepuede_tool.ui.page_data_input import page_data_input_server, page_data_input_ui
from sisepuede_tool.ui.page_macroeconomic_impacts import (
    page_macroeconomic_impacts_server,
    page_macroeconomic_impacts_ui,
)
from sisepuede_tool.ui.page_monitoring import page_monitoring_server, page_monitoring_ui
from sisepuede_tool.ui.page_emissions import (
    page_emissions_server,
    page_emissions_ui,
)
from sisepuede_tool.ui.page_pathways import page_pathways_server, page_pathways_ui
from sisepuede_tool.ui.page_projects import page_projects_server, page_projects_ui
from sisepuede_tool.ui.page_run import page_run_server, page_run_ui
from sisepuede_tool.ui.page_save_load import page_save_load_server, page_save_load_ui
from sisepuede_tool.ui.shell_nav import DEFAULT_NAV_ID, NAV_GROUPS, NAV_ITEMS, NAV_ITEMS_BY_ID
from sisepuede_tool.ui.state import new_app_state

# SISEPUEDE_TOOL_LOG_LEVEL=DEBUG shows e.g. why the editor marks a transformation as edited
logging.basicConfig(format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logging.getLogger("sisepuede_tool").setLevel(os.environ.get("SISEPUEDE_TOOL_LOG_LEVEL", "INFO").upper())

_THEME_CSS_PATH = pathlib.Path(__file__).resolve().parent.parent / "resources" / "theme.css"

_PAGE_UI_FNS = {
    "data_input": page_data_input_ui,
    "projects": page_projects_ui,
    "pathways": page_pathways_ui,
    "run": page_run_ui,
    "output_explorer": page_emissions_ui,  # nav id kept from the old explorer
    "validation": page_monitoring_ui,
    "cost_benefits": page_cost_benefits_ui,
    "macroeconomic_impacts": page_macroeconomic_impacts_ui,
    "article_6": page_article_6_ui,
    "persistence": page_save_load_ui,
}

_SHELL_JS = """
window.mrvGoTo = function(id) {
  document.querySelectorAll('.nav-item').forEach(function(el) {
    el.classList.toggle('active', el.dataset.nav === id);
  });
  Shiny.setInputValue('sidebar_nav', id, {priority: 'event'});
  var main = document.querySelector('.main');
  if (main) { main.scrollTop = 0; }
  window.scrollTo(0, 0);
};
$(document).on('shiny:inputchanged', function(e) {
  if (e.name === 'advanced_mode') {
    document.body.classList.toggle('advanced-on', !!e.value);
  }
});
// ⓘ info bubbles (ui/components/info_tip.py): click toggles, click elsewhere closes.
// preventDefault so an ⓘ inside a <label> doesn't also toggle its input.
$(document).on('click', '.info-tip', function(e) {
  e.preventDefault();
  e.stopPropagation();
  var open = this.classList.contains('open');
  document.querySelectorAll('.info-tip.open').forEach(function(el) { el.classList.remove('open'); });
  if (!open) {
    this.classList.add('open');
    var r = this.getBoundingClientRect();
    this.classList.toggle('tip-left', r.left > window.innerWidth - 300);
  }
});
$(document).on('click keydown', function(e) {
  if (e.type === 'keydown' && e.key !== 'Escape') { return; }
  if (!$(e.target).closest('.info-tip').length) {
    document.querySelectorAll('.info-tip.open').forEach(function(el) { el.classList.remove('open'); });
  }
});
// The sidebar is an icon rail that opens on hover; the pin keeps it open
// (remembered per browser).
window.mrvTogglePin = function() {
  var on = !document.body.classList.contains('sidebar-pinned');
  document.body.classList.toggle('sidebar-pinned', on);
  var btn = document.querySelector('.pin-btn');
  if (btn) { btn.setAttribute('aria-pressed', on ? 'true' : 'false'); }
  try { localStorage.setItem('mrv.sidebarPinned', on ? '1' : '0'); } catch (err) {}
};
$(function() {
  var pinned = false;
  try { pinned = localStorage.getItem('mrv.sidebarPinned') === '1'; } catch (err) {}
  document.body.classList.toggle('sidebar-pinned', pinned);
  var btn = document.querySelector('.pin-btn');
  if (btn) { btn.setAttribute('aria-pressed', pinned ? 'true' : 'false'); }
});
"""

_EGYPT_FLAG_SVG = (
    '<svg viewBox="0 0 30 20" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">'
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

_PIN_SVG = (
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" '
    'stroke-linejoin="round" aria-hidden="true"><path d="M9 4h6l-1 6 3 3H7l3-3z"/><path d="M12 13v7"/></svg>'
)


def _nav_link(item, active: bool) -> ui.Tag:
    if item.step is not None:
        lead = ui.output_ui(f"navstep_{item.id}", inline=True)
        text = ui.span(
            ui.span(item.label),
            ui.output_text(f"navmeta_{item.id}", inline=True),
            class_="nav-text",
        )
    else:
        lead = ui.HTML(item.icon_svg)
        text = ui.span(item.label, class_="nav-text")
    return ui.tags.a(
        lead,
        text,
        class_="nav-item active" if active else "nav-item",
        href="javascript:void(0)",
        onclick=f"mrvGoTo('{item.id}'); return false;",
        **{"data-nav": item.id},
    )


def _build_sidebar() -> ui.Tag:
    groups = []
    for group in NAV_GROUPS:
        items = [item for item in NAV_ITEMS if item.group == group and not item.hidden]
        groups.append(
            ui.div(
                ui.div(group, class_="nav-group-label"),
                *[_nav_link(item, item.id == DEFAULT_NAV_ID) for item in items],
                class_="nav-group",
            )
        )

    return ui.tags.aside(
        ui.div(ui.span(ui.HTML(_EGYPT_FLAG_SVG), class_="flag-icon"), class_="rail-mark", title="Egypt"),
        ui.div(
            ui.div(
                ui.div("MRV Console", class_="brand-eyebrow"),
                ui.tags.button(
                    ui.HTML(_PIN_SVG),
                    type="button",
                    class_="pin-btn",
                    title="Keep the menu open",
                    onclick="mrvTogglePin()",
                    **{"aria-pressed": "false", "aria-label": "Keep the menu open"},
                ),
                class_="brand-row",
            ),
            ui.div(
                ui.span(ui.span(ui.HTML(_EGYPT_FLAG_SVG), class_="flag-icon"), "Egypt", class_="region-name"),
                ui.span("EGY", class_="mono"),
                class_="region-box",
            ),
            class_="brand",
        ),
        ui.tags.nav(*groups),
        ui.div("ADV", class_="rail-adv", title="Advanced options are on"),
        ui.div(
            ui.input_switch("advanced_mode", "Advanced options", value=False),
            ui.div("Shows every sisepuede parameter and setting.", class_="foot-note"),
            ui.div("SISEPUEDE engine · CB module", class_="foot-note"),
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
        ui.tags.script(ui.HTML(_SHELL_JS)),
    )


app_ui = ui.page_fluid(
    _head(),
    ui.div(
        _build_sidebar(),
        ui.div(
            ui.output_ui("topbar"),
            ui.navset_hidden(
                *[
                    ui.nav_panel(
                        item.label,
                        ui.div(_PAGE_UI_FNS[item.id](item.id), class_="page-wrap flush" if item.flush else "page-wrap"),
                        value=item.id,
                    )
                    for item in NAV_ITEMS
                ],
                id="main_nav",
                selected=DEFAULT_NAV_ID,
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
    result_charts.use_model_subsector_colors(model_attributes)
    state.transformer_metadata.set(transformer_metadata_service.load_catalog())
    # default project -> NDC transformation links (by transformer); unusable items are
    # unlinked once the library is checked against sisepuede (first baseline)
    state.project_links.set(
        projects_service.default_links(
            projects_service.load_project_records_cached(config.PROJECTS_XLSX_PATH), library_service.load_library()
        )
    )
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
    page_pathways_server("pathways", state)
    page_run_server("run", state)
    page_emissions_server("output_explorer", state)
    page_monitoring_server("validation", state)
    page_cost_benefits_server("cost_benefits", state)
    page_macroeconomic_impacts_server("macroeconomic_impacts", state)
    page_article_6_server("article_6", state)
    page_save_load_server("persistence", state)

    @reactive.effect
    def _sync_advanced_mode():
        state.advanced_mode.set(bool(input.advanced_mode()))

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
        ui.update_navset("main_nav", selected=_current_nav_id())

    # ---- workflow step badges and meta lines ----

    def _n_pathways() -> int:
        return len(pathway_service.pathway_ids(state.strategies_map.get()))

    def _step_done(nav_id: str) -> bool:
        if nav_id == "data_input":
            return bool(state.baselines.get())
        if nav_id == "pathways":
            return any(e.transformation_codes for sid, e in state.strategies_map.get().items() if sid != 0)
        if nav_id == "run":
            return any(r.ok for r in state.run_results.get().values())
        return False

    def _make_step_badge(item):
        @output(id=f"navstep_{item.id}")
        @render.ui
        def _badge():
            done = _step_done(item.id)
            return ui.span("✓" if done else str(item.step), class_="nav-step done" if done else "nav-step")

    def _make_step_meta(item):
        @output(id=f"navmeta_{item.id}")
        @render.text
        def _meta():
            if item.id == "data_input":
                baselines = state.baselines.get()
                if not baselines:
                    return "No baseline yet"
                return next(iter(baselines.values())).label + (f" +{len(baselines) - 1}" if len(baselines) > 1 else "")
            if item.id == "pathways":
                n = _n_pathways()
                tx = state.transformations_obj.get()
                state.transformations_revision.get()
                n_tx = 0 if tx is None else len(tx.dict_transformations) - 1
                return f"{n} pathway{'s' if n != 1 else ''} · {n_tx} transformations"
            if item.id == "run":
                history = state.run_history.get()
                if not history:
                    return "Not run yet"
                last = history[0]
                n_ok = sum(1 for h in history if h["batch"] == last["batch"] and h["ok"])
                return f"Last run {last['at']:%H:%M} · {n_ok} ok"
            return ""

    for item in NAV_ITEMS:
        if item.step is not None:
            _make_step_badge(item)
            _make_step_meta(item)

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
                ui.div(item.crumb or item.group, class_="topbar-crumb"),
                ui.div(item.label, class_="topbar-title"),
                ui.div(item.description, class_="topbar-desc"),
            ),
            status,
            class_="topbar",
        )

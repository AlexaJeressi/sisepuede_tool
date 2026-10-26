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

UI language (services/i18n.py): `app_ui` is built in the language of `?lang=`
(remembered per browser). The topbar selector switches in place, without a
reload: it sets the `ui_lang` input, the server re-renders its outputs and
sends the page's text in the new language, and `mrvApplyLang` swaps the text
marked by i18n.mark() and sets `<html lang dir>`. theme.css uses logical
properties and theme-rtl.css only applies under dir="rtl", so flipping `dir`
mirrors the layout.
"""

import logging
import os
import pathlib

from shiny import reactive, render, ui

from sisepuede_tool import config
from sisepuede_tool.services import (
    catalog_service,
    cost_benefit_service,
    i18n,
    library_service,
    pathway_service,
    projects_service,
    run_service,
    transformer_metadata_service,
)
from sisepuede_tool.ui.components import result_charts
from sisepuede_tool.ui.components import chart_export, hover_panel
from sisepuede_tool.ui.page_article_6 import page_article_6_server, page_article_6_ui
from sisepuede_tool.ui.page_cost_benefits import page_cost_benefits_server, page_cost_benefits_ui
from sisepuede_tool.ui.page_data_input import page_data_input_server, page_data_input_ui
from sisepuede_tool.ui.page_jobs import page_jobs_server, page_jobs_ui
from sisepuede_tool.ui.page_mac import page_mac_server, page_mac_ui
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
_THEME_RTL_CSS_PATH = _THEME_CSS_PATH.with_name("theme-rtl.css")
# plotly legend clicks sent to the server (Article 6), see the file
_LEGEND_EVENTS_JS = _THEME_CSS_PATH.with_name("legend_events.js").read_text()

_PAGE_UI_FNS = {
    "data_input": page_data_input_ui,
    "projects": page_projects_ui,
    "pathways": page_pathways_ui,
    "run": page_run_ui,
    "output_explorer": page_emissions_ui,  # nav id kept from the old explorer
    "validation": page_monitoring_ui,
    "cost_benefits": page_cost_benefits_ui,
    "mac": page_mac_ui,
    "macroeconomic_impacts": page_macroeconomic_impacts_ui,
    "article_6": page_article_6_ui,
    "jobs": page_jobs_ui,
    "persistence": page_save_load_ui,
}

# Runs first in <head>: back to the language this browser picked last (when the
# URL has none), and the text direction before the body renders.
_EARLY_JS = """
(function() {
  var url = new URL(window.location.href);
  if (!url.searchParams.has('lang')) {
    var saved = null;
    try { saved = localStorage.getItem('mrv.lang'); } catch (err) {}
    if (saved && saved !== '%(default)s') {
      url.searchParams.set('lang', saved);
      window.location.replace(url.toString());
      return;
    }
  }
  document.documentElement.dir = '%(dir)s';
})();
"""

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
    // near the left edge (e.g. the main column under RTL) the bubble opens rightward
    if (r.right < 300) { this.classList.add('tip-right'); }
  }
});
$(document).on('click keydown', function(e) {
  if (e.type === 'keydown' && e.key !== 'Escape') { return; }
  if (!$(e.target).closest('.info-tip').length) {
    document.querySelectorAll('.info-tip.open').forEach(function(el) { el.classList.remove('open'); });
  }
});
// Language selector (topbar): switch in place; the server answers with
// mrv-i18n (the page text in that language). The URL keeps the choice for a reload.
window.mrvSetLang = function(sel) {
  try { localStorage.setItem('mrv.lang', sel.value); } catch (err) {}
  var url = new URL(window.location.href);
  url.searchParams.set('lang', sel.value);
  window.history.replaceState(null, '', url.toString());
  Shiny.setInputValue('ui_lang', sel.value, {priority: 'event'});
};
// CLDR plural categories, as services/i18n.plural_category
function mrvPlural(lang, n) {
  if (lang === 'ar') {
    var m = n % 100;
    if (n === 0) return 'zero';
    if (n === 1) return 'one';
    if (n === 2) return 'two';
    if (m >= 3 && m <= 10) return 'few';
    if (m >= 11 && m <= 99) return 'many';
    return 'other';
  }
  return n === 1 ? 'one' : 'other';
}
window.mrvApplyLang = function(msg) {
  var S = msg.strings, rtl = msg.dir === 'rtl';
  function text(key, n, args) {
    var t = S[key];
    if (n !== undefined && n !== null && n !== '') {
      n = Number(n);
      t = S[key + '.' + mrvPlural(msg.lang, n)] || S[key + '.other'] || S[key + '.one'];
      args = Object.assign({n: n}, args || {});
    }
    if (t === undefined) return null;
    return t.replace(/\\{(\\w+)(:[^}]*)?\\}/g, function(all, name, spec) {
      if (!args || !(name in args)) return all;
      var v = args[name];
      if (spec === ':,' && typeof v === 'number') v = v.toLocaleString('en-US');
      return rtl ? '\\u2068' + v + '\\u2069' : String(v);
    });
  }
  function args(el, attr) {
    var raw = el.getAttribute(attr + '-args');
    try { return raw ? JSON.parse(raw) : null; } catch (err) { return null; }
  }
  document.documentElement.lang = msg.lang;
  document.documentElement.dir = msg.dir;
  document.querySelectorAll('[data-i18n]').forEach(function(el) {
    var t = text(el.getAttribute('data-i18n'), el.getAttribute('data-i18n-n'), args(el, 'data-i18n'));
    if (t !== null) el.textContent = t;
  });
  document.querySelectorAll('[data-i18n-attrs]').forEach(function(el) {
    el.getAttribute('data-i18n-attrs').split(' ').forEach(function(attr) {
      var p = 'data-i18n-' + attr;
      var t = text(el.getAttribute(p), el.getAttribute(p + '-n'), args(el, p));
      if (t !== null) el.setAttribute(attr, t);
    });
  });
  // selectize keeps its own copy of the option labels
  document.querySelectorAll('select[data-i18n-options]').forEach(function(sel) {
    var keys = JSON.parse(sel.getAttribute('data-i18n-options'));
    var sz = sel.selectize;
    Object.keys(keys).forEach(function(value) {
      var t = text(keys[value]);
      if (t === null) return;
      if (sz && sz.options[value]) { sz.updateOption(value, Object.assign({}, sz.options[value], {label: t, text: t})); }
    });
  });
};
$(document).on('shiny:connected', function() {
  Shiny.addCustomMessageHandler('mrv-i18n', window.mrvApplyLang);
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
            ui.span(i18n.t(f"nav.{item.id}.label")),
            ui.output_text(f"navmeta_{item.id}", inline=True),
            class_="nav-text",
        )
    else:
        lead = ui.HTML(item.icon_svg)
        text = ui.span(i18n.t(f"nav.{item.id}.label"), class_="nav-text")
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
                ui.div(i18n.t(f"nav.groups.{group}"), class_="nav-group-label"),
                *[_nav_link(item, item.id == DEFAULT_NAV_ID) for item in items],
                class_="nav-group",
            )
        )

    return ui.tags.aside(
        ui.div(ui.span(ui.HTML(_EGYPT_FLAG_SVG), class_="flag-icon"), class_="rail-mark", title=i18n.t("shell.country")),
        ui.div(
            ui.div(
                ui.div(i18n.t("shell.console"), class_="brand-eyebrow"),
                ui.tags.button(
                    ui.HTML(_PIN_SVG),
                    type="button",
                    class_="pin-btn",
                    title=i18n.t("shell.pin"),
                    onclick="mrvTogglePin()",
                    **{"aria-pressed": "false", "aria-label": i18n.t("shell.pin")},
                ),
                class_="brand-row",
            ),
            ui.div(
                ui.span(ui.span(ui.HTML(_EGYPT_FLAG_SVG), class_="flag-icon"), i18n.t("shell.country"), class_="region-name"),
                ui.span("EGY", class_="mono"),
                class_="region-box",
            ),
            class_="brand",
        ),
        ui.tags.nav(*groups),
        ui.div("ADV", class_="rail-adv", title=i18n.t("shell.advanced_on")),
        ui.div(
            ui.input_switch("advanced_mode", i18n.t("shell.advanced"), value=False),
            ui.div(i18n.t("shell.advanced_note"), class_="foot-note"),
            ui.div(i18n.t("shell.engine_note"), class_="foot-note"),
            class_="sidebar-foot",
        ),
        class_="sidebar",
    )


def _head(lang: str) -> ui.Tag:
    early_js = _EARLY_JS % {"default": i18n.DEFAULT_LANG, "dir": i18n.LANGUAGES[lang].dir}
    return ui.head_content(
        ui.tags.script(ui.HTML(early_js)),
        ui.tags.link(rel="preconnect", href="https://fonts.googleapis.com"),
        ui.tags.link(rel="preconnect", href="https://fonts.gstatic.com", crossorigin=""),
        ui.tags.link(
            href=(
                "https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700"
                "&family=IBM+Plex+Mono:wght@400;500;600"
                # Arabic glyphs; theme.css lists it as a fallback, so it only downloads where Arabic text shows
                "&family=IBM+Plex+Sans+Arabic:wght@400;500;600;700&display=swap"
            ),
            rel="stylesheet",
        ),
        ui.include_css(_THEME_CSS_PATH),
        ui.include_css(_THEME_RTL_CSS_PATH),  # every rule is scoped to dir="rtl"
        ui.tags.script(ui.HTML(_SHELL_JS)),
        ui.tags.script(ui.HTML(chart_export.JS)),
        ui.tags.script(ui.HTML(hover_panel.JS)),
        ui.tags.script(ui.HTML(_LEGEND_EVENTS_JS)),
    )


def app_ui(request):
    lang = i18n.from_query(request.url.query)
    with i18n.use(lang, static=True):
        return i18n.mark(_page(lang))


def _page(lang: str) -> ui.Tag:
    return ui.page_fluid(
        _head(lang),
        chart_export.dialog(),
        ui.div(
            _build_sidebar(),
            ui.div(
                ui.output_ui("topbar"),
                ui.navset_hidden(
                    *[
                        ui.nav_panel(
                            i18n.t(f"nav.{item.id}.label"),
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
        title=i18n.t("shell.title"),
        lang=lang,
    )


def _lang_select(lang: str) -> ui.Tag:
    return ui.tags.select(
        *[
            ui.tags.option(language.name, value=code, lang=code, **({"selected": ""} if code == lang else {}))
            for code, language in i18n.LANGUAGES.items()
        ],
        class_="lang-select",
        onchange="mrvSetLang(this)",
        title=i18n.t("shell.language", lang),
        **{"aria-label": i18n.t("shell.language", lang)},
    )


def server(input, output, session):
    chosen_lang = reactive.Value(None)  # set by the topbar selector; until then, the page's ?lang=

    @reactive.calc
    def lang() -> str:
        return chosen_lang.get() or i18n.from_query(session.clientdata.url_search())

    @reactive.effect
    @reactive.event(input.ui_lang)
    async def _switch_language():
        new = i18n.normalize(input.ui_lang())
        chosen_lang.set(new)
        await session.send_custom_message(
            "mrv-i18n", {"lang": new, "dir": i18n.LANGUAGES[new].dir, "strings": i18n.client_strings(new)}
        )

    def session_lang() -> str:
        # inside i18n.keep_inputs builds, the language without a reactive dependency
        return i18n.pinned() or lang()

    state = new_app_state(lang=session_lang)
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
    page_mac_server("mac", state)
    page_macroeconomic_impacts_server("macroeconomic_impacts", state)
    page_article_6_server("article_6", state)
    page_jobs_server("jobs", state)
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
                    return i18n.t("nav.meta.no_baseline", lang())
                return next(iter(baselines.values())).label + (f" +{len(baselines) - 1}" if len(baselines) > 1 else "")
            if item.id == "pathways":
                n = _n_pathways()
                tx = state.transformations_obj.get()
                state.transformations_revision.get()
                n_tx = 0 if tx is None else len(tx.dict_transformations) - 1
                return f"{i18n.tn('nav.meta.pathways', n, lang())} · {i18n.tn('nav.meta.transformations', n_tx, lang())}"
            if item.id == "run":
                history = state.run_history.get()
                if not history:
                    return i18n.t("nav.meta.not_run", lang())
                last = history[0]
                n_ok = sum(1 for h in history if h["batch"] == last["batch"] and h["ok"])
                return i18n.t("nav.meta.last_run", lang(), time=f"{last['at']:%H:%M}", ok=n_ok)
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
                i18n.tn("shell.baselines_loaded", n_baselines, lang()),
                class_="status-pill",
            )

        crumb = i18n.t(f"nav.{item.id}.crumb", lang(), default="") or i18n.t(f"nav.groups.{item.group}", lang())
        return ui.div(
            ui.div(
                ui.div(crumb, class_="topbar-crumb"),
                ui.div(i18n.t(f"nav.{item.id}.label", lang()), class_="topbar-title"),
                ui.div(i18n.t(f"nav.{item.id}.description", lang()), class_="topbar-desc"),
            ),
            ui.div(status, _lang_select(lang()), class_="topbar-tools"),
            class_="topbar",
        )

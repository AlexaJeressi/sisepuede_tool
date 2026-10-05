"""Pathways page: transformer browser, transformation editor and pathway
tray in three columns (Claude Design prototype, "Pathways").

* Left: transformers grouped by sector. Opening one lists its
  transformations (the user's, plus the NDC news library) and "+ New".
* Centre: the transformer view (description, emissions if used alone,
  library default, "what this moves in the model", how it adds up in the
  pathway) or the transformation editor (basic controls; everything else
  under the sidebar's Advanced options).
* Right: the active pathway's contents, grouped by transformer.

"Pathway" is the UI name for a sisepuede Strategy (services/pathway_service).
Business as usual (strategy 0) is implicit and not shown as a tab.

Clicks in the hand-built HTML (rows, tabs, footer buttons) all go through
one namespaced input, `ui_event`, carrying {"type", "value"}; `_on_event`
dispatches them. The editor form is rendered only when something is opened
(`editor_nonce`), so status/footers can re-render without resetting inputs.
"""

import json
import logging
import math
from typing import Any, Dict, List, Optional

from shiny import module, reactive, render, ui
from shiny.module import resolve_id

from sisepuede_tool.models.param_spec import WidgetKind
from sisepuede_tool import config
from sisepuede_tool.services import (
    pathway_service,
    projects_service,
    ramp_service,
    transformation_service,
    transformer_metadata_service,
    widget_metadata,
)
from sisepuede_tool.ui.components import charts, param_widget
from sisepuede_tool.ui.state import AppState

logger = logging.getLogger(__name__)


_EMISSION_LABELS = {
    "decreases": ("↓ Lower", "dir-down"),
    "increases": ("↑ Higher", "dir-up"),
    "no_change": ("≈ No clear change", "dir-flat"),
    "depends_on_grid": ("≈ Depends on the grid", "dir-mixed"),
    "needs_electricity_model": ("Needs the electricity model", "dir-mixed"),
}
_DIRECTION_LABELS = {
    "increases": ("↑ increases", "dir-up"),
    "decreases": ("↓ decreases", "dir-down"),
    "shifts": ("↕ shifts", "dir-mixed"),
    "no_change": ("→ no change", "dir-flat"),
}


def _sector_class(sector: Optional[str]) -> str:
    return "sector-" + (sector or "other").lower().replace(" ", "-")


# Policy areas used to group and filter transformers on the left: coarser
# than sisepuede subsectors, closer to how NDC chapters are organised.
# (label, sector colour, subsector codes)
_AREAS = [
    ("Electricity & fuels", "Energy", ("ENTC", "ENFU", "FGTV", "CCSQ")),
    ("Transport", "Energy", ("TRNS", "TRDE")),
    ("Buildings", "Energy", ("SCOE",)),
    ("Industry", "IPPU", ("INEN", "IPPU")),
    ("Agriculture & food", "AFOLU", ("AGRC", "LVST", "LSMM", "SOIL")),
    ("Land & forests", "AFOLU", ("LNDU", "FRST")),
    ("Waste", "Circular Economy", ("WASO", "WALI", "TRWW")),
    ("Cross-cutting", "other", ("GNRL",)),
]
# cross-sector (PFLO) transformers go where they act
_AREA_OVERRIDES = {
    "TFR:PFLO:INC_HEALTHIER_DIETS": "Agriculture & food",
    "TFR:PFLO:INC_IND_CCS": "Industry",
}
_AREA_OF_SUBSECTOR = {abv: label for label, _, abvs in _AREAS for abv in abvs}
_AREA_SECTOR = {label: sector for label, sector, _ in _AREAS}
_AREA_ORDER = [label for label, _, _ in _AREAS]


def _area_of(code: str) -> str:
    if code in _AREA_OVERRIDES:
        return _AREA_OVERRIDES[code]
    parts = code.split(":")
    return _AREA_OF_SUBSECTOR.get(parts[1] if len(parts) > 2 else "", "Cross-cutting")


def _codes_by_area(tk) -> Dict[str, List[str]]:
    """{area: transformer codes}, areas in display order, codes in catalog order."""
    out: Dict[str, List[str]] = {a: [] for a in _AREA_ORDER}
    for codes in tk.get_tkernel_codes_by_sector().values():
        for code in codes:
            if code != tk.code_baseline:
                out[_area_of(code)].append(code)
    return {a: codes for a, codes in out.items() if codes}


def _strip_news_prefix(name: str) -> str:
    if name and name.startswith("NEWS_") and " - " in name:
        return name.split(" - ", 1)[1]
    return name


@module.ui
def page_pathways_ui():
    return ui.div(
        ui.div(ui.output_ui("strip"), class_="pw-strip"),
        ui.div(
            ui.div(
                ui.div(ui.output_ui("sector_chips"), class_="pw-pad", style="padding-bottom:0"),
                ui.div(ui.input_text("search", None, placeholder="Search transformers…"), class_="pw-pad"),
                ui.div(ui.output_ui("transformer_list"), class_="pw-pad", style="padding-top:0"),
                class_="pw-col pw-left",
            ),
            ui.div(
                ui.div(ui.output_ui("center_form"), ui.output_ui("center_dynamic"), class_="pw-center-body"),
                ui.output_ui("center_footer"),
                class_="pw-col pw-center",
            ),
            ui.div(ui.output_ui("tray"), class_="pw-col pw-right"),
            class_="pw-grid",
        ),
        class_="pw-root",
    )


@module.server
def page_pathways_server(input, output, session, state: AppState):
    ev_id = resolve_id("ui_event")

    open_transformer = reactive.Value(None)  # transformer code
    # editor: None, or {"mode": "new"|"edit", "transformer": code, "code": tx code|None,
    #                   "params": dict, "name": str, "description": str, "basis": str|None}
    editor = reactive.Value(None)
    editor_nonce = reactive.Value(0)
    expanded = reactive.Value(set())  # transformer codes expanded in the left list
    chips_open = reactive.Value(True)  # the subsector filter block is expanded
    area_filter = reactive.Value(frozenset())  # policy areas (_AREAS) shown in the left list; empty = all

    overrides = widget_metadata.load_overrides(widget_metadata.default_overrides_path())

    # ------------------------------------------------------------------ helpers

    def _ev(kind: str, value: Any = "") -> str:
        payload = json.dumps({"type": kind, "value": value})
        return f"Shiny.setInputValue({json.dumps(ev_id)}, {payload}, {{priority: 'event'}}); return false;"

    def _btn(label, kind, value="", cls="btn btn-inline", title=None):
        return ui.tags.button(label, class_=cls, onclick=_ev(kind, value), type="button", title=title)

    @reactive.calc
    def ctx():
        """Everything the renderers need, recomputed when the model objects change."""
        tk = state.transformers_catalog.get()
        tx = state.transformations_obj.get()
        state.transformations_revision.get()
        ma = state.model_attributes.get()
        if tk is None or tx is None:
            return None
        years = ramp_service.model_years(ma)
        return {
            "tk": tk,
            "tx": tx,
            "ma": ma,
            "years": years,
            "default_ramp": ramp_service.catalog_default_ramp(tk),
            "by_transformer": pathway_service.transformations_by_transformer(tx),
            "library": {i.code: i for i in state.library_items.get()},
        }

    @reactive.calc
    def catalog_meta():
        return state.transformer_metadata.get()

    def card(code: str) -> Dict[str, Any]:
        c = ctx()
        return transformer_metadata_service.get_card(code, catalog_meta(), tk=c["tk"] if c else None)

    def active_pathway() -> Optional[int]:
        pathways = state.strategies_map.get()
        sid = state.active_pathway_id.get()
        ids = pathway_service.pathway_ids(pathways)
        if sid in ids:
            return sid
        return ids[0] if ids else None

    def pathway_name(sid: Optional[int]) -> str:
        if sid is None:
            return ""
        return state.strategies_map.get()[sid].strategy.name

    def specs_for(transformer_code: str):
        c = ctx()
        return widget_metadata.build_param_specs(c["tk"].get_tkernel(transformer_code), c["ma"], c["tk"], overrides)

    def ramp_values(params: Dict[str, Any]) -> List[float]:
        c = ctx()
        ramp = params.get("vec_implementation_ramp")
        ramp = ramp if isinstance(ramp, dict) else None
        return list(ramp_service.ramp_curve(ramp or {}, len(c["years"]), c["default_ramp"]))

    def tx_summary(code: str) -> str:
        c = ctx()
        t = c["tx"].dict_transformations[code]
        cd = card(t.transformer_code)
        return pathway_service.summarize(t, cd["magnitude_param"], c["years"], c["default_ramp"], cd["magnitude_default"])

    def tx_label(code: str) -> str:
        t = ctx()["tx"].dict_transformations[code]
        return _strip_news_prefix(t.name or code)

    def basis_of(code: Optional[str]) -> Optional[str]:
        if code is None:
            return None
        item = ctx()["library"].get(code)
        if item is None:
            linked = projects_service.projects_for_transformation(code, state.project_links.get())
            return f"Based on project: {', '.join(linked)}" if linked else None
        project = item.project.get("project") or item.name
        status = item.project.get("status")
        return f"Based on project: {project}" + (f" · {status}" if status else "")

    def open_editor(
        mode: str, transformer_code: str, code: Optional[str] = None, params=None, name="", description="", link_project=None
    ):
        editor.set(
            {
                "mode": mode,
                "transformer": transformer_code,
                "code": code,
                "params": dict(params or {}),
                "name": name,
                "description": description or "",
                "basis": basis_of(code) if mode == "edit" else (f"For project: {link_project}" if link_project else None),
                "link_project": link_project,
            }
        )
        open_transformer.set(transformer_code)
        expanded.set(expanded.get() | {transformer_code})
        editor_nonce.set(editor_nonce.get() + 1)

    def open_existing(code: str):
        t = ctx()["tx"].dict_transformations[code]
        open_editor("edit", t.transformer_code, code, t.dict_parameters, t.name or code, t.description or "")

    def set_pathways(pathways):
        state.strategies_map.set(pathways)

    def bump():
        state.transformations_revision.set(state.transformations_revision.get() + 1)

    # ------------------------------------------------------------------ events

    @reactive.effect
    @reactive.event(input.ui_event)
    def _on_event():
        ev = input.ui_event() or {}
        kind, value = ev.get("type"), ev.get("value")
        c = ctx()
        if c is None:
            return
        try:
            if kind == "pathway":
                state.active_pathway_id.set(int(value))
            elif kind == "new_pathway":
                _show_new_pathway_modal()
            elif kind == "rename_pathway":
                _show_rename_modal()
            elif kind == "delete_pathway":
                _show_delete_modal()
            elif kind == "area":
                if not value:
                    area_filter.set(frozenset())
                else:
                    area_filter.set(area_filter.get() ^ {value})
            elif kind == "toggle":
                cur = set(expanded.get())
                cur.symmetric_difference_update({value})
                expanded.set(cur)
                open_transformer.set(value)
                editor.set(None)
            elif kind == "transformer":
                open_transformer.set(value)
                expanded.set(expanded.get() | {value})
                editor.set(None)
            elif kind == "tx":
                open_existing(value)
            elif kind == "new_tx":
                cd = card(value)
                open_editor("new", value, None, {}, f"{cd['name']} (custom)", "")
            elif kind == "duplicate":
                t = c["tx"].dict_transformations[value]
                open_editor("new", t.transformer_code, None, t.dict_parameters, f"{tx_label(value)} (copy)", t.description or "")
            elif kind == "cancel":
                ed = editor.get()
                if ed and ed["mode"] == "edit":
                    open_existing(ed["code"])
                else:
                    editor.set(None)
            elif kind in ("save_library", "create_add", "update", "save_new_add"):
                _save(kind)
            elif kind == "add":
                _require_pathway()
                set_pathways(pathway_service.add_to_pathway(state.strategies_map.get(), c["tx"], active_pathway(), value))
                ui.notification_show(f"Added to {pathway_name(active_pathway())}.", type="message")
            elif kind == "remove":
                sid = active_pathway()
                set_pathways(pathway_service.remove_from_pathway(state.strategies_map.get(), c["tx"], sid, value))
                ui.notification_show(f"Removed from {pathway_name(sid)}.", type="message")
            elif kind == "delete_tx":
                set_pathways(pathway_service.delete_transformation(state.strategies_map.get(), c["tx"], value))
                bump()
                editor.set(None)
                ui.notification_show(f"Deleted {value}.", type="message")
            elif kind == "dry_run":
                _dry_run()
            elif kind == "unlink_project":
                links = dict(state.project_links.get())
                links[value] = None
                state.project_links.set(links)
        except Exception as e:  # show, don't crash the session
            logger.exception("pathways event %s failed", kind)
            ui.notification_show(str(e), type="error", duration=8)

    @reactive.effect
    def _on_request():
        req = state.pathways_request.get()
        if not req:
            return
        with reactive.isolate():
            c = ctx()
            if c is None:
                return
            kind, value = req.get("type"), req.get("value")
            if kind == "tx" and value in c["tx"].dict_transformations:
                open_existing(value)
            elif kind == "new_tx" and value in c["tk"].all_tkernels:
                open_editor("new", value, None, {}, req.get("name") or f"{card(value)['name']} (custom)", "", link_project=req.get("link_project"))
            elif kind == "transformer" and value in c["tk"].all_tkernels:
                open_transformer.set(value)
                expanded.set(expanded.get() | {value})
                editor.set(None)

    def _require_pathway():
        if active_pathway() is None:
            raise ValueError("Create a pathway first (+ New pathway).")

    def _save(kind: str):
        c = ctx()
        ed = editor.get()
        if ed is None:
            return
        specs = specs_for(ed["transformer"])
        try:
            params = param_widget.read_editor_params(input, specs, c["years"])
        except param_widget.ParamReadError as e:
            ui.notification_show(f"Check the values: {e}", type="error", duration=8)
            return
        name = (input.tx_name() or "").strip()
        if not name:
            ui.notification_show("Give the transformation a name.", type="error")
            return
        description = input.tx_description() or ""
        existing = set(c["tx"].dict_transformations)

        if kind == "update":
            code = ed["code"]
        else:
            code = (input.tx_code() or "").strip() or transformation_service.suggest_transformation_code(
                ed["transformer"], existing
            )
            if not code.startswith("TX:"):
                ui.notification_show("Transformation codes must start with 'TX:'.", type="error")
                return
            if code in existing:
                ui.notification_show(f"{code} already exists; choose another code under Advanced options.", type="error")
                return

        transformation = transformation_service.build_transformation(
            code, name, ed["transformer"], params, c["tk"], description=description
        )
        # surface transformer errors now rather than at run time; still saved
        try:
            transformation()
        except Exception as e:
            logger.warning("transformation %s fails on the baseline: %s", code, e)
            ui.notification_show(
                f"Saved, but this transformation fails with the installed sisepuede: {type(e).__name__}: {e}",
                type="warning",
                duration=10,
            )

        pathways = pathway_service.save_transformation(state.strategies_map.get(), c["tx"], transformation)
        message = f"Saved {code} to the library."
        if kind in ("create_add", "save_new_add"):
            _require_pathway()
            pathways = pathway_service.add_to_pathway(pathways, c["tx"], active_pathway(), code)
            message = f"Created {code} and added it to {pathway_name(active_pathway())}."
        elif kind == "update":
            n = len(pathway_service.pathways_using(code, pathways))
            message = f"Updated {code}" + (f" in {n} pathway{'s' if n != 1 else ''}." if n else ".")
        set_pathways(pathways)
        bump()
        if ed.get("link_project"):
            links = dict(state.project_links.get())
            links[ed["link_project"]] = code
            state.project_links.set(links)
            message += f" Linked to project '{ed['link_project']}'."
        ui.notification_show(message, type="message")
        open_existing(code)

    def _dry_run():
        sid = active_pathway()
        baselines = state.baselines.get()
        if sid is None or not baselines:
            return
        baseline = next(iter(baselines.values()))
        entry = state.strategies_map.get()[sid]
        try:
            entry.strategy(df_input=baseline.df)
        except Exception as e:
            ui.notification_show(f"Dry run failed: {type(e).__name__}: {e}", type="error", duration=10)
            return
        ui.notification_show(f"{entry.strategy.name}: all transformations apply cleanly to {baseline.label}.", type="message")

    # ---- pathway modals

    def _show_new_pathway_modal():
        pathways = state.strategies_map.get()
        choices = {"": "Blank"}
        for sid in pathway_service.pathway_ids(pathways):
            entry = pathways[sid]
            choices[str(sid)] = f"Copy of {entry.strategy.name} ({len(entry.transformation_codes)})"
        n = len(pathway_service.pathway_ids(pathways)) + 1
        ui.modal_show(
            ui.modal(
                ui.input_text("new_pathway_name", "Name", placeholder=f"Pathway {n}"),
                ui.input_radio_buttons("new_pathway_from", "Start from", choices=choices, selected=""),
                title="New pathway",
                footer=ui.div(
                    ui.modal_button("Cancel", class_="btn btn-inline"),
                    ui.input_action_button("new_pathway_create", "Create", class_="btn-primary btn-inline"),
                    class_="btn-row",
                ),
                easy_close=True,
            )
        )

    @reactive.effect
    @reactive.event(input.new_pathway_create)
    def _on_create_pathway():
        c = ctx()
        name = (input.new_pathway_name() or "").strip() or f"Pathway {len(pathway_service.pathway_ids(state.strategies_map.get())) + 1}"
        copy_from = input.new_pathway_from()
        try:
            pathways, sid = pathway_service.create_pathway(
                state.strategies_map.get(), c["tx"], name, copy_from=int(copy_from) if copy_from else None
            )
        except ValueError as e:
            ui.notification_show(str(e), type="error")
            return
        set_pathways(pathways)
        state.active_pathway_id.set(sid)
        ui.modal_remove()
        src = f" from {pathways[int(copy_from)].strategy.name}" if copy_from else ""
        ui.notification_show(f"Created {name}{src}.", type="message")

    def _show_rename_modal():
        sid = active_pathway()
        if sid is None:
            return
        ui.modal_show(
            ui.modal(
                ui.input_text("rename_pathway_name", "Name", value=pathway_name(sid)),
                title="Rename pathway",
                footer=ui.div(
                    ui.modal_button("Cancel", class_="btn btn-inline"),
                    ui.input_action_button("rename_pathway_ok", "Rename", class_="btn-primary btn-inline"),
                    class_="btn-row",
                ),
                easy_close=True,
            )
        )

    @reactive.effect
    @reactive.event(input.rename_pathway_ok)
    def _on_rename():
        try:
            set_pathways(
                pathway_service.rename_pathway(state.strategies_map.get(), ctx()["tx"], active_pathway(), input.rename_pathway_name())
            )
        except ValueError as e:
            ui.notification_show(str(e), type="error")
            return
        ui.modal_remove()

    def _show_delete_modal():
        sid = active_pathway()
        if sid is None:
            return
        ui.modal_show(
            ui.modal(
                ui.p(f"Delete the pathway '{pathway_name(sid)}'? Its transformations stay in the library."),
                title="Delete pathway",
                footer=ui.div(
                    ui.modal_button("Cancel", class_="btn btn-inline"),
                    ui.input_action_button("delete_pathway_ok", "Delete", class_="btn-rust btn-inline"),
                    class_="btn-row",
                ),
                easy_close=True,
            )
        )

    @reactive.effect
    @reactive.event(input.delete_pathway_ok)
    def _on_delete_pathway():
        sid = active_pathway()
        set_pathways(pathway_service.delete_pathway(state.strategies_map.get(), sid))
        state.active_pathway_id.set(None)
        ui.modal_remove()

    # ------------------------------------------------------------------ top strip

    @render.ui
    def strip():
        pathways = state.strategies_map.get()
        if ctx() is None:
            return ui.span("Load a baseline to start building pathways.", class_="muted")
        sid_active = active_pathway()
        tabs = []
        for sid in pathway_service.pathway_ids(pathways):
            entry = pathways[sid]
            tabs.append(
                ui.tags.button(
                    entry.strategy.name,
                    ui.span(str(len(entry.transformation_codes)), class_="n"),
                    class_="pw-tab active" if sid == sid_active else "pw-tab",
                    onclick=_ev("pathway", sid),
                    type="button",
                )
            )
        tabs.append(ui.tags.button("+ New pathway", class_="pw-tab new", onclick=_ev("new_pathway"), type="button"))
        baselines = state.baselines.get()
        note = None
        if baselines:
            first = next(iter(baselines.values()))
            note = ui.span(
                ui.span("Catalog from ", class_="muted"),
                ui.span(first.label, class_="mono"),
                class_="small",
                style="white-space:nowrap",
            )
        return ui.TagList(ui.div(*tabs, class_="pw-tabs"), note)

    # ------------------------------------------------------------------ left column

    @render.ui
    def transformer_list():
        c = ctx()
        if c is None:
            return ui.div(
                "No baseline loaded yet.",
                ui.tags.button("Go to Baseline data →", class_="link-btn d-block mt-2", onclick="mrvGoTo('data_input')"),
                class_="info-box",
            )
        query = (input.search() or "").strip().lower()
        pathways = state.strategies_map.get()
        sid = active_pathway()
        in_pathway = set(pathways[sid].transformation_codes) if sid is not None else set()
        by_area = _codes_by_area(c["tk"])
        current_open = open_transformer.get()
        ed = editor.get()
        open_code = ed["code"] if ed else None
        exp = expanded.get()
        shown = area_filter.get()

        blocks = []
        for area, codes in by_area.items():
            if shown and area not in shown:
                continue
            rows = []
            for code in codes:
                cd = card(code)
                haystack = f"{cd['name']} {code} {cd.get('description') or ''}".lower()
                if query and query not in haystack:
                    continue
                txs = c["by_transformer"].get(code, [])
                n_in = sum(1 for t in txs if t in in_pathway)
                if cd.get("status") == "error":
                    meta = "Fails in installed sisepuede"
                elif txs:
                    meta = f"{len(txs)} transformation{'s' if len(txs) != 1 else ''}" + (f" · {n_in} in pathway" if n_in else "")
                else:
                    meta = "No transformations yet"
                is_exp = code in exp or bool(query and txs)
                row = ui.div(
                    ui.span("▾" if is_exp else "▸", class_="chev"),
                    ui.div(ui.div(cd["name"], class_="name"), ui.div(meta, class_="meta"), style="flex:1;min-width:0"),
                    ui.span(class_="dot") if n_in else None,
                    class_="tf-row"
                    + (" active" if code == current_open and ed is None else "")
                    + (" broken" if cd.get("status") == "error" else ""),
                    onclick=_ev("toggle", code),
                    title=code,
                )
                rows.append(row)
                if is_exp:
                    items = []
                    for t_code in txs:
                        lib = c["library"].get(t_code)
                        items.append(
                            ui.div(
                                ui.span(class_="dot" if t_code in in_pathway else "dot off"),
                                ui.span(tx_label(t_code), class_="label", title=t_code),
                                ui.span(f"NEWS {lib.news_number}", class_="tx-src") if lib and lib.news_number else None,
                                ui.span(tx_summary(t_code).split(" · ")[0], class_="spec"),
                                class_="tx-item active" if t_code == open_code else "tx-item",
                                onclick=_ev("tx", t_code),
                            )
                        )
                    items.append(ui.div("+ New transformation", class_="tx-item add", onclick=_ev("new_tx", code)))
                    rows.append(ui.div(*items, class_="tx-list"))
            if rows:
                blocks.append(
                    ui.div(
                        ui.div(ui.span(class_=f"swatch {_sector_class(_AREA_SECTOR[area])}"), area.upper(), class_="section-label"),
                        *rows,
                        class_="tf-sector",
                    )
                )
        if not blocks:
            return ui.div("No transformer matches.", class_="muted small")
        return ui.TagList(
            *blocks,
            ui.div(ui.span(class_="dot"), " In the current pathway", class_="small muted mt-3"),
        )

    @reactive.effect
    @reactive.event(input.chips_open)
    def _on_chips_toggle():
        chips_open.set(bool(input.chips_open()))

    @render.ui
    def sector_chips():
        """Policy-area filter chips, coloured by sector."""
        c = ctx()
        if c is None:
            return None
        by_area = _codes_by_area(c["tk"])
        shown = area_filter.get()
        chips = [
            ui.tags.button(
                "All",
                type="button",
                class_="sector-chip all" + ("" if shown else " on"),
                onclick=_ev("area", ""),
            )
        ]
        for area, codes in by_area.items():
            subsectors = sorted({code.split(":")[1] for code in codes})
            chips.append(
                ui.tags.button(
                    ui.span(class_=f"swatch {_sector_class(_AREA_SECTOR[area])}"),
                    area,
                    ui.span(str(len(codes)), class_="n"),
                    type="button",
                    title="sisepuede: " + ", ".join(subsectors),
                    class_=f"sector-chip {_sector_class(_AREA_SECTOR[area])}-chip" + (" on" if area in shown else ""),
                    onclick=_ev("area", area),
                    **{"aria-pressed": "true" if area in shown else "false"},
                )
            )
        rows = [ui.div(*chips, class_="chip-row")]
        picked = ", ".join(a for a in _AREA_ORDER if a in shown) if shown else "All"
        return ui.tags.details(
            ui.tags.summary(ui.span("Policy areas", class_="section-label"), ui.span(f" · {picked}", class_="small muted")),
            ui.div(*rows, class_="sector-chips"),
            class_="chip-filter",
            open=chips_open.get(),
            ontoggle=f"Shiny.setInputValue({json.dumps(resolve_id('chips_open'))}, this.open)",
        )

    # ------------------------------------------------------------------ centre: shared pieces

    def _emissions_badge(cd):
        label, cls = _EMISSION_LABELS.get(cd.get("emissions_direction"), ("Not available", "dir-flat"))
        emis = cd.get("emissions") or {}
        pct = emis.get("total_delta_pct")
        detail = "Default settings, 2050, without the electricity model."
        if pct is not None and cd.get("emissions_direction") not in ("needs_electricity_model",):
            detail = f"{pct:+.2f}% of 2050 total · " + detail
        return ui.div(
            ui.div("Emissions if used alone", class_="section-label"),
            ui.div(label, class_=f"v {cls}"),
            ui.div(detail, class_="small muted", style="max-width:220px"),
            class_="emis-badge",
        )

    def _status_notes(cd):
        if cd.get("status") == "error":
            return ui.div(
                ui.tags.b("This transformer fails in the installed sisepuede. "),
                "Transformations that use it will fail when run. ",
                ui.span(cd.get("error") or "", class_="code"),
                class_="warn-box",
            )
        if cd.get("status") == "no_effect_on_baseline":
            return ui.div(
                "With its default settings this transformer does not change the Egypt baseline "
                "(the variables it targets are zero there). Check its parameters under Advanced options.",
                class_="info-box",
            )
        return None

    def _moves_panel(cd, ramp):
        rows = []
        for v in cd.get("top_variables") or []:
            label, cls = _DIRECTION_LABELS.get(v.get("direction"), ("", "dir-flat"))
            code = (v.get("example_fields") or [""])[0]
            rows.append(
                ui.div(
                    ui.div(
                        ui.div(ui.span("input" if v.get("kind") == "input" else "result", class_="kind-tag"), v.get("label"), class_="vname"),
                        ui.div(code, class_="vcode", title=v.get("variable")),
                    ),
                    charts.direction_band(v.get("direction"), ramp),
                    ui.div(label, class_=f"vdir {cls}"),
                    class_="moves-row",
                )
            )
        e_dir = cd.get("emissions_direction")
        e_label, e_cls = _EMISSION_LABELS.get(e_dir, ("Not available", "dir-flat"))
        band_dir = {"decreases": "decreases", "increases": "increases"}.get(e_dir, "no_change")
        sector = cd.get("sector") or ""
        rows.append(
            ui.div(
                ui.div(ui.div("Total emissions", class_="vname"), ui.div(f"main effect in {sector}" if sector else "", class_="vcode")),
                charts.direction_band(band_dir, ramp),
                ui.div(e_label, class_=f"vdir {e_cls}"),
                class_="moves-row emissions",
            )
        )
        if not cd.get("top_variables"):
            rows.insert(0, ui.div("No variable changes found with default settings.", class_="small muted"))
        return ui.div(
            ui.div(
                ui.span("What this moves in the model", class_="section-label"),
                ui.span("Direction and timing only · sizes come from the run", class_="hint"),
                class_="panel-head",
            ),
            *rows,
            ui.div(
                ui.tags.details(
                    ui.tags.summary("Where this comes from", class_="small muted"),
                    ui.div(
                        "Computed by scripts/build_transformer_metadata.py with default parameters on the Egypt "
                        "baseline. 'input' rows are levers the transformer sets; 'result' rows are model outputs "
                        "that move most. Emissions are from a run without the electricity model (NemoMod).",
                        ui.div(cd.get("electricity_model_note") or "", class_="mt-1"),
                        class_="small muted",
                    ),
                ),
                class_="adv-only mt-2",
            ),
            class_="panel",
        )

    def _pair_note(cd):
        pairs = cd.get("pair_with") or []
        sid = active_pathway()
        if not pairs or sid is None:
            return None
        c = ctx()
        in_pathway = set(state.strategies_map.get()[sid].transformation_codes)
        notes = []
        for pair in pairs:
            pair_card = card(pair)
            has = any(t in in_pathway for t in c["by_transformer"].get(pair, []))
            if has:
                notes.append(ui.div(f"✓ {pair_card['name']} is in {pathway_name(sid)}.", class_="ok-box small"))
            else:
                notes.append(
                    ui.div(
                        ui.div(
                            "Moves emissions from the point of use to power plants: the net effect depends on how clean the grid is. ",
                            ui.tags.b(f"{pair_card['name']} is not in {pathway_name(sid)}."),
                        ),
                        ui.tags.button(f"Open {pair_card['name']} →", class_="link-btn mt-1", onclick=_ev("transformer", pair)),
                        class_="warn-box",
                    )
                )
        return ui.TagList(*notes)

    def _adds_up(transformer_code):
        sid = active_pathway()
        if sid is None:
            return None
        c = ctx()
        groups = pathway_service.grouped_pathway(state.strategies_map.get()[sid], c["tx"])
        codes = groups.get(transformer_code, [])
        head = ui.div(
            ui.span(f"How this transformer adds up in {pathway_name(sid)}", class_="section-label"),
            class_="panel-head",
        )
        if not codes:
            return ui.div(head, ui.div(f"No transformations from this transformer in {pathway_name(sid)} yet.", class_="small muted"), class_="panel")
        curves = []
        rows = []
        for i, code in enumerate(codes, 1):
            t = c["tx"].dict_transformations[code]
            curves.append((ramp_values(t.dict_parameters or {}), "main" if len(codes) == 1 else "muted"))
            rows.append(
                ui.div(
                    ui.span(f"{i}.", class_="mono muted", style="width:18px"),
                    ui.span(tx_label(code), class_="label", style="flex:1"),
                    ui.span(tx_summary(code), class_="spec"),
                    class_="tx-item",
                    onclick=_ev("tx", code),
                )
            )
        warning = None
        if len(codes) > 1:
            warning = ui.div(
                ui.tags.b("Applied one after another, in this order. "),
                "sisepuede runs each transformation on the result of the previous one, so a later one can "
                "overwrite or compound an earlier one depending on the parameter type. How several "
                "transformations of one transformer should combine is not defined yet.",
                class_="warn-box",
            )
        return ui.div(
            head,
            *rows,
            warning,
            ui.div(charts.ramp_chart(curves, c["years"], width=600, height=130, fill_main=len(codes) == 1), class_="ramp-chart mt-2"),
            class_="panel",
        )

    def _project_panel(code):
        links = state.project_links.get()
        linked = projects_service.projects_for_transformation(code, links)
        records = {r["name"]: r for r in _projects().to_dict("records")}
        rows = []
        for name in linked:
            r = records.get(name, {})
            facts = " · ".join(str(x) for x in (r.get("status"), r.get("investment")) if x)
            rows.append(
                ui.div(
                    ui.div(ui.div(name, style="font-weight:500"), ui.div(facts, class_="small muted")),
                    ui.tags.button("Unlink", class_="link-btn danger", onclick=_ev("unlink_project", name)),
                    class_="btn-row",
                    style="justify-content:space-between;flex-wrap:nowrap;padding:6px 0;border-top:1px solid var(--border-soft)",
                )
            )
        item = ctx()["library"].get(code)
        sources = []
        if item is not None and item.citations:
            sources = [
                ui.tags.details(
                    ui.tags.summary("Sources", class_="small muted mt-1"),
                    *[ui.tags.a(u, href=u, target="_blank", class_="small d-block", style="color:var(--accent);word-break:break-all") for u in item.citations],
                )
            ]
        transformer_code = ctx()["tx"].dict_transformations[code].transformer_code
        candidates = {}
        for name, r in records.items():
            if name in linked:
                continue
            group = "Same transformer" if r.get("transformer_code") == transformer_code else "Other projects"
            candidates.setdefault(group, {})[name] = name + (f" (now: {links[name]})" if links.get(name) else "")
        link_ui = None
        if candidates:
            link_ui = ui.tags.details(
                ui.tags.summary("+ Link project", class_="link-btn mt-1", style="list-style:none;cursor:pointer"),
                ui.div(
                    ui.input_select("link_project_select", None, choices=dict(sorted(candidates.items(), key=lambda kv: kv[0] != "Same transformer"))),
                    ui.input_action_button("link_project_btn", "Link", class_="btn-inline"),
                    class_="btn-row mt-1",
                ),
            )
        return ui.div(
            ui.div(ui.span(f"Linked projects · {len(linked)}", class_="section-label"), class_="panel-head"),
            *(rows or [ui.div("No projects linked. Modelled as a policy measure without an identified funding source.", class_="small muted")]),
            *sources,
            link_ui,
            class_="panel",
        )

    @reactive.calc
    def _projects():
        return projects_service.all_projects(
            projects_service.load_project_records_cached(config.PROJECTS_XLSX_PATH), state.custom_projects.get()
        )

    @reactive.effect
    @reactive.event(input.link_project_btn)
    def _on_link_project():
        ed = editor.get()
        name = input.link_project_select() if "link_project_select" in input else None
        if not ed or ed["mode"] != "edit" or not name:
            return
        links = dict(state.project_links.get())
        links[name] = ed["code"]
        state.project_links.set(links)
        ui.notification_show(f"Linked '{name}' to {ed['code']}.", type="message")

    # ------------------------------------------------------------------ centre: editor form

    @render.ui
    def center_form():
        editor_nonce.get()
        ed = editor.get()
        c = ctx()
        if ed is None or c is None:
            return None
        with reactive.isolate():
            cd = card(ed["transformer"])
            specs = specs_for(ed["transformer"])
            blocks = param_widget.render_editor_params(
                specs,
                ed["params"],
                c["years"],
                c["default_ramp"],
                magnitude_name=cd["magnitude_param"],
                magnitude_label=cd["magnitude_label"],
                magnitude_help=cd.get("magnitude_help"),
            )
            existing = set(c["tx"].dict_transformations)
        suggested = ed["code"] or transformation_service.suggest_transformation_code(ed["transformer"], existing)
        is_library = ed["mode"] == "edit" and ed["code"] in c["library"]
        no_magnitude = blocks["magnitude"] is None
        no_basic = no_magnitude and not len(blocks["basic"])
        header = ui.div(
            ui.div(
                ui.tags.button(f"← {cd['name']}", class_="link-btn", onclick=_ev("transformer", ed["transformer"])),
                ui.span(f" / {ed['code'] or 'new transformation'}", class_="code"),
                ui.output_ui("edit_status", inline=True),
            ),
            ui.h2(ed["name"] or cd["name"], style="font-size:23px;font-weight:600;margin:6px 0 2px"),
            ui.div(ed["basis"] or "Policy measure · no linked project", class_="small muted"),
            class_="tf-head",
        )
        spec_panel = ui.div(
            ui.div(ui.span("Specification", class_="section-label"), class_="panel-head"),
            ui.div(
                ui.div(
                    ui.input_text("tx_name", "Name", value=ed["name"]),
                    ui.input_text_area("tx_description", "Notes", value=ed["description"], rows=2),
                    ui.div(
                        ui.input_text("tx_code", "Transformation code", value=suggested),
                        ui.tags.small(
                            "Used in sisepuede files. Changing it on an existing transformation saves a new one.",
                            class_="muted d-block",
                        ),
                        class_="adv-only",
                    ),
                    blocks["magnitude"],
                    ui.div(
                        "This transformer has no single magnitude. It uses its default settings unless you change "
                        "them under Advanced options.",
                        class_="info-box mb-3",
                    )
                    if no_basic
                    else None,
                    blocks["basic"],
                ),
                ui.div(blocks["ramp"], ui.div(ui.output_ui("ramp_preview"), class_="ramp-chart")),
                class_="editor-grid",
            ),
            ui.div(
                ui.div(
                    ui.span("Advanced parameters ", param_widget.code_tip(ed["transformer"]), class_="section-label"),
                    ui.span("ADVANCED", class_="adv-tag"),
                    class_="panel-head",
                ),
                blocks["advanced"] if len(blocks["advanced"]) else ui.div("No other parameters.", class_="small muted"),
                class_="adv-only adv-box mt-2",
            ),
            ui.div(
                "Library transformations are kept as published; use Duplicate & adjust to change one.",
                class_="info-box mt-2",
            )
            if is_library
            else None,
            ui.div("Tip: switch on Advanced options in the sidebar to see every parameter.", class_="small muted mt-2")
            if no_basic
            else None,
            class_="panel",
        )
        return ui.TagList(header, spec_panel)

    def _current_ramp_from_inputs(ed) -> Optional[Dict]:
        """Ramp dict from the editor inputs, or None if they aren't readable yet."""
        c = ctx()
        ramp_specs = [s for s in specs_for(ed["transformer"]) if s.kind == WidgetKind.RAMP_VECTOR]
        if not ramp_specs:
            return None
        try:
            return param_widget.read_editor_params(input, ramp_specs, c["years"])[ramp_specs[0].name]
        except Exception:
            return None

    @render.ui
    def ramp_preview():
        ed = editor.get()
        c = ctx()
        if ed is None or c is None:
            return None
        current = _current_ramp_from_inputs(ed)
        curves = []
        saved = ed["params"].get("vec_implementation_ramp")
        if ed["mode"] == "edit":
            curves.append((ramp_values({"vec_implementation_ramp": saved}), "ghost"))
        if current is not None:
            curves.append((list(ramp_service.ramp_curve(current, len(c["years"]), c["default_ramp"])), "main"))
        return charts.ramp_chart(curves, c["years"], width=340, height=150)

    def _is_dirty(ed) -> bool:
        if ed is None or ed["mode"] != "edit":
            return False
        c = ctx()
        try:
            params = param_widget.read_editor_params(input, specs_for(ed["transformer"]), c["years"])
            name = input.tx_name()
            description = input.tx_description()
        except Exception:
            return False
        if (name or "").strip() != (ed["name"] or "").strip() or (description or "") != (ed["description"] or ""):
            logger.debug("dirty %s: name/description", ed["code"])
            return True
        saved = ed["params"]
        for spec in specs_for(ed["transformer"]):
            # a cleared table is left out of `params` (sisepuede default)
            if spec.kind != WidgetKind.NOTE and spec.name not in params and not _same(saved.get(spec.name), None):
                if not _same(saved.get(spec.name), spec.default):
                    logger.debug("dirty %s: %s cleared", ed["code"], spec.name)
                    return True
        for key, value in params.items():
            if key == "vec_implementation_ramp":
                a = ramp_service.ramp_curve(value or {}, len(c["years"]), c["default_ramp"])
                b = ramp_service.ramp_curve(saved.get(key) if isinstance(saved.get(key), dict) else {}, len(c["years"]), c["default_ramp"])
                if max(abs(x - y) for x, y in zip(a, b)) > 1e-9:
                    logger.debug("dirty %s: ramp", ed["code"])
                    return True
                continue
            if not _same(value, saved.get(key, _default_of(ed["transformer"], key))):
                logger.debug("dirty %s: %s %r != %r", ed["code"], key, value, saved.get(key))
                return True
        return False

    def _default_of(transformer_code, key):
        for s in specs_for(transformer_code):
            if s.name == key:
                return s.default
        return None

    @render.ui
    def edit_status():
        ed = editor.get()
        if ed is None:
            return None
        if ed["mode"] == "new":
            return ui.span("  ● unsaved", style="color:var(--amber);font-size:13px")
        if _is_dirty(ed):
            return ui.span("  ● edited", style="color:var(--amber);font-size:13px")
        return None

    # ------------------------------------------------------------------ centre: dynamic

    @render.ui
    def center_dynamic():
        c = ctx()
        if c is None:
            return ui.div(
                ui.h2("Pathways", style="font-size:23px"),
                ui.p("Load a baseline first: the transformer catalog is built from it.", class_="muted"),
                ui.tags.button("Go to Baseline data →", class_="btn btn-primary btn-inline", onclick="mrvGoTo('data_input')"),
            )
        ed = editor.get()
        code = ed["transformer"] if ed else open_transformer.get()
        if code is None:
            return ui.div(
                ui.div(ui.span("Start here", class_="section-label")),
                ui.h2("Build a pathway from transformers", style="font-size:23px;margin:6px 0"),
                ui.p(
                    "A transformer is a policy lever in SISEPUEDE (e.g. raise the renewable electricity share). "
                    "A transformation sets its size and timing. A pathway is a set of transformations that "
                    "runs against a baseline and is compared with business as usual.",
                    style="max-width:70ch",
                ),
                ui.tags.ol(
                    ui.tags.li("Create a pathway with + New pathway (top)."),
                    ui.tags.li("Open a transformer on the left."),
                    ui.tags.li("Add one of its transformations, or create one from the default."),
                    ui.tags.li("Continue to Run."),
                    class_="small",
                ),
                class_="panel",
            )
        cd = card(code)
        default_ramp_vals = ramp_values({})
        if ed is not None:
            return ui.TagList(
                _status_notes(cd),
                _moves_panel(cd, ramp_values(ed["params"])),
                _pair_note(cd),
                _adds_up(code),
                _project_panel(ed["code"]) if ed["mode"] == "edit" else None,
            )

        # transformer view
        policy = ramp_service.policy_from_ramp(None, c["years"], c["default_ramp"])
        n_tx = len(c["by_transformer"].get(code, []))
        mag = pathway_service.format_magnitude(cd["magnitude_default"]) if cd["magnitude_default"] is not None else "per category"
        header = ui.div(
            ui.div(
                ui.div(f"{(cd.get('sector') or '').upper()} · TRANSFORMER · {code.split(':')[1]}", class_="crumb"),
                ui.h2(cd["name"]),
                ui.p(cd.get("description") or ""),
                ui.tags.details(
                    ui.tags.summary("More about this transformer", class_="small muted mt-1"),
                    ui.p(cd.get("description_long") or "", class_="small"),
                    ui.div(cd.get("magnitude_help") or "", class_="small muted"),
                    ui.div(code, class_="code mt-1"),
                )
                if (cd.get("description_long") or cd.get("magnitude_help"))
                else ui.div(code, class_="code mt-1"),
                style="flex:1;min-width:0",
            ),
            _emissions_badge(cd),
            class_="tf-head",
            style="display:flex;gap:20px;align-items:flex-start",
        )
        default_block = ui.div(
            ui.div(ui.span("Library default", class_="section-label"), class_="panel-head"),
            ui.div(
                ui.div(
                    ui.div(cd["magnitude_label"] or "Magnitude", class_="k"),
                    ui.div(mag, class_="v"),
                    ui.div("Starts in", class_="k"),
                    ui.div(str(policy.start_year), class_="v"),
                    ui.div("Full effect by", class_="k"),
                    ui.div(str(policy.full_year), class_="v"),
                    ui.div("Ramp", class_="k"),
                    ui.div(ramp_service.SHAPES.get(policy.shape, {"label": "Custom"})["label"], class_="v"),
                    ui.div("Transformations", class_="k"),
                    ui.div(str(n_tx), class_="v"),
                    class_="kv",
                ),
                ui.div(charts.ramp_chart([(default_ramp_vals, "muted")], c["years"], width=340, height=140, fill_main=False), class_="ramp-chart"),
                class_="editor-grid",
            ),
            class_="panel",
        )
        return ui.TagList(
            header,
            _status_notes(cd),
            default_block,
            _moves_panel(cd, default_ramp_vals),
            _pair_note(cd),
            _adds_up(code),
        )

    # ------------------------------------------------------------------ centre: footer

    @render.ui
    def center_footer():
        c = ctx()
        if c is None:
            return None
        ed = editor.get()
        sid = active_pathway()
        pw = pathway_name(sid)
        pathways = state.strategies_map.get()

        if ed is None:
            code = open_transformer.get()
            if code is None:
                return None
            return ui.div(
                ui.span("Open an existing transformation on the left to reuse or duplicate it, or start from the default.", class_="note"),
                ui.div(_btn("+ New transformation from default", "new_tx", code, "btn btn-primary btn-inline"), class_="btn-row"),
                class_="pw-footer",
            )

        if ed["mode"] == "new":
            buttons = [_btn("Cancel", "cancel"), _btn("Save to library only", "save_library")]
            if sid is not None:
                buttons.append(_btn(f"Create & add to {pw}", "create_add", cls="btn btn-primary btn-inline"))
            return ui.div(ui.span("Not saved yet", class_="note"), ui.div(*buttons, class_="btn-row"), class_="pw-footer")

        code = ed["code"]
        used = pathway_service.pathways_using(code, pathways)
        used_names = ", ".join(pathways[s].strategy.name for s in used)
        is_library = code in c["library"]
        in_active = sid is not None and sid in used

        if _is_dirty(ed) and not is_library:
            n = len(used)
            buttons = [
                _btn("Discard", "cancel"),
                _btn(f"Update {code}" + (f" ({n} pathway{'s' if n != 1 else ''})" if n else ""), "update", cls="btn btn-primary btn-inline"),
            ]
            if sid is not None:
                buttons.insert(1, _btn(f"Save as new & add to {pw}", "save_new_add"))
            note = f"Edited · {code} is used in {n} pathway{'s' if n != 1 else ''}" if n else f"Edited · {code}"
            return ui.div(ui.span(note, class_="note"), ui.div(*buttons, class_="btn-row"), class_="pw-footer")

        buttons = [_btn("Duplicate & adjust", "duplicate", code)]
        if in_active:
            buttons.insert(0, _btn(f"Remove from {pw}", "remove", code))
            buttons.append(ui.span(f"✓ In {pw}", class_="pill pill-ok"))
            others = [pathways[s].strategy.name for s in used if s != sid]
            note = f"Also in {', '.join(others)}" if others else ""
        else:
            if sid is not None:
                buttons.append(_btn(f"Add to {pw}", "add", code, "btn btn-primary btn-inline"))
            note = f"Used in {used_names}" if used else "Not in any pathway yet"
            if not used and not is_library:
                buttons.insert(0, _btn("Delete", "delete_tx", code, "btn btn-inline adv-only"))
        return ui.div(ui.span(note, class_="note"), ui.div(*buttons, class_="btn-row"), class_="pw-footer")

    # ------------------------------------------------------------------ right tray

    @render.ui
    def tray():
        c = ctx()
        if c is None:
            return None
        sid = active_pathway()
        if sid is None:
            return ui.div(
                ui.div("In this pathway", class_="section-label"),
                ui.p("No pathways yet.", class_="small muted mt-2"),
                ui.tags.button("+ New pathway", class_="btn btn-primary btn-inline", onclick=_ev("new_pathway")),
                class_="pw-pad",
            )
        entry = state.strategies_map.get()[sid]
        groups = pathway_service.grouped_pathway(entry, c["tx"])
        n_codes = sum(len(v) for v in groups.values())
        cards = {tfr: card(tfr) for tfr in groups}
        in_pathway = set(entry.transformation_codes)

        raising = []
        for tfr, cd in cards.items():
            direction = cd.get("emissions_direction")
            pair_ok = any(any(t in in_pathway for t in c["by_transformer"].get(p, [])) for p in cd.get("pair_with") or [])
            if direction == "increases" or (direction == "depends_on_grid" and not pair_ok):
                raising.append(tfr)
        broken = [tfr for tfr, cd in cards.items() if cd.get("status") == "error"]
        stacked = [tfr for tfr, codes in groups.items() if len(codes) > 1]

        warnings = []
        if raising:
            warnings.append(
                ui.div(
                    f"{len(raising)} transformer{'s' if len(raising) != 1 else ''} may raise emissions on "
                    "their own. Add a grid transformation or check the run.",
                    class_="warn-box small",
                )
            )
        if broken:
            warnings.append(ui.div(f"{len(broken)} transformer(s) fail in the installed sisepuede; this pathway will fail to run.", class_="warn-box small"))
        if stacked:
            warnings.append(ui.div(f"{len(stacked)} transformer(s) have several transformations, applied one after another.", class_="info-box small"))

        rows = []
        for tfr, codes in groups.items():
            cd = cards[tfr]
            tx_rows = []
            for code in codes:
                tx_rows.append(
                    ui.div(
                        ui.span(tx_label(code), class_="label", title=code, onclick=_ev("tx", code), style="cursor:pointer"),
                        ui.span(tx_summary(code).split(" · ")[0], class_="mono"),
                        ui.tags.button("×", class_="x-btn", onclick=_ev("remove", code), title=f"Remove from {entry.strategy.name}"),
                        class_="tray-tx",
                    )
                )
            flag = None
            if tfr in raising:
                flag = ui.div("May raise emissions without a cleaner grid", class_="small", style="color:var(--rust);padding-left:16px")
            rows.append(
                ui.div(
                    ui.div(
                        ui.span(class_=f"swatch {_sector_class(cd.get('sector'))}"),
                        ui.span(cd["name"], class_="tname", onclick=_ev("transformer", tfr)),
                        ui.span(f"+{len(codes) - 1}", class_="pill pill-mute") if len(codes) > 1 else None,
                        style="display:flex;gap:6px;align-items:center",
                    ),
                    *tx_rows,
                    flag,
                    class_="tray-group",
                )
            )
        if not rows:
            rows = [ui.div("Empty pathway. Open a transformer on the left and add one of its transformations.", class_="small muted pw-pad")]

        sectors: Dict[str, int] = {}
        for tfr in groups:
            s = cards[tfr].get("sector") or "other"
            sectors[s] = sectors.get(s, 0) + len(groups[tfr])

        return ui.TagList(
            ui.div(
                ui.div("In this pathway", class_="section-label"),
                ui.div(entry.strategy.name, style="font-weight:600;font-size:15.5px;margin-top:4px"),
                ui.div(f"{n_codes} transformation{'s' if n_codes != 1 else ''} · {len(groups)} transformer{'s' if len(groups) != 1 else ''}", class_="small muted"),
                ui.div(
                    ui.tags.button("Rename", class_="link-btn", onclick=_ev("rename_pathway")),
                    ui.tags.button("Delete", class_="link-btn danger", onclick=_ev("delete_pathway")),
                    class_="btn-row mt-1",
                ),
                *warnings,
                class_="pw-pad",
                style="display:flex;flex-direction:column;gap:8px",
            ),
            *rows,
            ui.div(
                ui.div(" · ".join(f"{s} {n}" for s, n in sectors.items()), class_="small muted") if sectors else None,
                ui.tags.button(
                    "Validate on baseline (dry run)", class_="btn btn-inline adv-only", onclick=_ev("dry_run"), type="button"
                ),
                ui.tags.button("Continue to Run →", class_="btn btn-inline", style="border-color:var(--accent);color:var(--accent)", onclick="mrvGoTo('run')", type="button"),
                class_="tray-foot",
            ),
        )


def _same(a, b) -> bool:
    """Loose equality for parameter values read back from inputs."""
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool) and not isinstance(b, bool):
        return math.isclose(float(a), float(b), rel_tol=1e-9, abs_tol=1e-9)
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        return len(a) == len(b) and all(_same(x, y) for x, y in zip(a, b))
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(_same(a[k], b[k]) for k in a)
    # sisepuede accepts one number for every key of a dict parameter
    if isinstance(a, dict) != isinstance(b, dict):
        d, n = (a, b) if isinstance(a, dict) else (b, a)
        if isinstance(n, (int, float)) and not isinstance(n, bool) and d:
            return all(_same(v, n) for v in d.values())
    empty = (None, [], (), {}, "")
    if any(a is e or a == e for e in empty) and any(b is e or b == e for e in empty):
        return True
    return a == b

"""Pathways page: transformer browser, transformation editor and pathway
tray in three columns (Claude Design prototype, "Pathways").

* Left: transformers grouped by sector. Opening one lists its
  transformations (the user's, plus the NDC library) and "+ New".
* Centre: the transformer view (description, emissions if used alone,
  library default, "what this moves in the model", how it adds up in the
  pathway) or the transformation editor (basic controls; everything else
  under the sidebar's Advanced options).
* Right: the active pathway's contents, grouped by transformer.

"Pathway" is the UI name for a sisepuede Strategy (services/pathway_service).
UI text is in resources/i18n/<lang>/pathways.yaml; transformer, parameter and
library text from the resource files goes through `i18n.td` (es/ar in
data_*.yaml), applied in `card()`, `specs_for()` and `tx_label()`.
Business as usual (strategy 0) is implicit and not shown as a tab.

Clicks in the hand-built HTML (rows, tabs, footer buttons) all go through
one namespaced input, `ui_event`, carrying {"type", "value"}; `_on_event`
dispatches them. The editor form is rendered only when something is opened
(`editor_nonce`), so status/footers can re-render without resetting inputs.
On a language switch the form is redrawn in the new language from what the
user has typed so far (`draft`), so unsaved edits survive.
"""

import dataclasses
import json
import logging
import math
from typing import Any, Dict, List, Optional

from shiny import module, reactive, render, ui
from shiny.module import resolve_id

from sisepuede_tool.models.param_spec import WidgetKind
from sisepuede_tool import config
from sisepuede_tool.services import (
    i18n,
    library_service,
    pathway_service,
    projects_service,
    ramp_service,
    transformation_service,
    transformer_metadata_service,
    widget_metadata,
)
from sisepuede_tool.ui.components import charts, param_widget
from sisepuede_tool.services.labels import clean_label, strip_subsector_prefix
from sisepuede_tool.ui.state import AppState

logger = logging.getLogger(__name__)


# direction -> css class; text is pathways.emission.<direction> / pathways.direction.<direction>
_EMISSION_CLASSES = {
    "decreases": "dir-down",
    "increases": "dir-up",
    "no_change": "dir-flat",
    "depends_on_grid": "dir-mixed",
    "needs_electricity_model": "dir-mixed",
}
_DIRECTION_CLASSES = {
    "increases": "dir-up",
    "decreases": "dir-down",
    "shifts": "dir-mixed",
    "no_change": "dir-flat",
}


def _sector_class(sector: Optional[str]) -> str:
    return "sector-" + (sector or "other").lower().replace(" ", "-")


# Policy areas used to group and filter transformers on the left: coarser
# than sisepuede subsectors, closer to how NDC chapters are organised.
# (label, sector colour, subsector codes); the label is the area's id, shown
# as pathways.areas.<_AREA_KEYS[label]>
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
_AREA_KEYS = {
    "Electricity & fuels": "electricity_fuels",
    "Transport": "transport",
    "Buildings": "buildings",
    "Industry": "industry",
    "Agriculture & food": "agriculture_food",
    "Land & forests": "land_forests",
    "Waste": "waste",
    "Cross-cutting": "cross_cutting",
}
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


def _strip_ndc_prefix(name: str) -> str:
    return library_service.strip_set_prefix(name)


def _area_label(area: str, lang: str) -> str:
    return i18n.t(f"pathways.areas.{_AREA_KEYS[area]}", lang, default=area)


def _sector_label(sector: Optional[str], lang: str) -> str:
    if not sector:
        return ""
    return i18n.t(f"sectors.{sector.lower().replace(' ', '_')}", lang, default=sector)


def _localize_card(cd: Dict[str, Any], lang: str) -> Dict[str, Any]:
    """Transformer card with its resource text translated (data.transformers.*).

    Translations replace the English text get_card shows (curated or computed)
    and are cleaned the same way, so a translated name may keep the "AGRC: " prefix.
    """
    if lang == i18n.DEFAULT_LANG:
        return cd
    code = cd["code"]

    def tr(field, english):
        return i18n.td("transformers", code, field, english, lang)

    out = dict(cd)
    out["name"] = strip_subsector_prefix(clean_label(tr("name", cd["name"])))
    out["description"] = clean_label(tr("short_description", "") or tr("description", cd["description"]))
    out["magnitude_label"] = tr("magnitude_label", cd["magnitude_label"])
    help_text = tr("magnitude_help", "") or tr("units_description", cd["magnitude_help"])
    out["magnitude_help"] = clean_label(help_text) if help_text else help_text
    return out


@module.ui
def page_pathways_ui():
    return ui.div(
        ui.div(ui.output_ui("strip"), class_="pw-strip"),
        ui.div(
            ui.div(
                ui.div(ui.output_ui("sector_chips"), class_="pw-pad", style="padding-bottom:0"),
                ui.div(ui.input_text("search", None, placeholder=i18n.t("pathways.search_placeholder")), class_="pw-pad"),
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
    #                   "params": dict, "name": str, "description": str, "link_project": str|None, "auto_name": bool}
    editor = reactive.Value(None)
    editor_nonce = reactive.Value(0)
    draft = reactive.Value(None)  # the form's unsaved values, kept across a language switch: {"name", "description", "code", "params"}
    shown_default_name = {"value": None}  # the generated name last put in the form (not reactive)
    expanded = reactive.Value(set())  # transformer codes expanded in the left list
    chips_open = reactive.Value(True)  # the subsector filter block is expanded
    area_filter = reactive.Value(frozenset())  # policy areas (_AREAS) shown in the left list; empty = all

    overrides = widget_metadata.load_overrides(widget_metadata.default_overrides_path())

    # ------------------------------------------------------------------ helpers

    def _t(key, **fmt):
        return i18n.t(f"pathways.{key}", state.lang(), **fmt)

    def _tn(key, n, **fmt):
        return i18n.tn(f"pathways.{key}", n, state.lang(), **fmt)

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
        return _localize_card(transformer_metadata_service.get_card(code, catalog_meta(), tk=c["tk"] if c else None), state.lang())

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
        specs = widget_metadata.build_param_specs(c["tk"].get_tkernel(transformer_code), c["ma"], c["tk"], overrides)
        lang = state.lang()
        if lang == i18n.DEFAULT_LANG:
            return specs
        # labels and help from param_schemas.yaml, translated (data.params.*)
        out = []
        for spec in specs:
            key = f"{transformer_code}.{spec.name}"
            out.append(
                dataclasses.replace(
                    spec,
                    label=i18n.td("params", key, "label", spec.label, lang),
                    help_text=i18n.td("params", key, "help", spec.help_text, lang),
                )
            )
        return out

    def ramp_values(params: Dict[str, Any]) -> List[float]:
        c = ctx()
        ramp = params.get("vec_implementation_ramp")
        ramp = ramp if isinstance(ramp, dict) else None
        return list(ramp_service.ramp_curve(ramp or {}, len(c["years"]), c["default_ramp"]))

    def tx_summary(code: str) -> str:
        c = ctx()
        t = c["tx"].dict_transformations[code]
        cd = card(t.transformer_code)
        # pathway_service.summarize, with the text translated
        value = pathway_service.magnitude_of(t, cd["magnitude_param"], cd["magnitude_default"])
        mag = pathway_service.format_magnitude(value) if value is not None else _t("custom_magnitude")
        policy = pathway_service.policy_ramp_of(t, c["years"], c["default_ramp"])
        return f"{mag} · {param_widget.describe_ramp(policy, state.lang())}"

    def tx_name(code: str) -> str:
        """Transformation name as shown; NDC/LEP library names translated (data.library.*)."""
        t = ctx()["tx"].dict_transformations[code]
        name = t.name or code
        if code in ctx()["library"]:
            name = i18n.td("library", code, "name", name, state.lang())
        return name

    def tx_label(code: str) -> str:
        return _strip_ndc_prefix(tx_name(code))

    def basis_of(code: Optional[str]) -> Optional[str]:
        if code is None:
            return None
        linked = projects_service.projects_for_transformation(code, state.project_links.get())
        if code in ctx()["library"]:
            item = ctx()["library"][code]
            if item.source == library_service.SOURCE_LEP:
                return _t("basis_lep")
            return _t("basis_ndc") + (f" · {_tn('linked_projects', len(linked))}" if linked else "")
        return _t("basis_project", names=", ".join(linked)) if linked else None

    def open_editor(
        mode: str, transformer_code: str, code: Optional[str] = None, params=None, name="", description="", link_project=None,
        auto_name: bool = False,
    ):
        editor.set(
            {
                "mode": mode,
                "transformer": transformer_code,
                "code": code,
                "params": dict(params or {}),
                "name": name,
                "description": description or "",
                "link_project": link_project,
                "auto_name": auto_name,  # name is the generated default, which follows the language until edited
            }
        )
        open_transformer.set(transformer_code)
        expanded.set(expanded.get() | {transformer_code})
        draft.set(None)
        editor_nonce.set(editor_nonce.get() + 1)

    def open_existing(code: str):
        t = ctx()["tx"].dict_transformations[code]
        description = t.description or ""
        if code in ctx()["library"]:  # library items are read-only, so translated text is never saved back
            description = i18n.td("library", code, "description", description, state.lang())
        open_editor("edit", t.transformer_code, code, t.dict_parameters, tx_name(code), description)

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
                open_editor("new", value, None, {}, i18n.plain(_t("custom_name", name=cd["name"])), "", auto_name=True)
            elif kind == "duplicate":
                t = c["tx"].dict_transformations[value]
                open_editor("new", t.transformer_code, None, t.dict_parameters, _t("copy_name", name=tx_label(value)), t.description or "")
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
                ui.notification_show(_t("added_to", pathway=pathway_name(active_pathway())), type="message")
            elif kind == "remove":
                sid = active_pathway()
                set_pathways(pathway_service.remove_from_pathway(state.strategies_map.get(), c["tx"], sid, value))
                ui.notification_show(_t("removed_from", pathway=pathway_name(sid)), type="message")
            elif kind == "delete_tx":
                set_pathways(pathway_service.delete_transformation(state.strategies_map.get(), c["tx"], value))
                bump()
                editor.set(None)
                ui.notification_show(_t("deleted", code=value), type="message")
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
                open_editor(
                    "new", value, None, {}, req.get("name") or i18n.plain(_t("custom_name", name=card(value)["name"])), "",
                    link_project=req.get("link_project"), auto_name=not req.get("name"),
                )
            elif kind == "transformer" and value in c["tk"].all_tkernels:
                open_transformer.set(value)
                expanded.set(expanded.get() | {value})
                editor.set(None)

    def _require_pathway():
        if active_pathway() is None:
            raise ValueError(_t("need_pathway"))

    def _save(kind: str):
        c = ctx()
        ed = editor.get()
        if ed is None:
            return
        specs = specs_for(ed["transformer"])
        try:
            params = param_widget.read_editor_params(input, specs, c["years"], state.lang())
        except param_widget.ParamReadError as e:
            ui.notification_show(_t("check_values", error=e), type="error", duration=8)
            return
        name = (input.tx_name() or "").strip()
        if not name:
            ui.notification_show(_t("need_name"), type="error")
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
                ui.notification_show(_t("code_prefix"), type="error")
                return
            if code in existing:
                ui.notification_show(_t("code_exists", code=code), type="error")
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
                _t("saved_but_fails", error=f"{type(e).__name__}: {e}"),
                type="warning",
                duration=10,
            )

        pathways = pathway_service.save_transformation(state.strategies_map.get(), c["tx"], transformation)
        message = _t("saved", code=code)
        if kind in ("create_add", "save_new_add"):
            _require_pathway()
            pathways = pathway_service.add_to_pathway(pathways, c["tx"], active_pathway(), code)
            message = _t("created_added", code=code, pathway=pathway_name(active_pathway()))
        elif kind == "update":
            n = len(pathway_service.pathways_using(code, pathways))
            message = _tn("updated_in", n, code=code) if n else _t("updated", code=code)
        set_pathways(pathways)
        bump()
        if ed.get("link_project"):
            links = dict(state.project_links.get())
            links[ed["link_project"]] = code
            state.project_links.set(links)
            message += " " + _t("linked_to_project", name=ed["link_project"])
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
            ui.notification_show(_t("dry_run_failed", error=f"{type(e).__name__}: {e}"), type="error", duration=10)
            return
        ui.notification_show(_t("dry_run_ok", pathway=entry.strategy.name, baseline=baseline.label), type="message")

    # ---- pathway modals

    def _show_new_pathway_modal():
        pathways = state.strategies_map.get()
        choices = {"": _t("blank")}
        for sid in pathway_service.pathway_ids(pathways):
            entry = pathways[sid]
            choices[str(sid)] = _t("copy_of", name=entry.strategy.name, n=len(entry.transformation_codes))
        n = len(pathway_service.pathway_ids(pathways)) + 1
        ui.modal_show(
            ui.modal(
                ui.input_text("new_pathway_name", _t("name"), placeholder=_t("pathway_n", n=n)),
                ui.input_radio_buttons("new_pathway_from", _t("start_from"), choices=choices, selected=""),
                title=_t("new_pathway_title"),
                footer=ui.div(
                    ui.modal_button(_t("cancel"), class_="btn btn-inline"),
                    ui.input_action_button("new_pathway_create", _t("create"), class_="btn-primary btn-inline"),
                    class_="btn-row",
                ),
                easy_close=True,
            )
        )

    @reactive.effect
    @reactive.event(input.new_pathway_create)
    def _on_create_pathway():
        c = ctx()
        name = (input.new_pathway_name() or "").strip() or _t("pathway_n", n=len(pathway_service.pathway_ids(state.strategies_map.get())) + 1)
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
        if copy_from:
            message = _t("created_pathway_from", name=name, source=pathways[int(copy_from)].strategy.name)
        else:
            message = _t("created_pathway", name=name)
        ui.notification_show(message, type="message")

    def _show_rename_modal():
        sid = active_pathway()
        if sid is None:
            return
        ui.modal_show(
            ui.modal(
                ui.input_text("rename_pathway_name", _t("name"), value=pathway_name(sid)),
                title=_t("rename_title"),
                footer=ui.div(
                    ui.modal_button(_t("cancel"), class_="btn btn-inline"),
                    ui.input_action_button("rename_pathway_ok", _t("rename"), class_="btn-primary btn-inline"),
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
                ui.p(_t("delete_confirm", name=pathway_name(sid))),
                title=_t("delete_title"),
                footer=ui.div(
                    ui.modal_button(_t("cancel"), class_="btn btn-inline"),
                    ui.input_action_button("delete_pathway_ok", _t("delete"), class_="btn-rust btn-inline"),
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
            return ui.span(_t("load_baseline"), class_="muted")
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
        tabs.append(ui.tags.button(_t("new_pathway"), class_="pw-tab new", onclick=_ev("new_pathway"), type="button"))
        baselines = state.baselines.get()
        note = None
        if baselines:
            first = next(iter(baselines.values()))
            note = ui.span(
                ui.span(_t("catalog_from") + " ", class_="muted"),
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
                _t("no_baseline"),
                ui.tags.button(_t("go_baseline"), class_="link-btn d-block mt-2", onclick="mrvGoTo('data_input')"),
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
                    meta = _t("fails_installed")
                elif txs:
                    meta = _tn("n_transformations", len(txs)) + (f" · {_t('n_in_pathway', n=n_in)}" if n_in else "")
                else:
                    meta = _t("no_transformations")
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
                                ui.span(library_service.SOURCE_LABELS.get(lib.source, "NDC"), class_="tx-src") if lib else None,
                                ui.span(tx_summary(t_code).split(" · ")[0], class_="spec"),
                                class_="tx-item active" if t_code == open_code else "tx-item",
                                onclick=_ev("tx", t_code),
                            )
                        )
                    items.append(ui.div(_t("new_transformation"), class_="tx-item add", onclick=_ev("new_tx", code)))
                    rows.append(ui.div(*items, class_="tx-list"))
            if rows:
                blocks.append(
                    ui.div(
                        ui.div(ui.span(class_=f"swatch {_sector_class(_AREA_SECTOR[area])}"), _area_label(area, state.lang()).upper(), class_="section-label"),
                        *rows,
                        class_="tf-sector",
                    )
                )
        if not blocks:
            return ui.div(_t("no_match"), class_="muted small")
        return ui.TagList(
            *blocks,
            ui.div(ui.span(class_="dot"), " " + _t("in_current_pathway"), class_="small muted mt-3"),
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
                _t("all"),
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
                    _area_label(area, state.lang()),
                    ui.span(str(len(codes)), class_="n"),
                    type="button",
                    title="sisepuede: " + ", ".join(subsectors),
                    class_=f"sector-chip {_sector_class(_AREA_SECTOR[area])}-chip" + (" on" if area in shown else ""),
                    onclick=_ev("area", area),
                    **{"aria-pressed": "true" if area in shown else "false"},
                )
            )
        rows = [ui.div(*chips, class_="chip-row")]
        picked = ", ".join(_area_label(a, state.lang()) for a in _AREA_ORDER if a in shown) if shown else _t("all")
        return ui.tags.details(
            ui.tags.summary(ui.span(_t("policy_areas"), class_="section-label"), ui.span(f" · {picked}", class_="small muted")),
            ui.div(*rows, class_="sector-chips"),
            class_="chip-filter",
            open=chips_open.get(),
            ontoggle=f"Shiny.setInputValue({json.dumps(resolve_id('chips_open'))}, this.open)",
        )

    # ------------------------------------------------------------------ centre: shared pieces

    def _emission_label(direction):
        """(text, css class) for an emissions direction."""
        if direction in _EMISSION_CLASSES:
            return _t(f"emission.{direction}"), _EMISSION_CLASSES[direction]
        return _t("not_available"), "dir-flat"

    def _emissions_badge(cd):
        label, cls = _emission_label(cd.get("emissions_direction"))
        emis = cd.get("emissions") or {}
        pct = emis.get("total_delta_pct")
        detail = _t("emissions_detail")
        if pct is not None and cd.get("emissions_direction") not in ("needs_electricity_model",):
            detail = _t("emissions_pct", pct=f"{pct:+.2f}%") + " · " + detail
        return ui.div(
            ui.div(_t("emissions_alone"), class_="section-label"),
            ui.div(label, class_=f"v {cls}"),
            ui.div(detail, class_="small muted", style="max-width:220px"),
            class_="emis-badge",
        )

    def _status_notes(cd):
        if cd.get("status") == "error":
            return ui.div(
                ui.tags.b(_t("fails_title") + " "),
                _t("fails_text") + " ",
                ui.span(cd.get("error") or "", class_="code"),
                class_="warn-box",
            )
        if cd.get("status") == "no_effect_on_baseline":
            return ui.div(_t("no_effect"), class_="info-box")
        return None

    def _electricity_note(cd):
        """When to switch on the electricity dispatch, from the attribute table flags."""
        need = cd.get("electricity_need")
        if need not in ("needed", "optional"):
            return None
        label = _t(f"electricity.{need}.label")
        text = _t(f"electricity.{need}.text")
        note = cd.get("electricity_model_note")
        more = ui.tags.details(ui.tags.summary(_t("why"), class_="small muted"), ui.div(note, class_="small muted")) if note else None
        if need == "needed":
            return ui.div(
                ui.div(ui.tags.b(f"{label}. "), text, " " + _t("switch_dispatch")),
                more,
                class_="info-box",
            )
        return ui.div(ui.div(ui.tags.b(f"{label}. "), text), more, class_="small muted")

    def _moves_panel(cd, ramp):
        rows = []
        for v in cd.get("top_variables") or []:
            direction = v.get("direction")
            label = _t(f"direction.{direction}") if direction in _DIRECTION_CLASSES else ""
            cls = _DIRECTION_CLASSES.get(direction, "dir-flat")
            code = (v.get("example_fields") or [""])[0]
            rows.append(
                ui.div(
                    ui.div(
                        ui.div(ui.span(_t("kind_input") if v.get("kind") == "input" else _t("kind_result"), class_="kind-tag"), v.get("label"), class_="vname"),
                        ui.div(code, class_="vcode", title=v.get("variable")),
                    ),
                    charts.direction_band(v.get("direction"), ramp),
                    ui.div(label, class_=f"vdir {cls}"),
                    class_="moves-row",
                )
            )
        e_dir = cd.get("emissions_direction")
        e_label, e_cls = _emission_label(e_dir)
        band_dir = {"decreases": "decreases", "increases": "increases"}.get(e_dir, "no_change")
        sector = cd.get("sector") or ""
        rows.append(
            ui.div(
                ui.div(ui.div(_t("total_emissions"), class_="vname"), ui.div(_t("main_effect", sector=_sector_label(sector, state.lang())) if sector else "", class_="vcode")),
                charts.direction_band(band_dir, ramp),
                ui.div(e_label, class_=f"vdir {e_cls}"),
                class_="moves-row emissions",
            )
        )
        if not cd.get("top_variables"):
            rows.insert(0, ui.div(_t("no_variable_changes"), class_="small muted"))
        return ui.div(
            ui.div(
                ui.span(_t("moves_title"), class_="section-label"),
                ui.span(_t("moves_hint"), class_="hint"),
                class_="panel-head",
            ),
            *rows,
            ui.div(
                ui.tags.details(
                    ui.tags.summary(_t("where_from"), class_="small muted"),
                    ui.div(
                        _t("where_from_text"),
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
                notes.append(ui.div(_t("pair_ok", name=pair_card["name"], pathway=pathway_name(sid)), class_="ok-box small"))
            else:
                notes.append(
                    ui.div(
                        ui.div(
                            _t("pair_moves") + " ",
                            ui.tags.b(_t("pair_missing", name=pair_card["name"], pathway=pathway_name(sid))),
                        ),
                        ui.tags.button(_t("open_pair", name=pair_card["name"]), class_="link-btn mt-1", onclick=_ev("transformer", pair)),
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
            ui.span(_t("adds_up", pathway=pathway_name(sid)), class_="section-label"),
            class_="panel-head",
        )
        if not codes:
            return ui.div(head, ui.div(_t("adds_up_none", pathway=pathway_name(sid)), class_="small muted"), class_="panel")
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
                ui.tags.b(_t("sequence_title") + " "),
                _t("sequence_text"),
                class_="warn-box",
            )
        return ui.div(
            head,
            *rows,
            warning,
            ui.div(charts.ramp_chart(curves, c["years"], width=600, height=130, fill_main=len(codes) == 1, lang=state.lang()), class_="ramp-chart mt-2"),
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
                    ui.tags.button(_t("unlink"), class_="link-btn danger", onclick=_ev("unlink_project", name)),
                    class_="btn-row",
                    style="justify-content:space-between;flex-wrap:nowrap;padding:6px 0;border-top:1px solid var(--border-soft)",
                )
            )
        item = ctx()["library"].get(code)
        sources = []
        if item is not None and item.citations:
            sources = [
                ui.tags.details(
                    ui.tags.summary(_t("sources"), class_="small muted mt-1"),
                    *[ui.tags.a(u, href=u, target="_blank", class_="small d-block", style="color:var(--accent);word-break:break-all") for u in item.citations],
                )
            ]
        transformer_code = ctx()["tx"].dict_transformations[code].transformer_code
        candidates = {}
        same_group = _t("same_transformer")
        for name, r in records.items():
            if name in linked:
                continue
            group = same_group if r.get("transformer_code") == transformer_code else _t("other_projects")
            candidates.setdefault(group, {})[name] = _t("now_linked", name=name, code=links[name]) if links.get(name) else name
        link_ui = None
        if candidates:
            link_ui = ui.tags.details(
                ui.tags.summary(_t("link_project"), class_="link-btn mt-1", style="list-style:none;cursor:pointer"),
                ui.div(
                    ui.input_select("link_project_select", None, choices=dict(sorted(candidates.items(), key=lambda kv: kv[0] != same_group))),
                    ui.input_action_button("link_project_btn", _t("link"), class_="btn-inline"),
                    class_="btn-row mt-1",
                ),
            )
        return ui.div(
            ui.div(ui.span(_t("linked_projects_title", n=len(linked)), class_="section-label"), class_="panel-head"),
            *(rows or [ui.div(_t("no_projects"), class_="small muted")]),
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
        ui.notification_show(_t("linked_notice", name=name, code=ed["code"]), type="message")

    # ------------------------------------------------------------------ centre: editor form

    @reactive.effect
    @reactive.event(state.lang, ignore_init=True)
    def _keep_form_on_language_switch():
        # the form is redrawn in the new language from what's typed, not from the saved values
        ed, c = editor.get(), ctx()
        if ed is None or c is None or "tx_name" not in input:
            return
        try:
            params = param_widget.read_editor_params(input, specs_for(ed["transformer"]), c["years"], state.lang())
        except param_widget.ParamReadError:
            params = (draft.get() or {}).get("params", ed["params"])  # an invalid value isn't carried over
        name = input.tx_name()
        draft.set({
            "name": name,
            "name_untouched": name == shown_default_name["value"],
            "description": input.tx_description(),
            "code": input.tx_code(),
            "params": params,
        })

    @render.ui
    @i18n.keep_inputs(state.lang)
    def center_form():
        editor_nonce.get()
        ed = editor.get()
        c = ctx()
        if ed is None or c is None:
            return None
        typed = draft.get() or {}
        with reactive.isolate():
            cd = card(ed["transformer"])
            # text worked out now, in the current language, rather than stored when the editor opened
            basis = basis_of(ed["code"]) if ed["mode"] == "edit" else (
                _t("for_project", name=ed["link_project"]) if ed.get("link_project") else None
            )
            name = typed.get("name", ed["name"])
            shown_default_name["value"] = None
            if ed.get("auto_name"):
                default_name = i18n.plain(_t("custom_name", name=cd["name"]))
                if not typed or typed.get("name_untouched"):
                    name = shown_default_name["value"] = default_name
                ed = {**ed, "name": default_name}
            specs = specs_for(ed["transformer"])
            blocks = param_widget.render_editor_params(
                specs,
                typed.get("params", ed["params"]),
                c["years"],
                c["default_ramp"],
                magnitude_name=cd["magnitude_param"],
                magnitude_label=cd["magnitude_label"],
                magnitude_help=cd.get("magnitude_help"),
                lang=state.lang(),
            )
            existing = set(c["tx"].dict_transformations)
        suggested = typed.get("code") or ed["code"] or transformation_service.suggest_transformation_code(ed["transformer"], existing)
        is_library = ed["mode"] == "edit" and ed["code"] in c["library"]
        no_magnitude = blocks["magnitude"] is None
        no_basic = no_magnitude and not len(blocks["basic"])
        header = ui.div(
            ui.div(
                ui.tags.button(_t("back", name=cd["name"]), class_="link-btn", onclick=_ev("transformer", ed["transformer"])),
                ui.span(f" / {ed['code'] or _t('new_transformation_code')}", class_="code"),
                ui.output_ui("edit_status", inline=True),
            ),
            ui.h2(ed["name"] or cd["name"], style="font-size:23px;font-weight:600;margin:6px 0 2px"),
            ui.div(basis or _t("policy_measure"), class_="small muted"),
            class_="tf-head",
        )
        spec_panel = ui.div(
            ui.div(ui.span(_t("specification"), class_="section-label"), class_="panel-head"),
            ui.div(
                ui.div(
                    ui.input_text("tx_name", _t("name"), value=name),
                    ui.input_text_area("tx_description", _t("notes"), value=typed.get("description", ed["description"]), rows=2),
                    ui.div(
                        ui.input_text("tx_code", _t("tx_code"), value=suggested),
                        ui.tags.small(_t("tx_code_help"), class_="muted d-block"),
                        class_="adv-only",
                    ),
                    blocks["magnitude"],
                    ui.div(_t("no_magnitude"), class_="info-box mb-3")
                    if no_basic
                    else None,
                    # trajectory sits under the magnitude, beside the timing controls it previews
                    ui.div(ui.output_ui("ramp_preview"), class_="ramp-chart mb-3") if blocks["ramp"] is not None else None,
                    blocks["basic"],
                ),
                ui.div(blocks["ramp"]),
                class_="editor-grid",
            ),
            ui.div(
                ui.div(
                    ui.span(_t("advanced_params") + " ", param_widget.code_tip(ed["transformer"]), class_="section-label"),
                    ui.span(_t("advanced_tag"), class_="adv-tag"),
                    class_="panel-head",
                ),
                blocks["advanced"] if len(blocks["advanced"]) else ui.div(_t("no_other_params"), class_="small muted"),
                class_="adv-only adv-box mt-2",
            ),
            ui.div(_t("library_kept"), class_="info-box mt-2") if is_library else None,
            ui.div(_t("tip_advanced"), class_="small muted mt-2")
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
            return param_widget.read_editor_params(input, ramp_specs, c["years"], state.lang())[ramp_specs[0].name]
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
        return charts.ramp_chart(curves, c["years"], width=340, height=150, lang=state.lang())

    def _is_dirty(ed) -> bool:
        if ed is None or ed["mode"] != "edit":
            return False
        c = ctx()
        try:
            params = param_widget.read_editor_params(input, specs_for(ed["transformer"]), c["years"], state.lang())
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
            return ui.span("  " + _t("unsaved"), style="color:var(--amber);font-size:13px")
        if _is_dirty(ed):
            return ui.span("  " + _t("edited"), style="color:var(--amber);font-size:13px")
        return None

    # ------------------------------------------------------------------ centre: dynamic

    @render.ui
    def center_dynamic():
        c = ctx()
        if c is None:
            return ui.div(
                ui.h2(_t("title"), style="font-size:23px"),
                ui.p(_t("load_first"), class_="muted"),
                ui.tags.button(_t("go_baseline"), class_="btn btn-primary btn-inline", onclick="mrvGoTo('data_input')"),
            )
        ed = editor.get()
        code = ed["transformer"] if ed else open_transformer.get()
        if code is None:
            return ui.div(
                ui.div(ui.span(_t("start_here"), class_="section-label")),
                ui.h2(_t("build_title"), style="font-size:23px;margin:6px 0"),
                ui.p(_t("intro"), style="max-width:70ch"),
                ui.tags.ol(
                    ui.tags.li(_t("step_create")),
                    ui.tags.li(_t("step_open")),
                    ui.tags.li(_t("step_add")),
                    ui.tags.li(_t("step_run")),
                    class_="small",
                ),
                class_="panel",
            )
        cd = card(code)
        default_ramp_vals = ramp_values({})
        if ed is not None:
            return ui.TagList(
                _status_notes(cd),
                _electricity_note(cd),
                _moves_panel(cd, ramp_values(ed["params"])),
                _pair_note(cd),
                _adds_up(code),
                _project_panel(ed["code"]) if ed["mode"] == "edit" else None,
            )

        # transformer view
        policy = ramp_service.policy_from_ramp(None, c["years"], c["default_ramp"])
        n_tx = len(c["by_transformer"].get(code, []))
        mag = pathway_service.format_magnitude(cd["magnitude_default"]) if cd["magnitude_default"] is not None else _t("per_category")
        header = ui.div(
            ui.div(
                ui.div(_t("crumb", sector=_sector_label(cd.get("sector"), state.lang()).upper(), abv=code.split(":")[1]), class_="crumb"),
                ui.h2(cd["name"]),
                ui.p(cd.get("description") or ""),
                ui.tags.details(
                    ui.tags.summary(_t("more_about"), class_="small muted mt-1"),
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
            ui.div(ui.span(_t("library_default"), class_="section-label"), class_="panel-head"),
            ui.div(
                ui.div(
                    ui.div(cd["magnitude_label"] or _t("magnitude"), class_="k"),
                    ui.div(mag, class_="v"),
                    ui.div(_t("starts_in"), class_="k"),
                    ui.div(str(policy.start_year), class_="v"),
                    ui.div(_t("full_effect_by"), class_="k"),
                    ui.div(str(policy.full_year), class_="v"),
                    ui.div(_t("ramp"), class_="k"),
                    ui.div(param_widget.shape_label(policy.shape, state.lang()), class_="v"),
                    ui.div(_t("transformations"), class_="k"),
                    ui.div(str(n_tx), class_="v"),
                    class_="kv",
                ),
                ui.div(
                    charts.ramp_chart([(default_ramp_vals, "muted")], c["years"], width=340, height=140, fill_main=False, lang=state.lang()),
                    class_="ramp-chart",
                ),
                class_="editor-grid",
            ),
            class_="panel",
        )
        return ui.TagList(
            header,
            _status_notes(cd),
            _electricity_note(cd),
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
                ui.span(_t("footer_open"), class_="note"),
                ui.div(_btn(_t("new_from_default"), "new_tx", code, "btn btn-primary btn-inline"), class_="btn-row"),
                class_="pw-footer",
            )

        if ed["mode"] == "new":
            buttons = [_btn(_t("cancel"), "cancel"), _btn(_t("save_library"), "save_library")]
            if sid is not None:
                buttons.append(_btn(_t("create_add", pathway=pw), "create_add", cls="btn btn-primary btn-inline"))
            return ui.div(ui.span(_t("not_saved"), class_="note"), ui.div(*buttons, class_="btn-row"), class_="pw-footer")

        code = ed["code"]
        used = pathway_service.pathways_using(code, pathways)
        used_names = ", ".join(pathways[s].strategy.name for s in used)
        is_library = code in c["library"]
        in_active = sid is not None and sid in used

        if _is_dirty(ed) and not is_library:
            n = len(used)
            buttons = [
                _btn(_t("discard"), "cancel"),
                _btn(_tn("update_n", n, code=code) if n else _t("update", code=code), "update", cls="btn btn-primary btn-inline"),
            ]
            if sid is not None:
                buttons.insert(1, _btn(_t("save_new_add", pathway=pw), "save_new_add"))
            note = _tn("edited_used", n, code=code) if n else _t("edited_code", code=code)
            return ui.div(ui.span(note, class_="note"), ui.div(*buttons, class_="btn-row"), class_="pw-footer")

        buttons = [_btn(_t("duplicate"), "duplicate", code)]
        if in_active:
            buttons.insert(0, _btn(_t("remove_from", pathway=pw), "remove", code))
            buttons.append(ui.span(_t("in_pathway_pill", pathway=pw), class_="pill pill-ok"))
            others = [pathways[s].strategy.name for s in used if s != sid]
            note = _t("also_in", names=", ".join(others)) if others else ""
        else:
            if sid is not None:
                buttons.append(_btn(_t("add_to", pathway=pw), "add", code, "btn btn-primary btn-inline"))
            note = _t("used_in", names=used_names) if used else _t("not_in_any")
            if not used and not is_library:
                buttons.insert(0, _btn(_t("delete"), "delete_tx", code, "btn btn-inline adv-only"))
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
                ui.div(_t("in_this_pathway"), class_="section-label"),
                ui.p(_t("no_pathways"), class_="small muted mt-2"),
                ui.tags.button(_t("new_pathway"), class_="btn btn-primary btn-inline", onclick=_ev("new_pathway")),
                class_="pw-pad",
            )
        entry = state.strategies_map.get()[sid]
        groups = pathway_service.grouped_pathway(entry, c["tx"])
        n_codes = sum(len(v) for v in groups.values())
        cards = {tfr: card(tfr) for tfr in groups}
        in_pathway = set(entry.transformation_codes)

        # why a transformer is flagged: "increases" = raises emissions on its own;
        # "grid" = moves emissions to power plants and no grid transformation is in
        # the pathway. Library transformations (NDC, LEP) are judged by their own
        # run, since their parameters can change the sign of the transformer default.
        raising: Dict[str, str] = {}
        for tfr, cd in cards.items():
            lib_dirs = [transformer_metadata_service.library_direction(catalog_meta(), code) for code in groups[tfr]]
            if lib_dirs and all(d is not None for d in lib_dirs):
                direction = "increases" if "increases" in lib_dirs else ("depends_on_grid" if "depends_on_grid" in lib_dirs else lib_dirs[0])
            else:
                direction = cd.get("emissions_direction")
            pair_ok = any(any(t in in_pathway for t in c["by_transformer"].get(p, [])) for p in cd.get("pair_with") or [])
            if direction == "increases":
                raising[tfr] = "increases"
            elif direction == "depends_on_grid" and not pair_ok:
                raising[tfr] = "grid"
        broken = [tfr for tfr, cd in cards.items() if cd.get("status") == "error"]
        stacked = [tfr for tfr, codes in groups.items() if len(codes) > 1]

        warnings = []
        if raising:
            key = "may_raise_grid" if "grid" in raising.values() else "may_raise_alone"
            warnings.append(ui.div(_tn(key, len(raising)), class_="warn-box small"))
        if broken:
            warnings.append(ui.div(_tn("broken", len(broken)), class_="warn-box small"))
        needs_dispatch = [tfr for tfr, cd in cards.items() if cd.get("electricity_need") == "needed"]
        if needs_dispatch:
            n = len(needs_dispatch)
            warnings.append(
                ui.div(
                    _tn("needs_dispatch", n),
                    class_="info-box small",
                    title=", ".join(cards[t]["name"] for t in needs_dispatch),
                )
            )
        if stacked:
            warnings.append(ui.div(_tn("stacked", len(stacked)), class_="info-box small"))

        rows = []
        for tfr, codes in groups.items():
            cd = cards[tfr]
            tx_rows = []
            for code in codes:
                tx_rows.append(
                    ui.div(
                        ui.span(tx_label(code), class_="label", title=code, onclick=_ev("tx", code), style="cursor:pointer"),
                        ui.span(tx_summary(code).split(" · ")[0], class_="mono"),
                        ui.tags.button("×", class_="x-btn", onclick=_ev("remove", code), title=_t("remove_from", pathway=entry.strategy.name)),
                        class_="tray-tx",
                    )
                )
            flag = None
            if tfr in raising:
                flag = ui.div(
                    _t("raise_grid") if raising[tfr] == "grid" else _t("raise_alone"),
                    class_="small",
                    style="color:var(--rust);padding-inline-start:16px",
                )
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
            rows = [ui.div(_t("empty_pathway"), class_="small muted pw-pad")]

        sectors: Dict[str, int] = {}
        for tfr in groups:
            s = cards[tfr].get("sector") or "other"
            sectors[s] = sectors.get(s, 0) + len(groups[tfr])

        return ui.TagList(
            ui.div(
                ui.div(_t("in_this_pathway"), class_="section-label"),
                ui.div(entry.strategy.name, style="font-weight:600;font-size:15.5px;margin-top:4px"),
                ui.div(f"{_tn('n_transformations', n_codes)} · {_tn('n_transformers', len(groups))}", class_="small muted"),
                ui.div(
                    ui.tags.button(_t("rename"), class_="link-btn", onclick=_ev("rename_pathway")),
                    ui.tags.button(_t("delete"), class_="link-btn danger", onclick=_ev("delete_pathway")),
                    class_="btn-row mt-1",
                ),
                *warnings,
                class_="pw-pad",
                style="display:flex;flex-direction:column;gap:8px",
            ),
            *rows,
            ui.div(
                ui.div(" · ".join(f"{_sector_label(s, state.lang())} {n}" for s, n in sectors.items()), class_="small muted") if sectors else None,
                ui.tags.button(_t("dry_run"), class_="btn btn-inline adv-only", onclick=_ev("dry_run"), type="button"),
                ui.tags.button(_t("continue_run"), class_="btn btn-inline", style="border-color:var(--accent);color:var(--accent)", onclick="mrvGoTo('run')", type="button"),
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

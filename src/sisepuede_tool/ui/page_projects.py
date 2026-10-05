"""Projects page (optional portfolio): announced projects from the Egypt
NDC/LTS workbook plus projects added in the app, each linked to the
transformation that models it (Claude Design prototype, "Projects").

Links default to the NDC transformation on the same transformer (projects_service.
default_links) and live in `state.project_links`; the Pathways editor shows
and edits the same links. "Open in Pathways" and "Create transformation"
hand off to the Pathways page through `state.pathways_request`.
"""

import json
from typing import Optional

from shiny import module, reactive, render, ui
from shiny.module import resolve_id

from sisepuede_tool import config
from sisepuede_tool.services import library_service, pathway_service, projects_service, ramp_service
from sisepuede_tool.services import transformer_metadata_service as tms
from sisepuede_tool.ui.components import charts
from sisepuede_tool.ui.state import AppState

_STATUS_PILL = {
    "operational": "pill-ok",
    "under construction": "pill-warn",
}
_STATUSES = ["Planned", "Study/Feasibility", "Agreement/MoU", "Under Construction", "Operational"]


@module.ui
def page_projects_ui():
    return ui.div(
        ui.div(
            ui.output_ui("filters"),
            ui.div(
                ui.output_ui("scope_summary", inline=True),
                ui.input_action_button("add_project", "+ Add project", class_="btn-inline"),
                class_="btn-row",
            ),
            class_="btn-row",
            style="justify-content:space-between;margin-bottom:14px",
        ),
        ui.div(
            ui.div(ui.output_ui("table"), class_="box", style="padding:6px 10px"),
            ui.div(ui.output_ui("inspector"), class_="box"),
            class_="proj-grid",
        ),
    )


@module.server
def page_projects_server(input, output, session, state: AppState):
    ev_id = resolve_id("ui_event")
    workbook = projects_service.load_project_records_cached(config.PROJECTS_XLSX_PATH)
    library = {i.code: i for i in library_service.load_library()}
    active_filter = reactive.Value("all")
    selected = reactive.Value(workbook["name"].iloc[0] if len(workbook) else None)
    request_nonce = [0]

    def _ev(kind, value=""):
        payload = json.dumps({"type": kind, "value": value})
        return f"Shiny.setInputValue({json.dumps(ev_id)}, {payload}, {{priority: 'event'}}); return false;"

    @reactive.calc
    def projects():
        return projects_service.all_projects(workbook, state.custom_projects.get())

    @reactive.calc
    def sector_of():
        ma = state.model_attributes.get()
        mapping = tms.subsector_to_sector(ma) if ma is not None else {}
        mapping.update({"pflo": "Cross-sector"})
        return mapping

    def project_sector(rec) -> str:
        sub = (rec.get("subsector") or "").lower()
        return sector_of().get(sub, "Other")

    def tx_info(code: Optional[str]):
        """(name, params, transformer_code) for a transformation code, from
        the session collection if loaded, else from the library files."""
        if not code:
            return None
        tx = state.transformations_obj.get()
        state.transformations_revision.get()
        if tx is not None and code in tx.dict_transformations:
            t = tx.dict_transformations[code]
            return t.name or code, t.dict_parameters or {}, t.transformer_code
        item = library.get(code)
        if item is not None:
            return item.name, item.config.get("parameters") or {}, item.transformer_code
        return code, {}, None

    def _years_and_default():
        ma = state.model_attributes.get()
        years = ramp_service.model_years(ma)
        tk = state.transformers_catalog.get()
        default = ramp_service.catalog_default_ramp(tk) if tk is not None else {"tp_0_ramp": 12, "n_tp_ramp": 23, "alpha_logistic": 0.0}
        return years, default

    def ramp_of(params):
        years, default = _years_and_default()
        ramp = params.get("vec_implementation_ramp")
        ramp = ramp if isinstance(ramp, dict) else None
        return years, ramp_service.ramp_curve(ramp or {}, len(years), default), ramp_service.policy_from_ramp(ramp, years, default)

    def summary_of(code):
        info = tx_info(code)
        if info is None:
            return ""
        name, params, tfr = info
        years, _, policy = ramp_of(params)
        mag_name = None
        meta = state.transformer_metadata.get()
        if tfr:
            mag_name = (meta.get("transformers", {}).get(tfr, {}).get("computed") or {}).get("magnitude", {}) or {}
            mag_name = mag_name.get("param") if isinstance(mag_name, dict) else None
        mag = params.get(mag_name) if mag_name else None
        mag_txt = pathway_service.format_magnitude(float(mag)) if isinstance(mag, (int, float)) else "custom"
        return f"{mag_txt} · {ramp_service.describe(policy)}"

    # ---- filters

    def _filtered():
        df = projects()
        links = state.project_links.get()
        f = active_filter.get()
        recs = df.to_dict("records")
        if f == "ndc":
            recs = [r for r in recs if projects_service.ndc_flag(r.get("ndc")) != "no"]
        elif f == "unlinked":
            recs = [r for r in recs if not links.get(r["name"])]
        elif f.startswith("sector:"):
            recs = [r for r in recs if project_sector(r) == f.split(":", 1)[1]]
        return recs

    @render.ui
    def filters():
        recs = projects().to_dict("records")
        links = state.project_links.get()
        f = active_filter.get()

        def chip(label, key, n, rust=False):
            style = "border-color:var(--rust);color:var(--rust)" if rust and n else None
            return ui.tags.button(label, ui.span(str(n), class_="n"), class_="chip active" if f == key else "chip", onclick=_ev("filter", key), style=style)

        sectors = {}
        for r in recs:
            sectors[project_sector(r)] = sectors.get(project_sector(r), 0) + 1
        chips = [chip("All", "all", len(recs))]
        chips += [chip(s, f"sector:{s}", n) for s, n in sorted(sectors.items(), key=lambda kv: -kv[1])]
        chips.append(chip("In NDC", "ndc", sum(1 for r in recs if projects_service.ndc_flag(r.get("ndc")) != "no")))
        chips.append(chip("Unlinked", "unlinked", sum(1 for r in recs if not links.get(r["name"])), rust=True))
        return ui.div(*chips, class_="btn-row")

    @render.ui
    def scope_summary():
        scope = state.selected_projects.get()
        n = sum(1 for v in scope.values() if v)
        return ui.span(
            ui.span(f"{n} in scope · ", class_="small muted"),
            ui.tags.button("Select all", class_="link-btn", onclick=_ev("scope_all")),
            ui.span(" · ", class_="muted"),
            ui.tags.button("None", class_="link-btn", onclick=_ev("scope_none")),
        )

    # ---- events

    @reactive.effect
    @reactive.event(input.ui_event)
    def _on_event():
        ev = input.ui_event() or {}
        kind, value = ev.get("type"), ev.get("value")
        if kind == "filter":
            active_filter.set(value)
        elif kind == "select":
            selected.set(value)
        elif kind == "scope":
            scope = dict(state.selected_projects.get())
            scope[value] = not scope.get(value, False)
            state.selected_projects.set(scope)
        elif kind == "scope_all":
            state.selected_projects.set({r["name"]: True for r in _filtered()} | {k: v for k, v in state.selected_projects.get().items() if v})
        elif kind == "scope_none":
            state.selected_projects.set({})
        elif kind == "unlink":
            links = dict(state.project_links.get())
            links[value] = None
            state.project_links.set(links)
        elif kind == "open":
            code = state.project_links.get().get(value)
            if state.transformations_obj.get() is None:
                ui.notification_show("Load a baseline first: transformations open in Pathways once the catalog is built.", type="warning")
                return
            _request({"type": "tx", "value": code})
        elif kind == "create":
            rec = next((r for r in projects().to_dict("records") if r["name"] == value), None)
            if rec is None or not rec.get("transformer_code"):
                ui.notification_show("This project has no transformer; link an existing transformation instead.", type="warning")
                return
            if state.transformations_obj.get() is None:
                ui.notification_show("Load a baseline first.", type="warning")
                return
            _request({"type": "new_tx", "value": rec["transformer_code"], "link_project": rec["name"], "name": rec["name"]})

    def _request(req):
        request_nonce[0] += 1
        state.pathways_request.set({**req, "nonce": request_nonce[0]})

    @reactive.effect
    @reactive.event(input.link_btn)
    def _on_link():
        name = selected.get()
        code = input.link_select() if "link_select" in input else None
        if not name or not code:
            ui.notification_show("Choose a transformation to link.", type="error")
            return
        links = dict(state.project_links.get())
        links[name] = code
        state.project_links.set(links)
        ui.notification_show(f"Linked '{name}' to {code}.", type="message")

    # ---- add project

    @reactive.effect
    @reactive.event(input.add_project)
    def _on_add_open():
        tk = state.transformers_catalog.get()
        choices = {"": "(none yet)"}
        if tk is not None:
            meta = state.transformer_metadata.get()
            for code in tk.all_tkernels_non_baseline:
                choices[code] = tms.get_card(code, meta)["name"]
        ui.modal_show(
            ui.modal(
                ui.input_text("new_name", "Project name"),
                ui.input_select("new_transformer", "Modelled by transformer", choices=choices)
                if tk is not None
                else ui.input_text("new_transformer", "Transformer code (e.g. TFR:ENTC:TARGET_RENEWABLE_ELEC)"),
                ui.input_text("new_investment", "Investment", placeholder="e.g. $120M (EIB)"),
                ui.input_select("new_status", "Status", choices=_STATUSES, selected="Planned"),
                ui.input_text("new_start", "Start / online year"),
                ui.input_select("new_ndc", "In the NDC?", choices=["No", "Partial", "Yes — measure", "Yes — named"]),
                ui.input_text_area("new_description", "Description", rows=3),
                title="Add project",
                footer=ui.div(
                    ui.modal_button("Cancel", class_="btn btn-inline"),
                    ui.input_action_button("new_create", "Add project", class_="btn-primary btn-inline"),
                    class_="btn-row",
                ),
                easy_close=True,
            )
        )

    @reactive.effect
    @reactive.event(input.new_create)
    def _on_add():
        try:
            rec = projects_service.make_custom_project(
                input.new_name(),
                transformer_code=(input.new_transformer() or "").strip() or None,
                description=input.new_description(),
                investment=input.new_investment(),
                status=input.new_status(),
                start=input.new_start(),
                ndc=input.new_ndc(),
            )
        except ValueError as e:
            ui.notification_show(str(e), type="error")
            return
        if rec["name"] in set(projects()["name"]):
            ui.notification_show(f"A project named '{rec['name']}' already exists.", type="error")
            return
        state.custom_projects.set(state.custom_projects.get() + [rec])
        selected.set(rec["name"])
        active_filter.set("all")
        ui.modal_remove()
        ui.notification_show(f"Added project '{rec['name']}'.", type="message")

    # ---- table

    @render.ui
    def table():
        recs = _filtered()
        links = state.project_links.get()
        scope = state.selected_projects.get()
        current = selected.get()
        if not recs:
            return ui.div("No project matches this filter.", class_="small muted pw-pad")
        rows = []
        for r in recs:
            name = r["name"]
            code = links.get(name)
            if code:
                info = tx_info(code)
                _, ramp, _ = ramp_of(info[1]) if info else (None, [0, 1], None)
                linked = ui.div(charts.mini_ramp(ramp, width=46, height=14), ui.span(_short(info[0] if info else code, 38), class_="small"), class_="btn-row", style="gap:6px;flex-wrap:nowrap")
            else:
                linked = ui.tags.button(
                    "+ Link transformation",
                    class_="chip",
                    style="border:1px dashed var(--rust);color:var(--rust)",
                    onclick=_ev("select", name),
                )
            status = r.get("status") or ""
            in_scope = scope.get(name, False)
            rows.append(
                ui.tags.tr(
                    ui.tags.td(
                        ui.tags.button(
                            "✓" if in_scope else "",
                            class_="scope-box on" if in_scope else "scope-box",
                            onclick="event.stopPropagation();" + _ev("scope", name),
                            title="In scope",
                        )
                    ),
                    ui.tags.td(
                        ui.div(name, style="font-weight:500"),
                        ui.div((r.get("transformer_code") or "no transformer") + (" · added here" if r.get("source") == "custom" else ""), class_="code"),
                    ),
                    ui.tags.td(project_sector(r), class_="small"),
                    ui.tags.td(_short(r.get("investment") or "–", 26), class_="small mono"),
                    ui.tags.td(ui.span(status, class_=f"pill {_STATUS_PILL.get(status.lower(), 'pill-mute')}") if status else ""),
                    ui.tags.td(linked),
                    onclick=_ev("select", name),
                    style="cursor:pointer" + (";background:var(--accent-soft);box-shadow:inset 2px 0 0 var(--accent)" if name == current else ""),
                )
            )
        head = ui.tags.tr(*[ui.tags.th(t) for t in ("", "Project", "Sector", "Invest.", "Status", "Linked transformation")])
        return ui.tags.table(ui.tags.thead(head), ui.tags.tbody(*rows), class_="history")

    # ---- inspector

    @render.ui
    def inspector():
        name = selected.get()
        recs = {r["name"]: r for r in projects().to_dict("records")}
        r = recs.get(name)
        if r is None:
            return ui.div("Select a project.", class_="small muted")
        code = state.project_links.get().get(name)
        ndc = projects_service.ndc_flag(r.get("ndc"))

        kpis = ui.div(
            _kpi("Investment", _short(r.get("investment") or "–", 40)),
            _kpi("Start / online", _short(r.get("start") or "–", 40)),
            _kpi("In NDC", {"yes": "Yes", "partial": "Partial", "no": "No"}[ndc]),
            class_="kpi-strip",
        )

        if code:
            info = tx_info(code)
            years, ramp, _ = ramp_of(info[1] if info else {})
            in_session = state.transformations_obj.get() is not None
            modeled = ui.div(
                ui.div("Modeled as", class_="section-label"),
                ui.div(info[0] if info else code, style="font-weight:600;margin-top:4px"),
                ui.div(code, class_="code"),
                ui.div(charts.ramp_chart([(ramp, "main")], years, width=340, height=110), class_="ramp-chart mt-2"),
                ui.div(summary_of(code), class_="mono small"),
                ui.div(
                    ui.tags.button("Open in Pathways →", class_="link-btn", onclick="mrvGoTo('pathways');" + _ev("open", name)) if in_session else ui.span("Load a baseline to open it in Pathways.", class_="small muted"),
                    ui.tags.button("Unlink", class_="link-btn danger", onclick=_ev("unlink", name)),
                    class_="btn-row mt-1",
                    style="justify-content:space-between",
                ),
                class_="info-box",
            )
        else:
            modeled = ui.div(
                ui.tags.b("Not modeled yet"),
                ui.div("Link this project to an existing transformation, or create a new transformation from it.", class_="small"),
                _link_controls(r),
                style="border:1px dashed var(--rust);border-radius:8px;padding:12px;display:flex;flex-direction:column;gap:8px;background:var(--rust-soft)",
            )

        notes = []
        for key, label in (("ndc_notes", "NDC notes"), ("lts_notes", "LTS notes"), ("overlap_note", "Duplicate / overlap")):
            if r.get(key):
                notes += [ui.div(label, class_="section-label mt-2"), ui.div(str(r[key]), class_="small")]
        links = projects_service.split_links(r.get("links"))
        return ui.TagList(
            ui.div(f"{project_sector(r).upper()} · {r.get('subsector') or '–'}", class_="section-label"),
            ui.h2(name, style="font-size:21px;font-weight:600;margin:2px 0 0"),
            kpis,
            ui.div(ui.span(r.get("status"), class_=f"pill {_STATUS_PILL.get((r.get('status') or '').lower(), 'pill-mute')}") if r.get("status") else None),
            ui.p(r.get("description") or "", class_="small", style="margin:0"),
            modeled,
            *notes,
            ui.tags.details(
                ui.tags.summary(f"Sources ({len(links)})", class_="small muted"),
                *[ui.tags.a(u, href=u, target="_blank", class_="small d-block", style="color:var(--accent);word-break:break-all") for u in links],
            )
            if links
            else None,
        )

    def _link_controls(r):
        tx = state.transformations_obj.get()
        state.transformations_revision.get()
        if tx is None:
            return ui.div("Load a baseline to link or create transformations.", class_="small muted")
        same, other = {}, {}
        for code, t in sorted(tx.dict_transformations.items()):
            if code == tx.code_baseline:
                continue
            (same if t.transformer_code == r.get("transformer_code") else other)[code] = t.name or code
        choices = {}
        if same:
            choices["Same transformer"] = same
        if other:
            choices["Other transformations"] = other
        return ui.TagList(
            ui.input_select("link_select", None, choices=choices) if choices else None,
            ui.div(
                ui.input_action_button("link_btn", "Link existing", class_="btn-rust btn-inline") if choices else None,
                ui.tags.button("Create transformation", class_="btn btn-inline", onclick="mrvGoTo('pathways');" + _ev("create", r["name"]), type="button")
                if r.get("transformer_code")
                else None,
                class_="btn-row",
            ),
        )


def _kpi(label, value):
    return ui.div(ui.div(label, class_="section-label"), ui.div(value, class_="mono", style="font-size:14.5px;margin-top:2px"), class_="kpi")


def _short(text, n):
    text = str(text)
    return text if len(text) <= n else text[: n - 1] + "…"

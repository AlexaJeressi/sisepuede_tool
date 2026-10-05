"""Baseline data page: upload one or more baseline CSVs for a single region,
validate each, and manage and preview the collection (Claude Design
prototype, "Baseline data").

Choosing a file validates it right away (checklist), "Add baseline" adds it.
All loaded baselines must share one region (the first baseline fixes it for
the session). The transformer catalog, the transformations collection with
the NDC library, and the business-as-usual strategy are built once,
from the first baseline added -- see services/catalog_service.py.

The checklist also lists model input fields missing from the file: sisepuede
accepts such a file, but the sector models that need those inputs fail at
run time (this happened with Egypt baselines older than the biomass_fix
branch), so the user is told before running.
"""

import dataclasses
import datetime
import json
import pathlib
import uuid
from typing import Optional

import numpy as np
from shiny import module, reactive, render, ui
from shiny.module import resolve_id

from sisepuede_tool.models.baseline import BaselineDataset
from sisepuede_tool.models.strategy_entry import StrategyEntry
from sisepuede_tool.services import (
    catalog_service,
    input_service,
    library_service,
    output_service,
    pathway_service,
    ramp_service,
    strategy_service,
    transformation_service,
)
from sisepuede_tool.ui.components import charts
from sisepuede_tool.ui.state import AppState

_SECTORS = ["AFOLU", "Energy", "Circular Economy", "IPPU", "Socioeconomic"]
_PREVIEW_ROW_LIMIT = 60
_PREVIEW_YEARS = (2015, 2020, 2025, 2030, 2035, 2040, 2045, 2050)

_FIELD_CATALOGS = {}


def _field_catalog(model_attributes):
    key = id(model_attributes)
    if key not in _FIELD_CATALOGS:
        _FIELD_CATALOGS[key] = output_service.build_field_catalog(model_attributes)
    return _FIELD_CATALOGS[key]


def _fmt(value) -> str:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "–"
    if np.isnan(v):
        return "–"
    a = abs(v)
    if a == 0:
        return "0"
    if a >= 1e9:
        return f"{v / 1e9:.2f}B"
    if a >= 1e6:
        return f"{v / 1e6:.2f}M"
    if a >= 1e4:
        return f"{v / 1e3:.1f}k"
    if a >= 100:
        return f"{v:.0f}"
    if a >= 1:
        return f"{v:.2f}"
    return f"{v:.3g}"


@module.ui
def page_data_input_ui():
    return ui.div(
        ui.div(
            ui.div(
                ui.div(ui.span("Add a baseline", class_="section-label"), class_="box-head"),
                ui.input_file("csv_file", None, accept=[".csv"], multiple=False, button_label="Browse", placeholder="Drop a CSV or browse"),
                ui.div(
                    ui.input_text("baseline_label", "Label", placeholder="e.g. Egypt BAU 2024"),
                    ui.tags.small("Shown in the run and results pickers.", class_="muted d-block"),
                ),
                ui.output_ui("validation_panel"),
                ui.input_action_button("add_baseline", "Add baseline", class_="btn-primary"),
                class_="box",
            ),
            ui.div(
                ui.div(
                    ui.span("Loaded baselines", class_="section-label"),
                    ui.span("Click a row to preview", class_="small muted"),
                    class_="box-head",
                ),
                ui.output_ui("baselines_table"),
                class_="box",
            ),
            class_="content",
        ),
        ui.div(
            ui.output_ui("preview_head"),
            ui.div(
                ui.output_ui("preview_chips"),
                ui.div(ui.input_text("preview_search", None, placeholder="Search variables…"), style="width:280px"),
                class_="btn-row",
                style="justify-content:space-between",
            ),
            ui.output_ui("preview_grid"),
            class_="box mt-3",
            style="margin-top:18px",
        ),
    )


@module.server
def page_data_input_server(input, output, session, state: AppState):
    ev_id = resolve_id("ui_event")
    pending = reactive.Value(None)  # {"result", "missing", "filename"} for the chosen file
    preview_id = reactive.Value(None)
    preview_sector = reactive.Value("All")

    def _ev(kind, value=""):
        payload = json.dumps({"type": kind, "value": value})
        return f"Shiny.setInputValue({json.dumps(ev_id)}, {payload}, {{priority: 'event'}}); return false;"

    # ---- validate on file choice

    @reactive.effect
    @reactive.event(input.csv_file)
    def _on_file():
        file_infos = input.csv_file()
        if not file_infos:
            pending.set(None)
            return
        info = file_infos[0]
        model_attributes = state.model_attributes.get()
        try:
            df = input_service.load_csv(info["datapath"])
        except Exception as e:
            pending.set({"result": None, "error": f"Could not read the file: {e}", "filename": info["name"]})
            return
        result = input_service.validate_baseline(df, model_attributes)
        missing = input_service.missing_input_fields(df, model_attributes) if result.ok else []
        pending.set({"result": result, "missing": missing, "filename": info["name"], "n_columns": df.shape[1]})
        if not (input.baseline_label() or "").strip():
            ui.update_text("baseline_label", value=pathlib.Path(info["name"]).stem)

    @render.ui
    def validation_panel():
        p = pending.get()
        if p is None:
            return ui.div("Choose a baseline CSV. It is checked against the SISEPUEDE schema before you add it.", class_="info-box")
        result = p.get("result")
        if result is None:
            return ui.div(f"✕ {p.get('error')}", class_="warn-box")
        if not result.ok:
            return ui.div(ui.tags.b("✕ Not a valid SISEPUEDE baseline. "), result.error, class_="warn-box")

        ma = state.model_attributes.get()
        years = ramp_service.model_years(ma)
        n_inputs = len(ma.all_variable_fields_input)
        missing = p["missing"]

        def line(ok, text, warn=False):
            mark = "✓" if ok else ("!" if warn else "✕")
            color = "var(--accent)" if ok else ("var(--amber)" if warn else "var(--rust)")
            return ui.div(ui.span(mark, style=f"color:{color};font-weight:600;width:14px;display:inline-block"), text, class_="small")

        lines = [
            line(not missing, f"Schema matches SISEPUEDE ({n_inputs - len(missing):,} of {n_inputs:,} input variables)", warn=True),
            line(True, f"Region: {result.region}"),
            line(True, f"{result.n_time_periods} years, {years[0]}–{years[result.n_time_periods - 1]}"),
            line(not result.interpolated_periods, "No missing years" if not result.interpolated_periods
                 else f"Interpolated missing years: {', '.join(str(years[t]) for t in result.interpolated_periods)}", warn=True),
        ]
        detail = None
        if missing:
            detail = ui.div(
                ui.tags.b(f"{len(missing)} input variable(s) missing. "),
                "sisepuede accepts the file, but sector models that need them fail when run "
                "(e.g. a baseline made for an older sisepuede version). ",
                ui.tags.details(
                    ui.tags.summary("Show missing fields", class_="small"),
                    ui.div(*[ui.div(f, class_="code") for f in missing[:200]]),
                ),
                class_="warn-box small",
            )
        existing_regions = {b.region for b in state.baselines.get().values()}
        if existing_regions and result.region not in existing_regions:
            (session_region,) = existing_regions
            detail = ui.div(
                f"✕ Region mismatch: this file is '{result.region}', but this session is locked to "
                f"'{session_region}' (set by the first baseline).",
                class_="warn-box small",
            )
        return ui.div(
            ui.div(ui.span("CSV", class_="pill pill-ok"), ui.span(p["filename"], class_="mono small"), class_="btn-row"),
            ui.div(*lines, class_="ok-box" if not missing else "info-box", style="display:flex;flex-direction:column;gap:3px"),
            detail,
            style="display:flex;flex-direction:column;gap:8px",
        )

    # ---- add / remove / default

    @reactive.effect
    @reactive.event(input.add_baseline)
    def _on_add_baseline():
        p = pending.get()
        if p is None or p.get("result") is None:
            ui.notification_show("Choose a CSV file first.", type="error")
            return
        result = p["result"]
        if not result.ok:
            ui.notification_show(f"Validation failed: {result.error}", type="error", duration=None)
            return
        label = (input.baseline_label() or "").strip()
        if not label:
            ui.notification_show("Enter a label for this baseline.", type="error")
            return
        baselines = state.baselines.get()
        if any(b.label == label for b in baselines.values()):
            ui.notification_show(f"A baseline labelled '{label}' is already loaded.", type="error")
            return
        existing_regions = {b.region for b in baselines.values()}
        if existing_regions and result.region not in existing_regions:
            (session_region,) = existing_regions
            msg = (
                f"Region mismatch: this baseline is '{result.region}', but this "
                f"session is locked to '{session_region}' (set by the first baseline loaded)."
            )
            pending.set({**p, "result": dataclasses.replace(result, ok=False, error=msg)})
            ui.notification_show(msg, type="error", duration=None)
            return

        new_id = uuid.uuid4().hex[:8]
        baseline = BaselineDataset(
            id=new_id,
            label=label,
            df=result.df,
            region=result.region,
            loaded_at=datetime.datetime.now(),
            n_time_periods=result.n_time_periods,
            interpolated_periods=result.interpolated_periods,
        )
        baselines = dict(baselines)
        baselines[new_id] = baseline
        state.baselines.set(baselines)
        if state.default_baseline_id.get() not in baselines:
            state.default_baseline_id.set(new_id)
        preview_id.set(new_id)

        if state.transformers_catalog.get() is None:
            _init_catalog(baseline)

        ui.notification_show(f"Added baseline '{label}' ({result.region}).", type="message")
        ui.update_text("baseline_label", value="")
        pending.set(None)

    def _init_catalog(baseline):
        transformers_catalog = catalog_service.build_transformers_catalog(baseline.df)
        state.transformers_catalog.set(transformers_catalog)
        transformations_obj = transformation_service.create_transformations_collection(transformers_catalog)
        # ready-made NDC transformations; unusable ones are kept with an error for display
        library_items = library_service.add_library_to_collection(transformations_obj, transformers_catalog)
        state.library_items.set(library_items)
        unusable = {i.code for i in library_items if not i.ok}
        links = state.project_links.get()
        state.project_links.set({k: (None if v in unusable else v) for k, v in links.items()})
        state.transformations_obj.set(transformations_obj)
        state.transformations_revision.set(state.transformations_revision.get() + 1)
        baseline_strategy = strategy_service.build_baseline_strategy(transformations_obj)
        pathways = {0: StrategyEntry(strategy=baseline_strategy, transformation_codes=[transformations_obj.code_baseline])}
        # the NDC pathway (strategy 6003 in ssp_egypt btr_invent), ready to run or edit
        pathways, _ = pathway_service.add_library_pathway(
            pathways, transformations_obj, library_items, name="NDC", description="Egypt NDC transformations"
        )
        state.strategies_map.set(pathways)

    @reactive.effect
    @reactive.event(input.ui_event)
    def _on_event():
        ev = input.ui_event() or {}
        kind, value = ev.get("type"), ev.get("value")
        baselines = state.baselines.get()
        if kind == "preview" and value in baselines:
            preview_id.set(value)
        elif kind == "default" and value in baselines:
            state.default_baseline_id.set(value)
        elif kind == "remove" and value in baselines:
            baselines = dict(baselines)
            removed = baselines.pop(value)
            state.baselines.set(baselines)
            if state.default_baseline_id.get() == value:
                state.default_baseline_id.set(next(iter(baselines), None))
            if preview_id.get() == value:
                preview_id.set(state.default_baseline_id.get())
            ui.notification_show(f"Removed baseline '{removed.label}'. Its run results stay in the history.", type="message")
        elif kind == "sector":
            preview_sector.set(value)

    @render.ui
    def baselines_table():
        baselines = state.baselines.get()
        if not baselines:
            return ui.div("No baselines loaded yet. Add one on the left to get started.", class_="info-box")
        ma = state.model_attributes.get()
        years = ramp_service.model_years(ma)
        default_id = state.default_baseline_id.get()
        current = preview_id.get() or default_id
        rows = []
        for b in baselines.values():
            default_cell = (
                ui.span("DEFAULT", class_="pill pill-ok")
                if b.id == default_id
                else ui.tags.button("Set default", class_="link-btn", onclick=_ev("default", b.id))
            )
            rows.append(
                ui.tags.tr(
                    ui.tags.td(ui.span(b.label, style="font-weight:500")),
                    ui.tags.td(b.region, class_="mono"),
                    ui.tags.td(f"{years[0]}–{years[b.n_time_periods - 1]}", class_="mono"),
                    ui.tags.td(str(len(b.interpolated_periods)), class_="mono"),
                    ui.tags.td(f"{b.loaded_at:%H:%M}", class_="mono"),
                    ui.tags.td(default_cell, onclick="event.stopPropagation()"),
                    ui.tags.td(
                        ui.tags.button("×", class_="x-btn", title=f"Remove {b.label}", onclick=_ev("remove", b.id)),
                        onclick="event.stopPropagation()",
                    ),
                    onclick=_ev("preview", b.id),
                    style="cursor:pointer" + (";background:var(--accent-soft)" if b.id == current else ""),
                )
            )
        head = ui.tags.tr(*[ui.tags.th(t) for t in ("Label", "Region", "Years", "Interp.", "Loaded", "", "")])
        return ui.tags.table(ui.tags.thead(head), ui.tags.tbody(*rows), class_="history")

    # ---- preview

    def _preview_baseline() -> Optional[BaselineDataset]:
        baselines = state.baselines.get()
        bid = preview_id.get()
        if bid not in baselines:
            bid = state.default_baseline_id.get()
        return baselines.get(bid)

    @reactive.calc
    def _preview_catalog():
        b = _preview_baseline()
        if b is None:
            return None
        cat = _field_catalog(state.model_attributes.get())
        return cat[cat["is_input"] & cat["field"].isin(b.df.columns)]

    @render.ui
    def preview_head():
        b = _preview_baseline()
        if b is None:
            return ui.div(ui.span("Preview", class_="section-label"))
        return ui.div(ui.span(f"Preview · {b.label}", class_="section-label"), class_="box-head")

    @render.ui
    def preview_chips():
        cat = _preview_catalog()
        if cat is None:
            return None
        active = preview_sector.get()
        chips = [
            ui.tags.button(
                "All", ui.span(f"{len(cat):,}", class_="n"), class_="chip active" if active == "All" else "chip", onclick=_ev("sector", "All")
            )
        ]
        for sector in _SECTORS:
            n = int((cat["sector"] == sector).sum())
            if n:
                chips.append(
                    ui.tags.button(
                        sector, ui.span(f"{n:,}", class_="n"), class_="chip active" if active == sector else "chip", onclick=_ev("sector", sector)
                    )
                )
        return ui.div(*chips, class_="btn-row")

    @render.ui
    def preview_grid():
        b = _preview_baseline()
        cat = _preview_catalog()
        if b is None or cat is None:
            return ui.div("Add a baseline to preview its variables.", class_="small muted")
        sector = preview_sector.get()
        if sector != "All":
            cat = cat[cat["sector"] == sector]
        query = (input.preview_search() or "").strip().lower()
        if query:
            cat = cat[cat["label"].str.lower().str.contains(query, regex=False) | cat["field"].str.contains(query, regex=False)]
        n_match = len(cat)
        cat = cat.head(_PREVIEW_ROW_LIMIT)

        years = ramp_service.model_years(state.model_attributes.get())
        idx = [years.index(y) for y in _PREVIEW_YEARS if y in years and years.index(y) < len(b.df)]
        df = b.df.reset_index(drop=True)
        rows = []
        for rec in cat.to_dict("records"):
            series = df[rec["field"]].to_numpy(dtype=float)
            lo, hi = np.nanmin(series), np.nanmax(series)
            norm = (series - lo) / (hi - lo) if hi > lo else np.full_like(series, 0.5)
            rows.append(
                ui.tags.tr(
                    ui.tags.td(ui.div(rec["label"], style="font-weight:500"), ui.div(rec["field"], class_="code")),
                    ui.tags.td(rec["units"] or "", class_="small muted"),
                    *[ui.tags.td(_fmt(series[i]), class_="mono", style="text-align:right") for i in idx],
                    ui.tags.td(charts.mini_ramp(np.nan_to_num(norm, nan=0.5), width=70, height=18)),
                )
            )
        head = ui.tags.tr(
            ui.tags.th("Variable"),
            ui.tags.th("Unit"),
            *[ui.tags.th(str(years[i]), style="text-align:right") for i in idx],
            ui.tags.th("Trend"),
        )
        note = (
            ui.div(f"Showing {len(cat)} of {n_match:,} matching variables. Search to narrow down.", class_="small muted mt-2")
            if n_match > len(cat)
            else ui.div(f"{n_match:,} variable field{'s' if n_match != 1 else ''}.", class_="small muted mt-2")
        )
        return ui.div(ui.tags.table(ui.tags.thead(head), ui.tags.tbody(*rows), class_="history"), note, class_="table-wrap")

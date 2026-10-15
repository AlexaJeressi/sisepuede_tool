"""Baseline data page: upload one or more baseline CSVs for a single region,
validate each, and manage and preview the collection (Claude Design
prototype, "Baseline data").

The example input (tests/fixtures/example_input.csv) is preloaded at session
start. Choosing a file validates it right away (checklist), "Add baseline" adds it.
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

from sisepuede_tool import config
from sisepuede_tool.models.baseline import BaselineDataset
from sisepuede_tool.models.strategy_entry import StrategyEntry
from sisepuede_tool.services import (
    catalog_service,
    i18n,
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

_SECTORS = ["AFOLU", "Energy", "Circular Economy", "IPPU", "Socioeconomic"]  # field catalog values
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
                ui.div(ui.span(i18n.t("data_input.add_title"), class_="section-label"), class_="box-head"),
                ui.input_file(
                    "csv_file",
                    None,
                    accept=[".csv"],
                    multiple=False,
                    button_label=i18n.t("data_input.browse"),
                    placeholder=i18n.t("data_input.drop"),
                ),
                ui.div(
                    ui.input_text("baseline_label", i18n.t("data_input.label"), placeholder=i18n.t("data_input.label_placeholder")),
                    ui.tags.small(i18n.t("data_input.label_help"), class_="muted d-block"),
                ),
                ui.output_ui("validation_panel"),
                ui.input_action_button("add_baseline", i18n.t("data_input.add_button"), class_="btn-primary"),
                class_="box",
            ),
            ui.div(
                ui.div(
                    ui.span(i18n.t("data_input.loaded_title"), class_="section-label"),
                    ui.span(i18n.t("data_input.click_row"), class_="small muted"),
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
                ui.div(ui.input_text("preview_search", None, placeholder=i18n.t("data_input.search_placeholder")), style="width:280px"),
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
    example_id = reactive.Value(None)  # the preloaded example baseline

    def _t(key, **fmt):
        return i18n.t(f"data_input.{key}", state.lang(), **fmt)

    def _tn(key, n, **fmt):
        return i18n.tn(f"data_input.{key}", n, state.lang(), **fmt)

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
            pending.set({"result": None, "error": _t("read_error", error=e), "filename": info["name"]})
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
            return ui.div(_t("choose_csv"), class_="info-box")
        result = p.get("result")
        if result is None:
            return ui.div(f"✕ {p.get('error')}", class_="warn-box")
        if not result.ok:
            return ui.div(ui.tags.b(f"✕ {_t('not_valid')} "), result.error, class_="warn-box")

        ma = state.model_attributes.get()
        years = ramp_service.model_years(ma)
        n_inputs = len(ma.all_variable_fields_input)
        missing = p["missing"]

        def line(ok, text, warn=False):
            mark = "✓" if ok else ("!" if warn else "✕")
            color = "var(--accent)" if ok else ("var(--amber)" if warn else "var(--rust)")
            return ui.div(ui.span(mark, style=f"color:{color};font-weight:600;width:14px;display:inline-block"), text, class_="small")

        lines = [
            line(not missing, _t("schema_matches", found=n_inputs - len(missing), total=n_inputs), warn=True),
            line(True, _t("region", region=result.region)),
            line(True, _tn("years", result.n_time_periods, start=years[0], end=years[result.n_time_periods - 1])),
            line(not result.interpolated_periods, _t("no_missing_years") if not result.interpolated_periods
                 else _t("interpolated", years=", ".join(str(years[t]) for t in result.interpolated_periods)), warn=True),
        ]
        detail = None
        if missing:
            detail = ui.div(
                ui.tags.b(_tn("missing_inputs", len(missing)) + " "),
                _t("missing_explain") + " ",
                ui.tags.details(
                    ui.tags.summary(_t("show_missing"), class_="small"),
                    ui.div(*[ui.div(f, class_="code") for f in missing[:200]]),
                ),
                class_="warn-box small",
            )
        existing_regions = {b.region for b in state.baselines.get().values()}
        if existing_regions and result.region not in existing_regions:
            (session_region,) = existing_regions
            detail = ui.div(
                "✕ " + _t("region_mismatch", region=result.region, session_region=session_region),
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
            ui.notification_show(_t("choose_first"), type="error")
            return
        result = p["result"]
        if not result.ok:
            ui.notification_show(_t("validation_failed", error=result.error), type="error", duration=None)
            return
        label = (input.baseline_label() or "").strip()
        if not label:
            ui.notification_show(_t("enter_label"), type="error")
            return
        baselines = state.baselines.get()
        if any(b.label == label for b in baselines.values()):
            ui.notification_show(_t("duplicate_label", label=label), type="error")
            return
        existing_regions = {b.region for b in baselines.values()}
        if existing_regions and result.region not in existing_regions:
            (session_region,) = existing_regions
            msg = _t("region_mismatch", region=result.region, session_region=session_region)
            pending.set({**p, "result": dataclasses.replace(result, ok=False, error=msg)})
            ui.notification_show(msg, type="error", duration=None)
            return

        _add_baseline(result, label)
        ui.notification_show(_t("added", label=label, region=result.region), type="message")
        ui.update_text("baseline_label", value="")
        pending.set(None)

    def _add_baseline(result, label):
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
        baselines = dict(state.baselines.get())
        baselines[new_id] = baseline
        state.baselines.set(baselines)
        if state.default_baseline_id.get() not in baselines:
            state.default_baseline_id.set(new_id)
        preview_id.set(new_id)

        if state.transformers_catalog.get() is None:
            _init_catalog(baseline)
        return new_id

    # the shipped example input is loaded when the session starts, so the NDC/LEP
    # pathways are ready without an upload; it can be removed like any other baseline
    @reactive.effect
    def _preload_example():
        with reactive.isolate():
            if state.baselines.get() or not config.EXAMPLE_INPUT_PATH.exists():
                return
            result = input_service.validate_baseline(
                input_service.load_csv(config.EXAMPLE_INPUT_PATH), state.model_attributes.get()
            )
            if result.ok:
                example_id.set(_add_baseline(result, _t("example_label")))

    # the example's label follows the language, unless the user gave it another one
    @reactive.effect
    def _relabel_example():
        label = _t("example_label")
        with reactive.isolate():
            baselines = state.baselines.get()
            b = baselines.get(example_id.get())
            auto = {i18n.t("data_input.example_label", code) for code in i18n.LANGUAGES}
            if b is not None and b.label in auto and b.label != label:
                state.baselines.set({**baselines, b.id: dataclasses.replace(b, label=label)})

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
        # the LEP pathway (strategy 6005 in ssp_egypt btr_invent): NDC + LEP transformations,
        # the example used to demonstrate Article 6 opportunities
        pathways, _ = pathway_service.add_library_pathway(
            pathways,
            transformations_obj,
            library_items,
            name="LEP",
            description="Egypt LEP pathway: NDC plus higher-ambition LEP transformations",
            codes=library_service.lep_pathway_codes(),
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
            ui.notification_show(_t("removed", label=removed.label), type="message")
        elif kind == "sector":
            preview_sector.set(value)

    @render.ui
    def baselines_table():
        baselines = state.baselines.get()
        if not baselines:
            return ui.div(_t("no_baselines"), class_="info-box")
        ma = state.model_attributes.get()
        years = ramp_service.model_years(ma)
        default_id = state.default_baseline_id.get()
        current = preview_id.get() or default_id
        rows = []
        for b in baselines.values():
            default_cell = (
                ui.span(_t("default"), class_="pill pill-ok")
                if b.id == default_id
                else ui.tags.button(_t("set_default"), class_="link-btn", onclick=_ev("default", b.id))
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
                        ui.tags.button("×", class_="x-btn", title=_t("remove", label=b.label), onclick=_ev("remove", b.id)),
                        onclick="event.stopPropagation()",
                    ),
                    onclick=_ev("preview", b.id),
                    style="cursor:pointer" + (";background:var(--accent-soft)" if b.id == current else ""),
                )
            )
        cols = [_t(f"col_{c}") for c in ("label", "region", "years", "interp", "loaded")]
        head = ui.tags.tr(*[ui.tags.th(c) for c in (*cols, "", "")])
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
            return ui.div(ui.span(_t("preview"), class_="section-label"))
        return ui.div(ui.span(_t("preview_of", label=b.label), class_="section-label"), class_="box-head")

    @render.ui
    def preview_chips():
        cat = _preview_catalog()
        if cat is None:
            return None
        active = preview_sector.get()
        chips = [
            ui.tags.button(
                _t("all"), ui.span(f"{len(cat):,}", class_="n"), class_="chip active" if active == "All" else "chip", onclick=_ev("sector", "All")
            )
        ]
        for sector in _SECTORS:
            n = int((cat["sector"] == sector).sum())
            if n:
                chips.append(
                    ui.tags.button(
                        i18n.t(f"sectors.{sector.lower().replace(' ', '_')}", state.lang()),
                        ui.span(f"{n:,}", class_="n"),
                        class_="chip active" if active == sector else "chip",
                        onclick=_ev("sector", sector),
                    )
                )
        return ui.div(*chips, class_="btn-row")

    @render.ui
    def preview_grid():
        b = _preview_baseline()
        cat = _preview_catalog()
        if b is None or cat is None:
            return ui.div(_t("no_preview"), class_="small muted")
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
                    *[ui.tags.td(_fmt(series[i]), class_="mono", style="text-align:end") for i in idx],
                    ui.tags.td(charts.mini_ramp(np.nan_to_num(norm, nan=0.5), width=70, height=18)),
                )
            )
        head = ui.tags.tr(
            ui.tags.th(_t("col_variable")),
            ui.tags.th(_t("col_unit")),
            *[ui.tags.th(str(years[i]), style="text-align:end") for i in idx],
            ui.tags.th(_t("col_trend")),
        )
        note = (
            ui.div(_t("showing", shown=len(cat), total=n_match), class_="small muted mt-2")
            if n_match > len(cat)
            else ui.div(_tn("n_fields", n_match), class_="small muted mt-2")
        )
        return ui.div(ui.tags.table(ui.tags.thead(head), ui.tags.tbody(*rows), class_="history"), note, class_="table-wrap")

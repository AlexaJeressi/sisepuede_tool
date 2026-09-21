"""Transformer -> Transformation Designer page (M2): pick a Transformer,
adjust its parameters via an auto-generated form, save as a named
Transformation.
"""

import asyncio
import os

import pandas as pd
from shiny import module, reactive, render, ui

from sisepuede_tool.services import persistence_service, transformation_service, widget_metadata
from sisepuede_tool.ui.components import param_widget
from sisepuede_tool.ui.state import AppState

_ICON_FOLDER = ui.HTML(
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" '
    'stroke-linecap="round" stroke-linejoin="round"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7z"/></svg>'
)

# Native folder picker via `osascript` (a separate OS process) rather than an
# in-process GUI toolkit like tkinter: Tk/Cocoa calls must happen on the main
# thread on macOS, and running them from an asyncio-offloaded thread (as an
# earlier version of this did) deadlocks the whole app -- the wedged Tk call
# holds the GIL, freezing every other request/websocket in this single
# process, not just the dialog. A subprocess has none of that coupling and
# is naturally awaitable without blocking the event loop.
#
# `choose folder` requires macOS's Automation/TCC permission for whatever
# process launched this app to control Finder/System Events. Without it, the
# call doesn't raise -- it silently auto-denies after a multi-second OS-level
# delay and returns AppleScript's "-128 User canceled", indistinguishable
# from a real cancel. _PICK_DIRECTORY_TIMEOUT_S bounds that delay so a denied
# permission (or any other stall) can never wedge the app; if it keeps timing
# out, grant Automation access in System Settings > Privacy & Security.
_PICK_DIRECTORY_TIMEOUT_S = 20
_CHOOSE_FOLDER_SCRIPT_LINES = [
    "on run argv",
    "if (count of argv) > 0 then",
    'set chosenFolder to choose folder with prompt "Choose a directory" default location (POSIX file (item 1 of argv))',
    "else",
    'set chosenFolder to choose folder with prompt "Choose a directory"',
    "end if",
    "return POSIX path of chosenFolder",
    "end run",
]


async def _pick_directory(initial_dir: str = "") -> str:
    """Open the native macOS folder-picker dialog and return the chosen
    path, or "" if the user cancels (or the dialog times out -- see
    _PICK_DIRECTORY_TIMEOUT_S)."""
    args = ["osascript"]
    for line in _CHOOSE_FOLDER_SCRIPT_LINES:
        args += ["-e", line]
    if initial_dir and os.path.isdir(initial_dir):
        args.append(initial_dir)

    proc = await asyncio.create_subprocess_exec(
        *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=_PICK_DIRECTORY_TIMEOUT_S)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise TimeoutError(
            "Folder picker timed out -- macOS may be blocking it. Check System Settings > "
            "Privacy & Security > Automation and allow this app to control Finder/System Events."
        )
    if proc.returncode != 0:
        # includes user cancellation (AppleScript error -128), which isn't a
        # real failure -- just report no path chosen either way.
        return ""
    return stdout.decode().strip()


def _format_param_value(value) -> str:
    if isinstance(value, dict):
        return ", ".join(f"{k}={v}" for k, v in value.items())
    return str(value)


def _transformation_tooltip(transformation) -> ui.Tag:
    """A `transformation_code` label that shows the Transformation's
    description and parameters on hover (used in the per-transformer
    existing-transformations list)."""
    parameters = transformation.dict_parameters or {}
    body = [ui.p(transformation.description or "No description.", class_="mb-1")]
    if parameters:
        body.append(
            ui.tags.ul(
                *[ui.tags.li(f"{name}: {_format_param_value(value)}") for name, value in parameters.items()],
                class_="mb-0 ps-3",
            )
        )
    else:
        body.append(ui.p("No parameters.", class_="text-muted mb-0"))

    trigger = ui.span(
        transformation.code, tabindex="0", style="cursor: help; text-decoration: underline dotted;"
    )
    return ui.tooltip(trigger, *body, placement="right")


@module.ui
def page_transformations_ui():
    return ui.TagList(
        ui.layout_columns(
            ui.card(
                ui.card_header("Choose a Transformer"),
                ui.input_select("sector", "Sector", choices={}),
                ui.input_select("transformer_code", "Transformer", choices={}),
                ui.output_ui("transformer_description"),
                ui.tags.h6("Existing Transformations for this Transformer", class_="mt-3"),
                ui.output_ui("existing_transformations_list"),
            ),
            ui.card(
                ui.card_header("Configure Transformation"),
                ui.input_text("transformation_code", "Transformation code"),
                ui.input_text("transformation_name", "Name"),
                ui.input_text_area("transformation_description", "Description", rows=2),
                ui.output_ui("param_form"),
                ui.input_action_button("save_transformation", "Add Transformation", class_="btn-primary"),
                ui.output_ui("save_status_ui"),
            ),
            ui.card(
                ui.card_header("Saved Transformations"),
                ui.output_data_frame("transformations_table"),
                ui.input_select("remove_transformation_select", "Remove transformation", choices={}),
                ui.input_action_button(
                    "remove_transformation_btn", "Remove selected", class_="btn-outline-danger"
                ),
            ),
            col_widths=[4, 4, 4],
        ),
        ui.layout_columns(
            ui.card(
                ui.card_header("Save Transformations Directory"),
                ui.p(
                    "Write config_general.yaml, one transformation_*.yaml per saved Transformation, "
                    "strategy_definitions.csv, and citations.bib for this session's Transformations "
                    "and Strategies to a directory -- loadable by the sisepuede CLI/notebooks unmodified.",
                    class_="text-muted",
                ),
                ui.input_action_button(
                    "save_dir_btn", ui.TagList(_ICON_FOLDER, "Save"), class_="btn-primary"
                ),
                ui.output_ui("save_dir_status_ui"),
            ),
            ui.card(
                ui.card_header("Load Transformations Directory"),
                ui.p(
                    "Replace this session's Transformations and Strategies by loading a standard "
                    "transformations directory (config_general.yaml + transformation_*.yaml + "
                    "strategy_definitions.csv) -- export first if you want to keep the current ones.",
                    class_="text-muted",
                ),
                ui.input_action_button(
                    "load_dir_btn", ui.TagList(_ICON_FOLDER, "Load"), class_="btn-outline-secondary"
                ),
                ui.output_ui("load_dir_status_ui"),
            ),
            col_widths=[6, 6],
        ),
    )


@module.server
def page_transformations_server(input, output, session, state: AppState):
    overrides = widget_metadata.load_overrides(widget_metadata.default_overrides_path())
    last_save_result = reactive.Value(None)  # (ok: bool, message: str) | None

    def _current_transformer_and_specs():
        catalog = state.transformers_catalog.get()
        model_attributes = state.model_attributes.get()
        code = input.transformer_code()
        if catalog is None or not code:
            return None, []
        transformer = catalog.get_tkernel(code)
        specs = widget_metadata.build_param_specs(
            transformer, model_attributes, catalog, overrides=overrides
        )
        return transformer, specs

    @reactive.effect
    def _sync_sector_choices():
        catalog = state.transformers_catalog.get()
        if catalog is None:
            return
        sectors = sorted(catalog.get_tkernel_codes_by_sector().keys())
        ui.update_select("sector", choices=sectors)

    @reactive.effect
    def _sync_transformer_choices():
        catalog = state.transformers_catalog.get()
        sector = input.sector()
        if catalog is None or not sector:
            return
        codes = catalog.get_tkernel_codes_by_sector().get(sector, [])
        choices = {code: catalog.get_tkernel(code).name for code in codes}
        ui.update_select("transformer_code", choices=choices)

    @reactive.effect
    @reactive.event(input.transformer_code)
    def _autofill_transformation_fields():
        catalog = state.transformers_catalog.get()
        code = input.transformer_code()
        if catalog is None or not code:
            return
        transformer = catalog.get_tkernel(code)
        transformations_obj = state.transformations_obj.get()
        existing = set(transformations_obj.dict_transformations.keys()) if transformations_obj else set()

        ui.update_text("transformation_code", value=transformation_service.suggest_transformation_code(code, existing))
        ui.update_text("transformation_name", value=transformer.name)
        ui.update_text_area("transformation_description", value=transformer.description or "")

    @render.ui
    def transformer_description():
        transformer, _specs = _current_transformer_and_specs()
        if transformer is None:
            return ui.p("Add a baseline on the Baseline Data page first.", class_="text-muted")
        parts = [ui.p(transformer.description or "No description available.")]
        if transformer.description_units:
            parts.append(ui.tags.small(transformer.description_units, class_="text-muted"))
        return ui.div(*parts)

    @render.ui
    def existing_transformations_list():
        state.transformations_revision.get()
        transformations_obj = state.transformations_obj.get()
        code = input.transformer_code()
        if transformations_obj is None or not code:
            return ui.p("No transformations defined yet.", class_="text-muted")

        matches = sorted(
            (t for t in transformations_obj.dict_transformations.values() if t.transformer_code == code),
            key=lambda t: t.code,
        )
        if not matches:
            return ui.p("No transformations defined yet for this transformer.", class_="text-muted")

        items = [ui.tags.li(_transformation_tooltip(t)) for t in matches]
        return ui.tags.ul(*items, class_="ps-3 mb-0")

    @render.ui
    def param_form():
        _transformer, specs = _current_transformer_and_specs()
        if not specs:
            return ui.p("No parameters.", class_="text-muted")
        return param_widget.render_params(specs)

    @reactive.effect
    @reactive.event(input.save_transformation)
    def _on_save():
        transformer, specs = _current_transformer_and_specs()
        if transformer is None:
            last_save_result.set((False, "Choose a transformer first."))
            return

        code = (input.transformation_code() or "").strip()
        name = (input.transformation_name() or "").strip()
        if not code or not name:
            last_save_result.set((False, "Transformation code and name are required."))
            return
        if not code.startswith("TX:"):
            last_save_result.set((False, "Transformation code must start with 'TX:'."))
            return

        try:
            parameters = param_widget.read_params(input, specs)
        except param_widget.ParamReadError as e:
            last_save_result.set((False, str(e)))
            return

        transformations_obj = state.transformations_obj.get()
        try:
            transformation = transformation_service.build_transformation(
                transformation_code=code,
                transformation_name=name,
                transformer_code=transformer.code,
                parameters=parameters,
                transformers_catalog=state.transformers_catalog.get(),
                description=input.transformation_description() or "",
            )
            transformation_service.add_transformation(transformations_obj, transformation)
        except Exception as e:
            last_save_result.set((False, f"Failed to save: {e}"))
            return

        state.transformations_revision.set(state.transformations_revision.get() + 1)
        last_save_result.set((True, f"Saved '{code}'."))
        ui.notification_show(f"Saved transformation '{code}'.", type="message")

    @render.ui
    def save_status_ui():
        result = last_save_result.get()
        if result is None:
            return None
        ok, message = result
        return ui.div(message, class_="text-success" if ok else "text-danger")

    @reactive.effect
    @reactive.event(input.remove_transformation_btn)
    def _on_remove():
        transformations_obj = state.transformations_obj.get()
        target_code = input.remove_transformation_select()
        if transformations_obj is None or not target_code:
            return
        try:
            transformation_service.remove_transformation(transformations_obj, target_code)
        except ValueError as e:
            ui.notification_show(str(e), type="error")
            return
        state.transformations_revision.set(state.transformations_revision.get() + 1)
        ui.notification_show(f"Removed transformation '{target_code}'.", type="message")

    @reactive.effect
    def _sync_remove_choices():
        state.transformations_revision.get()
        transformations_obj = state.transformations_obj.get()
        if transformations_obj is None:
            return
        choices = {
            code: t.name
            for code, t in transformations_obj.dict_transformations.items()
            if code != transformations_obj.code_baseline
        }
        ui.update_select("remove_transformation_select", choices=choices)

    @render.data_frame
    def transformations_table():
        state.transformations_revision.get()
        transformations_obj = state.transformations_obj.get()
        if transformations_obj is None:
            return render.DataGrid(pd.DataFrame(columns=["code", "name", "transformer_code"]))
        rows = [
            {"code": t.code, "name": t.name, "transformer_code": t.transformer_code}
            for t in transformations_obj.dict_transformations.values()
        ]
        return render.DataGrid(pd.DataFrame(rows))

    def _n_non_baseline(transformations_obj, strategies_map) -> "tuple[int, int]":
        n_transformations = len(transformations_obj.dict_transformations) - 1
        n_strategies = len(strategies_map) - (1 if 0 in strategies_map else 0)
        return n_transformations, n_strategies

    last_save_dir_result = reactive.Value(None)  # (ok, message) | None
    last_load_dir_result = reactive.Value(None)  # (ok, message) | None

    @reactive.effect
    @reactive.event(input.save_dir_btn)
    async def _on_save_dir():
        transformations_obj = state.transformations_obj.get()
        if transformations_obj is None:
            last_save_dir_result.set((False, "Add a baseline on the Baseline Data page first."))
            return

        try:
            path = await _pick_directory()
        except Exception as e:
            last_save_dir_result.set((False, f"Could not open folder picker: {e}"))
            return
        if not path:
            return  # user cancelled -- leave prior status as-is

        strategies_map = state.strategies_map.get()
        try:
            persistence_service.export_transformations_dir(transformations_obj, strategies_map, path)
        except Exception as e:
            last_save_dir_result.set((False, f"Save failed: {e}"))
            return

        n_transformations, n_strategies = _n_non_baseline(transformations_obj, strategies_map)
        last_save_dir_result.set(
            (True, f"Saved {n_transformations} transformation(s) and {n_strategies} strategy(ies) to '{path}'.")
        )
        ui.notification_show("Transformations directory saved.", type="message")

    @reactive.effect
    @reactive.event(input.load_dir_btn)
    async def _on_load_dir():
        transformers_catalog = state.transformers_catalog.get()
        if transformers_catalog is None:
            last_load_dir_result.set((False, "Add a baseline on the Baseline Data page first."))
            return

        try:
            path = await _pick_directory()
        except Exception as e:
            last_load_dir_result.set((False, f"Could not open folder picker: {e}"))
            return
        if not path:
            return  # user cancelled -- leave prior status as-is

        try:
            transformations_obj, strategies_map = persistence_service.import_transformations_dir(
                path, transformers_catalog
            )
        except Exception as e:
            last_load_dir_result.set((False, f"Load failed: {e}"))
            return

        state.transformations_obj.set(transformations_obj)
        state.transformations_revision.set(state.transformations_revision.get() + 1)
        state.strategies_map.set(strategies_map)

        n_transformations, n_strategies = _n_non_baseline(transformations_obj, strategies_map)
        last_load_dir_result.set(
            (True, f"Loaded {n_transformations} transformation(s) and {n_strategies} strategy(ies) from '{path}'.")
        )
        ui.notification_show("Transformations directory loaded.", type="message")

    @render.ui
    def save_dir_status_ui():
        result = last_save_dir_result.get()
        if result is None:
            return None
        ok, message = result
        return ui.div(message, class_="text-success" if ok else "text-danger")

    @render.ui
    def load_dir_status_ui():
        result = last_load_dir_result.get()
        if result is None:
            return None
        ok, message = result
        return ui.div(message, class_="text-success" if ok else "text-danger")

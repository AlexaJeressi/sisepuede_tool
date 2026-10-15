"""Validation page (M6): compare model output against an observed dataset,
via a required crosswalk mapping combinations of validation fields to
combinations of SISEPUEDE output fields.
"""

import pandas as pd
import plotly.express as px
from shiny import module, reactive, render, ui
from shinywidgets import output_widget, render_plotly

from sisepuede_tool.services import i18n, output_service, validation_service
from sisepuede_tool.ui.state import AppState


@module.ui
def page_monitoring_ui():
    return ui.TagList(
        ui.layout_columns(
            ui.card(
                ui.card_header(i18n.t("monitoring.upload_title")),
                ui.input_file("validation_file", i18n.t("monitoring.dataset_csv"), accept=[".csv"]),
                ui.input_file("crosswalk_file", i18n.t("monitoring.crosswalk_csv"), accept=[".csv"]),
                ui.input_action_button("load_btn", i18n.t("monitoring.validate_load"), class_="btn-primary"),
                ui.output_ui("load_status_ui"),
            ),
            ui.card(
                ui.card_header(i18n.t("monitoring.compare_title")),
                ui.input_select("comparison_id", i18n.t("monitoring.comparison"), choices={}),
                ui.input_checkbox_group("combinations", i18n.t("monitoring.runs_to_compare"), choices={}),
                ui.output_ui("metrics_ui"),
            ),
            col_widths=[6, 6],
        ),
        ui.card(
            ui.card_header(i18n.t("monitoring.chart_title")),
            output_widget("chart"),
        ),
    )


@module.server
def page_monitoring_server(input, output, session, state: AppState):
    last_load_result = reactive.Value(None)  # (ok, message) | None

    def _t(key, **fmt):
        return i18n.t(f"monitoring.{key}", state.lang(), **fmt)

    @reactive.calc
    def output_catalog():
        if state.io_fields_cache.get() is None:
            state.io_fields_cache.set(output_service.get_output_catalog(state.model_attributes.get()))
        return state.io_fields_cache.get()

    @reactive.effect
    @reactive.event(input.load_btn)
    def _on_load():
        validation_file = input.validation_file()
        crosswalk_file = input.crosswalk_file()
        if not validation_file or not crosswalk_file:
            last_load_result.set((False, _t("choose_both")))
            return

        validation_df = validation_service.load_validation_dataset(validation_file[0]["datapath"])
        crosswalk_df = validation_service.load_crosswalk(crosswalk_file[0]["datapath"])
        result = validation_service.validate_crosswalk(crosswalk_df, validation_df, output_catalog())

        if not result.ok:
            last_load_result.set((False, _t("crosswalk_errors") + "\n" + "\n".join(result.errors)))
            return

        state.validation_dataset.set(validation_df)
        state.validation_crosswalk.set(crosswalk_df)
        last_load_result.set((True, i18n.tn("monitoring.loaded", len(result.comparison_ids), state.lang())))
        ui.notification_show(_t("data_loaded"), type="message")

    @render.ui
    def load_status_ui():
        result = last_load_result.get()
        if result is None:
            return ui.p(_t("no_data"), class_="text-muted")
        ok, message = result
        return ui.div(ui.tags.pre(message), class_="text-success" if ok else "text-danger")

    @reactive.effect
    def _sync_comparison_choices():
        crosswalk_df = state.validation_crosswalk.get()
        if crosswalk_df is None:
            return
        ids = sorted(crosswalk_df["comparison_id"].unique())
        labels = {cid: validation_service.comparison_label(crosswalk_df, cid) for cid in ids}
        ui.update_select("comparison_id", choices=labels)

    @reactive.effect
    def _sync_combination_choices():
        run_results = state.run_results.get()
        strategies_map = state.strategies_map.get()
        baselines = state.baselines.get()
        choices = {}
        for (strategy_id, baseline_id), result in run_results.items():
            if not result.ok:
                continue
            strategy_label = strategies_map[strategy_id].strategy.name if strategy_id in strategies_map else strategy_id
            baseline_label = baselines[baseline_id].label if baseline_id in baselines else baseline_id
            choices[f"{strategy_id}||{baseline_id}"] = f"{strategy_label} x {baseline_label}"
        ui.update_checkbox_group("combinations", choices=choices, selected=list(choices.keys()))

    def _comparison_frames():
        crosswalk_df = state.validation_crosswalk.get()
        validation_df = state.validation_dataset.get()
        run_results = state.run_results.get()
        comparison_id = input.comparison_id()
        raw_combinations = [tuple(c.split("||", 1)) for c in input.combinations()]

        frames = {}
        if crosswalk_df is None or validation_df is None or not comparison_id or not raw_combinations:
            return frames

        for strategy_id_str, baseline_id in raw_combinations:
            strategy_id = int(strategy_id_str)
            result = run_results.get((strategy_id, baseline_id))
            if result is None or not result.ok or result.df_output is None:
                continue
            frame = validation_service.aggregate_comparison(
                crosswalk_df, comparison_id, result.df_output, validation_df
            )
            frame = frame.copy()
            frame["run"] = f"{strategy_id}||{baseline_id}"
            frames[(strategy_id, baseline_id)] = frame
        return frames

    @render_plotly
    def chart():
        frames = _comparison_frames()
        if not frames:
            return px.line(title=_t("chart_empty"))

        strategies_map = state.strategies_map.get()
        baselines = state.baselines.get()
        combined = []
        for (strategy_id, baseline_id), frame in frames.items():
            frame = frame.copy()
            strategy_label = strategies_map[strategy_id].strategy.name if strategy_id in strategies_map else strategy_id
            baseline_label = baselines[baseline_id].label if baseline_id in baselines else baseline_id
            frame["series_label"] = frame["series"] + " (" + f"{strategy_label} x {baseline_label}" + ")"
            combined.append(frame)
        df = pd.concat(combined, ignore_index=True)

        fig = px.line(
            df,
            x="time_period",
            y="value",
            color="series_label",
            markers=True,
            labels={"time_period": _t("axis_year"), "value": _t("axis_value")},
        )
        fig.update_layout(legend_title_text=None)
        return fig

    @render.ui
    def metrics_ui():
        frames = _comparison_frames()
        if not frames:
            return None
        rows = []
        strategies_map = state.strategies_map.get()
        baselines = state.baselines.get()
        for (strategy_id, baseline_id), frame in frames.items():
            metrics = validation_service.compute_fit_metrics(frame)
            if not metrics:
                continue
            strategy_label = strategies_map[strategy_id].strategy.name if strategy_id in strategies_map else strategy_id
            baseline_label = baselines[baseline_id].label if baseline_id in baselines else baseline_id
            rows.append(
                ui.tags.li(
                    _t(
                        "metrics",
                        label=f"{strategy_label} x {baseline_label}",
                        rmse=metrics["rmse"],
                        mae=metrics["mae"],
                        bias=metrics["bias"],
                    )
                )
            )
        return ui.tags.ul(*rows) if rows else ui.p(_t("no_overlap"), class_="text-muted")

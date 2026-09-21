"""Cost and Benefits page (Review): cost-benefit results computed from run
Strategies, via `costs_benefits_ssp.CBSSPWrapperForDFComparison`.

Populated by the Run page's "Run Selected" action (see page_run.py), keyed
by baseline_id -- state.cb_results: Dict[str, Tuple[df_cb, df_attr_variable]].
The stacked bar chart is built from CBSSPWrapperForDFComparison's own
get_cba_plot_data (grouped by cb_type by default) -- note the baseline
("BASE") strategy never appears in it, since cost/benefit figures are deltas
relative to it, not absolute values for it.
"""

import pandas as pd
import plotly.express as px
from shiny import module, reactive, render, ui
from shinywidgets import output_widget, render_plotly

from sisepuede_tool.services import cost_benefit_service
from sisepuede_tool.ui.state import AppState


@module.ui
def page_cost_benefits_ui():
    return ui.TagList(
        ui.card(
            ui.card_header("Cost and Benefits"),
            ui.p(
                "Cost/benefit results by strategy and time period, computed from the Run page's "
                "'Run Selected' action. Choose a baseline to inspect its results.",
                class_="text-muted",
            ),
            ui.input_select("baseline_id", "Baseline", choices={}),
        ),
        ui.card(
            ui.card_header("Cost/Benefit by Category"),
            ui.input_select("strategy_id", "Strategy", choices={}),
            output_widget("cba_chart"),
        ),
        ui.layout_columns(
            ui.card(
                ui.card_header("Cost/Benefit Results"),
                ui.output_data_frame("cb_results_table"),
            ),
            ui.card(
                ui.card_header("Variable Attributes"),
                ui.output_data_frame("cb_attr_variable_table"),
            ),
            col_widths=[6, 6],
        ),
    )


@module.server
def page_cost_benefits_server(input, output, session, state: AppState):
    @reactive.effect
    def _sync_baseline_choices():
        cb_results = state.cb_results.get()
        choices = list(cb_results.keys())
        current = input.baseline_id() if "baseline_id" in input else None
        selected = current if current in choices else (choices[0] if choices else None)
        ui.update_select("baseline_id", choices=choices, selected=selected)

    def _current_results():
        cb_results = state.cb_results.get()
        baseline_id = input.baseline_id() if "baseline_id" in input else None
        return cb_results.get(baseline_id)

    @reactive.calc
    def plot_data():
        results = _current_results()
        cb_wrapper = state.cb_wrapper.get()
        if results is None or cb_wrapper is None:
            return pd.DataFrame()
        df_cb, df_attr_variable = results
        return cost_benefit_service.get_cba_plot_data(cb_wrapper, df_cb, df_attr_variable)

    @reactive.effect
    def _sync_strategy_choices():
        df = plot_data()
        strategies_map = state.strategies_map.get()
        if df.empty:
            ui.update_select("strategy_id", choices={})
            return
        strategy_ids = sorted(df["strategy_id"].unique().tolist())
        choices = {
            str(sid): strategies_map[sid].strategy.name if sid in strategies_map else str(sid)
            for sid in strategy_ids
        }
        current = input.strategy_id() if "strategy_id" in input else None
        selected = current if current in choices else next(iter(choices), None)
        ui.update_select("strategy_id", choices=choices, selected=selected)

    @render_plotly
    def cba_chart():
        df = plot_data()
        strategy_id_raw = input.strategy_id() if "strategy_id" in input else None
        if df.empty or not strategy_id_raw:
            return px.bar(title="Run at least one strategy to see cost/benefit results.")

        strategy_id = int(strategy_id_raw)
        df_strategy = df[df["strategy_id"] == strategy_id]
        group_cols = [c for c in df.columns if c not in ("strategy_id", "time_period")]
        long = df_strategy.melt(id_vars="time_period", value_vars=group_cols, var_name="category", value_name="value")

        fig = px.bar(long, x="time_period", y="value", color="category", barmode="relative")
        fig.update_layout(legend_title_text="Category")
        return fig

    @render.data_frame
    def cb_results_table():
        results = _current_results()
        if results is None:
            return render.DataGrid(pd.DataFrame())
        df_cb, _df_attr_variable = results
        return render.DataGrid(df_cb, height="400px")

    @render.data_frame
    def cb_attr_variable_table():
        results = _current_results()
        if results is None:
            return render.DataGrid(pd.DataFrame())
        _df_cb, df_attr_variable = results
        return render.DataGrid(df_attr_variable, height="400px")

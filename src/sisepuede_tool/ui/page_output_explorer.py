"""Emissions and Drivers page (M5): browse ModelVariables by sector/subsector,
optionally narrow to specific categories, compare selected runs with an
overlaid time-series chart, and download the underlying data. Works against
either a run's input (drivers fed to the model) or output (model results).
"""

import plotly.express as px
from shiny import module, reactive, render, ui
from shinywidgets import output_widget, render_plotly

from sisepuede_tool.services import output_service
from sisepuede_tool.ui.state import AppState


@module.ui
def page_output_explorer_ui():
    return ui.TagList(
        ui.layout_columns(
            ui.card(
                ui.card_header("Variables"),
                ui.input_select("sector", "Sector", choices={}),
                ui.input_select("subsector", "Subsector", choices={}),
                ui.input_select("variable", "Variable", choices={}),
                ui.input_selectize("categories", "Categories", choices={}, multiple=True),
                ui.input_radio_buttons(
                    "data_source",
                    "Data Source",
                    choices={"output": "Output (model results)", "input": "Input (drivers)"},
                    selected="output",
                ),
            ),
            ui.card(
                ui.card_header("Runs to compare"),
                ui.input_checkbox_group("combinations", None, choices={}),
            ),
            col_widths=[6, 6],
        ),
        ui.card(
            ui.card_header("Chart"),
            output_widget("chart"),
        ),
        ui.card(
            ui.card_header("Data"),
            ui.download_button("download_csv", "Download CSV"),
            ui.output_data_frame("data_table"),
        ),
    )


@module.server
def page_output_explorer_server(input, output, session, state: AppState):
    @reactive.calc
    def catalog():
        if state.io_fields_cache.get() is None:
            model_attributes = state.model_attributes.get()
            state.io_fields_cache.set(output_service.get_variable_catalog(model_attributes))
        return state.io_fields_cache.get()

    @reactive.effect
    def _sync_sector_choices():
        sectors = sorted(catalog()["sector"].unique())
        ui.update_select("sector", choices=sectors)

    @reactive.effect
    def _sync_subsector_choices():
        sector = input.sector()
        if not sector:
            return
        subsectors = sorted(catalog().loc[catalog()["sector"] == sector, "subsector"].unique())
        ui.update_select("subsector", choices=subsectors)

    @reactive.effect
    def _sync_variable_choices():
        subsector = input.subsector()
        if not subsector:
            return
        variables = sorted(catalog().loc[catalog()["subsector"] == subsector, "variable"].unique())
        ui.update_select("variable", choices=variables)

    @reactive.effect
    def _sync_category_choices():
        variable = input.variable() if "variable" in input else None
        model_attributes = state.model_attributes.get()
        if not variable or model_attributes is None:
            ui.update_selectize("categories", choices=[], selected=[])
            return
        categories = model_attributes.get_variable_categories(variable)
        if categories is None:
            ui.update_selectize("categories", choices=[], selected=[])
            return
        ui.update_selectize("categories", choices=categories, selected=categories)

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
            key = f"{strategy_id}||{baseline_id}"
            choices[key] = f"{strategy_label} x {baseline_label}"
        ui.update_checkbox_group("combinations", choices=choices, selected=list(choices.keys()))

    def _selected_combinations():
        return [tuple(c.split("||", 1)) for c in input.combinations()]

    def _plot_frame():
        model_attributes = state.model_attributes.get()
        run_results = state.run_results.get()
        strategies_map = state.strategies_map.get()
        baselines = state.baselines.get()
        variable = input.variable() if "variable" in input else None
        categories = list(input.categories()) if "categories" in input else []
        data_source = input.data_source() if "data_source" in input else "output"
        raw_combinations = _selected_combinations()
        combinations = [(int(sid), bid) for sid, bid in raw_combinations]
        if not variable or not combinations or model_attributes is None:
            return output_service.assemble_plot_frame(model_attributes, {}, None, [], data_source, [], {}, {})

        strategy_labels = {sid: entry.strategy.name for sid, entry in strategies_map.items()}
        baseline_labels = {bid: b.label for bid, b in baselines.items()}
        return output_service.assemble_plot_frame(
            model_attributes, run_results, variable, categories, data_source, combinations, strategy_labels, baseline_labels
        )

    @render_plotly
    def chart():
        df = _plot_frame()
        if df.empty:
            return px.line(title="Select a variable and at least one run to compare.")
        df = df.copy()
        df["series"] = df["strategy"] + " x " + df["baseline"]
        n_categories = df["category"].nunique()
        fig = px.line(
            df,
            x="time_period",
            y="value",
            color="series",
            facet_col="category" if n_categories > 1 else None,
            facet_col_wrap=3,
            markers=True,
        )
        fig.update_layout(legend_title_text="Strategy x Baseline")
        return fig

    @render.data_frame
    def data_table():
        return render.DataGrid(_plot_frame())

    @render.download_button(filename="sisepuede_output_explorer.csv")
    def download_csv():
        yield _plot_frame().to_csv(index=False)

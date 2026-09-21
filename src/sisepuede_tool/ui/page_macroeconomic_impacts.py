"""Macroeconomic Impacts page (Review): GDP/employment/other macroeconomic
effects of run Strategies.

Placeholder -- not yet implemented.
"""

from shiny import module, ui

from sisepuede_tool.ui.state import AppState


@module.ui
def page_macroeconomic_impacts_ui():
    return ui.card(
        ui.card_header("Macroeconomic Impacts"),
        ui.p(
            "Macroeconomic impact analysis for run Strategies is not yet implemented.",
            class_="text-muted",
        ),
    )


@module.server
def page_macroeconomic_impacts_server(input, output, session, state: AppState):
    pass

"""Macroeconomic Impacts page (Review): GDP/employment/other macroeconomic
effects of run Strategies.

Placeholder -- not yet implemented.
"""

from shiny import module, ui

from sisepuede_tool.services import i18n
from sisepuede_tool.ui.state import AppState


@module.ui
def page_macroeconomic_impacts_ui():
    return ui.card(
        ui.card_header(i18n.t("macroeconomic_impacts.title")),
        ui.p(i18n.t("macroeconomic_impacts.not_implemented"), class_="text-muted"),
    )


@module.server
def page_macroeconomic_impacts_server(input, output, session, state: AppState):
    pass

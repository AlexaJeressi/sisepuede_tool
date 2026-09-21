"""Article 6 page (Review): Paris Agreement Article 6 (cooperative approaches
/ ITMO) accounting for run Strategies.

Placeholder -- not yet implemented.
"""

from shiny import module, ui

from sisepuede_tool.ui.state import AppState


@module.ui
def page_article_6_ui():
    return ui.card(
        ui.card_header("Article 6"),
        ui.p(
            "Article 6 accounting for run Strategies is not yet implemented.",
            class_="text-muted",
        ),
    )


@module.server
def page_article_6_server(input, output, session, state: AppState):
    pass

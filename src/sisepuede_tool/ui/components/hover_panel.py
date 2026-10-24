"""Hover panel: a strip above a chart with the details of the bar under the
cursor (its customdata), so a long hover doesn't cover the rest of the chart
(resources/hover_panel.js).
"""

import pathlib

from shiny import ui
from shiny.module import resolve_id

JS = (pathlib.Path(__file__).resolve().parent.parent.parent / "resources" / "hover_panel.js").read_text()


def hover_panel(output_id: str, hint: str) -> ui.Tag:
    """Strip for the plotly output `output_id` (module-local id), showing
    `hint` until a bar is hovered."""
    return ui.div(
        ui.span(hint, class_="hover-panel-hint muted"),
        ui.div(class_="hover-panel-body"),
        class_="hover-panel small",
        data_chart=resolve_id(output_id),
        aria_live="polite",
    )

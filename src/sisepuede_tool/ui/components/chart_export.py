"""Chart export: a ⤓ button next to a results chart and the dialog it opens
(one per page, in app_shell). The browser redraws the chart with a title,
subtitle, source line and legend, in the chosen size, background
(transparent by default) and text colour, and saves it as PNG or SVG
(resources/chart_export.js).
"""

import pathlib

from shiny import ui
from shiny.module import resolve_id

from sisepuede_tool.services import i18n

JS = (pathlib.Path(__file__).resolve().parent.parent.parent / "resources" / "chart_export.js").read_text()


def export_button(output_id: str, title: str = "", lang: str | None = None) -> ui.Tag:
    """Button for the plotly output `output_id` (module-local id); `title` is
    the exported title it starts with. `lang` when rendered by the server."""
    return ui.tags.button(
        "⤓",
        type="button",
        class_="chart-export",
        title=i18n.t("charts.export", lang),
        data_chart=resolve_id(output_id),
        data_title=title,
        onclick="mrvChartExport(this); return false;",
    )


def _row(label: str, control: ui.Tag) -> ui.Tag:
    return ui.tags.label(ui.span(label, class_="section-label"), control, class_="exp-row")


def _select(name: str, options: dict) -> ui.Tag:
    return ui.tags.select(*[ui.tags.option(text, value=value) for value, text in options.items()], id=f"mrv-export-{name}")


def dialog() -> ui.Tag:
    t = i18n.t
    return ui.tags.dialog(
        ui.tags.form(
            ui.div(t("charts.export_title"), class_="exp-head"),
            _row(t("charts.export_chart_title"), ui.tags.input(type="text", id="mrv-export-title")),
            _row(t("charts.export_subtitle"), ui.tags.input(type="text", id="mrv-export-subtitle")),
            _row(t("charts.export_source"), ui.tags.input(type="text", id="mrv-export-source", value=t("charts.export_source_default"))),
            ui.div(
                _row(t("charts.export_width"), ui.tags.input(type="number", id="mrv-export-width", min="300", max="6000", step="10")),
                _row(t("charts.export_height"), ui.tags.input(type="number", id="mrv-export-height", min="200", max="6000", step="10")),
                _row(t("charts.export_format"), _select("format", {"png": "PNG", "svg": "SVG"})),
                class_="exp-grid",
            ),
            ui.div(
                _row(
                    t("charts.export_background"),
                    _select("background", {"transparent": t("charts.export_transparent"), "white": t("charts.export_white")}),
                ),
                _row(t("charts.export_text"), _select("text", {"dark": t("charts.export_dark"), "light": t("charts.export_light")})),
                _row(
                    t("charts.export_font"),
                    _select("scale", {"1": t("charts.export_font_m"), "1.3": t("charts.export_font_l"), "1.6": t("charts.export_font_xl")}),
                ),
                class_="exp-grid",
            ),
            ui.tags.label(
                ui.tags.input(type="checkbox", id="mrv-export-legend", checked=""), ui.span(t("charts.export_legend")), class_="exp-check"
            ),
            ui.div(t("charts.export_note"), class_="small muted"),
            ui.div(
                ui.tags.button(t("charts.export_cancel"), type="button", onclick="this.closest('dialog').close()"),
                ui.tags.button(t("charts.export_go"), type="button", id="mrv-export-go", onclick="mrvChartExportGo()"),
                class_="exp-actions",
            ),
            method="dialog",
        ),
        id="mrv-export",
        class_="exp-dialog",
    )

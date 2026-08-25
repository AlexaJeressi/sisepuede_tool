"""Renders a list of ParamSpec into Shiny inputs, and reads their current
values back into a parameters dict ready for transformation_service.

Input ids are namespaced as `param__{name}` (or `param__{name}__{field}` for
the five RAMP_VECTOR sub-fields) so the same id scheme can be used to render
and to read back regardless of which transformer is currently selected --
callers must re-render whenever the selected transformer changes, since a
stale spec list read against a freshly-rendered form (or vice versa) would
reference ids that no longer exist.
"""

import json
from typing import Any, Dict, List

from shiny import ui

from sisepuede_tool.models.param_spec import ParamSpec, WidgetKind


def _param_id(name: str, field: str = None) -> str:
    return f"param__{name}" if field is None else f"param__{name}__{field}"


def _label(spec: ParamSpec) -> str:
    return spec.extra.get("label", spec.name)


def render_param(spec: ParamSpec) -> ui.TagList:
    label = _label(spec)
    help_text = ui.tags.small(spec.help_text, class_="text-muted d-block") if spec.help_text else None

    if spec.kind == WidgetKind.BOOL:
        widget = ui.input_switch(_param_id(spec.name), label, value=bool(spec.default))

    elif spec.kind == WidgetKind.NUMERIC:
        if spec.bounds is not None:
            lo, hi = spec.bounds
            widget = ui.input_slider(
                _param_id(spec.name), label, min=lo, max=hi, value=spec.default, step=(hi - lo) / 100 or 0.01
            )
        else:
            widget = ui.input_numeric(_param_id(spec.name), label, value=spec.default)

    elif spec.kind == WidgetKind.CATEGORICAL_MULTI:
        if spec.choices:
            widget = ui.input_selectize(
                _param_id(spec.name), label, choices=spec.choices, selected=spec.default, multiple=True
            )
        else:
            widget = ui.input_text(
                _param_id(spec.name), f"{label} (comma-separated)", value=", ".join(spec.default or [])
            )

    elif spec.kind == WidgetKind.TEXT:
        widget = ui.input_text(_param_id(spec.name), label, value=spec.default or "")

    elif spec.kind == WidgetKind.JSON:
        widget = ui.input_text_area(
            _param_id(spec.name), f"{label} (JSON)", value=json.dumps(spec.default), rows=3
        )

    elif spec.kind == WidgetKind.RAMP_VECTOR:
        total = spec.extra.get("total_time_periods", 100)
        d = spec.default
        widget = ui.card(
            ui.card_header(label),
            ui.input_numeric(
                _param_id(spec.name, "n_tp_ramp"), "n_tp_ramp (periods to reach full implementation)",
                value=d["n_tp_ramp"], min=0, max=total,
            ),
            ui.input_numeric(
                _param_id(spec.name, "tp_0_ramp"), "tp_0_ramp (first period of the ramp)",
                value=d["tp_0_ramp"], min=0, max=total,
            ),
            ui.input_slider(
                _param_id(spec.name, "alpha_logistic"), "alpha_logistic (logistic vs. linear weight)",
                min=0.0, max=1.0, value=d["alpha_logistic"], step=0.01,
            ),
            ui.input_numeric(
                _param_id(spec.name, "window_lower"), "window_logistic lower bound (must be < 0)",
                value=d["window_logistic"][0],
            ),
            ui.input_numeric(
                _param_id(spec.name, "window_upper"), "window_logistic upper bound (must be > 0)",
                value=d["window_logistic"][1],
            ),
            ui.input_numeric(
                _param_id(spec.name, "d"), "d (logistic centroid, must lie within the window bounds)",
                value=d["d"],
            ),
        )

    else:
        widget = ui.input_text(_param_id(spec.name), label, value=str(spec.default))

    if help_text is None:
        return ui.div(widget, class_="mb-3")
    return ui.div(widget, help_text, class_="mb-3")


def render_params(specs: List[ParamSpec]) -> ui.TagList:
    return ui.TagList(*[render_param(s) for s in specs])


class ParamReadError(ValueError):
    pass


def read_params(input, specs: List[ParamSpec]) -> Dict[str, Any]:
    values: Dict[str, Any] = {}

    for spec in specs:
        if spec.kind == WidgetKind.RAMP_VECTOR:
            n_tp_ramp = input[_param_id(spec.name, "n_tp_ramp")]()
            tp_0_ramp = input[_param_id(spec.name, "tp_0_ramp")]()
            alpha_logistic = input[_param_id(spec.name, "alpha_logistic")]()
            window_lower = input[_param_id(spec.name, "window_lower")]()
            window_upper = input[_param_id(spec.name, "window_upper")]()
            d = input[_param_id(spec.name, "d")]()

            if window_lower >= 0 or window_upper <= 0:
                raise ParamReadError(
                    f"'{spec.name}': window_logistic lower bound must be < 0 and upper bound must be > 0."
                )
            if not (window_lower < d < window_upper):
                raise ParamReadError(
                    f"'{spec.name}': d ({d}) must lie strictly between the window bounds "
                    f"({window_lower}, {window_upper})."
                )

            values[spec.name] = {
                "n_tp_ramp": int(n_tp_ramp),
                "tp_0_ramp": int(tp_0_ramp),
                "alpha_logistic": float(alpha_logistic),
                "d": float(d),
                "window_logistic": (window_lower, window_upper),
            }
            continue

        raw = input[_param_id(spec.name)]()

        if spec.kind == WidgetKind.JSON:
            try:
                values[spec.name] = json.loads(raw)
            except (json.JSONDecodeError, TypeError) as e:
                raise ParamReadError(f"'{spec.name}': invalid JSON ({e}).") from e
        elif spec.kind == WidgetKind.CATEGORICAL_MULTI and spec.choices is None:
            values[spec.name] = [v.strip() for v in raw.split(",") if v.strip()]
        else:
            values[spec.name] = raw

    return values

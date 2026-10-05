"""Renders a list of ParamSpec into Shiny inputs, and reads their current
values back into a parameters dict ready for transformation_service.

Input ids are namespaced as `param__{name}` (or `param__{name}__{field}` for
sub-fields: the five RAMP_VECTOR fields, the exact value of a numeric, one
cell per key of a DICT_TABLE) so the same id scheme can be used to render
and to read back regardless of which transformer is currently selected --
callers must re-render whenever the selected transformer changes, since a
stale spec list read against a freshly-rendered form (or vice versa) would
reference ids that no longer exist.

Labels are plain language; the sisepuede parameter name only appears in an
ⓘ tooltip (shown with Advanced options on).
"""

import dataclasses
import json
import math
from typing import Any, Dict, List, Optional

from shiny import ui
from shiny.module import resolve_id

from sisepuede_tool.models.param_spec import ParamSpec, WidgetKind
from sisepuede_tool.services import labels
from sisepuede_tool.services import param_schema_service as pss
from sisepuede_tool.ui.components.info_tip import info_tip


def _param_id(name: str, field: str = None) -> str:
    return f"param__{name}" if field is None else f"param__{name}__{field}"


def _label_text(spec: ParamSpec) -> str:
    return labels.param_label(spec.name, spec.label or spec.extra.get("label"))


def code_tip(name: str) -> ui.Tag:
    """ⓘ with the sisepuede name in its bubble (visible in advanced mode)."""
    return info_tip(f"sisepuede: {name}", class_="code-tip")


def _label_tag(text: str, name: str) -> ui.Tag:
    return ui.span(text, " ", code_tip(name))


##########################################
#    RANGE + EXACT VALUE                 #
##########################################

# A native <input type="range"> moves without any server traffic; only on
# release is the value written to the paired exact-value numeric input
# (`param__{name}__precise`), which is the Shiny input actually read.


def _range_sync_script(range_id: str, out_id: str, precise_id: str, factor: float, percent: bool) -> ui.Tag:
    return ui.tags.script(
        ui.HTML(
            f"""
            (function wire() {{
              var r = document.getElementById({json.dumps(range_id)});
              var o = document.getElementById({json.dumps(out_id)});
              var p = document.getElementById({json.dumps(precise_id)});
              if (!r || !p) {{ setTimeout(wire, 50); return; }}
              var f = {factor}, pct = {json.dumps(percent)};
              function fmt(v) {{ return pct ? (+v.toFixed(2)) + '%' : String(+v.toPrecision(5)); }}
              function paint(v) {{
                var lo = +r.min, hi = +r.max;
                r.style.setProperty('--fill', (hi > lo ? (v - lo) / (hi - lo) * 100 : 0) + '%');
                if (o) o.textContent = fmt(v);
              }}
              r.addEventListener('input', function() {{ paint(+r.value); }});
              r.addEventListener('change', function() {{
                $(p).val(+(+r.value / f).toFixed(8)).trigger('change');
              }});
              $(p).on('change input', function() {{
                var v = parseFloat(p.value);
                if (!isNaN(v)) {{ r.value = v * f; paint(v * f); }}
              }});
              paint(+r.value);
            }})();
            """
        )
    )


def _range_with_exact(
    name: str, label: ui.TagChild, value: float, lo: float, hi: float, exact_in_advanced: bool, note: str = None
) -> ui.Tag:
    as_percent = lo == 0.0 and hi == 1.0
    factor = 100.0 if as_percent else 1.0
    step = 0.1 if as_percent else ((hi - lo) / 1000 or 0.001)
    precise_id = _param_id(name, "precise")
    range_id = _param_id(name, "range")
    out_id = _param_id(name, "range_out")
    exact = ui.div(
        ui.input_numeric(precise_id, "Exact value", value=value, min=lo, max=hi, step=1e-5),
        ui.tags.small(note, class_="muted d-block") if note else None,
        class_="adv-only" if exact_in_advanced else None,
    )
    return ui.div(
        ui.tags.label(label, class_="control-label", **{"for": resolve_id(range_id)}),
        ui.div(
            ui.tags.input(
                type="range",
                id=resolve_id(range_id),
                min=lo * factor,
                max=hi * factor,
                step=step,
                value=value * factor,
                class_="mrv-range",
            ),
            ui.span("", id=resolve_id(out_id), class_="mrv-range-out mono"),
            class_="mrv-range-row",
        ),
        exact,
        _range_sync_script(resolve_id(range_id), resolve_id(out_id), resolve_id(precise_id), factor, as_percent),
    )


##########################################
#    DICT TABLES                         #
##########################################

# One row per allowed key (from param_schemas.yaml); a blank cell means "not
# included". A small delegated script keeps the total and the sum-rule
# message up to date while typing; the same rule is enforced on read.

_DICT_TABLE_JS = """
if (!window.mrvDictTable) {
  window.mrvDictTable = true;
  function mrvDictTotal(table) {
    var rule = table.getAttribute('data-rule');
    var out = table.querySelector('.dict-total');
    if (!out || !rule || rule === 'none') return;
    var total = 0;
    table.querySelectorAll('.dict-row input[type=number]').forEach(function(i) {
      var v = parseFloat(i.value); if (!isNaN(v)) total += v;
    });
    var ok = rule === 'eq1' ? Math.abs(total - 100) < 1e-4 : total <= 100 + 1e-4;
    var msg = rule === 'eq1' ? 'must total exactly 100%' : "can't be above 100%";
    out.textContent = 'Total ' + (+total.toFixed(3)) + '% · ' + msg;
    out.classList.toggle('bad', !ok);
    var btn = table.querySelector('.dict-scale');
    if (btn) btn.style.display = (!ok && total > 0) ? '' : 'none';
  }
  $(document).on('input change', '.dict-table .dict-row input[type=number]', function() {
    mrvDictTotal(this.closest('.dict-table'));
  });
  $(document).on('click', '.dict-table .dict-scale', function() {
    var table = this.closest('.dict-table');
    var inputs = Array.from(table.querySelectorAll('.dict-row input[type=number]'));
    var total = inputs.reduce(function(s, i) { var v = parseFloat(i.value); return isNaN(v) ? s : s + v; }, 0);
    if (total <= 0) return;
    inputs.forEach(function(i) {
      var v = parseFloat(i.value);
      if (!isNaN(v)) $(i).val(+(v * 100 / total).toFixed(4)).trigger('change');
    });
    mrvDictTotal(table);
  });
  window.mrvDictTotal = mrvDictTotal;
}
"""


def _cell_id(name: str, key: str, suffix: str = None) -> str:
    return _param_id(name, f"k__{key}" + (f"__{suffix}" if suffix else ""))


def _pair_id(name: str, i: int, field: str) -> str:
    return _param_id(name, f"r{i}__{field}")


def _unit_suffix(schema: dict) -> str:
    unit = schema.get("unit")
    if pss.is_percent(schema):
        return "%"
    return {"ha": "ha", "ratio": "×"}.get(unit, "")


def _value_bounds(schema: dict):
    """(min, max) in display units."""
    unit = schema.get("unit")
    if unit == "share":
        return 0.0, 100.0
    if unit == "percent_change":
        return -100.0, 100.0
    if unit in ("ha", "ratio"):
        return 0.0, None
    return None, None


def _to_display(schema: dict, v: Any) -> Optional[float]:
    if v is None or isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    return round(float(v) * 100, 6) if pss.is_percent(schema) else float(v)


def _from_display(schema: dict, v: float) -> float:
    return float(v) / 100 if pss.is_percent(schema) else float(v)


def _num_cell(input_id: str, value: Optional[float], schema: dict) -> ui.Tag:
    lo, hi = _value_bounds(schema)
    step = 0.1 if pss.is_percent(schema) else "any"
    return ui.input_numeric(input_id, None, value=value, min=lo, max=hi, step=step)


def _table_head(spec: ParamSpec, schema: dict) -> List[ui.Tag]:
    return [
        ui.div(_label_tag(_label_text(spec), spec.name), class_="dict-title"),
        ui.tags.small(spec.help_text, class_="muted d-block mb-1") if spec.help_text else None,
    ]


def _dropped_note(dropped: List[str]) -> Optional[ui.Tag]:
    if not dropped:
        return None
    return ui.tags.small(
        "Not valid for this transformer and ignored by sisepuede: " + ", ".join(dropped),
        class_="muted d-block",
    )


def _render_value_table(spec: ParamSpec, schema: dict) -> ui.Tag:
    keys, names = schema["keys"], schema["labels"]
    current = pss.expand_value(schema, spec.default, keys)
    dropped = [str(k) for k in current if k not in keys]
    suffix = _unit_suffix(schema)
    rows = [
        ui.div(
            ui.span(names.get(k, k), class_="dict-key", title=k),
            _num_cell(_cell_id(spec.name, k), _to_display(schema, current.get(k)), schema),
            ui.span(suffix, class_="dict-unit"),
            class_="dict-row",
        )
        for k in keys
    ]
    rule = schema.get("sum_rule") or pss.SUM_NONE
    foot = None
    if rule != pss.SUM_NONE:
        total = sum(v for v in (current.get(k) for k in keys) if isinstance(v, (int, float)))
        ok, _ = pss.check_sum({k: current.get(k) for k in keys if isinstance(current.get(k), (int, float))}, rule)
        msg = "must total exactly 100%" if rule == pss.SUM_EQ1 else "can't be above 100%"
        foot = ui.div(
            ui.span(f"Total {round(total * 100, 3):g}% · {msg}", class_="dict-total" + ("" if ok else " bad")),
            ui.tags.button(
                "Scale to 100%", type="button", class_="btn btn-inline dict-scale",
                style="" if (not ok and total > 0) else "display:none",
            ),
            class_="dict-foot",
        )
    return ui.div(
        *_table_head(spec, schema),
        ui.div(*rows, class_="dict-rows"),
        foot,
        ui.tags.small("Leave every cell blank to use sisepuede's default.", class_="muted d-block"),
        _dropped_note(dropped),
        ui.tags.script(ui.HTML(_DICT_TABLE_JS)),
        class_="dict-table",
        **{"data-rule": rule},
    )


def _render_bounds_table(spec: ParamSpec, schema: dict) -> ui.Tag:
    keys, names = schema["keys"], schema["labels"]
    current: Dict[tuple, float] = {}
    dropped = []
    for raw, v in (spec.default or {}).items() if isinstance(spec.default, dict) else []:
        parsed = pss.parse_bound_key(raw)
        if parsed and parsed[0] in keys and parsed[1] in pss.BOUND_DIRECTIONS:
            current[parsed] = v
        else:
            dropped.append(str(raw))
    unit = _unit_suffix(schema)
    head = ui.div(
        ui.span("", class_="dict-key"),
        *[ui.span(f"{d.capitalize()} ({unit})", class_="dict-bound-head muted small") for d in pss.BOUND_DIRECTIONS],
        class_="dict-row dict-bounds",
    )
    rows = [
        ui.div(
            ui.span(names.get(k, k), class_="dict-key", title=k),
            *[_num_cell(_cell_id(spec.name, k, d), _to_display(schema, current.get((k, d))), schema) for d in pss.BOUND_DIRECTIONS],
            class_="dict-row dict-bounds",
        )
        for k in keys
    ]
    return ui.div(
        *_table_head(spec, schema),
        ui.div(head, *rows, class_="dict-rows"),
        _dropped_note(dropped),
        class_="dict-table",
        **{"data-rule": pss.SUM_NONE},
    )


def _render_pairs_table(spec: ParamSpec, schema: dict) -> ui.Tag:
    names = schema["labels"]
    keys_out, keys_in = schema["keys_out"], schema["keys_in"]
    n_rows = int(schema.get("rows", 4))
    current = []
    if isinstance(spec.default, dict):
        for k_out, inner in spec.default.items():
            if isinstance(inner, dict):
                current.extend((k_out, k_in, v) for k_in, v in inner.items())
    choices_out = {"": "—", **{k: names.get(k, k) for k in keys_out}}
    choices_in = {"": "—", **{k: names.get(k, k) for k in keys_in}}
    rows = []
    for i in range(n_rows):
        k_out, k_in, v = current[i] if i < len(current) else ("", "", None)
        rows.append(
            ui.div(
                ui.input_select(_pair_id(spec.name, i, "out"), None, choices_out, selected=k_out if k_out in keys_out else ""),
                ui.input_select(_pair_id(spec.name, i, "in"), None, choices_in, selected=k_in if k_in in keys_in else ""),
                _num_cell(_pair_id(spec.name, i, "val"), _to_display(schema, v), schema),
                class_="dict-row dict-pair",
            )
        )
    ignored = [f"{a}/{b}" for a, b, _ in current[n_rows:]]
    return ui.div(
        *_table_head(spec, schema),
        ui.div(
            ui.span("Produced fuel", class_="muted small"),
            ui.span("Per unit of input fuel", class_="muted small"),
            ui.span("Output / input", class_="muted small"),
            class_="dict-pair dict-pair-head",
        ),
        ui.div(*rows, class_="dict-rows"),
        _dropped_note(ignored),
        class_="dict-table",
        **{"data-rule": pss.SUM_NONE},
    )


def _render_dict_table(spec: ParamSpec) -> ui.Tag:
    schema = spec.schema or {}
    widget = schema.get("widget")
    if widget == pss.WIDGET_BOUNDS:
        return _render_bounds_table(spec, schema)
    if widget == pss.WIDGET_PAIRS:
        return _render_pairs_table(spec, schema)
    return _render_value_table(spec, schema)


def _blank(v) -> bool:
    return v is None or v == "" or (isinstance(v, float) and math.isnan(v))


def _check_range(spec: ParamSpec, schema: dict, key: str, shown: float) -> None:
    lo, hi = _value_bounds(schema)
    suffix = _unit_suffix(schema)
    if (lo is not None and shown < lo) or (hi is not None and shown > hi):
        bounds = f"{lo:g}{suffix} to {hi:g}{suffix}" if hi is not None else f"at least {lo:g}{suffix}"
        raise ParamReadError(f"{_label_text(spec)}: {schema['labels'].get(key, key)} must be {bounds}.")


def _read_dict_table(input, spec: ParamSpec):
    """The dict for sisepuede, or None when every cell is blank (the
    parameter is then left out, so sisepuede uses its default)."""
    schema = spec.schema or {}
    widget = schema.get("widget")

    if widget == pss.WIDGET_PAIRS:
        out: Dict[str, Dict[str, float]] = {}
        for i in range(int(schema.get("rows", 4))):
            k_out = input[_pair_id(spec.name, i, "out")]()
            k_in = input[_pair_id(spec.name, i, "in")]()
            v = input[_pair_id(spec.name, i, "val")]()
            if not k_out and not k_in and _blank(v):
                continue
            if not k_out or not k_in or _blank(v):
                raise ParamReadError(f"{_label_text(spec)}: row {i + 1} needs a produced fuel, an input fuel and a value.")
            if float(v) <= 0:
                raise ParamReadError(f"{_label_text(spec)}: row {i + 1} efficiency must be above 0.")
            out.setdefault(k_out, {})[k_in] = float(v)
        return out or None

    if widget == pss.WIDGET_BOUNDS:
        out = {}
        for k in schema["keys"]:
            for d in pss.BOUND_DIRECTIONS:
                v = input[_cell_id(spec.name, k, d)]()
                if _blank(v):
                    continue
                _check_range(spec, schema, k, float(v))
                out[pss.bound_key(k, d)] = _from_display(schema, v)
        return out or None

    values = {}
    for k in schema["keys"]:
        v = input[_cell_id(spec.name, k)]()
        if _blank(v):
            continue
        _check_range(spec, schema, k, float(v))
        values[k] = _from_display(schema, v)
    if not values:
        return None
    rule = schema.get("sum_rule")
    ok, message = pss.check_sum(values, rule)
    if not ok:
        raise ParamReadError(f"{_label_text(spec)}: {message}")
    return pss.normalize_for_rule(values, rule)


##########################################
#    GENERIC WIDGETS                     #
##########################################

_RAMP_FIELD_LABELS = {
    "n_tp_ramp": ("Periods to reach full effect", "n_tp_ramp"),
    "tp_0_ramp": ("Last period with no change", "tp_0_ramp"),
    "alpha_logistic": ("Curve steepness (0 = straight line)", "alpha_logistic"),
    "window_lower": ("Curve window start (below 0)", "window_logistic[0]"),
    "window_upper": ("Curve window end (above 0)", "window_logistic[1]"),
    "d": ("Curve centre (has no effect)", "d"),
}


def _ramp_label(field: str) -> ui.Tag:
    text, name = _RAMP_FIELD_LABELS[field]
    return _label_tag(text, name)


def render_param(spec: ParamSpec) -> ui.TagList:
    label = _label_tag(_label_text(spec), spec.name)
    help_text = ui.tags.small(spec.help_text, class_="text-muted d-block") if spec.help_text else None

    if spec.kind == WidgetKind.DICT_TABLE:
        return ui.div(_render_dict_table(spec), class_="mb-3")

    if spec.kind == WidgetKind.NOTE:
        return ui.div(ui.tags.b(_label_text(spec)), " ", code_tip(spec.name), ui.div(spec.help_text or ""), class_="info-box mb-3")

    if spec.kind == WidgetKind.BOOL:
        widget = ui.input_switch(_param_id(spec.name), label, value=bool(spec.default))

    elif spec.kind == WidgetKind.NUMERIC:
        if spec.bounds is not None:
            lo, hi = spec.bounds
            value = float(spec.default) if isinstance(spec.default, (int, float)) else lo
            widget = _range_with_exact(spec.name, label, value, lo, hi, exact_in_advanced=False)
        else:
            widget = ui.input_numeric(_param_id(spec.name), label, value=spec.default)

    elif spec.kind == WidgetKind.SELECT:
        choices = dict(spec.choices) if isinstance(spec.choices, dict) else {c: c for c in spec.choices or []}
        selected = spec.default if spec.default in choices else ""
        widget = ui.input_select(_param_id(spec.name), label, {"": "sisepuede default", **choices}, selected=selected)

    elif spec.kind == WidgetKind.CATEGORICAL_MULTI:
        if spec.choices:
            widget = ui.input_selectize(
                _param_id(spec.name), label, choices=spec.choices, selected=spec.default, multiple=True
            )
        else:
            widget = ui.input_text(_param_id(spec.name), label, value=", ".join(spec.default or []))
            help_text = ui.tags.small(
                (spec.help_text + " " if spec.help_text else "") + "Separate entries with commas.",
                class_="text-muted d-block",
            )

    elif spec.kind == WidgetKind.TEXT:
        widget = ui.input_text(_param_id(spec.name), label, value=spec.default or "")

    elif spec.kind == WidgetKind.JSON:
        widget = ui.input_text_area(_param_id(spec.name), label, value=json.dumps(spec.default), rows=3)
        help_text = ui.tags.small(
            (spec.help_text + " " if spec.help_text else "") + "Written as JSON.", class_="text-muted d-block"
        )

    elif spec.kind == WidgetKind.RAMP_VECTOR:
        total = spec.extra.get("total_time_periods", 100)
        d = spec.default
        widget = ui.card(
            ui.card_header(label),
            ui.input_numeric(_param_id(spec.name, "n_tp_ramp"), _ramp_label("n_tp_ramp"), value=d["n_tp_ramp"], min=0, max=total),
            ui.input_numeric(_param_id(spec.name, "tp_0_ramp"), _ramp_label("tp_0_ramp"), value=d["tp_0_ramp"], min=0, max=total),
            ui.input_slider(
                _param_id(spec.name, "alpha_logistic"), _ramp_label("alpha_logistic"),
                min=0.0, max=1.0, value=d["alpha_logistic"], step=0.01,
            ),
            ui.input_numeric(_param_id(spec.name, "window_lower"), _ramp_label("window_lower"), value=d["window_logistic"][0]),
            ui.input_numeric(_param_id(spec.name, "window_upper"), _ramp_label("window_upper"), value=d["window_logistic"][1]),
            ui.input_numeric(_param_id(spec.name, "d"), _ramp_label("d"), value=d["d"]),
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
    """Note and blank dict-table parameters are left out of the result, so
    sisepuede uses its own default for them."""
    values: Dict[str, Any] = {}

    for spec in specs:
        if spec.kind == WidgetKind.NOTE:
            continue

        if spec.kind == WidgetKind.DICT_TABLE:
            value = _read_dict_table(input, spec)
            if value is not None:
                values[spec.name] = value
            continue

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

        if spec.kind == WidgetKind.NUMERIC and spec.bounds is not None:
            # The exact-value numeric input is the source of truth; the range
            # next to it only writes to it on release (see _range_sync_script).
            values[spec.name] = input[_param_id(spec.name, "precise")]()
            continue

        raw = input[_param_id(spec.name)]()

        if spec.kind == WidgetKind.JSON:
            try:
                values[spec.name] = json.loads(raw)
            except (json.JSONDecodeError, TypeError) as e:
                raise ParamReadError(f"'{spec.name}': invalid JSON ({e}).") from e
        elif spec.kind == WidgetKind.SELECT:
            values[spec.name] = raw or None
        elif spec.kind == WidgetKind.CATEGORICAL_MULTI:
            # selectize returns a tuple; an empty selection means "sisepuede's
            # default" (None), which sisepuede treats differently from []
            if not spec.choices:
                picked = [v.strip() for v in raw.split(",") if v.strip()]
            else:
                picked = list(raw or [])
            values[spec.name] = picked or None
        else:
            values[spec.name] = raw

    return values


##########################################
#    TRANSFORMATION EDITOR (basic/adv)   #
##########################################

# The Pathways editor shows the main magnitude as a percentage range and the
# implementation ramp as policy terms (start year, full-effect year, shape).
# Everything else is placed by `ParamSpec.tier`; advanced inputs are wrapped
# in `.adv-only` and so are only visible with the sidebar "Advanced options"
# switch on (they are always rendered, so reading them never fails).

RAMP_YEARS_FIELD = "years"
RAMP_SHAPE_FIELD = "shape"
RAMP_RAW_FIELD = "raw_on"


def spec_with_value(spec: ParamSpec, value: Any) -> ParamSpec:
    """Copy of `spec` whose default is a transformation's current value."""
    if value is None and spec.kind != WidgetKind.JSON:
        return spec
    if spec.kind == WidgetKind.RAMP_VECTOR and isinstance(value, dict):
        merged = dict(spec.default)
        merged.update({k: v for k, v in value.items() if v is not None})
        value = merged
    return dataclasses.replace(spec, default=value)


def render_magnitude(spec: ParamSpec, value: float, label: str, help_text: str = None) -> ui.Tag:
    lo, hi = spec.bounds or (0.0, 1.0)
    return ui.div(
        _range_with_exact(
            spec.name,
            _label_tag(label, spec.name),
            value,
            lo,
            hi,
            exact_in_advanced=True,
            note="The range moves in steps; this exact value is what gets saved.",
        ),
        ui.tags.small(help_text, class_="muted d-block") if help_text else None,
        class_="mb-3",
    )


def render_policy_ramp(
    spec: ParamSpec,
    ramp: dict,
    years: List[int],
    default_ramp: dict,
) -> ui.Tag:
    """Start / full-effect years + shape, with the raw sisepuede ramp in an
    advanced box. `ramp` is the transformation's ramp dict (may be partial)."""
    from sisepuede_tool.services import ramp_service

    policy = ramp_service.policy_from_ramp(ramp, years, default_ramp)
    raw_values = ramp_service.fill_ramp_defaults(ramp, default_ramp)
    raw_spec = spec_with_value(spec, {**raw_values, "window_logistic": tuple(raw_values["window_logistic"])})
    raw_spec = dataclasses.replace(raw_spec, label="Raw timing values")
    shape = policy.shape if policy.shape in ramp_service.SHAPES else "linear"
    return ui.div(
        ui.input_slider(
            _param_id(spec.name, RAMP_YEARS_FIELD),
            "Starts in → full effect by",
            min=years[1],
            max=years[-1],
            value=(policy.start_year, policy.full_year),
            step=1,
            sep="",
            drag_range=True,
        ),
        ui.div(
            ui.tags.label("Ramp shape", class_="d-block"),
            ui.input_radio_buttons(
                _param_id(spec.name, RAMP_SHAPE_FIELD),
                None,
                choices={k: v["label"] for k, v in ramp_service.SHAPES.items()},
                selected=shape,
                inline=True,
            ),
            class_="seg mb-2",
        ),
        ui.div(
            ui.input_switch(
                _param_id(spec.name, RAMP_RAW_FIELD),
                "Set the timing with raw values instead",
                value=policy.shape == ramp_service.CUSTOM_SHAPE,
            ),
            ui.tags.small(
                "Periods count from the first model year. Full effect is reached at "
                "“last period with no change” + “periods to reach full effect”.",
                class_="muted d-block mb-2",
            ),
            render_param(raw_spec),
            class_="adv-only adv-box",
        ),
        class_="mb-3",
    )


def render_editor_params(
    specs: List[ParamSpec],
    values: Dict[str, Any],
    years: List[int],
    default_ramp: dict,
    magnitude_name: str = None,
    magnitude_label: str = None,
    magnitude_help: str = None,
) -> Dict[str, ui.TagList]:
    """{'magnitude': ..., 'ramp': ..., 'basic': ..., 'advanced': ...} blocks
    for the editor to place."""
    out = {"magnitude": None, "ramp": None, "basic": [], "advanced": []}
    for spec in specs:
        value = values.get(spec.name)
        if spec.kind == WidgetKind.RAMP_VECTOR:
            ramp = value if isinstance(value, dict) else None
            out["ramp"] = render_policy_ramp(spec, ramp, years, default_ramp)
            continue
        if spec.name == magnitude_name and spec.kind == WidgetKind.NUMERIC:
            current = float(value) if isinstance(value, (int, float)) else float(spec.default)
            label = magnitude_label or _label_text(spec)
            out["magnitude"] = render_magnitude(spec, current, label, magnitude_help or spec.help_text)
            continue
        rendered = render_param(spec_with_value(spec, value))
        if spec.tier == "basic":
            out["basic"].append(rendered)
        else:
            out["advanced"].append(rendered)
    out["basic"] = ui.TagList(*out["basic"])
    out["advanced"] = ui.TagList(*out["advanced"])
    return out


def read_editor_params(input, specs: List[ParamSpec], years: List[int]) -> Dict[str, Any]:
    """Parameters dict for transformation_service from the editor's inputs.
    Raises ParamReadError on invalid input."""
    from sisepuede_tool.services import ramp_service

    ramp_specs = [s for s in specs if s.kind == WidgetKind.RAMP_VECTOR]
    other_specs = [s for s in specs if s.kind != WidgetKind.RAMP_VECTOR]
    values = read_params(input, other_specs)

    for spec in ramp_specs:
        if input[_param_id(spec.name, RAMP_RAW_FIELD)]():
            raw = read_params(input, [spec])[spec.name]
            raw["window_logistic"] = [float(w) for w in raw["window_logistic"]]
            values[spec.name] = raw
            continue
        start, full = input[_param_id(spec.name, RAMP_YEARS_FIELD)]()
        shape = input[_param_id(spec.name, RAMP_SHAPE_FIELD)]()
        try:
            values[spec.name] = ramp_service.ramp_from_policy(int(start), int(full), shape, years)
        except ramp_service.RampError as e:
            raise ParamReadError(str(e)) from e
    return values

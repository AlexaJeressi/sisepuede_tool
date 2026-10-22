"""Plotly figures for the results pages, styled like the app (IBM Plex, warm
greys, no chart chrome). Palettes for subsectors, cost/benefit categories and
pathways live here so every chart uses the same colours.

Figures are built from plain DataFrames/Series; nothing here reads app state.
Series keep their English names (colours are keyed by them); the figures
show them in `lang` (series_label). Time axes stay left to right in every
language.
"""

import functools
import re
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from sisepuede_tool.services import i18n
from sisepuede_tool.services.emissions_service import SUBSECTORS
from sisepuede_tool.services.mac_service import log_ticks, signed_log

FONT = "IBM Plex Sans, IBM Plex Sans Arabic, system-ui, sans-serif"
MONO = "IBM Plex Mono, IBM Plex Sans Arabic, ui-monospace, monospace"
TEXT = "#1C2B33"
LABEL = "#6F7A78"
GRID = "#E8E1D2"
ZERO = "#B9AE98"
NET = "#1C2B33"
COST = "#B4532A"

# Fallback colours; replaced at startup by the model's own subsector colours
# (use_model_subsector_colors). wali and enfu have no colour in the model.
SUBSECTOR_COLORS: Dict[str, str] = {
    # Energy
    "entc": "#E0A33A",
    "fgtv": "#7F98C7",
    "inen": "#E6CF6A",
    "scoe": "#5E9E6E",
    "trns": "#93C47D",
    "ccsq": "#A7B1BC",
    "enfu": "#D9A066",
    # IPPU
    "ippu": "#C7A64E",
    # AFOLU
    "agrc": "#C0504D",
    "lvst": "#E7A3A1",
    "lsmm": "#D27C6E",
    "soil": "#A86B4C",
    "lndu": "#9C8A64",
    "frst": "#6E8B3D",
    # Circular economy
    "waso": "#4E9AA6",
    "trww": "#93CAD1",
    "wali": "#93CAD1",
}

_TOTAL_FIELD_PREFIX = "emission_co2e_subsector_total_"


def model_subsector_colors(model_attributes) -> Dict[str, str]:
    """{subsector abbreviation: colour} from model_attributes.get_subsector_color_map(),
    which is keyed by emission_co2e_subsector_total_<abv>."""
    try:
        cmap = model_attributes.get_subsector_color_map() or {}
    except Exception:
        return {}
    return {k[len(_TOTAL_FIELD_PREFIX) :] if k.startswith(_TOTAL_FIELD_PREFIX) else k: v for k, v in cmap.items()}


def use_model_subsector_colors(model_attributes) -> None:
    """Update SUBSECTOR_COLORS in place with the model's colours (kept for subsectors it has none for)."""
    SUBSECTOR_COLORS.update(model_subsector_colors(model_attributes))


PATHWAY_PALETTE = ["#0F6E6E", "#C46B2A", "#6A5ACD", "#B8860B", "#2E8B57", "#A0446E"]
BAU_COLOR = "#7C8A8F"

SERIES_PALETTE = [
    "#0F6E6E", "#E0A33A", "#7F98C7", "#C0504D", "#93C47D", "#6A5ACD",
    "#C7A64E", "#4E9AA6", "#A86B4C", "#E7A3A1", "#5E9E6E", "#9C8A64",
]
OTHER_COLOR = "#C9C1B2"

# fixed colours for series that appear on several cards (fuels, technologies)
SEMANTIC_COLORS: Dict[str, str] = {
    "Solar": "#E8B931",
    "Wind": "#6F9BD1",
    "Hydropower": "#3E8FA3",
    "Natural gas": "#8A93A6",
    "Natural gas + CCS": "#B5BCCB",
    "Coal": "#4A4A4A",
    "Coal + CCS": "#7A7A7A",
    "Oil": "#8C5A3C",
    "Crude": "#8C5A3C",
    "Diesel": "#6B4E3D",
    "Gasoline": "#C0504D",
    "Kerosene": "#D98880",
    "Furnace gas": "#9C8A64",
    "Coke": "#5C5C5C",
    "LPG / gas liquids": "#C7A64E",
    "Electricity": "#0F6E6E",
    "Hydrogen": "#6A5ACD",
    "Ammonia": "#A0446E",
    "Biomass": "#6E8B3D",
    "Biogas": "#93C47D",
    "Biofuels": "#A9C25D",
    "Charcoal": "#3B3B30",
    "Geothermal": "#D27C6E",
    "Nuclear": "#A0446E",
    "Waste incineration": "#9C8A64",
}
# the small series merged into one layer; not "Other", which is a real model
# category in several variables (e.g. land use "other")
LUMP = "Smaller categories"
YEAR_TICKS = list(range(2015, 2051, 5))
YEAR_MIN, YEAR_MAX = 2015, 2050
Years = Optional[Tuple[int, int]]  # (first, last) shown; None = every year

CB_CATEGORY_COLORS: Dict[str, str] = {
    "Technology capex & opex": "#8A93A6",
    "O&M & technical savings": "#E6CF6A",
    "Fuel costs & savings": "#E0A33A",
    "Consumer savings": "#5B84C4",
    "Health & air quality": "#4FA36C",
    "Pollution avoided": "#D0674E",
    "Ecosystem services": "#9C7A4A",
    "Crop & livestock output": "#9CC4E4",
    "Industrial output": "#C7A64E",
    "Congestion & road safety": "#A0446E",
    "Other sector-specific": "#B9AE98",
    "Other": OTHER_COLOR,
}


_SUBSECTOR_BY_LABEL = {label: abv for abv, (_, label) in SUBSECTORS.items()}


def series_label(name: str, lang: Optional[str] = None, labels: Optional[Dict[str, str]] = None) -> str:
    """Display name of a series in `lang`: `labels` first, then subsector names
    (subsectors.<abv>), then results.series.<slug of the English name>."""
    if labels and name in labels:
        return labels[name]
    if not isinstance(name, str):
        return name
    abv = _SUBSECTOR_BY_LABEL.get(name)
    if abv:
        return i18n.t(f"subsectors.{abv}", lang, default=name)
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return i18n.t(f"results.series.{slug}", lang, default=name) if slug else name


def pathway_colors(pathway_ids: Sequence[int], bau_id: int = 0) -> Dict[int, str]:
    """Stable colour per pathway id (BAU grey; others by id order)."""
    out, i = {}, 0
    for sid in sorted(pathway_ids):
        if sid == bau_id:
            out[sid] = BAU_COLOR
        else:
            out[sid] = PATHWAY_PALETTE[i % len(PATHWAY_PALETTE)]
            i += 1
    return out


def series_colors(names: Sequence[str]) -> Dict[str, str]:
    """Semantic colour when the series is a known fuel/technology, else the palette in order."""
    out, i = {}, 0
    for n in names:
        if n == LUMP:
            out[n] = OTHER_COLOR
        elif n in SEMANTIC_COLORS:
            out[n] = SEMANTIC_COLORS[n]
        else:
            out[n] = SERIES_PALETTE[i % len(SERIES_PALETTE)]
            i += 1
    return out


def fmt(v: Optional[float], digits: int = 3) -> str:
    """Compact number: 1,234 / 12.3 / 0.123."""
    if v is None or pd.isna(v):
        return "–"
    a = abs(v)
    if a >= 1000:
        return f"{v:,.0f}"
    if a >= 100:
        return f"{v:.0f}"
    if a >= 10:
        return f"{v:.1f}"
    if a >= 1:
        return f"{v:.2f}"
    return f"{v:.{digits}g}"


def year_ticks(years: Years, default: Sequence[int] = YEAR_TICKS) -> List[int]:
    """Year ticks for (first, last): every year on a short range, every other
    one on a medium one, multiples of five otherwise. `default` when None."""
    if years is None:
        return list(default)
    first, last = years
    span = last - first
    step = 1 if span <= 10 else 2 if span <= 20 else 5
    ticks = [y for y in range(first, last + 1) if y % step == 0]
    return ticks or [first, last]


def in_years(index, years: Years):
    """Boolean mask of the years (an Index, Series or array) inside `years`."""
    v = pd.to_numeric(pd.Index(index), errors="coerce")
    if years is None:
        return np.ones(len(v), dtype=bool)
    return np.asarray((v >= years[0]) & (v <= years[1]))


def _base_layout(fig: go.Figure, height: int, legend: bool = True, legend_right: bool = True) -> go.Figure:
    # Legends sit to the right: a horizontal legend under the plot is placed relative
    # to the plot height, so on small windows its rows slide over the year labels.
    if legend_right:
        legend_cfg = dict(orientation="v", yanchor="top", y=1, x=1.01, xanchor="left", font=dict(size=11.5), traceorder="normal")
    else:
        legend_cfg = dict(orientation="h", yanchor="top", y=-0.16, x=0, font=dict(size=12), traceorder="normal")
    fig.update_layout(
        height=height,
        margin=dict(l=8, r=8, t=28, b=8),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family=FONT, size=12.5, color=TEXT),
        hoverlabel=dict(font=dict(family=MONO, size=12)),
        showlegend=legend,
        legend=legend_cfg,
        hovermode="x unified",
    )
    fig.update_xaxes(showgrid=False, ticks="outside", tickcolor=GRID, linecolor=GRID, tickfont=dict(family=MONO, size=11, color=LABEL))
    fig.update_yaxes(gridcolor=GRID, zeroline=True, zerolinecolor=ZERO, tickfont=dict(family=MONO, size=11, color=LABEL))
    for ann in fig.layout.annotations or []:
        ann.font = dict(family=FONT, size=13, color=TEXT)
    return fig


_RLI, _PDI = "\u2067", "\u2069"  # right-to-left isolate ... pop directional isolate


def bidi(fig: go.Figure, lang: Optional[str]) -> go.Figure:
    """Right-to-left text in a figure. Plotly lays text out left to right (theme-rtl.css
    keeps .js-plotly-plot ltr so labels anchor correctly), so under Arabic each title,
    legend name and hover text is isolated as right-to-left and keeps its own order."""
    if not lang or not i18n.is_rtl(lang):
        return fig

    def iso(text):
        return f"{_RLI}{text}{_PDI}" if isinstance(text, str) and text and not text.startswith(_RLI) else text

    fig.update_layout(title_text=iso(fig.layout.title.text), legend_title_text=iso(fig.layout.legend.title.text))
    for ann in fig.layout.annotations:
        ann.text = iso(ann.text)
    fig.for_each_xaxis(lambda ax: ax.update(title_text=iso(ax.title.text)))
    fig.for_each_yaxis(lambda ax: ax.update(title_text=iso(ax.title.text)))
    fig.for_each_trace(lambda tr: tr.update(name=iso(tr.name), hovertemplate=iso(getattr(tr, "hovertemplate", None))))
    return fig


def bidi_for(lang_fn):
    """Decorator for a @render_plotly function: bidi() on the figure it returns."""

    def wrap(fn):
        @functools.wraps(fn)
        def inner(*args, **kwargs):
            return bidi(fn(*args, **kwargs), lang_fn())

        return inner

    return wrap


def empty_figure(message: str, height: int = 260) -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(text=message, showarrow=False, font=dict(family=FONT, size=14, color=LABEL), x=0.5, y=0.5, xref="paper", yref="paper")
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    return _base_layout(fig, height, legend=False)


def top_series(frames: Dict[str, pd.DataFrame], n: int = 8) -> List[str]:
    """Series kept as their own layer (largest by max |value| across panels); the rest become LUMP."""
    if not frames:
        return []
    all_ = pd.concat(frames.values())
    if all_.empty:
        return []
    size = all_.groupby("series")["value"].apply(lambda s: s.abs().max()).sort_values(ascending=False)
    size = size[size > 0]
    keep = list(size.index[:n]) if len(size) > n + 1 else list(size.index)
    return keep


def lump_series(df: pd.DataFrame, keep: List[str]) -> pd.DataFrame:
    if df.empty:
        return df
    d = df.copy()
    d["series"] = d["series"].where(d["series"].isin(keep), LUMP)
    return d.groupby(["year", "series"], as_index=False, sort=False)["value"].sum()


def lumped(frames: Dict[str, pd.DataFrame], n: int = 8):
    """(frames with the small series merged into LUMP, series order)."""
    keep = top_series(frames, n=n)
    out = {k: lump_series(v, keep) for k, v in frames.items()}
    if any((v["series"] == LUMP).any() for v in out.values()):
        keep = keep + [LUMP]
    return out, keep


def stacked_panels(
    frames: Dict[str, pd.DataFrame],
    colors: Dict[str, str],
    order: List[str],
    unit: str,
    share: bool = False,
    net: Optional[Dict[str, pd.Series]] = None,
    height: int = 340,
    mark_year: Optional[int] = 2030,
    legend_right: bool = True,
    lang: Optional[str] = None,
    years: Years = None,
) -> go.Figure:
    """One panel per pathway (`frames`: {title: [year, series, value]}), stacked
    areas by series in `order`. Negative series stack below zero. `share`
    normalises each year to 100%. `net`: optional {title: Series by year} line.
    `years`: only those years."""
    frames = {k: f[in_years(f["year"], years)] for k, f in frames.items()}
    net = {k: s[in_years(s.index, years)] for k, s in net.items()} if net else net
    if years and mark_year and not years[0] < mark_year < years[1]:
        mark_year = None
    net_name = i18n.t("results.net_total", lang)
    titles = list(frames.keys())
    fig = make_subplots(rows=1, cols=max(len(titles), 1), shared_yaxes=True, subplot_titles=titles, horizontal_spacing=0.05)
    for j, title in enumerate(titles, start=1):
        wide = frames[title].pivot_table(index="year", columns="series", values="value", aggfunc="sum").fillna(0.0)
        if share:
            tot = wide.sum(axis=1).replace(0, float("nan"))
            wide = wide.div(tot, axis=0).mul(100).fillna(0.0)
        for name in order:
            if name not in wide.columns:
                continue
            y = wide[name]
            if (y.abs() < 1e-12).all():
                continue
            neg = y.sum() < 0
            label = series_label(name, lang)
            fig.add_trace(
                go.Scatter(
                    x=wide.index, y=y, name=label, legendgroup=name, showlegend=(j == 1),
                    mode="lines", line=dict(width=0.6, color=colors.get(name, OTHER_COLOR)),
                    fillcolor=colors.get(name, OTHER_COLOR), stackgroup="neg" if neg else "pos",
                    hovertemplate=f"{label}: %{{y:,.3~g}} {unit}<extra></extra>",
                ),
                row=1, col=j,
            )
        if net and title in net:
            s = net[title]
            fig.add_trace(
                go.Scatter(
                    x=s.index, y=s.values, name=net_name, legendgroup="net_total", showlegend=(j == 1),
                    mode="lines", line=dict(color=NET, width=2.4),
                    hovertemplate=f"{i18n.t('results.net', lang)}: %{{y:,.1f}} {unit}<extra></extra>",
                ),
                row=1, col=j,
            )
            if s.empty:
                continue
            last = s.index.max()
            fig.add_annotation(x=last, y=float(s[last]), text=f"{fmt(float(s[last]))}", showarrow=False, xanchor="right",
                               yshift=10, font=dict(family=MONO, size=11.5, color=NET), row=1, col=j)
        if mark_year:
            fig.add_vline(x=mark_year, line=dict(color=ZERO, width=1, dash="dot"), row=1, col=j)
    fig.update_yaxes(title_text=("%" if share else unit), row=1, col=1, title_font=dict(size=11.5, color=LABEL))
    if share:
        fig.update_yaxes(range=[0, 100])
    ticks = year_ticks(years)
    if len(titles) >= 2 and len(ticks) > 5:
        ticks = ticks[::2] + ([ticks[-1]] if (len(ticks) - 1) % 2 else [])
    fig.update_xaxes(tickvals=ticks)
    return _base_layout(fig, height, legend_right=legend_right)


def lines_by_pathway(
    series: Dict[str, pd.Series], colors: Dict[str, str], unit: str, height: int = 240, dashed: Sequence[str] = (), years: Years = None
) -> go.Figure:
    """One line per pathway (`series`: {name: Series by year}), over `years`."""
    fig = go.Figure()
    for name, s in series.items():
        s = s[in_years(s.index, years)]
        fig.add_trace(
            go.Scatter(
                x=s.index, y=s.values, name=name, mode="lines",
                line=dict(color=colors.get(name, OTHER_COLOR), width=2.2, dash="dash" if name in dashed else "solid"),
                hovertemplate=f"{name}: %{{y:,.3~g}} {unit}<extra></extra>",
            )
        )
    fig.update_yaxes(title_text=unit, title_font=dict(size=11.5, color=LABEL))
    fig.update_xaxes(tickvals=year_ticks(years))
    if years is None or years[0] < 2030 < years[1]:
        fig.add_vline(x=2030, line=dict(color=ZERO, width=1, dash="dot"))
    return _base_layout(fig, height, legend_right=True)


def delta_bars(
    deltas: pd.DataFrame, colors: Dict[str, str], years=(2030, 2050), height: int = 380, lang: Optional[str] = None
) -> go.Figure:
    """Change vs BAU by subsector. `deltas`: [subsector, pathway, year, delta] (MtCO2e).
    One panel per year, horizontal bars, one colour per pathway."""
    titles = [i18n.t("results.change_vs_bau_in", lang, year=y) for y in years]
    fig = make_subplots(rows=1, cols=len(years), shared_yaxes=True, subplot_titles=titles, horizontal_spacing=0.04)
    last = deltas[deltas["year"] == years[-1]]
    order = last.groupby("subsector")["delta"].sum().sort_values(ascending=False).index.tolist()
    for j, y in enumerate(years, start=1):
        d = deltas[deltas["year"] == y]
        for k, (pw, g) in enumerate(d.groupby("pathway", sort=False)):
            g = g.set_index("subsector").reindex(order)
            fig.add_trace(
                go.Bar(
                    y=[series_label(n, lang) for n in g.index], x=g["delta"], orientation="h", name=pw, legendgroup=pw, showlegend=(j == 1),
                    marker_color=colors.get(pw, OTHER_COLOR),
                    hovertemplate=f"{pw} · %{{y}}: %{{x:+,.1f}} MtCO₂e<extra></extra>",
                ),
                row=1, col=j,
            )
    fig.update_layout(barmode="group", bargap=0.25, hovermode="closest")
    fig.update_xaxes(title_text=i18n.t("results.mt_vs_bau", lang), title_font=dict(size=11.5, color=LABEL), zeroline=True, zerolinecolor=NET, showgrid=True, gridcolor=GRID)
    fig.update_yaxes(showgrid=False, tickfont=dict(family=FONT, size=12, color=TEXT))
    fig = _base_layout(fig, height)
    fig.update_layout(hovermode="closest")
    fig.update_yaxes(zeroline=False)
    return fig


def cb_bars(
    wide: pd.DataFrame, colors: Dict[str, str], unit: str, height: int = 420, lang: Optional[str] = None, years: Years = None
) -> go.Figure:
    """Stacked +/- bars per year by group (`wide`: year x group) and the net
    line, over `years`."""
    wide = wide[in_years(wide.index, years)]
    fig = go.Figure()
    for name in wide.columns:
        y = wide[name]
        if (y.abs() < 1e-12).all():
            continue
        label = series_label(name, lang)
        fig.add_trace(
            go.Bar(x=wide.index, y=y, name=label, marker_color=colors.get(name, OTHER_COLOR),
                   hovertemplate=f"{label}: %{{y:+,.3~g}} {unit}<extra></extra>"),
        )
    net = wide.sum(axis=1)
    net_name = i18n.t("results.net", lang)
    fig.add_trace(
        go.Scatter(x=net.index, y=net.values, name=net_name, mode="lines+markers", line=dict(color=NET, width=2.4), marker=dict(size=4),
                   hovertemplate=f"{net_name}: %{{y:+,.3~g}} {unit}<extra></extra>"),
    )
    fig.update_layout(barmode="relative", bargap=0.18)
    fig.update_yaxes(title_text=unit, title_font=dict(size=11.5, color=LABEL))
    fig.update_xaxes(tickvals=year_ticks(years, range(2025, 2051, 5)))
    fig = _base_layout(fig, height)
    fig.update_yaxes(zeroline=True, zerolinecolor=NET)
    return fig


def item_bars(items: pd.DataFrame, colors: Dict[str, str], unit: str, lang: Optional[str] = None) -> go.Figure:
    """Horizontal bars, one per cost/benefit item (`items`: display_name, category,
    sector_label, pv), largest at the top, coloured by category. Item names come
    from the C&B config workbook and stay as they are there."""
    d = items.iloc[::-1]
    custom = [[series_label(c, lang), series_label(s, lang)] for c, s in zip(d["category"], d["sector_label"])]
    fig = go.Figure(
        go.Bar(
            y=d["display_name"], x=d["pv"], orientation="h",
            marker_color=[colors.get(c, OTHER_COLOR) if v >= 0 else COST for c, v in zip(d["category"], d["pv"])],
            customdata=custom,
            hovertemplate="%{y}<br>%{customdata[0]} · %{customdata[1]}<br>%{x:+,.2f} "
            + i18n.t("results.busd_short", lang) + "<extra></extra>",
        )
    )
    fig.update_xaxes(title_text=unit, title_font=dict(size=11.5, color=LABEL), zeroline=True, zerolinecolor=NET, showgrid=True, gridcolor=GRID)
    fig = _base_layout(fig, max(220, 30 * len(d) + 80), legend=False)
    fig.update_yaxes(showgrid=False, tickfont=dict(family=FONT, size=12.5, color=TEXT), automargin=True)
    fig.update_layout(hovermode="closest")
    return fig


# MAC measures: colour and marker shape, fixed whatever is shown (validated as a set,
# light surface); the shape keeps them apart without colour
MAC_MEASURE_STYLE = {
    "mean": ("#00918A", "circle"),
    "tornado": ("#C46B2A", "diamond"),
    "whirlpool": ("#6A5ACD", "square"),
}
SURFACE = "#FFFDF8"


def short_number(v: float) -> str:
    """Compact number for a narrow label: 2,850 / 12.3k / 4.06B (three digits
    from 10,000 on, sign kept); fmt() below that."""
    a = abs(v)
    if a < 1e4:
        return fmt(v).replace("-", "−")
    sign = "−" if v < 0 else ""
    for div, suffix in ((1e3, "k"), (1e6, "M"), (1e9, "B"), (1e12, "T")):
        if round(a / div, 3 - len(str(int(a // div)))) < 1000 or suffix == "T":
            return f"{sign}{a / div:.3g}{suffix}"


def mac_chart(
    rows: pd.DataFrame,
    measures: Sequence[str],
    names: Dict[str, str],
    unit: str,
    log: bool = False,
    limit: Optional[float] = None,
    lang: Optional[str] = None,
) -> go.Figure:
    """Marginal abatement cost, one row per transformation (`rows`: code and a
    column per measure, cheapest first), cheapest at the top.

    One measure: a lollipop (stem from zero, value written after the dot).
    Two or three: a dot per measure joined by a line from the lowest to the
    highest, so the spread between tornado and whirlpool shows. Each measure
    keeps its colour and shape (MAC_MEASURE_STYLE).

    `log`: signed logarithmic axis (mac_service.signed_log), for values that
    span many orders of magnitude; ticks show the real values. Otherwise linear,
    and with `limit` the axis stops at ±limit: a dot beyond it is drawn at the
    edge as an arrow and the row's cut values are written there."""
    d = rows.iloc[::-1].reset_index(drop=True)
    labels = [names.get(c, c) for c in d["code"]]
    vals = d[list(measures)].astype(float)
    if log:
        pos = vals.apply(lambda col: col.map(signed_log))
    else:
        pos = vals.clip(-limit, limit) if limit else vals
    cut = (vals.abs() > limit) if (limit and not log) else vals.astype(bool) & False

    fig = go.Figure()
    # stems (one measure) or ranges (two or more): one trace, rows split by None
    xs, ys = [], []
    for i, lab in enumerate(labels):
        p = pos.iloc[i]
        a, b = (0.0, float(p.iloc[0])) if len(measures) == 1 else (float(p.min()), float(p.max()))
        xs += [a, b, None]
        ys += [lab, lab, None]
    fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines", line=dict(color=ZERO, width=2), hoverinfo="skip", showlegend=False))

    names_m = {m: i18n.t(f"mac.{m}", lang) for m in measures}
    hover_all = "<br>".join(f"{i18n.t(f'mac.{m}', lang)}: %{{customdata[{j}]:+,.2f}} {unit}" for j, m in enumerate(measures))
    custom = vals.to_numpy()
    for m in measures:
        color, symbol = MAC_MEASURE_STYLE[m]
        symbols = [
            ("triangle-right" if v > 0 else "triangle-left") if c else symbol for v, c in zip(vals[m], cut[m])
        ]
        text = None
        if len(measures) == 1:
            text = ["" if c else ("≈ 0" if abs(v) < 0.05 else short_number(v)) for v, c in zip(vals[m], cut[m])]
        fig.add_trace(
            go.Scatter(
                x=pos[m], y=labels, mode="markers+text" if text else "markers", name=names_m[m],
                marker=dict(color=color, symbol=symbols, size=11 if m == "mean" else 10, line=dict(color=SURFACE, width=1.5)),
                text=text, textposition=["middle right" if v >= 0 else "middle left" for v in vals[m]],
                textfont=dict(family=MONO, size=11, color=LABEL), cliponaxis=False,
                customdata=custom, hovertemplate=f"%{{y}}<br>{hover_all}<extra></extra>",
            )
        )

    if log:
        lo, hi = float(vals.min().min()), float(vals.max().max())
        ticks = log_ticks(min(lo, 0.0), max(hi, 0.0))
        tpos = [signed_log(t) for t in ticks]
        x0, x1 = min(signed_log(lo), 0.0), max(signed_log(hi), 0.0)
        pad = (0.04 if len(measures) > 1 else 0.14) * (x1 - x0)  # room for the value written after a dot
        fig.update_xaxes(tickvals=tpos, ticktext=[short_number(t) if abs(t) >= 1e4 else (f"{t / 1e3:.0f}k" if abs(t) >= 1e3 else f"{t:.0f}").replace("-", "−") for t in ticks], tickangle=0,
                         range=[x0 - (pad if lo < 0 else 0.02 * (x1 - x0)), x1 + (pad if hi > 0 else 0.02 * (x1 - x0))])
    else:
        lo, hi = float(pos.min().min()), float(pos.max().max())
        span = max(hi - lo, 1e-9)
        pad = 0.18 if len(measures) == 1 else 0.06
        fig.update_xaxes(range=[min(lo, 0.0) - pad * span * (lo < 0) - 0.02 * span, max(hi, 0.0) + pad * span * (hi > 0) + 0.02 * span])
        # the cut values of a row, written once at the edge it was cut at
        for i, lab in enumerate(labels):
            for side in (1, -1):
                over = [m for m in measures if cut[m].iloc[i] and (vals[m].iloc[i] > 0) == (side > 0)]
                if over:
                    txt = " · ".join(f"{vals[m].iloc[i]:,.0f}" for m in over)
                    fig.add_annotation(x=side * limit, y=lab, text=(txt + " ›") if side > 0 else ("‹ " + txt), showarrow=False,
                                       xanchor="right" if side > 0 else "left", yshift=12, font=dict(family=MONO, size=10.5, color=TEXT))

    fig.update_xaxes(title_text=unit + (" · " + i18n.t("mac.log_axis", lang) if log else ""), title_font=dict(size=11.5, color=LABEL),
                     zeroline=True, zerolinecolor=NET, showgrid=True, gridcolor=GRID)
    fig = _base_layout(fig, max(200, 32 * len(d) + 90), legend=False)
    fig.update_yaxes(showgrid=False, tickfont=dict(family=FONT, size=12.5, color=TEXT), automargin=True,
                     type="category", categoryorder="array", categoryarray=labels)
    fig.update_layout(hovermode="closest")
    return fig


def credit_bars(
    frames: Dict[str, pd.DataFrame],
    colors: Dict[str, str],
    order: List[str],
    unit: str,
    height: int = 380,
    lang: Optional[str] = None,
    labels: Optional[Dict[str, str]] = None,
    label_years: Optional[Iterable[int]] = None,
    legend: bool = True,
    years: Years = None,
) -> go.Figure:
    """Article 6 credits: one panel per pathway (`frames`: {title: [year, series, value]}),
    one stacked bar per target year, stacked by emission group in `order`
    (shown as `labels`, when given). The bar total is written above the bars of
    `label_years` (default: every year). The years are categories, so the bars
    keep their width whatever the gap between target years and Plotly drops
    tick labels when the chart is narrow."""
    frames = {k: f[in_years(f["year"], years)] for k, f in frames.items()}
    titles = list(frames.keys())
    fig = make_subplots(rows=1, cols=max(len(titles), 1), shared_yaxes=True, subplot_titles=titles, horizontal_spacing=0.05)
    years: List[int] = sorted({int(y) for f in frames.values() for y in f["year"].unique()})
    label_years = set(years if label_years is None else label_years)
    for j, title in enumerate(titles, start=1):
        wide = frames[title].pivot_table(index="year", columns="series", values="value", aggfunc="sum").fillna(0.0)
        x = [str(int(y)) for y in wide.index]
        for name in order:
            if name not in wide.columns or (wide[name].abs() < 1e-9).all():
                continue
            label = series_label(name, lang, labels)
            fig.add_trace(
                go.Bar(x=x, y=wide[name].to_numpy(), name=label, legendgroup=name,
                       showlegend=label not in {t.name for t in fig.data}, marker_color=colors.get(name, OTHER_COLOR),
                       hovertemplate=f"{label}: %{{y:,.1f}} {unit}<extra></extra>"),
                row=1, col=j,
            )
        for xi, v in zip(x, wide.sum(axis=1).to_numpy()):
            if int(xi) in label_years:
                # on a category axis a number is read as a position, and Plotly turns "2030" into 2030
                fig.add_annotation(x=years.index(int(xi)), y=float(v), text=fmt(float(v)), showarrow=False, yshift=10,
                                   font=dict(family=MONO, size=11.5, color=NET), row=1, col=j)
    # few bars (e.g. only 2030 and 2035) would otherwise be very wide
    fig.update_layout(barmode="stack", bargap=0.55 if len(years) <= 3 else 0.3)
    fig.update_yaxes(title_text=unit, row=1, col=1, title_font=dict(size=11.5, color=LABEL))
    fig = _base_layout(fig, height, legend=legend)
    fig.update_xaxes(type="category", categoryorder="array", categoryarray=[str(y) for y in years])
    fig.update_layout(hovermode="closest")
    return fig

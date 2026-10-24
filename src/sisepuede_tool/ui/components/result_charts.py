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


# the tool's own colour where the model's is too close to another subsector's
# (trns #756BB1 and entc #6B6ECF are both purple; trww #D6616B, a red, then
# looked like transport's orange)
SUBSECTOR_COLOR_OVERRIDES: Dict[str, str] = {"trns": "#E6550D", "trww": "#2A9D8F"}


def use_model_subsector_colors(model_attributes) -> None:
    """Update SUBSECTOR_COLORS in place with the model's colours (kept for
    subsectors it has none for), then SUBSECTOR_COLOR_OVERRIDES."""
    SUBSECTOR_COLORS.update(model_subsector_colors(model_attributes))
    SUBSECTOR_COLORS.update(SUBSECTOR_COLOR_OVERRIDES)


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
    wide: pd.DataFrame, colors: Dict[str, str], unit: str, height: int = 420, lang: Optional[str] = None, years: Years = None,
    labels: Optional[Dict[str, str]] = None,
) -> go.Figure:
    """Stacked +/- bars per year by group (`wide`: year x group) and the net
    line, over `years`. `labels`: display names of the groups (else series_label)."""
    return cb_panels({"": wide}, colors, unit, height=height, lang=lang, years=years, labels=labels)


def cb_panels(
    frames: Dict[str, pd.DataFrame], colors: Dict[str, str], unit: str, height: int = 420, lang: Optional[str] = None,
    years: Years = None, labels: Optional[Dict[str, str]] = None,
) -> go.Figure:
    """cb_bars for several pathways: one panel per pathway (`frames`: {title:
    year x group}), side by side on a shared axis, one legend for all. A
    single frame has no panel title."""
    titles = list(frames)
    many = len(titles) > 1
    fig = make_subplots(rows=1, cols=len(titles), shared_yaxes=True, horizontal_spacing=0.035,
                        subplot_titles=titles if many else None)
    net_name = i18n.t("results.net", lang)
    # legend in the groups' order across panels (a group only in a later panel too)
    rank = {n: k for k, n in enumerate(dict.fromkeys(c for w in frames.values() for c in w.columns))}
    shown = set()
    for j, title in enumerate(titles, start=1):
        wide = frames[title]
        wide = wide[in_years(wide.index, years)]
        for name in wide.columns:
            y = wide[name]
            if (y.abs() < 1e-12).all():
                continue
            label = series_label(name, lang, labels)
            fig.add_trace(
                go.Bar(x=wide.index, y=y, name=label, marker_color=colors.get(name, OTHER_COLOR), legendgroup=str(name),
                       showlegend=name not in shown, legendrank=rank[name], hovertemplate=f"{label}: %{{y:+,.3~g}} {unit}<extra></extra>"),
                row=1, col=j,
            )
            shown.add(name)
        net = wide.sum(axis=1)
        fig.add_trace(
            go.Scatter(x=net.index, y=net.values, name=net_name, mode="lines+markers", line=dict(color=NET, width=2.4),
                       marker=dict(size=4), legendgroup="net", showlegend=(j == 1), legendrank=len(rank),
                       hovertemplate=f"{net_name}: %{{y:+,.3~g}} {unit}<extra></extra>"),
            row=1, col=j,
        )
    fig.update_layout(barmode="relative", bargap=0.18)
    fig.update_yaxes(title_text=unit, title_font=dict(size=11.5, color=LABEL), row=1, col=1)
    ticks = year_ticks(years, range(2025, 2051, 5))
    if many and len(ticks) > 4:
        ticks = ticks[::2] + ([ticks[-1]] if (len(ticks) - 1) % 2 else [])
    fig.update_xaxes(tickvals=ticks)
    fig = _base_layout(fig, height)
    fig.update_yaxes(zeroline=True, zerolinecolor=NET)
    return fig


def cb_type_breakdown(
    table: pd.DataFrame,
    colors: Dict[str, str],
    type_labels: Dict[str, str],
    sector_labels: Dict[str, str],
    unit: str,
    lang: Optional[str] = None,
    pathway_colors: Optional[Dict[str, str]] = None,
) -> go.Figure:
    """Total by CB type (`table` of cb_summary_service.by_cb_type: cb_sector,
    cb_type, value), one row per type under a light header per CB sector, as in
    the Egypt Tableau workbook. Bars coloured like the yearly chart by CB type,
    the value written after each (0.0 too: the type is in the pathway's data).
    Several pathways (`table` with a `pathway` column, `pathway_colors`
    {pathway: colour} in order): one bar per pathway in each row, in the
    pathway's colour, with the pathways as legend."""
    many = bool(pathway_colors) and len(pathway_colors) > 1
    pws = list(pathway_colors) if many else [None]
    first = table[table["pathway"] == pws[0]] if many else table
    values = table.set_index(["pathway", "cb_type"])["value"] if many else None
    row = 1.0 if not many else 0.3 + 0.46 * len(pws)  # height of a type's row
    band = 0.62 if not many else row - 0.3  # its bars, together
    tickvals, ticktext, dividers = [], [], []
    bars = {p: {"y": [], "x": [], "color": [], "hover": []} for p in pws}
    y = 0.0
    n_rows = 0
    for sector, d in first.groupby("cb_sector", sort=False):
        if n_rows:
            y -= 0.3
            dividers.append(y + 0.15)
        tickvals.append(y)
        ticktext.append(f"<b>{sector_labels.get(sector, sector).upper()}</b>")
        y -= 0.35 + row / 2
        for t in d["cb_type"]:
            name = type_labels.get(t, t)
            tickvals.append(y)
            ticktext.append(name)
            for k, p in enumerate(pws):
                v = float(values.get((p, t), 0.0)) if many else float(d.loc[d["cb_type"] == t, "value"].iloc[0])
                b = bars[p]
                b["y"].append(y + band / 2 - (k + 0.5) * band / len(pws))
                b["x"].append(v)
                b["color"].append(pathway_colors[p] if many else colors.get(t, OTHER_COLOR))
                head = f"<b>{name}</b><br>" + (f"{p}<br>" if many else "")
                b["hover"].append(f"{head}{sector_labels.get(sector, sector)}<br>{v:+,.1f} {unit}")
            n_rows += 1
            y -= row
    y += row / 2
    fig = go.Figure()
    for p in pws:
        b = bars[p]
        fig.add_trace(go.Bar(
            x=b["x"], y=b["y"], orientation="h", width=band / len(pws), name=p or "",
            marker=dict(color=b["color"], line=dict(color=TEXT, width=0.6)),
            text=[("0.0" if abs(v) < 0.05 else f"{v:,.1f}".replace("-", "−")) for v in b["x"]], textposition="outside", cliponaxis=False,
            textfont=dict(family=MONO, size=10.5 if many else 11, color=TEXT), hovertext=b["hover"], hovertemplate="%{hovertext}<extra></extra>",
        ))
    legend_px = 28 if many else 0
    fig = _base_layout(fig, max(220, int(25 * row * n_rows + 30 * len(dividers) + 90 + legend_px)), legend=many, legend_right=False)
    for yd in dividers:
        fig.add_shape(type="line", xref="paper", x0=0, x1=1, y0=yd, y1=yd, line=dict(color=GRID, width=1))
    vals = [v for b in bars.values() for v in b["x"]]
    lo, hi = min(vals + [0.0]), max(vals + [0.0])
    span = max(hi - lo, 1e-9)
    fig.update_xaxes(title_text=unit, title_font=dict(size=11.5, color=LABEL), showgrid=True, gridcolor=GRID, zeroline=True,
                     zerolinecolor=NET, range=[lo - (0.45 if lo < 0 else 0.02) * span, hi + (0.3 if hi > 0 else 0.02) * span])
    fig.update_yaxes(tickvals=tickvals, ticktext=ticktext, range=[y - 0.1, 0.6], showgrid=False, zeroline=False, automargin=True,
                     tickfont=dict(family=FONT, size=12, color=TEXT))
    fig.update_layout(hovermode="closest", barmode="overlay", margin=dict(l=8, r=8, t=20 + legend_px, b=8),
                      uniformtext=dict(minsize=10, mode="show"))
    if many:
        fig.update_layout(legend=dict(orientation="h", x=0, xanchor="left", y=1.0, yanchor="bottom", traceorder="normal"))
    return fig


def item_bars(items: pd.DataFrame, colors: Dict[str, str], unit: str, lang: Optional[str] = None, flipped: bool = False) -> go.Figure:
    """Horizontal bars, one per cost/benefit item (`items`: display_name, category,
    sector_label, pv), largest at the top, coloured by category. Item names come
    from the C&B config workbook and stay as they are there. Costs in the cost
    colour: below zero, or above it when the values are `flipped` (times −1)."""
    d = items.iloc[::-1]
    custom = [[series_label(c, lang), series_label(s, lang)] for c, s in zip(d["category"], d["sector_label"])]
    fig = go.Figure(
        go.Bar(
            y=d["display_name"], x=d["pv"], orientation="h",
            marker_color=[COST if (v > 0 if flipped else v < 0) else colors.get(c, OTHER_COLOR) for c, v in zip(d["category"], d["pv"])],
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


def item_bars_by_pathway(items: pd.DataFrame, pathway_colors: Dict[str, str], unit: str, lang: Optional[str] = None) -> go.Figure:
    """item_bars for several pathways (`items`: pathway, display_name, pv): one
    bar per pathway for each item, in the pathway's colour, items in the order
    of `items` (largest first, at the top)."""
    order = list(dict.fromkeys(items["display_name"]))[::-1]
    fig = go.Figure()
    for p, color in reversed(pathway_colors.items()):  # horizontal groups fill bottom-up: the first pathway on top
        d = items[items["pathway"] == p].set_index("display_name")["pv"].reindex(order, fill_value=0.0)
        fig.add_trace(go.Bar(
            y=d.index, x=d.values, orientation="h", name=p, marker_color=color,
            hovertemplate=f"%{{y}}<br>{p}: %{{x:+,.2f}} " + i18n.t("results.busd_short", lang) + "<extra></extra>",
        ))
    fig.update_xaxes(title_text=unit, title_font=dict(size=11.5, color=LABEL), zeroline=True, zerolinecolor=NET, showgrid=True, gridcolor=GRID)
    fig = _base_layout(fig, max(240, int((12 + 12 * len(pathway_colors)) * len(order) + 110)), legend_right=False)
    fig.update_yaxes(showgrid=False, tickfont=dict(family=FONT, size=12.5, color=TEXT), automargin=True)
    fig.update_layout(hovermode="closest", barmode="group", bargap=0.25, legend=dict(y=1.0, yanchor="bottom", x=0, traceorder="reversed"),
                      margin=dict(t=36))
    return fig


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


def _mac_bar_text(abated: float, sep: str = " ") -> str:
    """Tonnes abated written by a MAC bar: '3,717 Mt' ('0.95 Mt' below 1)."""
    return (f"{abated:,.0f}" if abs(abated) >= 1 else f"{abated:,.2f}").replace("-", "−") + sep + "Mt"


def _mac_cost_hover(lang: Optional[str], **v) -> str:
    t = lambda k, **f: i18n.t(f"mac.{k}", lang, **f)  # noqa: E731
    lines = [f"<b>{v['title']}</b>", v["pathway"], t("hover_mac", v=f"{v['mac']:+,.1f}"), t("hover_abated", v=f"{v['abatement']:,.1f}")]
    return "<br>".join(lines + v.get("extra", []))


def mac_by_subsector(
    table: pd.DataFrame,
    order: List[str],
    pathways: List[str],
    colors: Dict[str, str],
    sub_names: Dict[str, str],
    unit: str,
    limit: Optional[float] = None,
    lang: Optional[str] = None,
) -> go.Figure:
    """Average cost per tonne abated in each subsector (`table` of
    mac_service.by_subsector), one column per subsector in `order` with a bar
    per pathway, side by side. At the end of each bar (above it, under it for
    a saving) its cost per tonne and the emissions abated there (MtCO2e), net; "no data" where the pathway abates nothing, and no bar but
    the net increase where its transformations raise the subsector's emissions
    on net (mac NaN).

    With `limit` (mac_service.axis_limit) a bar beyond ±limit is cut: drawn to
    the edge with a break and its value written inside."""
    t = lambda k, **f: i18n.t(f"mac.{k}", lang, **f)  # noqa: E731
    n = len(pathways)
    w = 0.8 / max(n, 1)
    vals = table.set_index(["pathway", "subsector"])
    fig = go.Figure()
    breaks, notes = [], []
    for j, p in enumerate(pathways):
        xs, ys, texts, hover = [], [], [], []
        for i, sub in enumerate(order):
            x = i + (j - (n - 1) / 2) * w
            if (p, sub) not in vals.index:
                notes.append(dict(x=x, y=0, text=f"<i>{t('no_data')}</i>", yshift=9))
                continue
            r = vals.loc[(p, sub)]
            v = float(r["mac"])
            if pd.isna(v):
                notes.append(dict(x=x, y=0, text=f"<i>{t('net_increase', v=_mac_bar_text(-r['abatement']))}</i>", yshift=9))
                continue
            y = max(-limit, min(limit, v)) if limit else v
            xs.append(x)
            ys.append(y)
            # its cost, as in the chart by transformation, then its tonnes
            cost = "" if (limit and abs(v) > limit) else f"<b>{short_number(v) if abs(v) >= 0.005 else '0'}</b><br>"
            texts.append(cost + _mac_bar_text(r["abatement"], "<br>"))
            hover.append(_mac_cost_hover(lang, title=sub_names.get(sub, sub), pathway=p, mac=v, abatement=r["abatement"],
                                         extra=[i18n.tn("mac.hover_n", int(r["n"]), lang)]))
            if limit and abs(v) > limit:
                breaks.append((x, y, v))
            # at the end of the bar: above it, under it for a saving
            notes.append(dict(x=x, y=y, text=texts[-1], yshift=24 if v >= 0 else -24, color=TEXT))
        fig.add_trace(go.Bar(x=xs, y=ys, width=w * 0.86, name=p, marker=dict(color=colors.get(p, OTHER_COLOR)),
                             hovertext=hover, hovertemplate="%{hovertext}<extra></extra>"))

    fig = _base_layout(fig, 470, legend=True)
    # after _base_layout, which sets the font of every annotation
    for a in notes:
        fig.add_annotation(x=a["x"], y=a["y"], text=a["text"], showarrow=False, yshift=a["yshift"],
                           font=dict(family=MONO, size=10, color=a.get("color", LABEL)))
    _mac_breaks(fig, breaks, w * 0.86, unit, vertical=True)
    for i in range(1, len(order)):
        fig.add_vline(x=i - 0.5, line=dict(color=GRID, width=1))
    fig.update_xaxes(tickvals=list(range(len(order))), ticktext=[_wrap(sub_names.get(s, s), 14) for s in order], side="top",
                     range=[-0.5, len(order) - 0.5], showgrid=False, ticks="", tickfont=dict(family=FONT, size=11.5, color=TEXT))
    ys = [0.0] + [max(-limit, min(limit, v)) if limit else v for v in table["mac"].dropna()]
    lo, hi = min(ys), max(ys)
    span = max(hi - lo, 1e-9)
    fig.update_yaxes(title_text=t("avg_cost_axis", unit=unit), title_font=dict(size=11.5, color=LABEL), showgrid=True, gridcolor=GRID,
                     zeroline=True, zerolinecolor=NET, range=[lo - 0.22 * span * (lo < 0) - 0.03 * span, hi + 0.22 * span])
    fig.update_layout(hovermode="closest", bargap=0, barmode="overlay", margin=dict(l=8, r=8, t=60, b=8),
                      legend=dict(title_text=t("pathway"), orientation="v", x=0.005, xanchor="left", y=0.98, yanchor="top",
                                  bgcolor="rgba(255,253,248,0.9)", bordercolor=GRID, borderwidth=1))
    return fig


def _wrap(text: str, width: int) -> str:
    """Break a label into lines of about `width` characters (<br>)."""
    lines, cur = [], ""
    for word in text.split():
        if cur and len(cur) + 1 + len(word) > width:
            lines.append(cur)
            cur = word
        else:
            cur = f"{cur} {word}".strip()
    return "<br>".join(lines + [cur])


def _mac_breaks(fig: go.Figure, breaks, size: float, unit: str, vertical: bool) -> None:
    """A cut bar: two light slashes near its end and its real value written inside
    (on a narrow column, 'USD/t' rather than 'USD/tCO₂e')."""
    for x, y, v in breaks:
        s = 1 if v > 0 else -1
        for k in (0.86, 0.9):
            if vertical:
                fig.add_shape(type="line", x0=x - size / 2, x1=x + size / 2, y0=y * k - s * 0.01 * abs(y), y1=y * k + s * 0.01 * abs(y),
                              line=dict(color=SURFACE, width=2.5), layer="above")
            else:
                fig.add_shape(type="line", y0=y - size / 2, y1=y + size / 2, x0=x * k - s * 0.006 * abs(x), x1=x * k + s * 0.006 * abs(x),
                              line=dict(color=SURFACE, width=2.5), layer="above")
        txt = f"<b>{v:,.0f}</b>".replace("-", "−")
        if vertical:
            fig.add_annotation(x=x, y=y * 0.6, text=f"{txt}<br>{unit.replace('CO₂e', '')}", showarrow=False, font=dict(family=MONO, size=10, color=SURFACE))
        else:
            fig.add_annotation(x=x * 0.6, y=y, text=f"{txt} {unit}", showarrow=False, font=dict(family=MONO, size=10, color=SURFACE))


def mac_by_transformation(
    rows: pd.DataFrame,
    order: List[str],
    pathways: List[str],
    colors: Dict[str, str],
    sub_names: Dict[str, str],
    names: Dict[str, str],
    unit: str,
    limit: Optional[float] = None,
    lang: Optional[str] = None,
) -> go.Figure:
    """Cost per tonne abated of each transformation (`rows` of
    mac_service.by_transformation), grouped by the subsector it abates in (a
    light header per subsector, in `order`), cheapest first within each. One
    bar per pathway (the NDC and LEP versions of a transformation share a row,
    by `key`); written after it, the emissions it abates in that subsector.
    `names`: key -> name. `limit`: as in mac_by_subsector. Each bar is the
    transformation's MAC in that subsector; the hover also gives its whole MAC
    (mac_all), when `rows` have it. The transformations that raise a
    subsector's emissions (`raises`) come after the others, with no bar: only
    what they raise there."""
    t = lambda k, **f: i18n.t(f"mac.{k}", lang, **f)  # noqa: E731
    n = len(pathways)
    h = 0.8 / max(n, 1)
    tickvals, ticktext, dividers = [], [], []
    slots: List[Tuple[float, str, str]] = []  # (y, subsector, key)
    y = 0.0
    for sub in order:
        d = rows[rows["subsector"] == sub]
        if d.empty:
            continue
        first = d.sort_values("pathway", key=lambda s: s.map(pathways.index)).drop_duplicates("key")
        raises = d.groupby("key")["abatement"].max() < 0  # in every pathway
        first = first.assign(_raises=first["key"].map(raises))
        keys = list(first.sort_values(["_raises", "mac"], kind="stable")["key"])
        if slots:
            y -= 0.35
            dividers.append(y + 0.15)
        tickvals.append(y)
        ticktext.append(f"<b>{sub_names.get(sub, sub).upper()}</b>")
        y -= 0.9
        for k in keys:
            slots.append((y, sub, k))
            tickvals.append(y)
            ticktext.append(names.get(k, k))
            y -= 1.0
    vals = rows.set_index(["subsector", "key", "pathway"])

    fig = go.Figure()
    breaks, notes = [], []
    for j, p in enumerate(pathways):
        xs, ys, hover = [], [], []
        for (ys0, sub, k) in slots:
            yy = ys0 - (j - (n - 1) / 2) * h
            if (sub, k, p) not in vals.index:
                if n > 1:
                    notes.append(dict(x=0, y=yy, text=f"<i>{t('not_in_pathway')}</i>", xanchor="left", xshift=4))
                continue
            r = vals.loc[(sub, k, p)]
            if r["abatement"] < 0:
                # raises the subsector's emissions: no cost per tonne abated
                notes.append(dict(x=0, y=yy, text=f"<i>{t('raises_here', v=_mac_bar_text(-r['abatement']))}</i>", xanchor="left", xshift=4))
                continue
            v = float(r["mac"])
            x = max(-limit, min(limit, v)) if limit else v
            xs.append(x)
            ys.append(yy)
            extra = [t("hover_share", pct=f"{100 * r['share']:.0f}", sub=sub_names.get(sub, sub))]
            est = [f"{t(m)} {r[f'mac_{m}']:+,.1f}" for m in ("tornado", "whirlpool") if pd.notna(r[f"mac_{m}"])]
            if est:
                extra.append(t("hover_estimates", v=" · ".join(est)))
            if "mac_all" in r and pd.notna(r["mac_all"]):
                extra.append(t("hover_all", v=f"{r['mac_all']:+,.1f}"))
            hover.append(_mac_cost_hover(lang, title=names.get(k, k), pathway=p, mac=v, abatement=r["abatement"], extra=extra))
            if limit and abs(v) > limit:
                breaks.append((x, yy, v))
            # a MAC of a few thousandths of a dollar (e.g. -1.45e-08 in the file) reads as 0
            cost = "" if (limit and abs(v) > limit) else f"<b>{short_number(v) if abs(v) >= 0.005 else '0'}</b> · "
            notes.append(dict(x=max(x, 0) if v >= 0 else x, y=yy, text=cost + _mac_bar_text(r["abatement"]),
                              xanchor="left" if v >= 0 else "right", xshift=5 if v >= 0 else -5))
        fig.add_trace(go.Bar(x=xs, y=ys, width=h * 0.86, orientation="h", name=p, marker=dict(color=colors.get(p, OTHER_COLOR)),
                             hovertext=hover, hovertemplate="%{hovertext}<extra></extra>"))

    fig = _base_layout(fig, max(240, int(26 * len(slots) * max(n, 1) ** 0.5 + 40 * len(dividers) + 110)), legend=False)
    for a in notes:
        fig.add_annotation(x=a["x"], y=a["y"], text=a["text"], showarrow=False, xanchor=a["xanchor"], xshift=a["xshift"],
                           font=dict(family=MONO, size=10, color=LABEL))
    _mac_breaks(fig, breaks, h * 0.86, unit, vertical=False)
    for yd in dividers:
        fig.add_shape(type="line", xref="paper", x0=0, x1=1, y0=yd, y1=yd, line=dict(color=GRID, width=1))
    xs = [0.0] + [max(-limit, min(limit, v)) if limit else v for v in rows.loc[rows["abatement"] > 0, "mac"]]
    lo, hi = min(xs), max(xs)
    span = max(hi - lo, 1e-9)
    fig.update_xaxes(title_text=t("cost_axis", unit=unit), title_font=dict(size=11.5, color=LABEL), showgrid=True, gridcolor=GRID,
                     zeroline=True, zerolinecolor=NET, range=[lo - 0.3 * span * (lo < 0) - 0.02 * span, hi + 0.32 * span], side="top")
    fig.update_yaxes(tickvals=tickvals, ticktext=ticktext, range=[y + 0.4, 0.6], showgrid=False, zeroline=False, automargin=True,
                     tickfont=dict(family=FONT, size=12, color=TEXT))
    # no legend: the pathway toggles above (and the chart by subsector) carry the colours
    fig.update_layout(hovermode="closest", bargap=0, barmode="overlay", margin=dict(l=8, r=8, t=50, b=8), showlegend=False)
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
    outside: Optional[Tuple[int, str]] = None,
    part_labels: Optional[Dict[str, str]] = None,
    part_projects: Optional[Dict[str, List[str]]] = None,
    hover_panel: bool = False,
    years: Years = None,
) -> go.Figure:
    """Article 6 credits: one panel per pathway (`frames`: {title: [year, series, value]}),
    one stacked bar per target year, stacked by emission group in `order`
    (shown as `labels`, when given): groups above their target (negative) below
    zero, the others above. The bar total is written above the bars of
    `label_years` (default: every year), under them when it is negative. The years are categories, so the bars
    keep their width whatever the gap between target years and Plotly drops
    tick labels when the chart is narrow. `outside` (year, label): the bars
    after `year` shaded grey, with the label.

    A frame with [part, mac] columns splits each group into its parts (the
    transformers), stacked in the frame's order, in the group's colour with a
    white edge between them; the hover (light, see-through) names the part
    (`part_labels`), its MAC (USD/tCO2e) and how many projects it has
    (`part_projects`: part -> one line each). Each segment's customdata,
    [name, group · year · value · MAC, project count, projects one per line],
    is what hover_panel shows above the chart; with `hover_panel` only there
    (no hover label over the bars)."""
    frames = {k: f[in_years(f["year"], years)] for k, f in frames.items()}
    titles = list(frames.keys())
    fig = make_subplots(rows=1, cols=max(len(titles), 1), shared_yaxes=True, subplot_titles=titles, horizontal_spacing=0.05)
    years: List[int] = sorted({int(y) for f in frames.values() for y in f["year"].unique()})
    label_years = set(years if label_years is None else label_years)
    for j, title in enumerate(titles, start=1):
        wide = frames[title].pivot_table(index="year", columns="series", values="value", aggfunc="sum").fillna(0.0)
        x = [str(int(y)) for y in wide.index]
        split = "part" in frames[title].columns
        for name in order:
            if name not in wide.columns or (wide[name].abs() < 1e-9).all():
                continue
            label = series_label(name, lang, labels)
            color = colors.get(name, OTHER_COLOR)
            if not split:
                fig.add_trace(
                    go.Bar(x=x, y=wide[name].to_numpy(), name=label, legendgroup=name,
                           showlegend=label not in {t.name for t in fig.data}, marker_color=color,
                           hovertemplate=f"{label}: %{{y:,.1f}} {unit}<extra></extra>"),
                    row=1, col=j,
                )
                continue
            g = frames[title][frames[title]["series"] == name]
            for part in g["part"].unique():
                rows = g[g["part"] == part].set_index("year").reindex(wide.index)
                if (rows["value"].fillna(0).abs() < 1e-9).all():
                    continue
                macs = rows["mac"].dropna()
                # a part with no name or MAC: the group not split
                head = f"<b>{(part_labels or {}).get(part, part)}</b><br>{label}" if part else f"<b>{label}</b>"
                mac = f" · MAC {float(macs.iloc[0]):,.1f} USD/tCO₂e" if len(macs) else ""
                projects = (part_projects or {}).get(part) or []
                count = i18n.tn("mac.n_projects", len(projects), lang) if projects else i18n.t("mac.no_projects", lang)
                values = rows["value"].fillna(0).to_numpy()
                name_ = (part_labels or {}).get(part, part) if part else label
                custom = [[name_, f"{label + ' · ' if part else ''}{xi} · {v:,.1f} {unit}{mac}", count, "\n".join(projects)]
                          for xi, v in zip(x, values)]
                fig.add_trace(
                    go.Bar(x=x, y=values, name=label, legendgroup=name, customdata=custom,
                           showlegend=False, marker=dict(color=color, line=dict(color="white", width=0.6)),
                           hoverlabel=dict(bgcolor="rgba(255,255,255,0.72)", bordercolor=color, font=dict(color=TEXT, size=11)),
                           # "none", not "skip": the hover events still reach the panel
                           hoverinfo="none" if hover_panel else None,
                           hovertemplate=None if hover_panel else f"{head}<br>%{{y:,.1f}} {unit}{mac}<br><i>{count}</i><extra></extra>"),
                    row=1, col=j,
                )
        shown = wide[[c for c in order if c in wide.columns]]
        for xi, v, top, bottom in zip(x, shown.sum(axis=1), shown.clip(lower=0).sum(axis=1), shown.clip(upper=0).sum(axis=1)):
            if int(xi) in label_years:
                # on a category axis a number is read as a position, and Plotly turns "2030" into 2030
                y, shift = (float(top), 10) if v >= 0 else (float(bottom), -10)
                fig.add_annotation(x=years.index(int(xi)), y=y, text=fmt(float(v)), showarrow=False, yshift=shift,
                                   font=dict(family=MONO, size=11.5, color=NET), row=1, col=j)
    # few bars (e.g. only 2030 and 2035) would otherwise be very wide
    fig.update_layout(barmode="relative", bargap=0.55 if len(years) <= 3 else 0.3)
    fig.update_yaxes(title_text=unit, row=1, col=1, title_font=dict(size=11.5, color=LABEL))
    fig = _base_layout(fig, height, legend=legend)
    fig.update_xaxes(type="category", categoryorder="array", categoryarray=[str(y) for y in years])
    fig.update_layout(hovermode="closest")
    after = [i for i, y in enumerate(years) if outside is not None and y > outside[0]]
    if after:
        # category positions: from between the last year in and the first one out;
        # the label at the bottom, in two lines, clear of the bar totals over the tallest bars
        label = outside[1].replace(": ", ":<br>", 1)
        for j in range(1, len(titles) + 1):
            _shade_outside(fig, after[0] - 0.5, len(years) - 0.5, label, "bottom left", row=1, col=j)
    return fig


def _rgba(hex_color: str, alpha: float) -> str:
    h = hex_color.lstrip("#")
    return f"rgba({int(h[0:2], 16)},{int(h[2:4], 16)},{int(h[4:6], 16)},{alpha})"


GAP_BELOW = "#2E8B57"  # a pathway below the reference (emits less)
GAP_ABOVE = "#C0392B"  # a pathway above the reference (emits more)
OUTSIDE_SHADE = "#8A8F8E"  # years past the reference's own targets


def _shade_outside(fig: go.Figure, x0, x1, label: str, position: str = "top left", **where) -> None:
    """Grey band from x0 to x1 with `label` at its `position` (after _base_layout,
    which restyles the annotations); `where`: row/col of a subplot."""
    fig.add_vrect(
        x0=x0, x1=x1, fillcolor=_rgba(OUTSIDE_SHADE, 0.08), line_width=0, layer="below",
        annotation_text=label, annotation_position=position, annotation_align="left",
        annotation_font=dict(family=FONT, size=11.5, color=LABEL), **where,
    )


def _gap_segments(x: Sequence[float], ref: Sequence[float], val: Sequence[float]) -> List[Tuple[bool, List[float], List[float], List[float]]]:
    """[(below, xs, ref ys, pathway ys)]: the stretches where the pathway stays
    on one side of the reference, split where the two lines cross (interpolated)."""
    out: List[Tuple[bool, List[float], List[float], List[float]]] = []
    for i, (xi, r, v) in enumerate(zip(x, ref, val)):
        below = v <= r
        if i and out and out[-1][0] != below:
            x0, r0, v0 = out[-1][1][-1], out[-1][2][-1], out[-1][3][-1]
            d0, d1 = v0 - r0, v - r
            t = d0 / (d0 - d1) if d0 != d1 else 0.0
            xc, yc = x0 + t * (xi - x0), r0 + t * (r - r0)
            out[-1][1].append(xc), out[-1][2].append(yc), out[-1][3].append(yc)
            out.append((below, [xc], [yc], [yc]))
        if not out:
            out.append((below, [], [], []))
        out[-1][1].append(float(xi)), out[-1][2].append(float(r)), out[-1][3].append(float(v))
    return out


def gap_lines(
    series: Dict[str, pd.Series],
    colors: Dict[str, str],
    unit: str,
    gaps: Sequence[Tuple[str, str]] = (),
    gap_years: Optional[Tuple[int, int]] = None,
    gap_label: str = "",
    above_label: str = "",
    outside: Optional[Tuple[int, str]] = None,
    height: int = 360,
    years: Years = None,
) -> go.Figure:
    """One line per pathway (`series`: {name: Series by year}, BAU first), with
    the gap between two of them shaded (`gaps`: [(reference, pathway)]): green
    where the pathway emits less than the reference (`gap_label`), red where it
    emits more (`above_label`), over `gap_years` (first, last) only when given.
    `outside` (year, label): the years from `year` on shaded grey, with the label."""
    series = {k: s[in_years(s.index, years)] for k, s in series.items()}
    fig = go.Figure()
    legend_done = set()
    # the shading first, so the lines are drawn over it
    for ref_name, name in gaps:
        if ref_name not in series or name not in series:
            continue
        both = pd.concat([series[ref_name], series[name]], axis=1, join="inner")
        if gap_years is not None:
            both = both[in_years(both.index, gap_years)]
        if both.empty:
            continue
        for below, xs, ref_y, val_y in _gap_segments(list(both.index), list(both.iloc[:, 0]), list(both.iloc[:, 1])):
            label = gap_label if below else above_label
            fig.add_trace(go.Scatter(x=xs, y=ref_y, mode="lines", line=dict(width=0), showlegend=False, hoverinfo="skip"))
            fig.add_trace(
                go.Scatter(
                    x=xs, y=val_y, mode="lines", line=dict(width=0), fill="tonexty",
                    fillcolor=_rgba(GAP_BELOW if below else GAP_ABOVE, 0.32), name=label, legendgroup=label,
                    showlegend=bool(label) and label not in legend_done, hoverinfo="skip",
                )
            )
            legend_done.add(label)
    for name, s in series.items():
        fig.add_trace(
            go.Scatter(
                x=s.index, y=s.values, name=name, mode="lines",
                line=dict(color=colors.get(name, OTHER_COLOR), width=2.2),
                hovertemplate=f"{name}: %{{y:,.1f}} {unit}<extra></extra>",
            )
        )
    fig.update_yaxes(title_text=unit, title_font=dict(size=11.5, color=LABEL))
    fig.update_xaxes(tickvals=year_ticks(years))
    fig = _base_layout(fig, height, legend_right=True)
    last = max((int(s.index.max()) for s in series.values() if len(s)), default=None)
    if outside is not None and last is not None and outside[0] < last:
        _shade_outside(fig, outside[0], last, outside[1])
    return fig


# ---------------------------------------------------------------------------
# Jobs (page_jobs.py)
# ---------------------------------------------------------------------------

JOBS_SCALE = ["#E6E1D6", "#9DB4C8", "#2F5D8A"]  # jobs per million USD, light to dark


def jobs_bars(
    grid: Dict[str, Dict[str, pd.DataFrame]],
    colors: Dict[str, str],
    order: List[str],
    unit: str,
    labels: Optional[Dict[str, str]] = None,
    height: int = 420,
    total_line: bool = False,
    categories: bool = False,
    lang: Optional[str] = None,
) -> go.Figure:
    """Stacked bars of jobs by year, one panel per cell of `grid` ({row title:
    {column title: [year, series, value]}}; "" for a single row), stacked by
    series in `order` (shown as `labels`), negative values below zero, one
    legend for all. `total_line`: the years' totals as a line with their
    values. `categories` (and `total_line`): the years as categories, for a
    few years apart (e.g. 2025, 2030, ...)."""
    categories = categories or total_line
    row_titles = list(grid)
    col_titles = list(dict.fromkeys(c for r in grid.values() for c in r))
    n_rows, n_cols = len(row_titles), len(col_titles)
    fig = make_subplots(
        rows=n_rows, cols=n_cols, shared_xaxes=True, shared_yaxes=True, horizontal_spacing=0.04, vertical_spacing=0.08,
        column_titles=col_titles if any(col_titles) else None, row_titles=row_titles if any(row_titles) else None,
    )
    shown = set()
    rank = {name: k for k, name in enumerate(order)}
    for i, r in enumerate(row_titles, start=1):
        for j, c in enumerate(col_titles, start=1):
            frame = grid[r].get(c)
            if frame is None or frame.empty:
                continue
            wide = frame.pivot_table(index="year", columns="series", values="value", aggfunc="sum").fillna(0.0)
            x = [str(int(y)) for y in wide.index] if categories else wide.index
            for name in [s for s in order if s in wide.columns]:
                y = wide[name]
                if (y.abs() < 1e-9).all():
                    continue
                label = series_label(name, lang, labels)
                fig.add_trace(
                    go.Bar(x=x, y=y, name=label, legendgroup=name, showlegend=name not in shown, legendrank=rank[name],
                           marker=dict(color=colors.get(name, OTHER_COLOR), line=dict(width=0)),
                           hovertemplate=f"<b>{label}</b><br>%{{x}}: %{{y:,.0f}} {unit}<extra></extra>"),
                    row=i, col=j,
                )
                shown.add(name)
            if total_line:
                tot = wide.sum(axis=1)
                fig.add_trace(
                    go.Scatter(x=x, y=tot.values, mode="lines+markers+text", line=dict(color=NET, width=2), marker=dict(size=6, color=NET),
                               text=[f"{v / 1e6:,.2f}M" for v in tot.values], textposition="top center",
                               textfont=dict(family=MONO, size=11, color=NET), showlegend=False, hoverinfo="skip"),
                    row=i, col=j,
                )
    fig.update_layout(barmode="relative", bargap=0.35 if categories else 0.18)
    fig.update_yaxes(tickformat="~s")
    for i in range(1, n_rows + 1):
        fig.update_yaxes(title_text=unit, title_font=dict(size=11.5, color=LABEL), row=i, col=1)
    fig = _base_layout(fig, height)
    if categories:
        fig.update_xaxes(type="category")
    if total_line:
        top = max((float(f.groupby("year")["value"].sum().max()) for r in grid.values() for f in r.values() if not f.empty), default=0.0)
        fig.update_yaxes(range=[0, top * 1.12])
    if not categories:
        fig.update_xaxes(dtick=5 if n_cols > 1 else 2)
    fig.update_layout(hovermode="closest")
    return fig


def jobs_heatmap(
    table: pd.DataFrame,
    rows: List[str],
    cols: List[str],
    row_labels: Dict[str, str],
    col_labels: Dict[str, str],
    unit: str,
    zmax: float = 10.0,
) -> go.Figure:
    """Jobs per million USD invested (`table`: [row, col, value]) by economic
    sector (`rows`) and SSP sector (`cols`), the value in each cell; the colour
    saturates at `zmax`."""
    wide = table.pivot_table(index="row", columns="col", values="value", aggfunc="sum").reindex(index=rows, columns=cols)
    z = wide.to_numpy(float)
    ylab = [row_labels.get(r, r) for r in rows]
    xlab = [_wrap(col_labels.get(c, c), 10) for c in cols]
    fig = go.Figure(go.Heatmap(
        z=z, x=xlab, y=ylab, zmin=0, zmax=zmax, colorscale=[[0, JOBS_SCALE[0]], [0.5, JOBS_SCALE[1]], [1, JOBS_SCALE[2]]],
        text=np.vectorize(lambda v: "" if np.isnan(v) else f"{v:.1f}")(z), texttemplate="%{text}",
        textfont=dict(family=MONO, size=10.5), xgap=1, ygap=1,
        colorbar=dict(title=dict(text=unit, side="right", font=dict(size=11, color=LABEL)), thickness=10, len=0.5, y=1, yanchor="top",
                      tickfont=dict(family=MONO, size=10, color=LABEL)),
        hovertemplate="%{y} · %{x}<br>%{z:.2f} " + unit + "<extra></extra>",
    ))
    fig = _base_layout(fig, 26 * len(rows) + 120, legend=False)
    fig.update_xaxes(side="top", tickangle=0, tickfont=dict(family=FONT, size=10, color=TEXT), ticks="", showline=False)
    fig.update_yaxes(autorange="reversed", tickfont=dict(family=FONT, size=11.5, color=TEXT), gridcolor="rgba(0,0,0,0)", zeroline=False)
    fig.update_layout(hovermode="closest", margin=dict(l=8, r=8, t=56, b=8))
    return fig

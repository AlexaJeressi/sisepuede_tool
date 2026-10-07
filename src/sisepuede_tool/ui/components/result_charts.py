"""Plotly figures for the results pages, styled like the app (IBM Plex, warm
greys, no chart chrome). Palettes for subsectors, cost/benefit categories and
pathways live here so every chart uses the same colours.

Figures are built from plain DataFrames/Series; nothing here reads app state.
"""

from typing import Dict, List, Optional, Sequence

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

FONT = "IBM Plex Sans, system-ui, sans-serif"
MONO = "IBM Plex Mono, ui-monospace, monospace"
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
) -> go.Figure:
    """One panel per pathway (`frames`: {title: [year, series, value]}), stacked
    areas by series in `order`. Negative series stack below zero. `share`
    normalises each year to 100%. `net`: optional {title: Series by year} line."""
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
            fig.add_trace(
                go.Scatter(
                    x=wide.index, y=y, name=name, legendgroup=name, showlegend=(j == 1),
                    mode="lines", line=dict(width=0.6, color=colors.get(name, OTHER_COLOR)),
                    fillcolor=colors.get(name, OTHER_COLOR), stackgroup="neg" if neg else "pos",
                    hovertemplate=f"{name}: %{{y:,.3~g}} {unit}<extra></extra>",
                ),
                row=1, col=j,
            )
        if net and title in net:
            s = net[title]
            fig.add_trace(
                go.Scatter(
                    x=s.index, y=s.values, name="Net total", legendgroup="Net total", showlegend=(j == 1),
                    mode="lines", line=dict(color=NET, width=2.4),
                    hovertemplate=f"Net: %{{y:,.1f}} {unit}<extra></extra>",
                ),
                row=1, col=j,
            )
            last = s.index.max()
            fig.add_annotation(x=last, y=float(s[last]), text=f"{fmt(float(s[last]))}", showarrow=False, xanchor="right",
                               yshift=10, font=dict(family=MONO, size=11.5, color=NET), row=1, col=j)
        if mark_year:
            fig.add_vline(x=mark_year, line=dict(color=ZERO, width=1, dash="dot"), row=1, col=j)
    fig.update_yaxes(title_text=("%" if share else unit), row=1, col=1, title_font=dict(size=11.5, color=LABEL))
    if share:
        fig.update_yaxes(range=[0, 100])
    fig.update_xaxes(tickvals=YEAR_TICKS if len(titles) < 2 else YEAR_TICKS[::2] + [2050])
    return _base_layout(fig, height, legend_right=legend_right)


def lines_by_pathway(series: Dict[str, pd.Series], colors: Dict[str, str], unit: str, height: int = 240, dashed: Sequence[str] = ()) -> go.Figure:
    """One line per pathway (`series`: {name: Series by year})."""
    fig = go.Figure()
    for name, s in series.items():
        fig.add_trace(
            go.Scatter(
                x=s.index, y=s.values, name=name, mode="lines",
                line=dict(color=colors.get(name, OTHER_COLOR), width=2.2, dash="dash" if name in dashed else "solid"),
                hovertemplate=f"{name}: %{{y:,.3~g}} {unit}<extra></extra>",
            )
        )
    fig.update_yaxes(title_text=unit, title_font=dict(size=11.5, color=LABEL))
    fig.update_xaxes(tickvals=YEAR_TICKS)
    fig.add_vline(x=2030, line=dict(color=ZERO, width=1, dash="dot"))
    return _base_layout(fig, height, legend_right=True)


def delta_bars(deltas: pd.DataFrame, colors: Dict[str, str], years=(2030, 2050), height: int = 380) -> go.Figure:
    """Change vs BAU by subsector. `deltas`: [subsector, pathway, year, delta] (MtCO2e).
    One panel per year, horizontal bars, one colour per pathway."""
    fig = make_subplots(rows=1, cols=len(years), shared_yaxes=True, subplot_titles=[f"Change vs BAU in {y}" for y in years], horizontal_spacing=0.04)
    last = deltas[deltas["year"] == years[-1]]
    order = last.groupby("subsector")["delta"].sum().sort_values(ascending=False).index.tolist()
    for j, y in enumerate(years, start=1):
        d = deltas[deltas["year"] == y]
        for k, (pw, g) in enumerate(d.groupby("pathway", sort=False)):
            g = g.set_index("subsector").reindex(order)
            fig.add_trace(
                go.Bar(
                    y=g.index, x=g["delta"], orientation="h", name=pw, legendgroup=pw, showlegend=(j == 1),
                    marker_color=colors.get(pw, OTHER_COLOR),
                    hovertemplate=f"{pw} · %{{y}}: %{{x:+,.1f}} MtCO₂e<extra></extra>",
                ),
                row=1, col=j,
            )
    fig.update_layout(barmode="group", bargap=0.25, hovermode="closest")
    fig.update_xaxes(title_text="MtCO₂e vs BAU", title_font=dict(size=11.5, color=LABEL), zeroline=True, zerolinecolor=NET, showgrid=True, gridcolor=GRID)
    fig.update_yaxes(showgrid=False, tickfont=dict(family=FONT, size=12, color=TEXT))
    fig = _base_layout(fig, height)
    fig.update_layout(hovermode="closest")
    fig.update_yaxes(zeroline=False)
    return fig


def cb_bars(wide: pd.DataFrame, colors: Dict[str, str], unit: str, height: int = 420) -> go.Figure:
    """Stacked +/- bars per year by group (`wide`: year x group) and the net line."""
    fig = go.Figure()
    for name in wide.columns:
        y = wide[name]
        if (y.abs() < 1e-12).all():
            continue
        fig.add_trace(
            go.Bar(x=wide.index, y=y, name=name, marker_color=colors.get(name, OTHER_COLOR),
                   hovertemplate=f"{name}: %{{y:+,.3~g}} {unit}<extra></extra>"),
        )
    net = wide.sum(axis=1)
    fig.add_trace(
        go.Scatter(x=net.index, y=net.values, name="Net", mode="lines+markers", line=dict(color=NET, width=2.4), marker=dict(size=4),
                   hovertemplate=f"Net: %{{y:+,.3~g}} {unit}<extra></extra>"),
    )
    fig.update_layout(barmode="relative", bargap=0.18)
    fig.update_yaxes(title_text=unit, title_font=dict(size=11.5, color=LABEL))
    fig.update_xaxes(tickvals=list(range(2025, 2051, 5)))
    fig = _base_layout(fig, height)
    fig.update_yaxes(zeroline=True, zerolinecolor=NET)
    return fig


def item_bars(items: pd.DataFrame, colors: Dict[str, str], unit: str) -> go.Figure:
    """Horizontal bars, one per cost/benefit item (`items`: display_name, category,
    sector_label, pv), largest at the top, coloured by category."""
    d = items.iloc[::-1]
    fig = go.Figure(
        go.Bar(
            y=d["display_name"], x=d["pv"], orientation="h",
            marker_color=[colors.get(c, OTHER_COLOR) if v >= 0 else COST for c, v in zip(d["category"], d["pv"])],
            customdata=d[["category", "sector_label"]].values,
            hovertemplate="%{y}<br>%{customdata[0]} · %{customdata[1]}<br>%{x:+,.2f} B USD<extra></extra>",
        )
    )
    fig.update_xaxes(title_text=unit, title_font=dict(size=11.5, color=LABEL), zeroline=True, zerolinecolor=NET, showgrid=True, gridcolor=GRID)
    fig = _base_layout(fig, max(220, 30 * len(d) + 80), legend=False)
    fig.update_yaxes(showgrid=False, tickfont=dict(family=FONT, size=12.5, color=TEXT), automargin=True)
    fig.update_layout(hovermode="closest")
    return fig


def credit_bars(frames: Dict[str, pd.DataFrame], colors: Dict[str, str], order: List[str], unit: str, height: int = 380) -> go.Figure:
    """Article 6 credits: one panel per pathway (`frames`: {title: [year, series, value]}),
    one stacked bar per target year, stacked by emission group in `order`."""
    titles = list(frames.keys())
    fig = make_subplots(rows=1, cols=max(len(titles), 1), shared_yaxes=True, subplot_titles=titles, horizontal_spacing=0.05)
    years: List[int] = sorted({int(y) for f in frames.values() for y in f["year"].unique()})
    for j, title in enumerate(titles, start=1):
        wide = frames[title].pivot_table(index="year", columns="series", values="value", aggfunc="sum").fillna(0.0)
        x = [int(y) for y in wide.index]
        for name in order:
            if name not in wide.columns or (wide[name].abs() < 1e-9).all():
                continue
            fig.add_trace(
                go.Bar(x=x, y=wide[name].to_numpy(), width=2.2, name=name, legendgroup=name,
                       showlegend=name not in {t.name for t in fig.data}, marker_color=colors.get(name, OTHER_COLOR),
                       hovertemplate=f"{name}: %{{y:,.1f}} {unit}<extra></extra>"),
                row=1, col=j,
            )
        for xi, v in zip(x, wide.sum(axis=1).to_numpy()):
            fig.add_annotation(x=xi, y=float(v), text=fmt(float(v)), showarrow=False, yshift=10,
                               font=dict(family=MONO, size=11.5, color=NET), row=1, col=j)
    fig.update_layout(barmode="stack")
    fig.update_yaxes(title_text=unit, row=1, col=1, title_font=dict(size=11.5, color=LABEL))
    fig = _base_layout(fig, height)
    if years:
        fig.update_xaxes(tickvals=years, range=[years[0] - 3, years[-1] + 3])
    fig.update_layout(hovermode="closest")
    return fig

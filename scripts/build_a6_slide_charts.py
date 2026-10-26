"""The two Article 6 slide charts from sisepuede_a6's ranked MAC file, as a
matched pair: credits by sector, then by transformation, with the bars in
exactly the same place in both, so one slide can follow the other.

    python scripts/build_a6_slide_charts.py [--out DIR]

Writes a6_slide_credits_by_sector.{html,png} and
a6_slide_credits_by_transformation.{html,png} to DIR (default: the current
folder). The PNGs (3200x1500) are drawn by kaleido (a dependency of the tool),
which uses a local Chrome; without it only the HTML files are written.

The data and colours are the Article 6 page's: ref/temporary_a6_ranked_mac_bar_df.csv
of the sisepuede_a6 clone (article6_service.load_ranked), each sector's MAC from
the file (ranked_group_macs), the sectors stacked by MAC (lowest at the base, the legends
highest first, lined up with the top of the stack),
every (sector, transformation) ranked by its own MAC, each in a lighter shade of
its sector's colour (result_charts.shades). The legends are drawn by hand on the
right: the sectors in one column; the transformations grouped by sector in two
columns, the names wrapped.
"""

import argparse
import pathlib
import sys
import textwrap

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))
import plotly.graph_objects as go  # noqa: E402

from sisepuede_tool.services import article6_service as a6  # noqa: E402
from sisepuede_tool.services import catalog_service, i18n  # noqa: E402
from sisepuede_tool.services import transformer_metadata_service as tms  # noqa: E402
from sisepuede_tool.ui.components import result_charts as rc  # noqa: E402
from sisepuede_tool.ui.page_article_6 import group_name  # noqa: E402

TEXT, GREY = "#1C2B33", "#6F7A78"
W, H = 1600, 750
# the plot area in pixels, the same in both charts: x 96..930, y 115..658
L, R, T, B = 96, W - 930, 115, 92
LEGEND_X = 978                    # the sectors' legend, and the transformations' first column
LEGEND_X2 = 1290                  # the transformations' second column
SECOND_COLUMN_FROM = "Stationary Combustion and Other Energy"
WRAP = 40                         # characters per line of a transformation's name
LINE, FONT_ITEM = 15.3, 11        # transformations' legend: line height (px), font size


def mac_text(v: float) -> str:
    return f"{v:,.1f} $/t".replace("-", "−")


def _px(x: float) -> float:
    return (x - L) / (W - L - R)


def _py(y: float) -> float:
    return 1 - (y - T) / (H - T - B)


def _text(fig, x, y, s, size, color=TEXT, anchor="top"):
    fig.add_annotation(xref="paper", yref="paper", x=_px(x), y=_py(y), xanchor="left", yanchor=anchor, showarrow=False,
                       align="left", text=s, font=dict(size=size, color=color))


def _swatch(fig, x, y, size, color):
    fig.add_shape(type="rect", xref="paper", yref="paper", x0=_px(x), x1=_px(x + size), y0=_py(y + size / 2), y1=_py(y - size / 2),
                  fillcolor=color, line=dict(width=0), layer="above")


def _frame(fig, title, subtitle, y_range):
    """The shared frame: size, margins, y range, title, subtitle, source."""
    for t in fig.data:
        t.showlegend = False
        if t.type == "bar":
            t.marker.line = dict(color="white", width=0.5)
    fig.update_layout(width=W, height=H, showlegend=False, paper_bgcolor="white", plot_bgcolor="white",
                      margin=dict(l=L, r=R, t=T, b=B, autoexpand=False), font=dict(family=rc.FONT, color=TEXT))
    fig.update_yaxes(range=y_range, autorange=False, tickformat=",", tickfont=dict(family=rc.FONT, size=14, color=GREY),
                     title=dict(text="million USD", font=dict(size=15, color=GREY)))
    fig.update_xaxes(tickfont=dict(family=rc.FONT, size=12, color=GREY), tickangle=-90)
    _text(fig, 96, 50, f"<b>{title}</b>", 22, anchor="middle")
    _text(fig, 96, 84, subtitle, 16, GREY, anchor="middle")
    _text(fig, 96, 739, "Source: SISEPUEDE", 13, GREY, anchor="middle")


def _wrap(name: str, mac: str):
    """The name in lines of about WRAP characters, its MAC after it when it fits, else on a line of its own."""
    lines = textwrap.wrap(name, WRAP)
    tail = " · " + mac
    if len(lines[-1]) + len(tail) <= WRAP + 4:
        lines[-1] += tail
    else:
        lines.append(tail.strip())
    return lines


def build(lang: str = "en"):
    """(sectors figure, transformations figure)."""
    rc.use_model_subsector_colors(catalog_service.build_model_attributes())
    ref = a6.load_reference()
    colors = a6.group_colors(ref["groupings"], rc.SUBSECTOR_COLORS)
    gmac = a6.ranked_group_macs()
    meta = tms.load_catalog()
    outside = (a6.NDC_LAST_YEAR, i18n.t("article_6.after_ndc_targets", lang, year=a6.NDC_LAST_YEAR))
    headline = a6.headline_years(a6.target_years(ref["targets"]))

    df = a6.load_ranked()
    if df.empty:
        raise SystemExit(f"no ranked MAC file at {a6.RANKED_PATH}")
    live = df.groupby([a6.FIELD_GROUP, a6.FIELD_KERNEL])["value_musd"].transform(lambda v: v.abs().max()) > 1e-9
    d = df[live]
    sectors = sorted(dict.fromkeys(d[a6.FIELD_GROUP]), key=lambda g: (g not in gmac, -gmac.get(g, 0.0)))
    # the stack, the base first: the lowest MAC (the sectors with none on top, as in the tool)
    stack = sorted(sectors, key=lambda g: (g not in gmac, gmac.get(g, 0.0)))

    # every (sector, transformation): its shade of the sector colour (closer to it = higher MAC), all by MAC
    pairs = d.drop_duplicates([a6.FIELD_GROUP, a6.FIELD_KERNEL])
    shade = {}
    for g, p in pairs.sort_values("mac", ascending=False, kind="stable").groupby(a6.FIELD_GROUP, sort=False):
        for k, c in zip(p[a6.FIELD_KERNEL], rc.shades(colors.get(g, rc.OTHER_COLOR), len(p))):
            shade[(g, k)] = c
    ranked = pairs.sort_values("mac", kind="stable")  # the stacking order: the lowest MAC at the base
    keys = list(ranked[a6.FIELD_GROUP] + "|" + ranked[a6.FIELD_KERNEL])
    sector_of = dict(zip(keys, ranked[a6.FIELD_GROUP]))
    mac_of = dict(zip(keys, ranked["mac"]))
    name = {k: i18n.td("transformers", k.split("|", 1)[1], "name", tms.get_card(k.split("|", 1)[1], meta)["name"], lang) for k in keys}
    color_of = {k: shade[(sector_of[k], k.split("|", 1)[1])] for k in keys}

    sector_frame = d.groupby(["year", a6.FIELD_GROUP], as_index=False)["value_musd"].sum().rename(
        columns={a6.FIELD_GROUP: "series", "value_musd": "value"})
    part_frame = d.assign(series=d[a6.FIELD_GROUP] + "|" + d[a6.FIELD_KERNEL]).rename(columns={"value_musd": "value"})[["year", "series", "value"]]
    by_year = part_frame.groupby("year")["value"]
    ylo = min(0.0, by_year.apply(lambda v: v.clip(upper=0).sum()).min())
    yhi = by_year.apply(lambda v: v.clip(lower=0).sum()).max()
    y_range = [ylo - 0.07 * (yhi - ylo), yhi + 0.05 * (yhi - ylo)]
    sector_name = {g: group_name(g, lang) for g in sectors}
    sector_title = {g: f"<b>{sector_name[g]}</b>" + (f" · {mac_text(gmac[g])}" if g in gmac else "") for g in sectors}

    # (1) sectors
    f1 = rc.credit_bars({"LEP": sector_frame}, colors, stack, "million USD", lang=lang, labels=sector_name,
                        label_years=headline, legend=False, outside=outside)
    _frame(f1, "Credits (emission reductions) by sector, ranked by MAC", "2026–2050", y_range)
    for i, g in enumerate(sectors):
        y = 124 + 36 * i
        _swatch(f1, LEGEND_X, y, 20, colors.get(g, rc.OTHER_COLOR))
        _text(f1, LEGEND_X + 33, y - 11, sector_name[g], 16)

    # (2) transformations
    f2 = rc.credit_bars({"LEP": part_frame}, color_of, keys, "million USD", lang=lang, labels=name,
                        label_years=headline, legend=False, outside=outside)
    _frame(f2, "Credits (emission reductions) by transformation, ranked by MAC",
           "2026–2050 · transformations shown in their sector’s colors", y_range)
    split = sectors.index(SECOND_COLUMN_FROM) if SECOND_COLUMN_FROM in sectors else (len(sectors) + 1) // 2
    for x, column in ((LEGEND_X, sectors[:split]), (LEGEND_X2, sectors[split:])):
        y = 46
        for g in column:
            _text(f2, x, y, sector_title[g], 12)
            y += LINE + 1
            for k in sorted((k for k in keys if sector_of[k] == g), key=lambda k: mac_of[k]):  # lowest MAC first, as they stack
                lines = _wrap(name[k], mac_text(mac_of[k]))
                _swatch(f2, x + 8, y + 8, 13, color_of[k])
                _text(f2, x + 36, y, "<br>".join(lines), FONT_ITEM)
                y += LINE * len(lines)
            y += 6
    return f1, f2


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--out", type=pathlib.Path, default=pathlib.Path("."), help="output folder (default: current)")
    args = p.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)
    figures = dict(zip(("a6_slide_credits_by_sector", "a6_slide_credits_by_transformation"), build()))
    for stem, fig in figures.items():
        fig.write_html(args.out / f"{stem}.html", include_plotlyjs="cdn")
        try:
            fig.write_image(args.out / f"{stem}.png", width=W, height=H, scale=2)
            print(args.out / f"{stem}.png")
        except Exception as err:  # no kaleido / Chrome: the HTML only
            print(f"{args.out / (stem + '.html')} (no PNG: {type(err).__name__}; pip install kaleido)")


if __name__ == "__main__":
    main()

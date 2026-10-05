"""Small inline SVG charts for the Pathways page (ramp curves, direction
bands). Plain SVG strings keep these cheap to re-render on every slider move;
colors come from the theme's CSS variables so light/dark both work.
"""

import datetime
from typing import List, Optional, Sequence, Tuple

import numpy as np
from shiny import ui

Curve = Tuple[Sequence[float], str]  # (values in 0..1, style: "main" | "ghost" | "muted" | css color)

_STYLES = {
    "main": 'stroke="var(--accent)" stroke-width="2" fill="none"',
    "ghost": 'stroke="var(--text-muted)" stroke-width="1.5" stroke-dasharray="4 3" fill="none"',
    "muted": 'stroke="var(--text-label)" stroke-width="2" fill="none"',
}


def _path(values: Sequence[float], x0: float, x1: float, y0: float, y1: float) -> str:
    n = len(values)
    if n < 2:
        return ""
    xs = np.linspace(x0, x1, n)
    pts = [f"{x:.1f},{y1 - (y1 - y0) * float(v):.1f}" for x, v in zip(xs, values)]
    return "M" + " L".join(pts)


def ramp_chart(
    curves: List[Curve],
    years: Sequence[int],
    width: int = 520,
    height: int = 150,
    fill_main: bool = True,
    max_value: float = 1.0,
    y_label: str = "Implementation",
) -> ui.HTML:
    """Line chart of implementation ramps (0..max_value) over model years,
    with a dashed 'today' marker."""
    pad_l, pad_r, pad_t, pad_b = 34, 10, 10, 22
    x0, x1, y0, y1 = pad_l, width - pad_r, pad_t, height - pad_b
    first, last = years[0], years[-1]

    def xpos(year: float) -> float:
        return x0 + (x1 - x0) * (year - first) / (last - first)

    parts = [f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="{y_label} over time">']
    # grid + axes
    for frac, lbl in ((0.0, "0%"), (0.5, f"{max_value * 50:.0f}%"), (1.0, f"{max_value * 100:.0f}%")):
        y = y1 - (y1 - y0) * frac
        parts.append(f'<line x1="{x0}" x2="{x1}" y1="{y:.1f}" y2="{y:.1f}" stroke="var(--border-soft)" />')
        parts.append(
            f'<text x="{x0 - 6}" y="{y + 3:.1f}" text-anchor="end" font-size="9.5" '
            f'font-family="IBM Plex Mono" fill="var(--text-muted)">{lbl}</text>'
        )
    this_year = datetime.date.today().year
    for year in (first, 2030, 2040, last):
        if first <= year <= last:
            parts.append(
                f'<text x="{xpos(year):.1f}" y="{height - 6}" text-anchor="middle" font-size="9.5" '
                f'font-family="IBM Plex Mono" fill="var(--text-muted)">{year}</text>'
            )
    if first < this_year < last:
        xt = xpos(this_year)
        parts.append(f'<line x1="{xt:.1f}" x2="{xt:.1f}" y1="{y0}" y2="{y1}" stroke="var(--text-muted)" stroke-dasharray="2 3" />')
        parts.append(
            f'<text x="{xt + 3:.1f}" y="{y0 + 8}" font-size="9" font-family="IBM Plex Mono" fill="var(--text-muted)">today</text>'
        )

    for values, style in curves:
        scaled = [float(v) / max_value if max_value else 0.0 for v in values]
        d = _path(scaled, x0, x1, y0, y1)
        if not d:
            continue
        if style == "main" and fill_main:
            parts.append(f'<path d="{d} L{x1},{y1} L{x0},{y1} Z" fill="var(--accent-soft)" stroke="none" />')
        attrs = _STYLES.get(style, f'stroke="{style}" stroke-width="1.6" fill="none"')
        parts.append(f'<path d="{d}" {attrs} />')
    parts.append("</svg>")
    return ui.HTML("".join(parts))


def direction_band(direction: str, ramp: Sequence[float], width: int = 120, height: int = 26) -> ui.HTML:
    """Tiny band that follows the ramp up (increases) or down (decreases);
    flat for no change, and a split band for 'shifts'."""
    color = {
        "increases": "var(--rust)",
        "decreases": "var(--accent)",
    }.get(direction, "var(--text-muted)")
    mid = height / 2
    values = np.asarray(ramp, dtype=float)
    if direction == "increases":
        shape = 0.5 + 0.45 * values
    elif direction == "decreases":
        shape = 0.5 - 0.45 * values
    else:
        shape = np.full_like(values, 0.5)
    d = _path(shape, 2, width - 2, 2, height - 2)
    extra = ""
    if direction == "shifts":
        up = _path(0.5 + 0.4 * values, 2, width - 2, 2, height - 2)
        dn = _path(0.5 - 0.4 * values, 2, width - 2, 2, height - 2)
        extra = f'<path d="{up}" stroke="var(--text-label)" stroke-width="1.3" fill="none" /><path d="{dn}" stroke="var(--text-label)" stroke-width="1.3" fill="none" stroke-dasharray="3 2" />'
        d = ""
    return ui.HTML(
        f'<svg viewBox="0 0 {width} {height}" width="{width}" height="{height}" aria-hidden="true">'
        f'<line x1="2" x2="{width - 2}" y1="{mid}" y2="{mid}" stroke="var(--border-soft)" />'
        + (f'<path d="{d}" stroke="{color}" stroke-width="1.8" fill="none" />' if d else "")
        + extra
        + "</svg>"
    )


def mini_ramp(values: Sequence[float], width: int = 64, height: int = 16, color: Optional[str] = None) -> ui.HTML:
    d = _path(values, 1, width - 1, 1, height - 1)
    stroke = color or "var(--accent)"
    return ui.HTML(
        f'<svg viewBox="0 0 {width} {height}" width="{width}" height="{height}" aria-hidden="true">'
        f'<path d="{d}" stroke="{stroke}" stroke-width="1.5" fill="none" /></svg>'
    )

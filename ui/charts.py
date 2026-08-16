"""Server-rendered inline SVG charts.

No external library and no CDN: the laboratory has to work offline. Colours come
from CSS custom properties so light and dark swap in one place, and every series
is also named in the legend and repeated in the table below the chart, so
identity never rests on colour alone.

An unknown measurement draws no bar. A zero-length bar would read as "free" or
"instant", which is exactly the confusion this project refuses to create.
"""

from __future__ import annotations

import html
import math
from collections.abc import Callable
from dataclasses import dataclass

LABEL_WIDTH = 150
RIGHT_PADDING = 96
ROW_HEIGHT = 34
BAR_HEIGHT = 18
AXIS_HEIGHT = 26
SEGMENT_GAP = 2
CORNER_RADIUS = 4
CHART_WIDTH = 760


@dataclass
class Segment:
    label: str
    slot: int
    value: float


@dataclass
class Row:
    label: str
    segments: list[Segment]
    total: float | None


def nice_ticks(maximum: float, count: int = 5) -> list[float]:
    """Round ticks whose last value always covers ``maximum``.

    The final tick sets the scale, so it must not fall short of the largest
    bar — otherwise the bar draws past the end of its own axis.
    """
    if maximum <= 0:
        return [0.0, 1.0]
    raw = maximum / count
    magnitude = 10.0 ** math.floor(math.log10(raw))
    step = magnitude * 10
    for factor in (1, 2, 2.5, 5, 10):
        if magnitude * factor >= raw:
            step = magnitude * factor
            break

    ticks: list[float] = []
    value = 0.0
    while value < maximum - step * 1e-9:
        ticks.append(round(value, 10))
        value += step
    ticks.append(round(value, 10))
    return ticks


def bar_path(x: float, y: float, width: float, height: float, round_end: bool) -> str:
    """A bar anchored square at the baseline, rounded only at the data end."""
    radius = CORNER_RADIUS
    if not round_end or width < radius:
        return (
            f'<rect x="{x:.2f}" y="{y:.2f}" width="{max(width, 0):.2f}" '
            f'height="{height:.2f}"/>'
        )
    right = x + width
    return (
        f'<path d="M{x:.2f},{y:.2f} H{right - radius:.2f} '
        f"A{radius},{radius} 0 0 1 {right:.2f},{y + radius:.2f} "
        f"V{y + height - radius:.2f} "
        f"A{radius},{radius} 0 0 1 {right - radius:.2f},{y + height:.2f} "
        f'H{x:.2f} Z"/>'
    )


def stacked_bars(
    rows: list[Row],
    unit: str,
    format_value: Callable[[float], str],
    format_tick: Callable[[float], str] | None = None,
    unknown_text: str = "неизвестно",
) -> str:
    """One horizontal stacked bar per row, segments coloured by series slot."""
    if not rows:
        return '<p class="empty">Нет данных для графика.</p>'

    tick_label = format_tick or format_value
    known = [row.total for row in rows if row.total is not None]
    maximum = max(known) if known else 0.0
    ticks = nice_ticks(maximum)
    scale_max = ticks[-1] if ticks and ticks[-1] > 0 else 1.0
    plot_width = CHART_WIDTH - LABEL_WIDTH - RIGHT_PADDING
    height = len(rows) * ROW_HEIGHT + AXIS_HEIGHT

    parts = [
        f'<svg class="chart" viewBox="0 0 {CHART_WIDTH} {height}" '
        f'role="img" preserveAspectRatio="xMinYMin meet">'
    ]

    for tick in ticks:
        x = LABEL_WIDTH + plot_width * (tick / scale_max)
        parts.append(
            f'<line class="grid" x1="{x:.2f}" y1="0" x2="{x:.2f}" '
            f'y2="{len(rows) * ROW_HEIGHT:.2f}"/>'
        )
        parts.append(
            f'<text class="tick" x="{x:.2f}" y="{height - 8}" '
            f'text-anchor="middle">{html.escape(tick_label(tick))}</text>'
        )
    parts.append(
        f'<text class="tick unit" x="{CHART_WIDTH - 4}" y="{height - 8}" '
        f'text-anchor="end">{html.escape(unit)}</text>'
    )

    for index, row in enumerate(rows):
        top = index * ROW_HEIGHT
        centre = top + ROW_HEIGHT / 2
        bar_top = centre - BAR_HEIGHT / 2
        parts.append(
            f'<text class="row-label" x="{LABEL_WIDTH - 10}" y="{centre + 4:.2f}" '
            f'text-anchor="end">{html.escape(row.label)}</text>'
        )

        if row.total is None:
            parts.append(
                f'<text class="unknown" x="{LABEL_WIDTH + 4}" y="{centre + 4:.2f}">'
                f"{html.escape(unknown_text)}</text>"
            )
            continue

        cursor = float(LABEL_WIDTH)
        drawable = [item for item in row.segments if item.value > 0]
        for position, segment in enumerate(drawable):
            width = plot_width * (segment.value / scale_max)
            last = position == len(drawable) - 1
            visible = max(width - (0 if last else SEGMENT_GAP), 0.5)
            parts.append(f'<g class="series-{segment.slot}">')
            parts.append(bar_path(cursor, bar_top, visible, BAR_HEIGHT, last))
            parts.append(
                "<title>"
                f"{html.escape(row.label)} · {html.escape(segment.label)}: "
                f"{html.escape(format_value(segment.value))} {html.escape(unit)}"
                "</title>"
            )
            parts.append("</g>")
            cursor += width

        parts.append(
            f'<text class="total" x="{cursor + 8:.2f}" y="{centre + 4:.2f}">'
            f"{html.escape(format_value(row.total))}</text>"
        )

    parts.append("</svg>")
    return "".join(parts)


def legend(entries: list[tuple[str, int]]) -> str:
    """Always present for two or more series; identity is never colour alone."""
    if len(entries) < 2:
        return ""
    items = "".join(
        f'<li><span class="swatch series-{slot}"></span>{html.escape(label)}</li>'
        for label, slot in entries
    )
    return f'<ul class="legend">{items}</ul>'

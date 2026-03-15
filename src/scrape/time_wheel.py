"""Timezone conversion wheel: donut with hollow center, UTC (inner ring), HST (outer). Hour 0 at noon (12 o'clock)."""
import datetime as dt
import math

from src.scrape.base import now_iso


HST = dt.timezone(dt.timedelta(hours=-10))
SIZE_PX = 280
HOURS = 24
DAY_START, DAY_END = 6, 18  # 06:00–18:00 = day

# SVG viewBox center 0,0. Donut: hole, then UTC ring, then HST ring.
R_HOLE = 80
R_INNER = 140   # UTC ring outer edge
R_OUTER = 200  # HST ring outer edge


def _theta(hour: float) -> float:
    """Angle in radians: hour 0 at noon (12 o'clock), hours increase clockwise."""
    return math.pi / 2 - hour * 2 * math.pi / HOURS


def _xy(r: float, hour: float) -> tuple[float, float]:
    """Position on circle: hour 0 at top (noon). x = r*cos(theta), y = -r*sin(theta)."""
    t = _theta(hour)
    return r * math.cos(t), -r * math.sin(t)


def _day_night_class(hour: int) -> str:
    return "day" if DAY_START <= hour < DAY_END else "night"


def _annulus_path(r1: float, r2: float, start_hour: float, end_hour: float) -> str:
    """SVG path for annulus segment between r1 and r2 (r2 > r1)."""
    x1o, y1o = _xy(r2, start_hour)
    x2o, y2o = _xy(r2, end_hour)
    x2i, y2i = _xy(r1, end_hour)
    x1i, y1i = _xy(r1, start_hour)
    large = 1 if (end_hour - start_hour) > 12 else 0
    return (
        f"M {x1o:.2f} {y1o:.2f} A {r2} {r2} 0 {large} 1 {x2o:.2f} {y2o:.2f} "
        f"L {x2i:.2f} {y2i:.2f} A {r1} {r1} 0 {large} 0 {x1i:.2f} {y1i:.2f} Z"
    )


def scrape() -> dict:
    # Donut: hole R_HOLE, inner ring UTC (R_HOLE to R_INNER), outer ring HST (R_INNER to R_OUTER).
    inner_day_paths = []
    inner_night_paths = []
    outer_day_paths = []
    outer_night_paths = []
    for i in range(HOURS):
        utc_h = (i + 10) % HOURS  # at HST hour i, UTC is i+10
        path_inner = _annulus_path(R_HOLE, R_INNER, i - 0.5, i + 0.5)
        path_outer = _annulus_path(R_INNER, R_OUTER, i - 0.5, i + 0.5)
        inner_fill = _day_night_class(utc_h)
        outer_fill = _day_night_class(i)
        if inner_fill == "day":
            inner_day_paths.append(f'<path d="{path_inner}" class="tw-seg tw-seg--day"/>')
        else:
            inner_night_paths.append(f'<path d="{path_inner}" class="tw-seg tw-seg--night"/>')
        if outer_fill == "day":
            outer_day_paths.append(f'<path d="{path_outer}" class="tw-seg tw-seg--day"/>')
        else:
            outer_night_paths.append(f'<path d="{path_outer}" class="tw-seg tw-seg--night"/>')

    # Labels in the middle of each ring
    r_inner_mid = (R_HOLE + R_INNER) / 2
    r_outer_mid = (R_INNER + R_OUTER) / 2
    inner_labels = []
    outer_labels = []
    for i in range(HOURS):
        xi, yi = _xy(r_inner_mid, i)
        xo, yo = _xy(r_outer_mid, i)
        utc_h = (i + 10) % HOURS
        inner_tone = "tw-label--night" if _day_night_class(utc_h) == "night" else "tw-label--day"
        outer_tone = "tw-label--night" if _day_night_class(i) == "night" else "tw-label--day"
        inner_labels.append(
            f'<text x="{xi:.2f}" y="{yi:.2f}" class="tw-label tw-label--inner {inner_tone}" text-anchor="middle" dominant-baseline="middle">{utc_h}</text>'
        )
        outer_labels.append(
            f'<text x="{xo:.2f}" y="{yo:.2f}" class="tw-label tw-label--outer {outer_tone}" text-anchor="middle" dominant-baseline="middle">{i}</text>'
        )

    # Next-day arc: along inner edge of UTC ring from position 1 to 10 (few px wide, red).
    x_arc_start, y_arc_start = _xy(R_HOLE, 14)
    x_arc_end, y_arc_end = _xy(R_HOLE, 0)
    next_day_arc = (
        f'<path d="M {x_arc_start:.2f} {y_arc_start:.2f} A {R_HOLE} {R_HOLE} 0 0 1 {x_arc_end:.2f} {y_arc_end:.2f}" '
        'class="tw-next-day-arc" fill="none"/>'
    )
    x_label, y_label = _xy(R_HOLE-28, 18.5)
    next_day_label = f'<text x="{x_label:.2f}" y="{y_label:.2f}" class="tw-next-day-label">+1 day</text>'

    # Draw order: hole (white), inner ring (UTC), outer ring (HST), next-day arc + label, labels, midnight, dots
    hole_circle = f'<circle cx="0" cy="0" r="{R_HOLE}" class="tw-hole"/>'
    svg_open = f'<svg class="time-wheel-svg" viewBox="-200 -200 400 400" preserveAspectRatio="xMidYMid meet" width="{SIZE_PX}" height="{SIZE_PX}">'
    inner_ring_label_y = r_inner_mid
    inner_ring_label = f'<text x="0" y="{inner_ring_label_y + 18:.2f}" class="tw-inner-label" text-anchor="middle" dominant-baseline="middle">UTC</text>'
    outer_label = f'<text x="0" y="{199 - 12:.0f}" class="tw-outer-label" text-anchor="middle" dominant-baseline="middle">HST</text>'
    svg_content = (
        svg_open
        + hole_circle
        + next_day_arc
        + next_day_label
        + "<g class=\"tw-ring tw-ring--inner\">"
        + "".join(inner_night_paths)
        + "".join(inner_day_paths)
        + "".join(inner_labels)
        + "</g>"
        + inner_ring_label
        + "<g class=\"tw-ring tw-ring--outer\">"
        + "".join(outer_night_paths)
        + "".join(outer_day_paths)
        + "".join(outer_labels)
        + "</g>"
        + outer_label
        + "</svg>"
    )

    css = """
.time-wheel { display: inline-block; margin: 0 auto; }
.time-wheel-svg { display: block; }
.time-wheel .tw-seg { stroke: none; }
.time-wheel .tw-seg--day { fill: #EAF6FF; }
.time-wheel .tw-seg--night { fill: #0B1020; }
.time-wheel .tw-hole { fill: #fff; stroke: none; }
.time-wheel .tw-next-day-arc { stroke: #c00; stroke-width: 6; }
.time-wheel .tw-next-day-label { font-size: 12px; fill: #c00; font-weight: 600; text-anchor: middle; dominant-baseline: middle; }
.time-wheel .tw-inner-label { font-size: 14px; font-weight: 600; fill: #999; pointer-events: none; }
.time-wheel .tw-outer-label { font-size: 14px; font-weight: 600; fill: #555; pointer-events: none; }
.time-wheel .tw-label { font-weight: 600; pointer-events: none; }
.time-wheel .tw-label--inner { font-size: 14px; fill: #111; }
.time-wheel .tw-label--outer { font-size: 16px; fill: #111; }
.time-wheel .tw-label--night { fill: #fff !important; }
"""

    body = (
        "<style>" + css + "</style>"
        '<div class="time-wheel">' + svg_content + "</div>"
    )

    return {
        "id": "time_wheel",
        "label": "Timezones (HST↔UTC)",
        "retrieved_at": now_iso(),
        "source_urls": [],
        "html": body,
        "error": None,
        "stale": False,
    }

"""Competition figure style and SVG rendering.

The style preset lives in :mod:`geobench.style` (it is read by two
backends). This module is the **SVG backend**: it turns the drawing
primitives of :mod:`geobench.primitives` into SVG.

Rendering is a pure function of (figure, style, view): no hidden state, so the
same file must always produce the same bytes (docs/spec.md section 10.3).

The screen is drawn by a second backend (geobench.app) from the *same*
primitives, so the picture on the screen and the exported figure cannot
drift apart (decision D20).
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from geobench.evaluate import numeric_circle, numeric_coords
from geobench.model import Figure
from geobench.primitives import (
    ArcPrimitive,
    CirclePrimitive,
    LabelPrimitive,
    LinePrimitive,
    PointPrimitive,
    RayPrimitive,
    SegmentPrimitive,
    figure_primitives,
)
from geobench.style import COMPETITION, PLAIN, FigureStyle, get_style

__all__ = [
    "COMPETITION",
    "PLAIN",
    "FigureStyle",
    "View",
    "clip_line",
    "fit_view",
    "get_style",
    "render_svg",
]


# -- view ------------------------------------------------------------------


@dataclass(frozen=True)
class View:
    """The viewport: a rectangle in figure coordinates."""

    x_min: float
    y_min: float
    x_max: float
    y_max: float

    @property
    def width(self) -> float:
        return self.x_max - self.x_min

    @property
    def height(self) -> float:
        return self.y_max - self.y_min


def fit_view(figure: Figure, padding: float = 0.6) -> View:
    """The bounding box of the figure, with padding.

    Only points and circles contribute: a line is infinite, so using it here
    would blow the box up to infinity and collapse everything else into the
    middle. Lines are clipped to the view at render time instead.
    """
    xs: list[float] = []
    ys: list[float] = []
    for node in figure.nodes.values():
        if not node.style.visible:
            continue
        if node.kind == "point":
            x, y = numeric_coords(figure, node.id)
            xs.append(x)
            ys.append(y)
        elif node.kind == "circle":
            cx, cy, r2 = numeric_circle(figure, node.id)
            if r2 <= 0:
                continue
            radius = math.sqrt(r2)
            xs.extend([cx - radius, cx + radius])
            ys.extend([cy - radius, cy + radius])
    if not xs:
        return View(-1.0, -1.0, 1.0, 1.0)
    return View(
        min(xs) - padding,
        min(ys) - padding,
        max(xs) + padding,
        max(ys) + padding,
    )


def clip_ray(
    x0: float, y0: float, x1: float, y1: float, view: View
) -> tuple[float, float, float, float] | None:
    """Clip the half-line from (x0, y0) through (x1, y1) to the view.

    The same clipping as a line, except that the parameter runs from
    zero: everything behind the starting point is not on the ray.
    """
    dx, dy = x1 - x0, y1 - y0
    if dx == 0 and dy == 0:
        return None
    low, high = 0.0, 1e12
    edges = [
        (1.0, 0.0, view.x_min),
        (-1.0, 0.0, -view.x_max),
        (0.0, 1.0, view.y_min),
        (0.0, -1.0, -view.y_max),
    ]
    for nx, ny, offset in edges:
        denominator = nx * dx + ny * dy
        numerator = offset - (nx * x0 + ny * y0)
        if abs(denominator) < 1e-12:
            if numerator > 0:
                return None
            continue
        t = numerator / denominator
        if denominator > 0:
            low = max(low, t)
        else:
            high = min(high, t)
    if low > high:
        return None
    return (x0 + low * dx, y0 + low * dy, x0 + high * dx, y0 + high * dy)


def clip_line(a: float, b: float, c: float, view: View) -> tuple[float, float, float, float] | None:
    """Clip the infinite line ``a*x + b*y + c = 0`` to a rectangle.

    Cyrus-Beck: parameterise the line as ``P + t*D`` and intersect the
    parameter interval with each of the four half-planes. Returns the two
    endpoints, or None when the line misses the rectangle entirely.
    """
    if abs(a) < 1e-12 and abs(b) < 1e-12:
        return None
    # A point on the line and a direction along it.
    if abs(b) > 1e-12:
        px, py = 0.0, -c / b
    else:
        px, py = -c / a, 0.0
    dx, dy = b, -a

    t_low, t_high = -1e12, 1e12
    edges = [
        (1.0, 0.0, view.x_min),  # x >= x_min
        (-1.0, 0.0, -view.x_max),  # x <= x_max
        (0.0, 1.0, view.y_min),
        (0.0, -1.0, -view.y_max),
    ]
    for nx, ny, offset in edges:
        denom = nx * dx + ny * dy
        numer = offset - (nx * px + ny * py)
        if abs(denom) < 1e-12:
            # Parallel to this edge: the constraint must already hold.
            if numer > 0:
                return None
            continue
        t = numer / denom
        if denom > 0:
            t_low = max(t_low, t)
        else:
            t_high = min(t_high, t)
    if t_low > t_high:
        return None
    return (
        px + t_low * dx,
        py + t_low * dy,
        px + t_high * dx,
        py + t_high * dy,
    )


# -- rendering -------------------------------------------------------------


def _fmt(value: float) -> str:
    return f"{value:.4f}".rstrip("0").rstrip(".")


def render_svg(
    figure: Figure,
    style: FigureStyle = COMPETITION,
    view: View | None = None,
    width_px: int = 640,
) -> str:
    """Render a figure to SVG. Pure function: same input, same bytes.

    The SVG is written from the drawing primitives, which the screen
    backend draws too -- so the picture on the screen and the exported
    figure are the same picture (decision D20).
    """
    view = view or fit_view(figure, style.padding)
    scale = width_px / view.width if view.width else 1.0
    height_px = round(view.height * scale)

    def tx(x: float) -> float:
        return (x - view.x_min) * scale

    def ty(y: float) -> float:
        # SVG's y axis points down; figures are drawn in maths orientation.
        return height_px - (y - view.y_min) * scale

    parts: list[str] = []
    parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width_px}" '
        f'height="{height_px}" viewBox="0 0 {width_px} {height_px}" '
        f'font-family="{style.font_family}" font-size="{style.font_size}">'
    )
    if style.background != "none":
        parts.append(
            f'<rect width="{width_px}" height="{height_px}" fill="{style.background}"/>'
        )

    primitives = figure_primitives(figure, style)

    for primitive in primitives:
        if isinstance(primitive, LinePrimitive):
            clipped = clip_line(primitive.a, primitive.b, primitive.c, view)
            if clipped is None:
                continue
            x1, y1, x2, y2 = clipped
            parts.append(_svg_line(tx, ty, x1, y1, x2, y2, primitive.auxiliary, style))
        elif isinstance(primitive, SegmentPrimitive):
            parts.append(
                _svg_line(
                    tx,
                    ty,
                    primitive.x1,
                    primitive.y1,
                    primitive.x2,
                    primitive.y2,
                    primitive.auxiliary,
                    style,
                )
            )
        elif isinstance(primitive, RayPrimitive):
            clipped = clip_ray(
                primitive.x0, primitive.y0, primitive.x1, primitive.y1, view
            )
            if clipped is None:
                continue
            x1, y1, x2, y2 = clipped
            parts.append(_svg_line(tx, ty, x1, y1, x2, y2, primitive.auxiliary, style))
        elif isinstance(primitive, CirclePrimitive):
            parts.append(
                f'<circle cx="{_fmt(tx(primitive.cx))}" cy="{_fmt(ty(primitive.cy))}" '
                f'r="{_fmt(primitive.radius * scale)}" fill="none" '
                f'stroke="{style.stroke}" '
                f'stroke-width="{_stroke_width(primitive.auxiliary, style)}"'
                f'{_dash(primitive.auxiliary)}/>'
            )
        elif isinstance(primitive, ArcPrimitive):
            parts.append(_svg_arc(tx, ty, primitive, scale, style))
        elif isinstance(primitive, PointPrimitive):
            if not (math.isfinite(primitive.x) and math.isfinite(primitive.y)):
                # A point that could not be placed has no sensible
                # position. Skip it rather than dragging the whole layout
                # into NaN with it.
                continue
            radius = (
                style.point_radius if primitive.free else style.derived_point_radius
            )
            fill = (
                style.stroke
                if (primitive.free or style.derived_point_filled)
                else "none"
            )
            parts.append(
                f'<circle cx="{_fmt(tx(primitive.x))}" cy="{_fmt(ty(primitive.y))}" '
                f'r="{_fmt(radius)}" fill="{fill}" stroke="{style.stroke}" '
                f'stroke-width="0.4"/>'
            )

    # Labels last, so they are never covered by a stroke.
    offset = style.label_offset
    for primitive in primitives:
        if not isinstance(primitive, LabelPrimitive):
            continue
        parts.append(
            f'<text x="{_fmt(tx(primitive.x) + primitive.offset_x * offset)}" '
            f'y="{_fmt(ty(primitive.y) - primitive.offset_y * offset)}" '
            f'text-anchor="middle" dominant-baseline="central" '
            f'font-style="italic" fill="{style.stroke}">{primitive.text}</text>'
        )

    parts.append("</svg>")
    return "\n".join(parts)


def _svg_arc(
    tx: Callable[[float], float],
    ty: Callable[[float], float],
    primitive: ArcPrimitive,
    scale: float,
    style: FigureStyle,
) -> str:
    """One arc as an SVG path.

    The angles are worked out in the figure's coordinates, where y
    points up. The screen's y points down, so a counter-clockwise arc
    in the figure is drawn with the opposite sweep flag.
    """
    radius = primitive.radius
    start = math.radians(primitive.start_angle)
    end = start + math.radians(primitive.span_angle)
    x1 = tx(primitive.cx + radius * math.cos(start))
    y1 = ty(primitive.cy + radius * math.sin(start))
    x2 = tx(primitive.cx + radius * math.cos(end))
    y2 = ty(primitive.cy + radius * math.sin(end))
    large = 1 if abs(primitive.span_angle) > 180.0 else 0
    sweep = 0 if primitive.span_angle >= 0 else 1
    scaled = radius * scale
    if primitive.filled:
        # A sector: the arc plus the two radii back to the centre.
        path = (
            f"M {_fmt(tx(primitive.cx))} {_fmt(ty(primitive.cy))} "
            f"L {_fmt(x1)} {_fmt(y1)} "
            f"A {_fmt(scaled)} {_fmt(scaled)} 0 {large} {sweep} {_fmt(x2)} {_fmt(y2)} Z"
        )
        fill = style.sector_fill
    else:
        path = (
            f"M {_fmt(x1)} {_fmt(y1)} "
            f"A {_fmt(scaled)} {_fmt(scaled)} 0 {large} {sweep} {_fmt(x2)} {_fmt(y2)}"
        )
        fill = "none"
    return (
        f'<path d="{path}" fill="{fill}" stroke="{style.stroke}" '
        f'stroke-width="{_stroke_width(primitive.auxiliary, style)}"'
        f"{_dash(primitive.auxiliary)}/>"
    )


def _stroke_width(auxiliary: bool, style: FigureStyle) -> float:
    return style.auxiliary_stroke_width if auxiliary else style.stroke_width


def _dash(auxiliary: bool) -> str:
    return ' stroke-dasharray="3 2"' if auxiliary else ""


def _svg_line(
    tx: Any,
    ty: Any,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    auxiliary: bool,
    style: FigureStyle,
) -> str:
    return (
        f'<line x1="{_fmt(tx(x1))}" y1="{_fmt(ty(y1))}" '
        f'x2="{_fmt(tx(x2))}" y2="{_fmt(ty(y2))}" '
        f'stroke="{style.stroke}" stroke-width="{_stroke_width(auxiliary, style)}"'
        f"{_dash(auxiliary)}/>"
    )

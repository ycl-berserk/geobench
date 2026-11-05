"""Competition figure style and SVG rendering.

The style preset follows the conventions that competition papers actually use.
These are not invented here: TikZ's defaults are the de-facto standard for
olympiad figures (0.4pt stroke, 1.5pt point radius, Times-family serif
labels), and Chinese olympiad papers add a few house rules of their own --
auxiliary lines dashed and unlabelled, circle written as ``⊙O``, the caption
("如图") living in the statement rather than inside the image.

Rendering is a pure function of (figure, style, view): no hidden state, so the
same file must always produce the same bytes (docs/spec.md section 10.3).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from geobench.evaluate import numeric_circle, numeric_coords, numeric_line, numeric_segment
from geobench.model import Figure

# -- style -----------------------------------------------------------------


@dataclass(frozen=True)
class FigureStyle:
    """Rendering attributes. Never affects geometry."""

    name: str = "competition"
    stroke: str = "#000000"
    stroke_width: float = 0.4
    auxiliary_stroke_width: float = 0.25
    point_radius: float = 1.5
    derived_point_radius: float = 1.5
    derived_point_filled: bool = True
    font_family: str = "Times New Roman, STIX Two Text, serif"
    font_size: float = 10.0
    label_offset: float = 0.22
    background: str = "none"
    padding: float = 0.6

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "stroke": self.stroke,
            "stroke_width": self.stroke_width,
            "auxiliary_stroke_width": self.auxiliary_stroke_width,
            "point_radius": self.point_radius,
            "derived_point_radius": self.derived_point_radius,
            "derived_point_filled": self.derived_point_filled,
            "font_family": self.font_family,
            "font_size": self.font_size,
            "label_offset": self.label_offset,
            "background": self.background,
            "padding": self.padding,
        }


COMPETITION = FigureStyle()
PLAIN = FigureStyle(name="plain", stroke="#1f2933", stroke_width=0.6, point_radius=2.0)


def get_style(name: str) -> FigureStyle:
    if name == "competition":
        return COMPETITION
    if name == "plain":
        return PLAIN
    raise ValueError(f"unknown style preset {name!r}")


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
    """Render a figure to SVG. Pure function: same input, same bytes."""
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

    # Auxiliary objects first, so the main figure sits on top.
    auxiliary = {"l_aux", "c_aux"}
    for node_id in figure.nodes:
        node = figure.nodes[node_id]
        if not node.style.visible:
            continue
        aux = node_id in auxiliary or node.style.line_style == "dashed"
        width = style.auxiliary_stroke_width if aux else style.stroke_width
        dash = ' stroke-dasharray="3 2"' if aux else ""
        if node.kind == "line":
            a, b, c = numeric_line(figure, node_id)
            clipped = clip_line(a, b, c, view)
            if clipped is None:
                continue
            x1, y1, x2, y2 = clipped
            parts.append(
                f'<line x1="{_fmt(tx(x1))}" y1="{_fmt(ty(y1))}" '
                f'x2="{_fmt(tx(x2))}" y2="{_fmt(ty(y2))}" '
                f'stroke="{style.stroke}" stroke-width="{width}"{dash}/>'
            )
        elif node.kind == "segment":
            x1, y1, x2, y2 = numeric_segment(figure, node_id)
            parts.append(
                f'<line x1="{_fmt(tx(x1))}" y1="{_fmt(ty(y1))}" '
                f'x2="{_fmt(tx(x2))}" y2="{_fmt(ty(y2))}" '
                f'stroke="{style.stroke}" stroke-width="{width}"{dash}/>'
            )
        elif node.kind == "circle":
            cx, cy, r2 = numeric_circle(figure, node_id)
            if r2 <= 0:
                continue
            radius = math.sqrt(r2)
            parts.append(
                f'<circle cx="{_fmt(tx(cx))}" cy="{_fmt(ty(cy))}" r="{_fmt(radius * scale)}" '
                f'fill="none" stroke="{style.stroke}" stroke-width="{width}"{dash}/>'
            )

    for node_id in figure.nodes:
        node = figure.nodes[node_id]
        if node.kind != "point" or not node.style.visible:
            continue
        x, y = numeric_coords(figure, node_id)
        radius = (
            style.point_radius if node.role == "free" else style.derived_point_radius
        )
        fill = style.stroke if (node.role == "free" or style.derived_point_filled) else "none"
        parts.append(
            f'<circle cx="{_fmt(tx(x))}" cy="{_fmt(ty(y))}" r="{_fmt(radius)}" '
            f'fill="{fill}" stroke="{style.stroke}" stroke-width="0.4"/>'
        )

    # Labels last, so they are never covered by a stroke.
    offset = style.label_offset * scale
    for node_id in figure.nodes:
        node = figure.nodes[node_id]
        if node.kind != "point" or not node.style.visible:
            continue
        label = node.style.label or node.label or node_id
        if not label:
            continue
        x, y = numeric_coords(figure, node_id)
        dx, dy = _label_offset(node_id, figure)
        parts.append(
            f'<text x="{_fmt(tx(x) + dx * offset)}" y="{_fmt(ty(y) - dy * offset)}" '
            f'text-anchor="middle" dominant-baseline="central" '
            f'font-style="italic" fill="{style.stroke}">{label}</text>'
        )

    parts.append("</svg>")
    return "\n".join(parts)


def _label_offset(node_id: str, figure: Figure) -> tuple[float, float]:
    """Place a label away from the figure's centroid, so it does not sit on a stroke."""
    xs: list[float] = []
    ys: list[float] = []
    for other in figure.nodes.values():
        if other.kind != "point":
            continue
        try:
            x, y = numeric_coords(figure, other.id)
        except Exception:  # pragma: no cover - defensive
            continue
        xs.append(x)
        ys.append(y)
    if not xs:
        return 0.0, 0.0
    cx = sum(xs) / len(xs)
    cy = sum(ys) / len(ys)
    x, y = numeric_coords(figure, node_id)
    dx, dy = x - cx, y - cy
    norm = math.hypot(dx, dy)
    if norm < 1e-9:
        return 0.0, 1.0
    return dx / norm, dy / norm

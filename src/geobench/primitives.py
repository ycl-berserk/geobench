"""The drawing primitives: what a figure looks like, independent of how it is drawn.

A figure is a construction; a *picture* of it is a list of primitives.
This module produces that list, once, and two backends consume it:

- the **SVG** backend (geobench.render) writes the exported figure;
- the **QPainter** backend (geobench.app) draws the screen.

The point of the split is that the screen and the export must not be two
independent implementations of "how a figure looks", which is how they
drift apart. Sharing the primitive list makes them agree by
construction, and a test holds them to it (decision D20).

The primitives carry **figure coordinates**, not pixels. The viewport
(the mapping from figure coordinates to the screen) belongs to the
backend, because the screen's viewport changes as the user zooms and
the export's does not.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from geobench.evaluate import numeric_circle, numeric_coords, numeric_line, numeric_segment
from geobench.model import Figure
from geobench.style import FigureStyle


@dataclass(frozen=True)
class PointPrimitive:
    """A point, with the label that belongs to it."""

    x: float
    y: float
    label: str
    free: bool
    undefined: bool = False


@dataclass(frozen=True)
class SegmentPrimitive:
    """A segment between two points."""

    x1: float
    y1: float
    x2: float
    y2: float
    auxiliary: bool = False


@dataclass(frozen=True)
class LinePrimitive:
    """An infinite line, as ``a*x + b*y + c = 0``."""

    a: float
    b: float
    c: float
    auxiliary: bool = False


@dataclass(frozen=True)
class CirclePrimitive:
    """A circle, by its centre and its radius."""

    cx: float
    cy: float
    radius: float
    auxiliary: bool = False


@dataclass(frozen=True)
class LabelPrimitive:
    """A piece of text, already placed."""

    x: float
    y: float
    text: str
    offset_x: float = 0.0
    offset_y: float = 0.0


Primitive = PointPrimitive | SegmentPrimitive | LinePrimitive | CirclePrimitive | LabelPrimitive


def is_auxiliary(node_id: str, style: FigureStyle) -> bool:
    """Is this object an auxiliary one (drawn dashed and thinner)?

    Auxiliary objects are the ones that only support the figure -- the
    altitude, the perpendicular bisector, the auxiliary circle. Chinese
    competition papers draw them dashed and unlabelled, because they are
    not part of the problem's statement (decision D6).
    """
    return node_id in style.auxiliary_ids or node_id.startswith("l_aux")


def figure_primitives(figure: Figure, style: FigureStyle) -> list[Primitive]:
    """Every primitive of a figure, in draw order.

    The order matters: auxiliary objects go down first so that the
    objects the problem is about are drawn on top of them, then the
    points, then the labels -- labels last, so a stroke never covers
    one.
    """
    auxiliary: list[Primitive] = []
    main: list[Primitive] = []
    points: list[PointPrimitive] = []
    labels: list[LabelPrimitive] = []

    for node_id, node in figure.nodes.items():
        if not node.style.visible:
            continue
        aux = is_auxiliary(node_id, style) or node.style.line_style == "dashed"
        if node.kind == "line":
            a, b, c = numeric_line(figure, node_id)
            primitive: Primitive = LinePrimitive(a, b, c, aux)
        elif node.kind == "segment":
            x1, y1, x2, y2 = numeric_segment(figure, node_id)
            primitive = SegmentPrimitive(x1, y1, x2, y2, aux)
        elif node.kind == "circle":
            cx, cy, r2 = numeric_circle(figure, node_id)
            if r2 <= 0:
                continue
            primitive = CirclePrimitive(cx, cy, math.sqrt(r2), aux)
        elif node.kind == "point":
            x, y = numeric_coords(figure, node_id)
            undefined = node.placement is None
            points.append(
                PointPrimitive(
                    x,
                    y,
                    node.style.label or node.label or node_id,
                    node.role == "free",
                    undefined,
                )
            )
            continue
        else:
            continue
        (auxiliary if aux else main).append(primitive)

    for point in points:
        if not point.label:
            continue
        dx, dy = _label_offset(figure, point)
        labels.append(LabelPrimitive(point.x, point.y, point.label, dx, dy))

    return [*auxiliary, *main, *points, *labels]


def _label_offset(figure: Figure, point: PointPrimitive) -> tuple[float, float]:
    """Place a label away from the figure's centroid, so it does not sit on a stroke.

    The centroid is taken over the points that *have* a position: one
    unplaceable point must not push every label off the canvas.
    """
    xs: list[float] = []
    ys: list[float] = []
    for node in figure.nodes.values():
        if node.kind != "point":
            continue
        try:
            x, y = numeric_coords(figure, node.id)
        except Exception:  # pragma: no cover - defensive
            continue
        if not (math.isfinite(x) and math.isfinite(y)):
            continue
        xs.append(x)
        ys.append(y)
    if not xs:
        return 0.0, 0.0
    cx = sum(xs) / len(xs)
    cy = sum(ys) / len(ys)
    dx, dy = point.x - cx, point.y - cy
    norm = math.hypot(dx, dy)
    if norm < 1e-9:
        return 0.0, 1.0
    return dx / norm, dy / norm

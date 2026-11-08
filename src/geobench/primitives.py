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

from geobench.errors import StateError
from geobench.evaluate import (
    numeric_circle,
    numeric_coords,
    numeric_line,
    numeric_segment,
)
from geobench.model import Figure, Node
from geobench.style import FigureStyle


def _numeric_payload(
    figure: Figure, node_id: str, key: str
) -> tuple[float, ...] | None:
    """The node's numeric payload, when the numeric path has computed it."""
    values = figure.node(node_id).cache.get("numeric")
    if not values:
        return None
    payload = values.get(key)
    if payload is None:
        return None
    if isinstance(payload, (int, float)):
        # A measurement is a single number, not a list of them.
        return (float(payload),)
    return tuple(payload)


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
class RayPrimitive:
    """A half-line: it starts at ``(x0, y0)`` and passes through ``(x1, y1)``.

    Both points are carried, because which end is the beginning is the
    only thing that tells a ray from a line.
    """

    x0: float
    y0: float
    x1: float
    y1: float
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
class ArcPrimitive:
    """A circular arc, by its centre, its radius and its angles.

    The angles are in **degrees**, measured counter-clockwise from the
    positive x-axis of the *figure* coordinates (where y points up). The
    span is signed: positive means counter-clockwise.

    The angles are worked out here, once, so that the screen and the
    export draw the same arc (decision D20). Which of the two arcs of a
    circle is meant depends on where the points are, so it is settled
    from the numbers rather than from the symbols.
    """

    cx: float
    cy: float
    radius: float
    start_angle: float
    span_angle: float
    auxiliary: bool = False
    filled: bool = False


@dataclass(frozen=True)
class LabelPrimitive:
    """A piece of text, already placed."""

    x: float
    y: float
    text: str
    offset_x: float = 0.0
    offset_y: float = 0.0


Primitive = (
    PointPrimitive
    | SegmentPrimitive
    | LinePrimitive
    | CirclePrimitive
    | RayPrimitive
    | ArcPrimitive
    | LabelPrimitive
)


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
            try:
                a, b, c = numeric_line(figure, node_id)
            except (StateError, TypeError, ValueError):
                # This object has no value at this placement. It is not
                # drawn, and the rest of the picture is.
                continue
            primitive: Primitive = LinePrimitive(a, b, c, aux)
        elif node.kind == "segment":
            try:
                x1, y1, x2, y2 = numeric_segment(figure, node_id)
            except (StateError, TypeError, ValueError):
                continue
            primitive = SegmentPrimitive(x1, y1, x2, y2, aux)
        elif node.kind == "circle":
            try:
                cx, cy, r2 = numeric_circle(figure, node_id)
            except (StateError, TypeError, ValueError):
                continue
            if r2 <= 0:
                continue
            primitive = CirclePrimitive(cx, cy, math.sqrt(r2), aux)
        elif node.kind == "point":
            try:
                x, y = numeric_coords(figure, node_id)
            except (StateError, TypeError, ValueError):
                # A point with no real value here is not drawn; the
                # rest of the picture is.
                continue
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
        elif node.kind == "number":
            # A measurement is a number written on the figure. Where it
            # goes depends on what was measured: the middle of the
            # segment, the vertex of the angle, the middle of the
            # polygon.
            value = _numeric_payload(figure, node_id, "value")
            if value is None:
                continue
            position = _number_position(figure, node)
            if position is None:
                continue
            # The opposite way from the point labels: a point and the
            # measurement taken from it both sit at the same place --
            # the midpoint of a segment, the vertex of an angle -- and
            # two labels on top of each other are unreadable.
            dx, dy = _label_offset(figure, position[0], position[1])
            offset = (-dx, -dy)
            labels.append(
                LabelPrimitive(
                    position[0],
                    position[1],
                    _format_number(value[0]),
                    offset[0],
                    offset[1],
                )
            )
            continue
        elif node.kind == "ray":
            payload = _numeric_payload(figure, node_id, "ray")
            if payload is None or len(payload) != 4:
                continue
            primitive = RayPrimitive(*payload[:4], aux)
        elif node.kind == "polyline":
            # A polyline is its edges, and they are not closed.
            vertices = _numeric_payload(figure, node_id, "polyline")
            if vertices is None or len(vertices) < 4:
                continue
            count = len(vertices) // 2
            for index in range(count - 1):
                x1, y1 = vertices[2 * index], vertices[2 * index + 1]
                x2, y2 = vertices[2 * index + 2], vertices[2 * index + 3]
                (auxiliary if aux else main).append(SegmentPrimitive(x1, y1, x2, y2, aux))
            continue
        elif node.kind == "polygon":
            # A polygon is its edges: the primitive list carries the
            # segments between its vertices, so the screen and the export
            # draw the same thing (decision D20).
            vertices = _numeric_payload(figure, node_id, "polygon")
            if vertices is None or len(vertices) < 6:
                continue
            count = len(vertices) // 2
            for index in range(count):
                x1, y1 = vertices[2 * index], vertices[2 * index + 1]
                next_index = (index + 1) % count
                x2, y2 = vertices[2 * next_index], vertices[2 * next_index + 1]
                (auxiliary if aux else main).append(
                    SegmentPrimitive(x1, y1, x2, y2, aux)
                )
            continue
        elif node.kind == "arc":
            payload = _numeric_payload(figure, node_id, "arc")
            if payload is None or len(payload) != 9:
                continue
            ox, oy, r2 = payload[0], payload[1], payload[2]
            if r2 <= 0:
                continue
            start, span = _arc_angles(
                ox,
                oy,
                payload[3],
                payload[4],
                payload[5],
                payload[6],
                (payload[7], payload[8]),
            )
            primitive = ArcPrimitive(ox, oy, math.sqrt(r2), start, span, aux)
        elif node.kind == "sector":
            payload = _numeric_payload(figure, node_id, "sector")
            if payload is None or len(payload) != 7:
                continue
            ox, oy, r2 = payload[0], payload[1], payload[2]
            if r2 <= 0:
                continue
            start, span = _arc_angles(
                ox,
                oy,
                payload[3],
                payload[4],
                payload[5],
                payload[6],
                None,
            )
            primitive = ArcPrimitive(ox, oy, math.sqrt(r2), start, span, aux, True)
        else:
            continue
        (auxiliary if aux else main).append(primitive)

    for point in points:
        if not point.label:
            continue
        dx, dy = _label_offset(figure, point.x, point.y)
        labels.append(LabelPrimitive(point.x, point.y, point.label, dx, dy))

    return [*auxiliary, *main, *points, *labels]


def _arc_angles(
    ox: float,
    oy: float,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    through: tuple[float, float] | None,
) -> tuple[float, float]:
    """The start angle and the span of an arc, in degrees.

    The arc runs from the first point to the second. When a third point
    is given, the arc is the one that passes through it -- of the two
    arcs between the endpoints, the one that contains the third point
    is meant, and which one that is depends on the order of the three
    points around the circle.

    The angles are measured counter-clockwise in figure coordinates,
    where y points up.
    """
    start = math.atan2(y1 - oy, x1 - ox)
    end = math.atan2(y2 - oy, x2 - ox)
    counter_clockwise = (end - start) % (2 * math.pi)
    if through is None:
        return math.degrees(start), math.degrees(counter_clockwise)
    xm, ym = through
    middle = math.atan2(ym - oy, xm - ox)
    offset = (middle - start) % (2 * math.pi)
    if offset <= counter_clockwise + 1e-9:
        # The middle point lies on the counter-clockwise arc.
        return math.degrees(start), math.degrees(counter_clockwise)
    # Otherwise the arc goes the other way: counter-clockwise from the
    # end point to the start point.
    return math.degrees(end), math.degrees(2 * math.pi - counter_clockwise)


def _format_number(value: float) -> str:
    """A number as it is written on a figure.

    A whole number is written as a whole number, and everything else to
    two decimals. A measurement that says 3.14159 is not more useful
    than one that says 3.14, and it is harder to read.
    """
    if not math.isfinite(value):
        return "?"
    if abs(value - round(value)) < 1e-9:
        return str(round(value))
    return f"{value:.2f}".rstrip("0").rstrip(".")


def _number_position(figure: Figure, node: Node) -> tuple[float, float] | None:
    """Where the label of a measurement goes.

    The rule follows what was measured: the middle of a segment, the
    vertex of an angle, the inside of a polygon for its area and the
    middle of one of its sides for its perimeter -- so the two numbers
    a polygon produces do not land on top of each other.
    """
    args = node.args
    try:
        if len(args) == 3:
            # An angle: the label belongs at the vertex.
            return numeric_coords(figure, args[1])
        if len(args) == 2:
            first = numeric_coords(figure, args[0])
            second = numeric_coords(figure, args[1])
            return ((first[0] + second[0]) / 2, (first[1] + second[1]) / 2)
        if len(args) == 1:
            kind = figure.node(args[0]).kind
            if kind == "segment":
                x1, y1, x2, y2 = numeric_segment(figure, args[0])
                return ((x1 + x2) / 2, (y1 + y2) / 2)
            if kind == "polygon":
                vertices = _numeric_payload(figure, args[0], "polygon")
                if not vertices:
                    return None
                count = len(vertices) // 2
                centre = (
                    sum(vertices[2 * i] for i in range(count)) / count,
                    sum(vertices[2 * i + 1] for i in range(count)) / count,
                )
                if node.op == "measure.perimeter":
                    # The perimeter belongs on the boundary, not inside.
                    x1, y1 = vertices[0], vertices[1]
                    x2, y2 = vertices[2], vertices[3]
                    return ((x1 + x2) / 2, (y1 + y2) / 2)
                return centre
            if kind == "circle":
                cx, cy, r2 = numeric_circle(figure, args[0])
                return (cx, cy + math.sqrt(r2))
            if kind == "line":
                return _point_on_line_near(figure, args[0])
    except Exception:  # pragma: no cover - defensive
        return None
    return None


def _point_on_line_near(figure: Figure, node_id: str) -> tuple[float, float] | None:
    """A point on a line, as close as possible to the middle of the figure."""
    a, b, c = numeric_line(figure, node_id)
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
        return None
    cx = sum(xs) / len(xs)
    cy = sum(ys) / len(ys)
    denominator = a * a + b * b
    if denominator == 0:
        return None
    distance = (a * cx + b * cy + c) / denominator
    return (cx - a * distance, cy - b * distance)


def _label_offset(figure: Figure, x: float, y: float) -> tuple[float, float]:
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
            px, py = numeric_coords(figure, node.id)
        except Exception:  # pragma: no cover - defensive
            continue
        if not (math.isfinite(px) and math.isfinite(py)):
            continue
        xs.append(px)
        ys.append(py)
    if not xs:
        return 0.0, 0.0
    cx = sum(xs) / len(xs)
    cy = sum(ys) / len(ys)
    dx, dy = x - cx, y - cy
    norm = math.hypot(dx, dy)
    if norm < 1e-9:
        return 0.0, 1.0
    return dx / norm, dy / norm

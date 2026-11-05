"""Oracle implementations for cross-checking the kernel's operators.

An oracle is an implementation that does **not** share code with the kernel.
Where possible it is sympy's own geometry module; otherwise it is a closed-form
derivation written independently of the kernel's formulas.

This is the project's most important gate: geometry code that looks right is
routinely wrong at the edges, and only an independent implementation can tell
the difference (docs/spec.md section 5.3).
"""

from __future__ import annotations

from typing import Any

import sympy as sp
from sympy.geometry import Line, Point, Segment

from geobench.operators import OpContext


def _point(ctx: OpContext, node_id: str) -> Point:
    x, y = ctx.point(node_id)
    return Point(x, y)


def _line(ctx: OpContext, node_id: str) -> Line:
    """A sympy Line from the implicit coefficients stored in the node.

    sympy's Line is built from two points, so the coefficients are turned
    back into points and sympy reconstructs the line by its own route.
    """
    a, b, c = ctx.line(node_id)
    if a == 0 and b == 0:
        raise ValueError("degenerate line")
    if b != 0:
        p1 = sp.Point(0, -c / b)
        p2 = sp.Point(b, -c / b - a)
    else:
        p1 = sp.Point(-c / a, 0)
        p2 = sp.Point(-c / a - b, a)
    return Line(p1, p2)


# -- oracles ---------------------------------------------------------------


def oracle_midpoint(ctx: OpContext, args: list[str]) -> tuple[Any, Any]:
    midpoint = Segment(_point(ctx, args[0]), _point(ctx, args[1])).midpoint
    return midpoint.x, midpoint.y


def oracle_centroid(ctx: OpContext, args: list[str]) -> tuple[Any, Any]:
    points = [_point(ctx, node_id) for node_id in args]
    centroid = sum(points, sp.Point(0, 0)) / len(points)
    return centroid.x, centroid.y


def oracle_foot(ctx: OpContext, args: list[str]) -> tuple[Any, Any]:
    projected = _line(ctx, args[1]).projection(_point(ctx, args[0]))
    return projected.x, projected.y


def oracle_intersect_lines(ctx: OpContext, args: list[str]) -> tuple[Any, Any]:
    intersection = _line(ctx, args[0]).intersection(_line(ctx, args[1]))
    # sympy returns a list of intersections; a single crossing yields one point.
    points = [p for p in intersection if isinstance(p, sp.Point)]
    if len(points) != 1:
        raise ValueError("lines do not intersect in a single point")
    return points[0].x, points[0].y


def oracle_circumcenter(ctx: OpContext, args: list[str]) -> tuple[Any, Any]:
    circle = sp.Circle(_point(ctx, args[0]), _point(ctx, args[1]), _point(ctx, args[2]))
    return circle.center.x, circle.center.y


def oracle_incenter(ctx: OpContext, args: list[str]) -> tuple[Any, Any]:
    triangle = sp.Triangle(_point(ctx, args[0]), _point(ctx, args[1]), _point(ctx, args[2]))
    incenter = triangle.incenter
    return incenter.x, incenter.y


def oracle_orthocenter(ctx: OpContext, args: list[str]) -> tuple[Any, Any]:
    triangle = sp.Triangle(_point(ctx, args[0]), _point(ctx, args[1]), _point(ctx, args[2]))
    # sympy exposes the altitudes as a dict keyed by vertex; the orthocenter is
    # where any two of them meet. The altitudes are segments, so they are
    # extended to full lines before intersecting.
    altitudes = list(triangle.altitudes.values())
    if len(altitudes) < 2:
        raise ValueError("triangle has too few altitudes")
    first = altitudes[0]
    second = altitudes[1]
    line1 = Line(first.p1, first.p2)
    line2 = Line(second.p1, second.p2)
    points = [p for p in line1.intersection(line2) if isinstance(p, sp.Point)]
    if len(points) != 1:
        raise ValueError("altitudes do not meet at a single point")
    return points[0].x, points[0].y


def oracle_line_free(ctx: OpContext, args: list[str]) -> tuple[Any, Any, Any]:
    line = Line(_point(ctx, args[0]), _point(ctx, args[1]))
    coefficients = line.coefficients
    return coefficients[0], coefficients[1], coefficients[2]


def oracle_perpendicular_through(ctx: OpContext, args: list[str]) -> tuple[Any, Any, Any]:
    line = _line(ctx, args[1]).perpendicular_line(_point(ctx, args[0]))
    coefficients = line.coefficients
    return coefficients[0], coefficients[1], coefficients[2]


def oracle_parallel_through(ctx: OpContext, args: list[str]) -> tuple[Any, Any, Any]:
    line = _line(ctx, args[1]).parallel_line(_point(ctx, args[0]))
    coefficients = line.coefficients
    return coefficients[0], coefficients[1], coefficients[2]


def oracle_circle_through(ctx: OpContext, args: list[str]) -> tuple[Any, Any, Any]:
    circle = sp.Circle(_point(ctx, args[0]), _point(ctx, args[1]), _point(ctx, args[2]))
    r2 = circle.radius ** 2
    return circle.center.x, circle.center.y, r2


def oracle_circle_free(ctx: OpContext, args: list[str]) -> tuple[Any, Any, Any]:
    center = _point(ctx, args[0])
    r2 = sp.sympify(args[1])
    circle = sp.Circle(center, sp.sqrt(r2))
    return circle.center.x, circle.center.y, r2


def oracle_segment_free(ctx: OpContext, args: list[str]) -> tuple[Any, Any, Any, Any]:
    segment = Segment(_point(ctx, args[0]), _point(ctx, args[1]))
    return segment.p1.x, segment.p1.y, segment.p2.x, segment.p2.y


ORACLES = {
    "point.midpoint": oracle_midpoint,
    "point.centroid": oracle_centroid,
    "point.foot": oracle_foot,
    "point.intersect_lines": oracle_intersect_lines,
    "point.circumcenter": oracle_circumcenter,
    "point.incenter": oracle_incenter,
    "point.orthocenter": oracle_orthocenter,
    "line.free": oracle_line_free,
    "line.perpendicular_through": oracle_perpendicular_through,
    "line.parallel_through": oracle_parallel_through,
    "segment.free": oracle_segment_free,
    "circle.through": oracle_circle_through,
    "circle.free": oracle_circle_free,
}

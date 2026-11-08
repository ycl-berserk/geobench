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


def oracle_perpendicular_bisector(ctx: OpContext, args: list[str]) -> tuple[Any, Any, Any]:
    bisector = Segment(_point(ctx, args[0]), _point(ctx, args[1])).perpendicular_bisector()
    coefficients = bisector.coefficients
    return coefficients[0], coefficients[1], coefficients[2]


def oracle_angle_bisector(ctx: OpContext, args: list[str]) -> tuple[Any, Any, Any]:
    """The bisector of the angle at B.

    An independent characterisation: the internal bisector of ∠ABC
    passes through the **incentre** of triangle ABC, because the incentre
    lies on all three internal bisectors. So the line is the one through
    B and the incentre -- a construction the kernel does not use.
    """
    triangle = sp.Triangle(_point(ctx, args[0]), _point(ctx, args[1]), _point(ctx, args[2]))
    incentre = triangle.incenter
    line = Line(_point(ctx, args[1]), sp.Point(incentre.x, incentre.y))
    coefficients = line.coefficients
    return coefficients[0], coefficients[1], coefficients[2]


def oracle_tangent(ctx: OpContext, args: list[str]) -> tuple[Any, Any, Any]:
    """The tangent to a circle at a point on it.

    Written as the **polar** of the point rather than as "the line
    through the point perpendicular to the radius": the polar of P with
    respect to (x-cx)^2 + (y-cy)^2 = r^2 is

        (x-cx)(px-cx) + (y-cy)(py-cy) = r^2,

    which is the same line but a different derivation. That the two agree
    is exactly what the point being on the circle means.
    """
    px, py = ctx.point(args[0])
    cx, cy, r2 = ctx.circle(args[1])
    nx, ny = px - cx, py - cy
    return (nx, ny, -(nx * cx + ny * cy) - r2)


def oracle_intersect_circles(ctx: OpContext, args: list[str]) -> tuple[Any, ...]:
    """The intersection points of two circles.

    The order of the two points is a convention of the kernel's, not a
    fact of the geometry, so this oracle returns the *set* and the
    harness checks membership.
    """
    cx1, cy1, r1 = ctx.circle(args[0])
    cx2, cy2, r2 = ctx.circle(args[1])
    first = sp.Circle(sp.Point(cx1, cy1), sp.sqrt(r1))
    second = sp.Circle(sp.Point(cx2, cy2), sp.sqrt(r2))
    points = [p for p in first.intersection(second) if isinstance(p, sp.Point)]
    if len(points) != 2:
        raise ValueError("the circles do not meet in two points")
    return tuple((p.x, p.y) for p in points)


def oracle_nearest_on_object(ctx: OpContext, args: list[str]) -> tuple[Any, Any]:
    """The point of a line or segment closest to a given point.

    For a line this is the perpendicular projection. For a segment the
    answer is whichever of the two ends and the projection is closest --
    a case analysis, where the kernel clamps the projection's parameter
    to the interval.
    """
    point = _point(ctx, args[0])
    node = ctx.figure.node(args[1])
    if node.kind == "line":
        projected = _line(ctx, args[1]).projection(point)
        return projected.x, projected.y
    x1, y1, x2, y2 = ctx.segment(args[1])
    first = sp.Point(x1, y1)
    second = sp.Point(x2, y2)
    projection = Line(first, second).projection(point)
    # Whether the projection lies *between* the two ends is decided by
    # the triangle equality |AP| + |PB| = |AB| -- a different
    # characterisation from the kernel's, which clamps a parameter.
    span = float(first.distance(second))
    through = float(first.distance(projection) + projection.distance(second))
    if abs(span - through) < 1e-9 * max(1.0, span):
        nearest = projection
    elif float(first.distance(point)) <= float(second.distance(point)):
        nearest = first
    else:
        nearest = second
    return nearest.x, nearest.y


def oracle_circle_center_point(ctx: OpContext, args: list[str]) -> tuple[Any, Any, Any]:
    centre = _point(ctx, args[0])
    through = _point(ctx, args[1])
    # sympy's Circle takes a radius, so the distance is computed first.
    radius = centre.distance(through)
    circle = sp.Circle(centre, radius)
    return circle.center.x, circle.center.y, circle.radius**2


def oracle_circle_incicle(ctx: OpContext, args: list[str]) -> tuple[Any, Any, Any]:
    triangle = sp.Triangle(_point(ctx, args[0]), _point(ctx, args[1]), _point(ctx, args[2]))
    circle = triangle.incircle
    return circle.center.x, circle.center.y, circle.radius**2


def oracle_transform_mirror(ctx: OpContext, args: list[str]) -> tuple[Any, Any]:
    reflected = _point(ctx, args[0]).reflect(_line(ctx, args[1]))
    return reflected.x, reflected.y


def oracle_transform_translate(ctx: OpContext, args: list[str]) -> tuple[Any, Any]:
    dx, dy = ctx.point(args[1])
    moved = _point(ctx, args[0]).translate(dx, dy)
    return moved.x, moved.y


def oracle_transform_rotate(ctx: OpContext, args: list[str]) -> tuple[Any, Any]:
    degrees = sp.sympify(args[1])
    centre = _point(ctx, args[2])
    # sympy rotates counter-clockwise by radians.
    moved = _point(ctx, args[0]).rotate(degrees * sp.pi / 180, centre)
    return moved.x, moved.y


def oracle_arc_three_points(ctx: OpContext, args: list[str]) -> tuple[Any, ...]:
    """The arc lies on the circle through the three points.

    The oracle builds that circle with sympy and checks the centre, the
    squared radius and the three points the arc carries.
    """
    a = _point(ctx, args[0])
    b = _point(ctx, args[1])
    c = _point(ctx, args[2])
    circle = sp.Circle(a, b, c)
    r2 = circle.radius ** 2
    return circle.center.x, circle.center.y, r2, a.x, a.y, c.x, c.y, b.x, b.y


def oracle_sector_three_points(ctx: OpContext, args: list[str]) -> tuple[Any, ...]:
    """The sector: a centre, a squared radius and the two end points."""
    centre = _point(ctx, args[0])
    start = _point(ctx, args[1])
    end = _point(ctx, args[2])
    r2 = start.distance(centre) ** 2
    return centre.x, centre.y, r2, start.x, start.y, end.x, end.y


def oracle_ray_free(ctx: OpContext, args: list[str]) -> tuple[Any, ...]:
    """A ray is its starting point and a point it passes through."""
    start = _point(ctx, args[0])
    through = _point(ctx, args[1])
    return start.x, start.y, through.x, through.y


def oracle_polyline_free(ctx: OpContext, args: list[str]) -> tuple[Any, ...]:
    """A polyline is its vertices, in order."""
    out: list[Any] = []
    for node_id in args:
        x, y = ctx.point(node_id)
        out.extend((x, y))
    return tuple(out)


def oracle_polygon_regular(ctx: OpContext, args: list[str]) -> tuple[Any, ...]:
    """The vertices are the first one turned about the centre, by sympy."""
    centre = _point(ctx, args[0])
    vertex = _point(ctx, args[1])
    count = int(sp.sympify(args[2]))
    out: list[Any] = []
    for index in range(count):
        turned = vertex.rotate(2 * sp.pi * index / count, centre)
        out.extend((turned.x, turned.y))
    return tuple(out)


def oracle_polygon_vertex(ctx: OpContext, args: list[str]) -> tuple[Any, Any]:
    """The nth vertex of the polygon, counted from one."""
    vertices = ctx.polygon(args[0])
    index = int(sp.sympify(args[1]))
    return vertices[2 * (index - 1)], vertices[2 * (index - 1) + 1]


def oracle_affine_ratio(ctx: OpContext, args: list[str]) -> tuple[Any, Any]:
    """The point that divides the segment in the ratio m : n.

    sympy's Segment has a point-at-a-fraction method, and the fraction
    is m / (m + n).
    """
    first = _point(ctx, args[0])
    second = _point(ctx, args[1])
    m = sp.sympify(args[2])
    n = sp.sympify(args[3])
    # sympy's points add and scale, so the point at the fraction t from
    # the first end is written the way a person would write it.
    point = first + (m / (m + n)) * (second - first)
    return point.x, point.y


def oracle_polar(ctx: OpContext, args: list[str]) -> tuple[Any, Any, Any]:
    """The polar of the point with respect to the circle.

    The polar passes through the *inverse* of the point -- the point
    on the ray from the centre with the centre-to-point distance
    multiplied by the ratio r^2 / d -- and is perpendicular to that
    ray.
    """
    point = _point(ctx, args[0])
    centre_x, centre_y, r2 = ctx.circle(args[1])
    dx = point.x - centre_x
    dy = point.y - centre_y
    squared = dx**2 + dy**2
    if squared == 0:
        raise ValueError("the centre has no polar")
    factor = r2 / squared
    inverse_x = centre_x + factor * dx
    inverse_y = centre_y + factor * dy
    a = dx
    b = dy
    c = -a * inverse_x - b * inverse_y
    return a, b, c


def oracle_measure_distance(ctx: OpContext, args: list[str]) -> tuple[Any, ...]:
    """sympy's own distance between two points."""
    return (_point(ctx, args[0]).distance(_point(ctx, args[1])),)


def oracle_measure_length(ctx: OpContext, args: list[str]) -> tuple[Any, ...]:
    """sympy's own length of the segment."""
    x1, y1, x2, y2 = ctx.segment(args[0])
    return (sp.Point(x1, y1).distance(sp.Point(x2, y2)),)


def _polygon_points(ctx: OpContext, node_id: str) -> list[sp.Point]:
    vertices = ctx.polygon(node_id)
    return [
        sp.Point(vertices[2 * index], vertices[2 * index + 1])
        for index in range(len(vertices) // 2)
    ]


def _shoelace(points: list[sp.Point]) -> Any:
    """The area of a polygon, from the shoelace formula.

    sympy reduces a polygon whose vertices are all on one line to a
    segment, which has no area to report, so the closed form is used
    for that case.
    """
    total = sp.Integer(0)
    for index, point in enumerate(points):
        following = points[(index + 1) % len(points)]
        total += point.x * following.y - following.x * point.y
    return sp.Abs(total) / 2


def oracle_measure_area(ctx: OpContext, args: list[str]) -> tuple[Any, ...]:
    """sympy's own area of the polygon."""
    points = _polygon_points(ctx, args[0])
    polygon = sp.Polygon(*points)
    if not isinstance(polygon, sp.Polygon):
        return (_shoelace(points),)
    # sympy's area is signed: the sign says which way round the
    # vertices were written. An area is not signed, so it is taken
    # positive here.
    return (sp.Abs(polygon.area),)


def oracle_measure_perimeter(ctx: OpContext, args: list[str]) -> tuple[Any, ...]:
    """The perimeter: the sides it was given, each measured by sympy.

    sympy's ``Polygon.perimeter`` reorders the vertices of a polygon
    that crosses itself, so it answers a question about a *different*
    polygon -- the simple one through the same points. The perimeter of
    a polygon is the sum of the sides it was written with, and each side
    is a sympy Segment.
    """
    points = _polygon_points(ctx, args[0])
    total: Any = sp.Integer(0)
    for index, point in enumerate(points):
        following = points[(index + 1) % len(points)]
        total += Segment(point, following).length
    return (total,)


def oracle_measure_angle(ctx: OpContext, args: list[str]) -> tuple[Any, ...]:
    """sympy's own angle at the second point, in degrees."""
    triangle = sp.Triangle(_point(ctx, args[0]), _point(ctx, args[1]), _point(ctx, args[2]))
    vertex = _point(ctx, args[1])
    return (triangle.angles[vertex] * 180 / sp.pi,)


def oracle_measure_radius(ctx: OpContext, args: list[str]) -> tuple[Any, ...]:
    """sympy's own radius of the circle."""
    _, _, r2 = ctx.circle(args[0])
    return (sp.sqrt(r2),)


def oracle_measure_slope(ctx: OpContext, args: list[str]) -> tuple[Any, ...]:
    """sympy's own slope of the line."""
    return (_line(ctx, args[0]).slope,)


def oracle_measure_direction(ctx: OpContext, args: list[str]) -> tuple[Any, ...]:
    """sympy's own direction of the line, in degrees.

    The line is rebuilt from its defining points, the way it was
    drawn: a line has no orientation of its own, and the direction
    follows the order of the points.
    """
    node = ctx.figure.node(args[0])
    direction = sp.Line(_point(ctx, node.args[0]), _point(ctx, node.args[1])).direction
    return (sp.atan2(direction.y, direction.x) * 180 / sp.pi,)


def oracle_polygon_free(ctx: OpContext, args: list[str]) -> tuple[Any, ...]:
    """A polygon is its edges; the oracle checks the vertices it carries."""
    out: list[Any] = []
    for node_id in args:
        x, y = ctx.point(node_id)
        out.extend((x, y))
    return tuple(out)


def oracle_transform_dilate(ctx: OpContext, args: list[str]) -> tuple[Any, Any]:
    """The homothety about a point.

    sympy's ``Point.scale`` scales the *coordinates*, not the point
    about a centre, so the oracle uses sympy's own vector arithmetic on
    points instead.
    """
    factor = sp.sympify(args[1])
    centre = _point(ctx, args[2])
    moved = centre + factor * (_point(ctx, args[0]) - centre)
    return moved.x, moved.y


def oracle_intersect_line_circle(ctx: OpContext, args: list[str]) -> tuple[Any, ...]:
    """The intersections of a line and a circle.

    The kernel orders the two roots by the sign of the square root in the
    quadratic formula -- an algebraic convention that no independent
    implementation would guess. So this oracle returns the *set* of
    intersections and the harness checks membership, which checks the
    mathematics rather than the convention.
    """
    line = _line(ctx, args[0])
    cx, cy, r2 = ctx.circle(args[1])
    circle = sp.Circle(sp.Point(cx, cy), sp.sqrt(r2))
    points = [p for p in line.intersection(circle) if isinstance(p, sp.Point)]
    if len(points) != 2:
        raise ValueError("the line and the circle do not meet in two points")
    return tuple((p.x, p.y) for p in points)


ORACLES = {
    "point.midpoint": oracle_midpoint,
    "point.centroid": oracle_centroid,
    "point.foot": oracle_foot,
    "point.intersect_lines": oracle_intersect_lines,
    "point.intersect_line_circle": oracle_intersect_line_circle,
    "point.circumcenter": oracle_circumcenter,
    "point.incenter": oracle_incenter,
    "point.orthocenter": oracle_orthocenter,
    "line.free": oracle_line_free,
    "line.perpendicular_through": oracle_perpendicular_through,
    "line.parallel_through": oracle_parallel_through,
    "line.perpendicular_bisector": oracle_perpendicular_bisector,
    "line.angle_bisector": oracle_angle_bisector,
    "line.tangent": oracle_tangent,
    "point.intersect_circles": oracle_intersect_circles,
    "point.nearest_on_object": oracle_nearest_on_object,
    "segment.free": oracle_segment_free,
    "circle.through": oracle_circle_through,
    "circle.center_point": oracle_circle_center_point,
    "circle.incircle": oracle_circle_incicle,
    "polygon.free": oracle_polygon_free,
    "ray.free": oracle_ray_free,
    "polyline.free": oracle_polyline_free,
    "polygon.regular": oracle_polygon_regular,
    "point.polygon_vertex": oracle_polygon_vertex,
    "point.affine_ratio": oracle_affine_ratio,
    "line.polar": oracle_polar,
    "measure.distance": oracle_measure_distance,
    "measure.length": oracle_measure_length,
    "measure.area": oracle_measure_area,
    "measure.perimeter": oracle_measure_perimeter,
    "measure.angle": oracle_measure_angle,
    "measure.radius": oracle_measure_radius,
    "measure.slope": oracle_measure_slope,
    "measure.direction": oracle_measure_direction,
    "arc.three_points": oracle_arc_three_points,
    "sector.three_points": oracle_sector_three_points,
    "transform.mirror": oracle_transform_mirror,
    "transform.translate": oracle_transform_translate,
    "transform.rotate": oracle_transform_rotate,
    "transform.dilate": oracle_transform_dilate,
    "circle.free": oracle_circle_free,
}

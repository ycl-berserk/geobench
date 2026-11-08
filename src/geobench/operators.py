"""Built-in operators.

The kernel's arithmetic is symbolic: a free point carries symbol names in
``coords`` (``x_A``/``y_A``) and concrete values in ``placement``. Every
operator therefore computes in the symbolic domain, and the numeric placement
is only substituted at render time. That is what allows a judge to decide a
relation *identically* rather than on one sample (docs/spec.md section 3.2).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import cast

import sympy as sp
from sympy import Expr

from geobench.errors import (
    AmbiguousIntersectionError,
    ArgumentTypeError,
    DegenerateError,
    OpNotImplementedError,
    StateError,
)
from geobench.field import FIELD
from geobench.model import Figure, Node
from geobench.registry import ArgSpec, OperatorRegistry, OpSpec

# -- representation -------------------------------------------------------

# A line is stored as the implicit equation a*x + b*y + c = 0.
LineCoeffs = tuple[Expr, Expr, Expr]
# A circle is stored as (center_x, center_y, r_squared).
CircleData = tuple[Expr, Expr, Expr]


@dataclass(frozen=True)
class OpContext:
    """Everything an operator implementation needs."""

    figure: Figure

    def point(self, node_id: str) -> tuple[Expr, Expr]:
        node = self.figure.node(node_id)
        if node.kind != "point":
            raise StateError(f"node {node_id!r} is not a point")
        if node.coords is None:
            raise StateError(f"point {node_id!r} has no coordinates")
        return FIELD.coerce(node.coords[0]), FIELD.coerce(node.coords[1])

    def line(self, node_id: str) -> LineCoeffs:
        node = self.figure.node(node_id)
        if node.kind != "line":
            raise StateError(f"node {node_id!r} is not a line")
        data = node.cache.get("line")
        if data is None:
            raise OpNotImplementedError(
                f"line {node_id!r} has not been evaluated yet; run evaluate_figure() first"
            )
        a, b, _ = cast(LineCoeffs, data)
        if a == 0 and b == 0:
            raise StateError(f"line {node_id!r} is degenerate (no direction)")
        return a, b, _

    def circle(self, node_id: str) -> CircleData:
        node = self.figure.node(node_id)
        if node.kind != "circle":
            raise StateError(f"node {node_id!r} is not a circle")
        data = node.cache.get("circle")
        if data is None:
            raise OpNotImplementedError(
                f"circle {node_id!r} has not been evaluated yet; run evaluate_figure() first"
            )
        return cast(CircleData, data)

    def segment(self, node_id: str) -> tuple[Expr, Expr, Expr, Expr]:
        node = self.figure.node(node_id)
        if node.kind != "segment":
            raise StateError(f"node {node_id!r} is not a segment")
        data = node.cache.get("segment")
        if data is None:
            raise OpNotImplementedError(
                f"segment {node_id!r} has not been evaluated yet; run evaluate_figure() first"
            )
        return cast(tuple[Expr, Expr, Expr, Expr], data)

    def as_line(self, node_id: str) -> LineCoeffs:
        """The supporting line of a line *or* a segment.

        Competition figures draw segments, but the operations that need a
        line (a foot, an intersection) work on the supporting line. Resolving
        here keeps the operators uniform and avoids inserting extra nodes
        into the figure.
        """
        node = self.figure.node(node_id)
        if node.kind == "line":
            return self.line(node_id)
        if node.kind == "segment":
            x1, y1, x2, y2 = self.segment(node_id)
            return _line_through((x1, y1), (x2, y2))
        raise StateError(f"node {node_id!r} is neither a line nor a segment")

    def line_points(self, node_id: str) -> list[tuple[Expr, Expr]]:
        """The points a line-like node was built from, if any."""
        node = self.figure.node(node_id)
        points: list[tuple[Expr, Expr]] = []
        for arg in node.args:
            try:
                points.append(self.point(arg))
            except StateError:
                continue
        return points


OpImpl = Callable[[OpContext, list[str]], dict[str, object]]


# -- helpers ---------------------------------------------------------------


def _line_through(a: tuple[Expr, Expr], b: tuple[Expr, Expr]) -> LineCoeffs:
    """Implicit coefficients of the line through two points."""
    (x1, y1), (x2, y2) = a, b
    if x1 == x2 and y1 == y2:
        raise StateError("cannot build a line through a single point twice")
    return (y1 - y2, x2 - x1, x1 * y2 - x2 * y1)


def _line_from_normal(p: tuple[Expr, Expr], normal: tuple[Expr, Expr]) -> LineCoeffs:
    a, b = normal
    x0, y0 = p
    return (a, b, -(a * x0 + b * y0))


# -- operators -------------------------------------------------------------


def op_midpoint(ctx: OpContext, args: list[str]) -> dict[str, object]:
    (x1, y1) = ctx.point(args[0])
    (x2, y2) = ctx.point(args[1])
    if x1 == x2 and y1 == y2:
        raise DegenerateError("midpoint of two identical points is degenerate")
    return {"kind": "point", "coords": ((x1 + x2) / 2, (y1 + y2) / 2)}


def op_centroid(ctx: OpContext, args: list[str]) -> dict[str, object]:
    xs: list[Expr] = []
    ys: list[Expr] = []
    for node_id in args:
        x, y = ctx.point(node_id)
        xs.append(x)
        ys.append(y)
    n = len(xs)
    return {"kind": "point", "coords": (sum(xs) / n, sum(ys) / n)}


def op_foot(ctx: OpContext, args: list[str]) -> dict[str, object]:
    px, py = ctx.point(args[0])
    a, b, c = ctx.as_line(args[1])
    denom = a * a + b * b
    if denom == 0:
        raise DegenerateError("cannot project onto a degenerate line")
    t = (a * px + b * py + c) / denom
    return {"kind": "point", "coords": (px - a * t, py - b * t)}


def op_intersect_lines(ctx: OpContext, args: list[str]) -> dict[str, object]:
    a1, b1, c1 = ctx.as_line(args[0])
    a2, b2, c2 = ctx.as_line(args[1])
    det = a1 * b2 - a2 * b1
    if det == 0:
        raise DegenerateError("lines are parallel or coincident; no unique intersection")
    x = (b1 * c2 - b2 * c1) / det
    y = (c1 * a2 - c2 * a1) / det
    return {"kind": "point", "coords": (x, y)}


def op_intersect_line_circle(ctx: OpContext, args: list[str]) -> dict[str, object]:
    """One intersection of a line and a circle.

    The selector is either an index (``0`` or ``1``) or the word ``other``,
    meaning "the intersection different from the point of the line that is
    already known to lie on the circle" -- the Chinese "另一交点".

    The two roots are ordered by the sign of the square root in the quadratic
    formula, which is an *algebraic* ordering: it needs no comparison
    between symbolic expressions, so it stays decidable.
    """
    a, b, c = ctx.as_line(args[0])
    cx, cy, r2 = ctx.circle(args[1])
    selector: object = args[2]
    if isinstance(selector, str) and selector.isdigit():
        selector = int(selector)

    # Parameterise the line: P(t) = P0 + t * D, where P0 is the point of
    # the line closest to the origin and D = (b, -a) is its direction.
    #
    # Both choices are canonical: they depend only on the line's
    # coefficients, so the numbering of the two intersections does not
    # change when the same line is written down differently.
    norm_sq = a * a + b * b
    if norm_sq == 0:
        raise DegenerateError("degenerate line")
    p0x, p0y = -a * c / norm_sq, -b * c / norm_sq
    dx, dy = b, -a

    fx, fy = p0x - cx, p0y - cy
    quad_a = dx * dx + dy * dy
    quad_b = 2 * (fx * dx + fy * dy)
    quad_c = fx * fx + fy * fy - r2
    if quad_a == 0:
        raise DegenerateError("degenerate line")
    disc = quad_b * quad_b - 4 * quad_a * quad_c
    if disc == 0:
        raise DegenerateError("the line is tangent to the circle; there is no second point")
    if disc.is_number and disc < 0:
        raise DegenerateError("the line does not meet the circle")
    root = sp.sqrt(disc)
    t_plus = (-quad_b + root) / (2 * quad_a)
    t_minus = (-quad_b - root) / (2 * quad_a)
    points = [
        (p0x + t_plus * dx, p0y + t_plus * dy),
        (p0x + t_minus * dx, p0y + t_minus * dy),
    ]

    if isinstance(selector, int):
        if selector not in (0, 1):
            raise ArgumentTypeError(
                "point.intersect_line_circle", 2, "0, 1 or 'other'", selector
            )
        x, y = points[selector]
        return {
            "kind": "point",
            "coords": (x, y),
            # A tangent line has no second intersection. The discriminant
            # is not identically zero -- it is zero only for some
            # placements -- so the condition is published and checked by
            # the evaluation pass, where the placement is known.
            "must_be_nonzero": {"discriminant": disc},
        }

    if selector != "other":
        raise ArgumentTypeError(
            "point.intersect_line_circle", 2, "0, 1 or 'other'", selector
        )

    # "Other": find the line's own point that lies on the circle, and take
    # the other intersection.
    #
    # This is done algebraically rather than by comparing the two roots. The
    # quadratic's roots satisfy t1 + t2 = -quad_b / quad_a, so once the
    # parameter of the known point is known, the other one follows by
    # subtraction -- no square root, and therefore no slow symbolic
    # comparison.
    #
    # The *sum* is used rather than the product (t1 * t2 = quad_c / quad_a)
    # because the product divides by the known root: when the known point
    # happens to sit at the base of the parameterisation, that root is zero
    # and the product form returns 0/0. The sum form never divides by a
    # root, so it stays valid there.
    reference: tuple[Expr, Expr] | None = None
    for candidate in ctx.line_points(args[0]):
        on = (candidate[0] - cx) ** 2 + (candidate[1] - cy) ** 2 - r2
        if FIELD.simplify_to_zero(on):
            if reference is not None:
                raise DegenerateError("both intersections coincide with known points on the line")
            reference = candidate
    if reference is None:
        raise AmbiguousIntersectionError(
            "no point of the line is known to lie on the circle; "
            "the 'other intersection' is ambiguous"
        )
    # The parameter of the reference point along D.
    t_ref = ((reference[0] - p0x) * dx + (reference[1] - p0y) * dy) / quad_a
    t_other = -quad_b / quad_a - t_ref
    return {
        "kind": "point",
        "coords": (p0x + t_other * dx, p0y + t_other * dy),
        "must_be_nonzero": {"discriminant": disc},
    }


def op_circumcenter(ctx: OpContext, args: list[str]) -> dict[str, object]:
    (x1, y1) = ctx.point(args[0])
    (x2, y2) = ctx.point(args[1])
    (x3, y3) = ctx.point(args[2])
    det = 2 * (x1 * (y2 - y3) + x2 * (y3 - y1) + x3 * (y1 - y2))
    if det == 0:
        raise DegenerateError("the three points are collinear; no circumcircle")
    s1 = x1 * x1 + y1 * y1
    s2 = x2 * x2 + y2 * y2
    s3 = x3 * x3 + y3 * y3
    ux = (s1 * (y2 - y3) + s2 * (y3 - y1) + s3 * (y1 - y2)) / det
    uy = (s1 * (x3 - x2) + s2 * (x1 - x3) + s3 * (x2 - x1)) / det
    return {
        "kind": "point",
        "coords": (ux, uy),
        # Three points are collinear for some placements, not identically,
        # so the condition is published for the evaluation pass to check.
        "must_be_nonzero": {"determinant": det},
    }


def op_incenter(ctx: OpContext, args: list[str]) -> dict[str, object]:
    ax, ay = ctx.point(args[0])
    bx, by = ctx.point(args[1])
    cx, cy = ctx.point(args[2])
    area2 = (bx - ax) * (cy - ay) - (cx - ax) * (by - ay)
    if area2 == 0:
        raise DegenerateError("the three points are collinear; no incenter")
    # Side lengths opposite each vertex.
    a_len = sp.sqrt((bx - cx) ** 2 + (by - cy) ** 2)
    b_len = sp.sqrt((cx - ax) ** 2 + (cy - ay) ** 2)
    c_len = sp.sqrt((ax - bx) ** 2 + (ay - by) ** 2)
    total = a_len + b_len + c_len
    if total == 0:
        raise DegenerateError("degenerate triangle; no incenter")
    x = (a_len * ax + b_len * bx + c_len * cx) / total
    y = (a_len * ay + b_len * by + c_len * cy) / total
    return {"kind": "point", "coords": (x, y)}


def op_orthocenter(ctx: OpContext, args: list[str]) -> dict[str, object]:
    ax, ay = ctx.point(args[0])
    bx, by = ctx.point(args[1])
    cx, cy = ctx.point(args[2])
    # The orthocenter is the reflection of the circumcenter over the centroid:
    # H = A + B + C - 2*O.
    ox, oy = cast(tuple[Expr, Expr], op_circumcenter(ctx, args)["coords"])
    return {"kind": "point", "coords": (ax + bx + cx - 2 * ox, ay + by + cy - 2 * oy)}


def op_perpendicular_through(ctx: OpContext, args: list[str]) -> dict[str, object]:
    px, py = ctx.point(args[0])
    a, b, _ = ctx.line(args[1])
    return {"kind": "line", "line": _line_from_normal((px, py), (-b, a))}


def op_parallel_through(ctx: OpContext, args: list[str]) -> dict[str, object]:
    px, py = ctx.point(args[0])
    a, b, _ = ctx.line(args[1])
    return {"kind": "line", "line": _line_from_normal((px, py), (a, b))}


def op_line_free(ctx: OpContext, args: list[str]) -> dict[str, object]:
    return {"kind": "line", "line": _line_through(ctx.point(args[0]), ctx.point(args[1]))}


def op_nearest_on_object(ctx: OpContext, args: list[str]) -> dict[str, object]:
    """The point of a line or segment closest to a given point (最近点).

    On a line this is the foot of the perpendicular. On a *segment* the
    foot may lie outside it, and then the nearest point is the nearer
    end -- which is what ``point.foot`` does not do, because a foot is
    on the supporting line.
    """
    (px, py) = ctx.point(args[0])
    node = ctx.figure.node(args[1])
    if node.kind == "line":
        a, b, c = ctx.line(args[1])
        denominator = a * a + b * b
        if denominator == 0:
            raise DegenerateError("degenerate line")
        # Moving p along the normal by the signed distance gives the foot.
        shift = (a * px + b * py + c) / denominator
        return {"kind": "point", "coords": (px - shift * a, py - shift * b)}
    x1, y1, x2, y2 = ctx.segment(args[1])
    dx, dy = x2 - x1, y2 - y1
    length2 = dx * dx + dy * dy
    if length2 == 0:
        raise DegenerateError("a segment needs two distinct endpoints")
    # Parametrise the segment by t in [0, 1] and clamp the unconstrained
    # minimiser to that interval.
    t = ((px - x1) * dx + (py - y1) * dy) / length2
    clamped = sp.Min(sp.Max(t, 0), 1)
    return {"kind": "point", "coords": (x1 + clamped * dx, y1 + clamped * dy)}


def op_transform_mirror(ctx: OpContext, args: list[str]) -> dict[str, object]:
    """The reflection of a point in a line (镜像).

    The reflection is twice the foot of the perpendicular minus the point
    itself -- the foot is the midpoint of the point and its mirror.
    """
    (px, py) = ctx.point(args[0])
    a, b, c = ctx.as_line(args[1])
    denominator = a * a + b * b
    if denominator == 0:
        raise DegenerateError("degenerate line")
    shift = (a * px + b * py + c) / denominator
    return {"kind": "point", "coords": (px - 2 * shift * a, py - 2 * shift * b)}


def op_transform_translate(ctx: OpContext, args: list[str]) -> dict[str, object]:
    """A translation by a vector (平移).

    The vector is written as a point, the way GeoGebra writes it: the
    coordinates of that point are the offsets.
    """
    (px, py) = ctx.point(args[0])
    (dx, dy) = ctx.point(args[1])
    return {"kind": "point", "coords": (px + dx, py + dy)}


def op_transform_rotate(ctx: OpContext, args: list[str]) -> dict[str, object]:
    """A rotation about a point (旋转).

    The angle is in **degrees**, as in GeoGebra. It is kept exact: the
    angle in radians is ``theta * pi / 180``, and sympy evaluates the
    cosine of the special angles to exact values -- the cosine of 60
    degrees is 1/2, not 0.5000000001.
    """
    (px, py) = ctx.point(args[0])
    degrees = FIELD.coerce(args[1])
    (cx, cy) = ctx.point(args[2])
    radians = degrees * sp.pi / 180
    cosine, sine = sp.cos(radians), sp.sin(radians)
    dx, dy = px - cx, py - cy
    return {
        "kind": "point",
        "coords": (
            cx + dx * cosine - dy * sine,
            cy + dx * sine + dy * cosine,
        ),
    }


def op_transform_dilate(ctx: OpContext, args: list[str]) -> dict[str, object]:
    """A homothety about a point (位似)."""
    (px, py) = ctx.point(args[0])
    factor = FIELD.coerce(args[1])
    (cx, cy) = ctx.point(args[2])
    return {
        "kind": "point",
        "coords": (cx + factor * (px - cx), cy + factor * (py - cy)),
    }


def op_polygon_free(ctx: OpContext, args: list[str]) -> dict[str, object]:
    """A polygon through the given points (多边形).

    A polygon is not a new shape: it is its **edges**. So it carries the
    vertices' coordinates and the renderer draws the segments between
    them. That keeps one shape in the figure instead of a polygon plus
    four segments, and it keeps the screen and the export agreeing (they
    draw the same primitives).
    """
    if len(args) < 3:
        raise DegenerateError("a polygon needs at least three vertices")
    vertices: list[Expr] = []
    for node_id in args:
        x, y = ctx.point(node_id)
        vertices.extend((x, y))
    # Two vertices in a row would make a side of zero length.
    for index in range(len(args)):
        first = 2 * index
        second = 2 * ((index + 1) % len(args))
        if vertices[first] == vertices[second] and vertices[first + 1] == vertices[second + 1]:
            raise DegenerateError("two vertices of the polygon coincide")
    return {"kind": "polygon", "polygon": tuple(vertices)}


def op_intersect_circles(ctx: OpContext, args: list[str]) -> dict[str, object]:
    """The intersection points of two circles (两圆交点).

    The common chord of two circles lies on the **radical axis**, which
    is found by subtracting the two circle equations -- no square root.
    Its distance from the first centre along the line of centres is
    ``k / (2 d^2)`` times the centre-to-centre vector, and the height of
    the chord is ``sqrt(n) / (2 d^2)``, where ``n`` is a polynomial in
    the coordinates. So exactly one square root survives.
    """
    x1, y1, r1 = ctx.circle(args[0])
    x2, y2, r2 = ctx.circle(args[1])
    selector = args[2]
    dx, dy = x2 - x1, y2 - y1
    d2 = dx * dx + dy * dy
    if d2 == 0:
        raise DegenerateError("the circles are concentric; no intersection points")
    # k is the squared-distance bookkeeping of the two circles.
    k = r1 - r2 + d2
    # n is four times the squared half-chord, times d2. It is a
    # polynomial, so the only irrationality left is its square root.
    n = 4 * r1 * d2 - k * k
    if n.is_number and n < 0:
        raise DegenerateError("the circles do not meet")
    # The foot of the common chord on the line of centres.
    t = k / (2 * d2)
    bx, by = x1 + dx * t, y1 + dy * t
    # The offset from that foot, perpendicular to the line of centres.
    s = sp.sqrt(n) / (2 * d2)
    if _is_second(selector):
        return {"kind": "point", "coords": (bx + dy * s, by - dx * s)}
    return {
        "kind": "point",
        "coords": (bx - dy * s, by + dx * s),
        # Tangency: the two circles meet in a single point, so there is
        # no second intersection to pick.
        "must_be_nonzero": {"discriminant": n},
    }


def _is_second(selector: object) -> bool:
    """Is this the second of the two answers?"""
    if isinstance(selector, int):
        return selector == 1
    text = str(selector)
    return text == "1"


def op_perpendicular_bisector(ctx: OpContext, args: list[str]) -> dict[str, object]:
    """The perpendicular bisector of a segment (中垂线).

    The bisector's *normal* is the segment's direction, and it passes
    through the midpoint -- which is all it takes, and needs no square
    root.
    """
    (x1, y1) = ctx.point(args[0])
    (x2, y2) = ctx.point(args[1])
    if x1 == x2 and y1 == y2:
        raise DegenerateError("a segment needs two distinct endpoints")
    dx, dy = x2 - x1, y2 - y1
    mx, my = (x1 + x2) / 2, (y1 + y2) / 2
    return {"kind": "line", "line": _line_from_normal((mx, my), (dx, dy))}


def op_angle_bisector(ctx: OpContext, args: list[str]) -> dict[str, object]:
    """The internal bisector of the angle ABC (角平分线).

    The bisector's direction is the sum of the two unit vectors along
    the sides. Clearing the common denominator |BA|*|BC| leaves the
    direction alone, so the square roots of the side lengths are the
    only irrationality involved.
    """
    (ax, ay) = ctx.point(args[0])
    (bx, by) = ctx.point(args[1])
    (cx, cy) = ctx.point(args[2])
    u_len = sp.sqrt((ax - bx) ** 2 + (ay - by) ** 2)
    v_len = sp.sqrt((cx - bx) ** 2 + (cy - by) ** 2)
    if u_len == 0 or v_len == 0:
        raise DegenerateError("the angle needs two sides of non-zero length")
    dx = v_len * (ax - bx) + u_len * (cx - bx)
    dy = v_len * (ay - by) + u_len * (cy - by)
    return {"kind": "line", "line": _line_from_normal((bx, by), (dy, -dx))}


def op_tangent(ctx: OpContext, args: list[str]) -> dict[str, object]:
    """The tangent to a circle at a point on it (切线).

    The tangent at a point of a circle is perpendicular to the radius
    there. The point must actually lie on the circle; that cannot be
    checked on symbols alone, so the condition is published and checked
    at each placement (the point may be on the circle for some
    placements and off it for others).
    """
    (px, py) = ctx.point(args[0])
    cx, cy, r2 = ctx.circle(args[1])
    nx, ny = px - cx, py - cy
    if nx == 0 and ny == 0:
        raise DegenerateError("the tangent is undefined at the centre of the circle")
    return {
        "kind": "line",
        "line": _line_from_normal((px, py), (nx, ny)),
        "must_be_zero": {"point_on_circle": nx * nx + ny * ny - r2},
    }


def op_segment_free(ctx: OpContext, args: list[str]) -> dict[str, object]:
    """A segment between two points -- what a competition figure actually draws."""
    a = ctx.point(args[0])
    b = ctx.point(args[1])
    if a == b:
        raise DegenerateError("a segment needs two distinct endpoints")
    return {"kind": "segment", "segment": (a[0], a[1], b[0], b[1])}


def op_circle_through(ctx: OpContext, args: list[str]) -> dict[str, object]:
    ox, oy = cast(tuple[Expr, Expr], op_circumcenter(ctx, args)["coords"])
    ax, ay = ctx.point(args[0])
    r2 = (ax - ox) ** 2 + (ay - oy) ** 2
    return {"kind": "circle", "circle": (ox, oy, r2)}


def op_circle_free(ctx: OpContext, args: list[str]) -> dict[str, object]:
    cx, cy = ctx.point(args[0])
    r2 = FIELD.coerce(args[1])
    if r2 <= 0:
        raise DegenerateError("a circle needs a positive squared radius")
    return {"kind": "circle", "circle": (cx, cy, r2)}


def op_circle_center_point(ctx: OpContext, args: list[str]) -> dict[str, object]:
    """The circle with a given centre that passes through another point (圆心一点)."""
    cx, cy = ctx.point(args[0])
    px, py = ctx.point(args[1])
    r2 = (px - cx) ** 2 + (py - cy) ** 2
    if r2 == 0:
        raise DegenerateError("the point is the centre, so the radius is zero")
    return {"kind": "circle", "circle": (cx, cy, r2)}


def op_circle_incicle(ctx: OpContext, args: list[str]) -> dict[str, object]:
    """The incircle of a triangle (内切圆).

    The centre is the incentre, and the radius is the area over the
    semi-perimeter: r = A/s. Since the area enters squared, the sign of
    the cross product does not matter and no absolute value is needed.
    """
    ax, ay = ctx.point(args[0])
    bx, by = ctx.point(args[1])
    cx, cy = ctx.point(args[2])
    ix, iy = cast(tuple[Expr, Expr], op_incenter(ctx, args)["coords"])
    a_len = sp.sqrt((bx - cx) ** 2 + (by - cy) ** 2)
    b_len = sp.sqrt((cx - ax) ** 2 + (cy - ay) ** 2)
    c_len = sp.sqrt((ax - bx) ** 2 + (ay - by) ** 2)
    total = a_len + b_len + c_len
    if total == 0:
        raise DegenerateError("degenerate triangle; no incircle")
    # Twice the signed area of the triangle.
    area2 = (bx - ax) * (cy - ay) - (cx - ax) * (by - ay)
    # r = area / s = |area2| / total, so r^2 = area2^2 / total^2.
    r2 = area2**2 / total**2
    return {"kind": "circle", "circle": (ix, iy, r2)}


# -- registry --------------------------------------------------------------

_BUILTINS: list[tuple[OpSpec, OpImpl]] = [
    (
        OpSpec(
            id="point.midpoint",
            kind="point",
            args=(ArgSpec("a", "point"), ArgSpec("b", "point")),
            returns="point",
            degenerate_when=("a == b",),
            oracle="sympy.geometry:Segment.midpoint",
        ),
        op_midpoint,
    ),
    (
        OpSpec(
            id="point.centroid",
            kind="point",
            args=(ArgSpec("a", "point"), ArgSpec("b", "point"), ArgSpec("c", "point")),
            returns="point",
            oracle="sympy.geometry:Triangle.centroid",
        ),
        op_centroid,
    ),
    (
        OpSpec(
            id="point.foot",
            kind="point",
            args=(ArgSpec("p", "point"), ArgSpec("line", "line")),
            returns="point",
            oracle="sympy.geometry:Line.projection",
        ),
        op_foot,
    ),
    (
        OpSpec(
            id="point.intersect_lines",
            kind="point",
            args=(ArgSpec("l1", "line"), ArgSpec("l2", "line")),
            returns="point",
            degenerate_when=("l1 parallel to l2",),
            oracle="sympy.geometry:Line.intersection",
        ),
        op_intersect_lines,
    ),
    (
        OpSpec(
            id="point.circumcenter",
            kind="point",
            args=(ArgSpec("a", "point"), ArgSpec("b", "point"), ArgSpec("c", "point")),
            returns="point",
            degenerate_when=("a, b, c collinear",),
            oracle="sympy.geometry:Point.circumcircle",
        ),
        op_circumcenter,
    ),
    (
        OpSpec(
            id="point.incenter",
            kind="point",
            args=(ArgSpec("a", "point"), ArgSpec("b", "point"), ArgSpec("c", "point")),
            returns="point",
            degenerate_when=("a, b, c collinear",),
            oracle="sympy.geometry:Triangle.incenter",
        ),
        op_incenter,
    ),
    (
        OpSpec(
            id="point.orthocenter",
            kind="point",
            args=(ArgSpec("a", "point"), ArgSpec("b", "point"), ArgSpec("c", "point")),
            returns="point",
            degenerate_when=("a, b, c collinear",),
            oracle="sympy.geometry:Triangle.orthocenter",
        ),
        op_orthocenter,
    ),
    (
        OpSpec(
            id="line.free",
            kind="line",
            args=(ArgSpec("a", "point"), ArgSpec("b", "point")),
            returns="line",
            degenerate_when=("a == b",),
            oracle="sympy.geometry:Line",
        ),        op_line_free,
    ),
    (
        OpSpec(
            id="circle.center_point",
            kind="circle",
            args=(ArgSpec("center", "point"), ArgSpec("through", "point")),
            returns="circle",
            degenerate_when=("the point is the centre",),
            oracle="sympy.geometry:Circle(centre, point)",
        ),
        op_circle_center_point,
    ),
    (
        OpSpec(
            id="circle.incircle",
            kind="circle",
            args=(ArgSpec("a", "point"), ArgSpec("b", "point"), ArgSpec("c", "point")),
            returns="circle",
            degenerate_when=("a, b, c collinear",),
            oracle="sympy.geometry:Triangle.incircle",
        ),
        op_circle_incicle,
    ),
    (
        OpSpec(
            id="transform.mirror",
            kind="point",
            args=(ArgSpec("p", "point"), ArgSpec("line", "line")),
            returns="point",
            degenerate_when=("degenerate line",),
            oracle="sympy.geometry:Point.reflect",
        ),
        op_transform_mirror,
    ),
    (
        OpSpec(
            id="transform.translate",
            kind="point",
            args=(ArgSpec("p", "point"), ArgSpec("vector", "point")),
            returns="point",
            oracle="sympy.geometry:Point.translate",
        ),
        op_transform_translate,
    ),
    (
        OpSpec(
            id="transform.rotate",
            kind="point",
            args=(
                ArgSpec("p", "point"),
                ArgSpec("degrees", "scalar"),
                ArgSpec("centre", "point"),
            ),
            returns="point",
            oracle="sympy.geometry:Point.rotate",
        ),
        op_transform_rotate,
    ),
    (
        OpSpec(
            id="transform.dilate",
            kind="point",
            args=(
                ArgSpec("p", "point"),
                ArgSpec("factor", "scalar"),
                ArgSpec("centre", "point"),
            ),
            returns="point",
            oracle="sympy.geometry:Point.scale",
        ),
        op_transform_dilate,
    ),
    (
        OpSpec(
            id="polygon.free",
            kind="polygon",
            args=(
                ArgSpec("a", "point"),
                ArgSpec("b", "point"),
                ArgSpec("c", "point"),
                ArgSpec("...", "point", variadic=True),
            ),
            returns="polygon",
            degenerate_when=("fewer than three vertices", "two vertices coincide"),
            oracle="the polygon is its edges: the oracle checks the vertices",
        ),
        op_polygon_free,
    ),
    (
        OpSpec(
            id="point.intersect_circles",
            kind="point",
            args=(
                ArgSpec("c1", "circle"),
                ArgSpec("c2", "circle"),
                ArgSpec("selector", "selector"),
            ),
            returns="point",
            degenerate_when=("the circles are concentric", "the circles do not meet"),
            oracle="sympy.geometry:Circle.intersection",
        ),
        op_intersect_circles,
    ),
    (
        OpSpec(
            id="point.nearest_on_object",
            kind="point",
            args=(ArgSpec("p", "point"), ArgSpec("object", "line")),
            returns="point",
            degenerate_when=("the object has zero length",),
            oracle="sympy.geometry:Segment / Line projection, clamped",
        ),
        op_nearest_on_object,
    ),
    (
        OpSpec(
            id="line.perpendicular_bisector",
            kind="line",            args=(ArgSpec("a", "point"), ArgSpec("b", "point")),
            returns="line",
            degenerate_when=("a == b",),
            oracle="sympy.geometry:Segment.perpendicular_bisector",
        ),
        op_perpendicular_bisector,
    ),
    (
        OpSpec(
            id="line.angle_bisector",
            kind="line",
            args=(
                ArgSpec("a", "point"),
                ArgSpec("b", "point"),
                ArgSpec("c", "point"),
            ),
            returns="line",
            degenerate_when=("a == b", "b == c"),
            oracle="sympy.geometry:Triangle.incenter (the bisector passes through it)",
        ),
        op_angle_bisector,
    ),
    (
        OpSpec(
            id="line.tangent",
            kind="line",
            args=(ArgSpec("p", "point"), ArgSpec("circle", "circle")),
            returns="line",
            degenerate_when=("p is the centre of the circle",),
            oracle="sympy.geometry:Circle.tangent_lines",
        ),
        op_tangent,
    ),
    (
        OpSpec(
            id="line.perpendicular_through",
            kind="line",
            args=(ArgSpec("p", "point"), ArgSpec("line", "line")),
            returns="line",
            oracle="sympy.geometry:Line.perpendicular_line",
        ),
        op_perpendicular_through,
    ),
    (
        OpSpec(
            id="line.parallel_through",
            kind="line",
            args=(ArgSpec("p", "point"), ArgSpec("line", "line")),
            returns="line",
            oracle="sympy.geometry:Line.parallel_line",
        ),
        op_parallel_through,
    ),
    (
        OpSpec(
            id="point.intersect_line_circle",
            kind="point",
            args=(
                ArgSpec("line", "line"),
                ArgSpec("circle", "circle"),
                ArgSpec("selector", "selector"),
            ),
            returns="point",
            degenerate_when=("line tangent to circle",),
            oracle="sympy.geometry:Line.intersection",
        ),
        op_intersect_line_circle,
    ),
    (
        OpSpec(
            id="segment.free",
            kind="segment",
            args=(ArgSpec("a", "point"), ArgSpec("b", "point")),
            returns="segment",
            degenerate_when=("a == b",),
            oracle="sympy.geometry:Segment",
        ),
        op_segment_free,
    ),
    (
        OpSpec(
            id="circle.through",
            kind="circle",
            args=(ArgSpec("a", "point"), ArgSpec("b", "point"), ArgSpec("c", "point")),
            returns="circle",
            degenerate_when=("a, b, c collinear",),
            oracle="sympy.geometry:Point.circumcircle",
        ),
        op_circle_through,
    ),
    (
        OpSpec(
            id="circle.free",
            kind="circle",
            args=(ArgSpec("center", "point"), ArgSpec("r2", "scalar")),
            returns="circle",
            degenerate_when=("r2 <= 0",),
            oracle="sympy.geometry:Circle",
        ),
        op_circle_free,
    ),
]


def builtin_registry() -> tuple[OpSpec, ...]:
    return tuple(spec for spec, _ in _BUILTINS)


def register_builtins(registry: OperatorRegistry) -> None:
    """Register every built-in operator into an OperatorRegistry."""
    for spec, impl in _BUILTINS:
        registry.register(spec, impl)


def node_symbols(node_id: str) -> tuple[sp.Symbol, sp.Symbol]:
    """The symbolic coordinates of a free point."""
    return sp.Symbol(f"x_{node_id}"), sp.Symbol(f"y_{node_id}")


def default_node(node_id: str, kind: str, role: str, **kwargs: object) -> Node:
    return Node(id=node_id, kind=kind, role=role, **kwargs)  # type: ignore[arg-type]

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

from geobench.errors import OpNotImplementedError, StateError
from geobench.field import FIELD
from geobench.model import Figure, Node
from geobench.registry import ArgSpec, OpSpec

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
        raise StateError("midpoint of two identical points is degenerate")
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
        raise StateError("cannot project onto a degenerate line")
    t = (a * px + b * py + c) / denom
    return {"kind": "point", "coords": (px - a * t, py - b * t)}


def op_intersect_lines(ctx: OpContext, args: list[str]) -> dict[str, object]:
    a1, b1, c1 = ctx.as_line(args[0])
    a2, b2, c2 = ctx.as_line(args[1])
    det = a1 * b2 - a2 * b1
    if det == 0:
        raise StateError("lines are parallel or coincident; no unique intersection")
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

    # Parameterise the line: P(t) = P0 + t * D.
    if b != 0:
        p0x, p0y = sp.Integer(0), -c / b
    else:
        p0x, p0y = -c / a, sp.Integer(0)
    dx, dy = b, -a

    fx, fy = p0x - cx, p0y - cy
    quad_a = dx * dx + dy * dy
    quad_b = 2 * (fx * dx + fy * dy)
    quad_c = fx * fx + fy * fy - r2
    if quad_a == 0:
        raise StateError("degenerate line")
    disc = quad_b * quad_b - 4 * quad_a * quad_c
    if disc == 0:
        raise StateError("the line is tangent to the circle; there is no second point")
    if disc.is_number and disc < 0:
        raise StateError("the line does not meet the circle")
    root = sp.sqrt(disc)
    t_plus = (-quad_b + root) / (2 * quad_a)
    t_minus = (-quad_b - root) / (2 * quad_a)
    points = [
        (p0x + t_plus * dx, p0y + t_plus * dy),
        (p0x + t_minus * dx, p0y + t_minus * dy),
    ]

    if isinstance(selector, int):
        if selector not in (0, 1):
            raise StateError("the intersection index must be 0 or 1")
        x, y = points[selector]
        return {"kind": "point", "coords": (x, y)}

    if selector != "other":
        raise StateError(f"unknown intersection selector {selector!r}")

    # "Other": find the line's own point that lies on the circle, and take
    # the other intersection.
    #
    # This is done algebraically rather than by comparing the two roots. The
    # quadratic's roots satisfy t1 * t2 = c/a, so once the parameter of the
    # known point is known, the other one follows by division -- no square
    # root, and therefore no slow symbolic comparison.
    reference: tuple[Expr, Expr] | None = None
    for candidate in ctx.line_points(args[0]):
        on = (candidate[0] - cx) ** 2 + (candidate[1] - cy) ** 2 - r2
        if FIELD.simplify_to_zero(on):
            if reference is not None:
                raise StateError("both intersections coincide with known points on the line")
            reference = candidate
    if reference is None:
        raise StateError(
            "no point of the line is known to lie on the circle; "
            "the 'other intersection' is ambiguous"
        )
    # The parameter of the reference point along D.
    t_ref = ((reference[0] - p0x) * dx + (reference[1] - p0y) * dy) / quad_a
    if t_ref == 0:
        raise StateError("the reference point is the base point of the parameterisation")
    t_other = (quad_c / quad_a) / t_ref
    return {
        "kind": "point",
        "coords": (p0x + t_other * dx, p0y + t_other * dy),
    }


def op_circumcenter(ctx: OpContext, args: list[str]) -> dict[str, object]:
    (x1, y1) = ctx.point(args[0])
    (x2, y2) = ctx.point(args[1])
    (x3, y3) = ctx.point(args[2])
    det = 2 * (x1 * (y2 - y3) + x2 * (y3 - y1) + x3 * (y1 - y2))
    if det == 0:
        raise StateError("the three points are collinear; no circumcircle")
    s1 = x1 * x1 + y1 * y1
    s2 = x2 * x2 + y2 * y2
    s3 = x3 * x3 + y3 * y3
    ux = (s1 * (y2 - y3) + s2 * (y3 - y1) + s3 * (y1 - y2)) / det
    uy = (s1 * (x3 - x2) + s2 * (x1 - x3) + s3 * (x2 - x1)) / det
    return {"kind": "point", "coords": (ux, uy)}


def op_incenter(ctx: OpContext, args: list[str]) -> dict[str, object]:
    ax, ay = ctx.point(args[0])
    bx, by = ctx.point(args[1])
    cx, cy = ctx.point(args[2])
    area2 = (bx - ax) * (cy - ay) - (cx - ax) * (by - ay)
    if area2 == 0:
        raise StateError("the three points are collinear; no incenter")
    # Side lengths opposite each vertex.
    a_len = sp.sqrt((bx - cx) ** 2 + (by - cy) ** 2)
    b_len = sp.sqrt((cx - ax) ** 2 + (cy - ay) ** 2)
    c_len = sp.sqrt((ax - bx) ** 2 + (ay - by) ** 2)
    total = a_len + b_len + c_len
    if total == 0:
        raise StateError("degenerate triangle; no incenter")
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


def op_segment_free(ctx: OpContext, args: list[str]) -> dict[str, object]:
    """A segment between two points -- what a competition figure actually draws."""
    a = ctx.point(args[0])
    b = ctx.point(args[1])
    if a == b:
        raise StateError("a segment needs two distinct endpoints")
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
        raise StateError("a circle needs a positive squared radius")
    return {"kind": "circle", "circle": (cx, cy, r2)}


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
        ),
        op_line_free,
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


def register_builtins(registry: object) -> None:
    """Register every built-in operator into an OperatorRegistry."""
    for spec, impl in _BUILTINS:
        registry.register(spec, impl)  # type: ignore[attr-defined]


def node_symbols(node_id: str) -> tuple[sp.Symbol, sp.Symbol]:
    """The symbolic coordinates of a free point."""
    return sp.Symbol(f"x_{node_id}"), sp.Symbol(f"y_{node_id}")


def default_node(node_id: str, kind: str, role: str, **kwargs: object) -> Node:
    return Node(id=node_id, kind=kind, role=role, **kwargs)  # type: ignore[arg-type]
